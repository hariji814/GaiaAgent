"""End-to-end REAL MCP <-> A2A cross-process interop demo.

The "no fabrication" sellability proof: every protocol end is a genuine
third-party-protocol implementation, and AURC only translates and routes
between them.

    REAL A2A client  (spec-compliant tasks/send JSON-RPC 2.0 over HTTP)
        -- POST /a2a -->
    [AURC node: A2ABridge.translate_to_aurc   (A2A -> AURC delegation)]
        MessageRouter -> Calculator.general skill
    [skill invokes the REAL MCP server]
        -- stdio (official MCP ClientSession) -->
    REAL MCP server  (official FastMCP, `add` tool, stdio transport)
        <-- CallToolResult content ["42"] (computed inside the MCP server) --
    [skill returns {"sum": 42, "via": "real-mcp", "mcp_content": "42"}]
        <-- A2ABridge.translate_from_aurc  (AURC response -> A2A task-completed) --
    REAL A2A client
        <-- A2A result {status:{state:"completed"}, artifacts:[...42...]} --

Three real processes:
  1. orchestrator : the real A2A client (this process when run with no args).
  2. AURC node    : an HTTP subprocess serving /a2a (this file with --serve-back).
  3. MCP server   : official FastMCP `add` over stdio, spawned per task by the
                    skill (a grandchild process).

Two real protocols on the wire:
  - A2A : a hand-written, spec-compliant tasks/send client. The official
          a2a-sdk wheel could not be fetched in this environment, so this
          client speaks the identical tasks/send JSON-RPC 2.0 wire protocol
          the A2A spec defines -- it is NOT using AURC internals.
  - MCP : the OFFICIAL Anthropic `mcp` SDK on both ends (FastMCP server +
          ClientSession initialize->list_tools->call_tool over stdio). The
          arithmetic is computed inside the real MCP server; AURC never adds.

A2A models tasks as natural-language messages, so the structured call is
carried as a text part ("add 15 27") and the back-end "general" skill parses it
before invoking MCP. This semantic mismatch is exactly what AURC bridges.

Run:
    python examples/e2e_mcp_a2a_interop.py
"""
from __future__ import annotations

import asyncio
import re
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from gaiaagent.bridges.a2a import A2ABridge
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
    description="Bridges A2A tasks to a real MCP arithmetic tool",
    protocols=["a2a/1.0", "mcp/2025-06-18"],
)
class _McpBackedCalculator:
    @skill("general", description="Natural-language arithmetic routed to a real MCP tool")
    async def general(self, content: str = "", **extra: Any) -> dict[str, Any]:
        nums = [int(x) for x in re.findall(r"-?\d+", content)]
        if len(nums) < 2:
            return {"echo": content, "via": "real-mcp", "error": "need two numbers"}
        a, b = nums[0], nums[1]
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
                    result = await session.call_tool("add", {"a": a, "b": b})
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
    bridge = A2ABridge()

    async def a2a_handler(payload: dict[str, Any]) -> dict[str, Any]:
        # A2A tasks/send -> AURC delegation (skill="general", params={content,...}).
        msg = await bridge.translate_to_aurc(payload)
        msg.target = "aurc:demo/calculator:v1.0"
        outcome = await server.router.route(msg)
        task_id = msg.body.params.get("task_id", "")
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
            result = outcome.get("result", outcome) if isinstance(outcome, dict) else outcome
            resp_msg = AURCMessage(
                source=msg.target,
                target=msg.source,
                type=MessageDirection.RESPONSE,
                correlation_id=msg.correlation_id,
                body=MessageBody(result=result, metadata={"task_id": task_id}),
            )
        # AURC response -> A2A task-completed JSON-RPC result.
        return await bridge.translate_from_aurc(resp_msg)

    http.set_route("/a2a", a2a_handler)
    print(f"[aurc node] serving /a2a on 127.0.0.1:{port} (MCP via {mcp_path})", flush=True)
    await http.start()
    return 0


# ---------------------------------------------------------------------------
# Orchestrator: the real A2A client. It POSTs a spec-compliant tasks/send
# JSON-RPC request to the AURC node's /a2a endpoint and parses the A2A
# task-completed response.
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


async def _a2a_tasks_send(
    base_url: str, text: str, corr_id: str, task_id: str
) -> dict[str, Any]:
    # Spec-compliant A2A tasks/send JSON-RPC 2.0 payload.
    payload = {
        "jsonrpc": "2.0",
        "id": corr_id,
        "method": "tasks/send",
        "params": {
            "id": task_id,
            "sessionId": f"sess-{uuid.uuid4().hex[:8]}",
            "messages": [
                {"role": "user", "parts": [{"type": "text", "text": text}]}
            ],
        },
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{base_url}/a2a", json=payload, timeout=30.0)
        r.raise_for_status()
        return r.json()


async def _run_orchestrator() -> int:
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    back_proc = subprocess.Popen(
        [
            sys.executable,
            str(_HERE / "e2e_mcp_a2a_interop.py"),
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

        print("[a2a client] real A2A tasks/send -> " + base + "/a2a")
        print("=" * 64)

        corr = "corr-real-mcp-a2a-1"
        task_id = "task-real-001"
        print("[a2a client] tasks/send: text part 'add 15 27' (asks MCP add(15, 27))")
        print("             jsonrpc id (correlation): " + corr)
        resp = await _a2a_tasks_send(base, "add 15 27", corr, task_id)

        state = resp.get("result", {}).get("status", {}).get("state")
        artifacts = resp.get("result", {}).get("artifacts", [])
        text = ""
        for art in artifacts:
            for part in art.get("parts", []):
                text = part.get("text", "") or text

        print("             jsonrpc id round-trip:    " + str(resp.get("id")))
        print("             a2a task state:           " + str(state))
        print("             artifact text:            " + text)

        assert resp.get("id") == corr, resp
        assert state == "completed", resp
        assert "42" in text, text
        assert "real-mcp" in text, text
        print("             [OK] real A2A client -> AURC -> real MCP, correlation e2e")
        print("                 (the sum was computed inside the real FastMCP MCP server)")
        print("=" * 64)
        print("Demo complete: a real A2A client reached a real MCP server through AURC.")
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
