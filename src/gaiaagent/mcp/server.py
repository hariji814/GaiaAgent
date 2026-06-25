"""AURC MCP stdio server — expose AURC `@skill` agents as MCP tools for the `claude` CLI.
AURC MCP stdio server —— 把 AURC `@skill` agent 暴露为 MCP 工具供 `claude` CLI 调用

This is the **keystone** of the Loop Roadmap (Step 1): a thin MCP server (JSON-RPC
over stdio) that fronts an AURC agent. Point the `claude` CLI at it via
`--mcp-config` and the CLI's tool calls cross the subprocess boundary at the
*protocol level* — through `MCPBridge` → `MessageRouter` → the agent's `@skill`
handlers — which is exactly what AURC's L4 bridges were built for. The subprocess
boundary stops mattering because the bus crossing is protocol-level, not
process-level.

    claude -p "<prompt>" --mcp-config '{"mcpServers":{"aurc":{ \
        "command":"python","args":["-m","gaiaagent.mcp","--agent","myproj:ResearchAgent"]}}}'

Supported JSON-RPC methods:
    - initialize           → protocol version + capabilities
    - tools/list           → enumerate the agent's @skill methods as MCP tools
    - tools/call           → translate via MCPBridge → MessageRouter.route → skill → result

Reuses (does not duplicate):
    - `MCPBridge.translate_to_aurc` mints `correlation_id` + `bridge_chain` on the
      inbound `tools/call` (`bridges/base.py`).
    - `MessageRouter.route` dispatches to the registered skill handler
      (`bus/router.py`); protocol-prefix routing to MCP/A2A/ACP peers engages
      automatically if a skill delegates to a `mcp:`/`a2a:`/`acp:` target.

Note: this server does bus routing, not lifecycle management. Starting/pausing
the agent through the AURC harness is the caller's concern (the harness wraps
the loop that *drives* the CLI, not the MCP server the CLI calls into).
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)

# MCP protocol version reported on initialize. Pinned conservatively; the CLI
# negotiates and tolerates older versions.
_MCP_PROTOCOL_VERSION = "2024-11-05"
_SERVER_NAME = "aurc-mcp"
_SERVER_VERSION = "0.1.0"

_JSONRPC_PARSE_ERROR = -32700
_JSONRPC_METHOD_NOT_FOUND = -32601
_JSONRPC_INTERNAL_ERROR = -32603


class AURCMCPStdioServer:
    """A minimal MCP stdio server fronting one AURC agent's @skill methods.
    暴露单个 AURC agent @skill 的最小 MCP stdio server
    """

    def __init__(
        self,
        agent: Any,
        *,
        bridge: Any | None = None,
        router: Any | None = None,
        trace_recorder: Any | None = None,
    ) -> None:
        self._agent = agent
        descriptor = getattr(agent, "aurc_descriptor", None) or getattr(
            agent.__class__, "_aurc_descriptor", None
        )
        if descriptor is None:
            raise ValueError(
                "agent has no aurc_descriptor — decorate it with @aurc_agent"
            )
        self._descriptor = descriptor
        self._agent_id = descriptor.aurc_id

        # Lazy-import to keep this module importable without the full package at
        # collection time (and to avoid a hard import cycle).
        from gaiaagent.bridges.base import MCPBridge
        from gaiaagent.bus.router import MessageRouter

        self._bridge = bridge or MCPBridge()
        self._router = router or MessageRouter()
        self._trace_recorder = trace_recorder
        self._router.register_handler(self._agent_id, self._dispatch_skill)
        logger.info("AURC MCP server fronting %s", self._agent_id)

    # ------------------------------------------------------------------
    # Skill dispatch (the MessageRouter handler)
    # ------------------------------------------------------------------

    async def _dispatch_skill(self, message: Any) -> Any:
        """MessageHandler: route an AURC `invoke` to the agent's @skill method.
        MessageHandler:把 AURC invoke 路由到 agent 的 @skill 方法
        """
        body = message.body
        skill_id = getattr(body, "skill", "") or ""
        params = getattr(body, "params", {}) or {}
        method_name = skill_id.replace("-", "_")
        fn = getattr(self._agent, method_name, None)
        if fn is None:
            raise KeyError(f"agent {self._agent_id} has no skill '{skill_id}'")
        logger.info("MCP dispatch: %s(%s)", skill_id, params)
        return await fn(**params)

    # ------------------------------------------------------------------
    # MCP tool enumeration
    # ------------------------------------------------------------------

    def _list_tools(self) -> list[dict[str, Any]]:
        """Enumerate the agent's @skill methods as MCP tool definitions.
        把 agent 的 @skill 方法枚举为 MCP 工具定义
        """
        tools: list[dict[str, Any]] = []
        provides = self._descriptor.capabilities.provides or []
        for skill in provides:
            schema = skill.input_schema
            tools.append(
                {
                    "name": skill.skill_id,
                    "description": skill.description or skill.name,
                    "inputSchema": {
                        "type": getattr(schema, "type", "object"),
                        "properties": getattr(schema, "properties", {}) or {},
                        "required": getattr(schema, "required", []) or [],
                    },
                }
            )
        return tools

    # ------------------------------------------------------------------
    # JSON-RPC dispatch
    # ------------------------------------------------------------------

    async def dispatch(self, request: Any) -> dict[str, Any] | None:
        """Dispatch one parsed JSON-RPC request; return the response object or None.
        分发一条 JSON-RPC 请求;返回响应对象或 None(通知无响应)
        """
        if not isinstance(request, dict):
            return _error(None, _JSONRPC_PARSE_ERROR, "Invalid request")

        req_id = request.get("id")
        method = request.get("method", "")
        is_notification = req_id is None and "method" in request

        try:
            if method == "initialize":
                return _result(req_id, {
                    "protocolVersion": _MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": _SERVER_NAME, "version": _SERVER_VERSION},
                })
            if method == "notifications/initialized":
                return None  # notification — no response
            if method == "tools/list":
                return _result(req_id, {"tools": self._list_tools()})
            if method == "tools/call":
                if is_notification:
                    return None
                return await self._handle_tools_call(req_id, request.get("params") or {})
            return _error(req_id, _JSONRPC_METHOD_NOT_FOUND, f"Method not found: {method}")
        except Exception as exc:  # noqa: BLE001 — MCP must return a JSON-RPC error, not crash
            logger.exception("MCP dispatch error for %s", method)
            return _error(req_id, _JSONRPC_INTERNAL_ERROR, f"Internal error: {exc}")

    async def _handle_tools_call(self, req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        """Translate tools/call via MCPBridge → route via MessageRouter → MCP result.
        经 MCPBridge 翻译 tools/call → MessageRouter 路由 → MCP 结果
        """
        name = params.get("name", "")
        arguments = params.get("arguments", {}) or {}
        # `translate_to_aurc` mints correlation_id (from msg id) + bridge_chain.
        mcp_message = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments, "_target_agent": self._agent_id},
            "id": req_id,
        }
        aurc_msg = await self._bridge.translate_to_aurc(mcp_message)
        # Belt-and-suspenders: ensure the router targets our registered handler.
        aurc_msg.target = self._agent_id
        if self._trace_recorder is not None:
            try:
                self._trace_recorder.record(aurc_msg)
            except Exception:  # pragma: no cover — observability must not break serving
                logger.debug("trace record failed", exc_info=True)
        try:
            result = await self._router.route(aurc_msg)
        except Exception as exc:  # noqa: BLE001
            return _result(req_id, {
                "content": [{"type": "text", "text": f"Error: {exc}"}],
                "isError": True,
            })
        return _result(req_id, {
            "content": [{"type": "text", "text": _stringify(result)}],
            "isError": False,
        })

    # ------------------------------------------------------------------
    # stdio loop
    # ------------------------------------------------------------------

    async def serve_stdio(self, stdin: Any = None, stdout: Any = None) -> None:
        """Read newline-delimited JSON-RPC from stdin, write responses to stdout.
        从 stdin 读换行分隔的 JSON-RPC,把响应写入 stdout
        """
        in_stream = stdin or sys.stdin
        out_stream = stdout or sys.stdout
        while True:
            line = await _readline(in_stream)
            if line is None:
                break  # EOF
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                err = _error(None, _JSONRPC_PARSE_ERROR, "Parse error")
                out_stream.write(json.dumps(err) + "\n")
                out_stream.flush()
                continue
            response = await self.dispatch(request)
            if response is not None:
                out_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
                out_stream.flush()


def _stringify(value: Any) -> str:
    """Render a skill result as text for the MCP client (JSON for structured data).
    把 skill 结果渲染为 MCP 客户端文本(结构化数据用 JSON)
    """
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _result(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


async def _readline(stream: Any) -> str | None:
    """Read one line from a stream; None at EOF.

    Handles both async streams (an ``async def readline()`` returning bytes,
    e.g. an asyncio StreamReader) and blocking text streams (``sys.stdin``,
    offloaded to a thread so it never blocks the event loop).
    """
    import asyncio
    import inspect

    rl = getattr(stream, "readline", None)
    if rl is None:
        return None
    if inspect.iscoroutinefunction(rl):
        data = await rl()
    else:
        data = await asyncio.to_thread(rl)
    if isinstance(data, (bytes, bytearray)):
        if not data:
            return None
        return data.decode("utf-8", errors="replace")
    return data if data else None


# ----------------------------------------------------------------------
# Entry point: python -m gaiaagent.mcp --agent myproj:Agent
# ----------------------------------------------------------------------


def _load_agent(spec: str) -> Any:
    """Import and instantiate an agent from a ``module:ClassName`` spec.
    从 module:ClassName 规格导入并实例化 agent
    """
    if ":" not in spec:
        raise ValueError(f"--agent must be 'module:ClassName', got {spec!r}")
    module_name, _, class_name = spec.partition(":")
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    return cls()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m gaiaagent.mcp", description="AURC MCP stdio server"
    )
    parser.add_argument(
        "--agent", required=True,
        help="agent spec module:ClassName (must be @aurc_agent-decorated)",
    )
    parser.add_argument("--log", default="WARNING", help="log level (default WARNING)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=args.log.upper(), stream=sys.stderr)
    agent = _load_agent(args.agent)
    server = AURCMCPStdioServer(agent)
    import asyncio

    try:
        asyncio.run(server.serve_stdio())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
