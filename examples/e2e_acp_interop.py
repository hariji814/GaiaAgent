"""End-to-end REAL ACP <-> MCP cross-process interop demo.

The ACP counterpart of ``e2e_mcp_a2a_interop.py``: the inbound protocol is
ACP instead of A2A, but the no-fabrication contract is identical -- every
protocol end is a genuine third-party-protocol implementation, and AURC
only translates and routes between them.

    REAL ACP client  (spec-compliant ACP invoke envelope over HTTP)
        -- POST /acp -->
    [AURC node: ACPBridge.translate_to_aurc  (ACP invoke -> AURC delegation)]
        MessageRouter -> Calculator.general skill
    [skill invokes the REAL MCP server]
        -- stdio (official MCP ClientSession) -->
    REAL MCP server  (official FastMCP, `add` tool, stdio transport)
        <-- CallToolResult content ["42"] (computed inside the MCP server) --
    [skill returns {"sum": 42, "via": "real-mcp", "mcp_content": "42"}]
        <-- ACPBridge.translate_from_aurc  (AURC response -> ACP completed) --
    REAL ACP client
        <-- ACP result {status:"completed", result:{sum:42,...}} --

Three real processes:
  1. orchestrator : the real ACP client (this process when run with no args).
  2. AURC node    : an HTTP subprocess serving /acp (this file with --serve-back).
  3. MCP server   : official FastMCP `add` over stdio, spawned per task by the
                    skill (a grandchild process).

Two real protocols on the wire:
  - ACP : a hand-written, spec-compliant invoke envelope client. ACP uses a
          simple JSON envelope (not JSON-RPC) with method-based dispatch --
          this client speaks that wire protocol, it is NOT using AURC
          internals.
  - MCP : the OFFICIAL Anthropic `mcp` SDK on both ends (FastMCP server +
          ClientSession initialize->list_tools->call_tool over stdio). The
          arithmetic is computed inside the real MCP server; AURC never adds.

ACP models invocations as (task, input) pairs, so the structured call is
carried directly as task="add" with input={"a":15,"b":27} and the back-end
"general" skill reads the numbers from `input` before invoking MCP. This
semantic shape is exactly what AURC bridges.

Run:
    python examples/e2e_acp_interop.py
"""
from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from gaiaagent.bridges.acp import ACPBridge
from gaiaagent.core.message import AURCMessage, ErrorInfo, MessageBody
from gaiaagent.core.types import MessageDirection
from gaiaagent.sdk.decorators import aurc_agent, skill
from gaiaagent.server import AURCServer
from gaiaagent.transport.http import HTTPTransportServer

_HERE = Path(__file__).resolve().parent
MCP_SERVER_PATH = str((_HERE / "_real_mcp_server.py").resolve())


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


# ---------------------------------------------------------------------------
# AURC back node. Its Calculator.general skill does NOT do math itself -- it
# calls the REAL MCP server (official FastMCP + official ClientSession over
# stdio) and returns whatever the MCP tool computed.
# ---------------------------------------------------------------------------


@aurc_agent(
    id="aurc:demo/calculator:v1.0",
    display_name="Calculator",
    description="Bridges ACP invoke to a real MCP arithmetic tool",
    protocols=["acp/1.0", "mcp/2025-06-18"],
)
class _McpBackedCalculator:
    @skill("general", description="Structured arithmetic routed to a real MCP tool")
    async def general(
        self,
        task: str = "",
        input: dict[str, Any] | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        # ACP invoke carries the structured payload as (task, input); the
        # numbers live in `input` ({"a": 15, "b": 27}).
        data = input or {}
        a = data.get("a")
        b = data.get("b")
        if a is None or b is None:
            return {"via": "real-mcp", "error": "need input.a and input.b"}
        # Official MCP client over stdio to the real FastMCP server.
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        server_params = StdioServerParameters(
            command=sys.executable, args=[MCP_SERVER_PATH]
        )
        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool("add", {"a": int(a), "b": int(b)})
                    text = ""
                    for c in result.content:
                        text = getattr(c, "text", "") or text
                    return {
                        "sum": int(text) if text.lstrip("-").isdigit() else None,
                        "via": "real-mcp",
                        "mcp_content": text,
                        "mcp_is_error": result.isError,
                    }
        except Exception as exc:  # pragma: no cover - demo diagnostics
            return {"via": "real-mcp", "error": f"mcp call failed: {exc}"}


async def _run_back_node(port: int, mcp_path: str) -> int:
    global MCP_SERVER_PATH
    MCP_SERVER_PATH = mcp_path

    server = AURCServer()
    await server.register_agent(_McpBackedCalculator())
    http = HTTPTransportServer(host="127.0.0.1", port=port)
    http.set_handler(server.http_handler)
    bridge = ACPBridge()

    async def acp_handler(payload: dict[str, Any]) -> dict[str, Any]:
        # ACP invoke -> AURC delegation (skill="general", params={task,input,...}).
        msg = await bridge.translate_to_aurc(payload)
        msg.target = "aurc:demo/calculator:v1.0"
        outcome = await server.router.route(msg)
        task_id = msg.body.params.get("session_id", "") or msg.correlation_id or ""
        if isinstance(outcome, dict) and "error" in outcome:
            err = outcome["error"]
            resp_msg = AURCMessage(
                source=msg.target,
                target=msg.source,
                type=MessageDirection.RESPONSE,
                correlation_id=msg.correlation_id,
                body=MessageBody(
                    error=ErrorInfo(
                        code=str(err.get("code", "error")),
                        message=str(err.get("message", "")),
                    ),
                    metadata={"task_id": task_id},
                ),
            )
        else:
            result = (
                outcome.get("result", outcome) if isinstance(outcome, dict) else outcome
            )
            resp_msg = AURCMessage(
                source=msg.target,
                target=msg.source,
                type=MessageDirection.RESPONSE,
                correlation_id=msg.correlation_id,
                body=MessageBody(result=result, metadata={"task_id": task_id}),
            )
        # AURC response -> ACP completed/failed envelope.
        return await bridge.translate_from_aurc(resp_msg)

    http.set_route("/acp", acp_handler)
    print(f"[aurc node] serving /acp on 127.0.0.1:{port} (MCP via {mcp_path})", flush=True)
    await http.start()
    return 0


# ---------------------------------------------------------------------------
# Orchestrator: the real ACP client. It POSTs a spec-compliant ACP invoke
# envelope to the AURC node's /acp endpoint and parses the ACP completed
# response.
# ---------------------------------------------------------------------------


async def _wait_for_server(url: str, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient() as client:
        while time.monotonic() < deadline:
            try:
                if (await client.get(url)).status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.2)
    return False


async def _acp_invoke(
    base_url: str, agent_id: str, task: str, inp: dict[str, Any], corr_id: str
) -> dict[str, Any]:
    # Spec-compliant ACP invoke envelope.
    payload = {
        "method": "invoke",
        "params": {
            "agent_id": agent_id,
            "task": task,
            "input": inp,
            "session_id": f"sess-{uuid.uuid4().hex[:8]}",
        },
        "id": corr_id,
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{base_url}/acp", json=payload, timeout=30.0)
        r.raise_for_status()
        return r.json()


async def _run_orchestrator() -> int:
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    back_proc = subprocess.Popen(
        [
            sys.executable,
            str(_HERE / "e2e_acp_interop.py"),
            "--serve-back",
            str(port),
            MCP_SERVER_PATH,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        if not await _wait_for_server(f"{base}/health"):
            err = back_proc.stderr.read().decode("utf-8", "replace") if back_proc.stderr else ""
            print("AURC node did not start.\nstderr:", err)
            return 1

        print("[acp client] real ACP invoke -> " + base + "/acp")
        print("=" * 64)

        corr = "corr-real-mcp-acp-1"
        print("[acp client] invoke: task 'add' input {a:15, b:27} (asks MCP add(15, 27))")
        print("             envelope id (correlation): " + corr)
        resp = await _acp_invoke(base, "calculator", "add", {"a": 15, "b": 27}, corr)

        status = resp.get("status")
        result = resp.get("result") or {}
        print("             envelope id round-trip:    " + str(resp.get("id")))
        print("             acp status:               " + str(status))
        print("             result.sum:               " + str(result.get("sum")))
        print("             result.via:               " + str(result.get("via")))
        print("             result.mcp_content:       " + str(result.get("mcp_content")))

        assert resp.get("id") == corr, resp
        assert status == "completed", resp
        assert result.get("sum") == 42, resp
        assert result.get("via") == "real-mcp", resp
        print("             [OK] real ACP client -> AURC -> real MCP, correlation e2e")
        print("                 (the sum was computed inside the real FastMCP MCP server)")
        print("=" * 64)
        print("Demo complete: a real ACP client reached a real MCP server through AURC.")
        return 0
    finally:
        back_proc.terminate()
        try:
            back_proc.wait(timeout=5)
        except Exception:
            back_proc.kill()
        for stream in (back_proc.stdout, back_proc.stderr):
            if stream is not None:
                rest = stream.read().decode("utf-8", "replace").strip()
                if rest:
                    print("[aurc node] output tail:", rest[-400:])


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--serve-back":
        sys.exit(asyncio.run(_run_back_node(int(sys.argv[2]), sys.argv[3])))
    sys.exit(asyncio.run(_run_orchestrator()))
