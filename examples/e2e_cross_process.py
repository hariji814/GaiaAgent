"""End-to-end cross-process AURC demo - "seeing is believing".

Process A: an AURC server that serves a real @aurc_agent (Calculator) at
           POST /aurc, plus an A2A bridge endpoint at POST /a2a.
Process B: an orchestrator that (1) sends a native AURC request over real HTTP
           and (2) uses BridgeConnector(A2ABridge()) to translate an AURC
           delegation into an A2A JSON-RPC payload, POST it to /a2a, and get a
           real AURC response back - with correlation_id carried end-to-end.

This proves AURC is a real interop runtime (translate -> POST -> translate
back over the wire), not just a translation library.

Run:
    python examples/e2e_cross_process.py
"""
from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
from typing import Any

import httpx

from gaiaagent.bridges.a2a import A2ABridge
from gaiaagent.bridges.connector import BridgeConnector
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection
from gaiaagent.transport.http import HTTPTransportClient


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


_SERVER_SRC = (
    "import asyncio\n"
    "from typing import Any\n"
    "from gaiaagent.bridges.a2a import A2ABridge\n"
    "from gaiaagent.sdk.decorators import aurc_agent, skill\n"
    "from gaiaagent.server import AURCServer\n"
    "from gaiaagent.transport.http import HTTPTransportServer\n"
    "\n"
    "@aurc_agent(\n"
    '    id="aurc:demo/calculator:v1.0",\n'
    '    display_name="Calculator",\n'
    '    description="A demo AURC agent that does arithmetic",\n'
    '    protocols=["mcp/2025-06-18","a2a/1.0"],\n'
    ")\n"
    "class Calculator:\n"
    '    @skill("add", description="Add two numbers")\n'
    "    async def add(self, a: int, b: int) -> dict[str, Any]:\n"
    '        return {"sum": a + b}\n'
    "\n"
    '    @skill("multiply", description="Multiply two numbers")\n'
    "    async def multiply(self, a: int, b: int) -> dict[str, Any]:\n"
    '        return {"product": a * b}\n'
    "\n"
    '    @skill("general", description="Handle natural-language arithmetic")\n'
    '    async def general(self, content: str = "", **extra: Any) -> dict[str, Any]:\n'
    "        import re\n"
    '        nums = [int(x) for x in re.findall(r"-?\\d+", content)]\n'
    '        if "mult" in content.lower() and len(nums) >= 2:\n'
    '            return {"product": nums[0] * nums[1]}\n'
    "        if len(nums) >= 2:\n"
    '            return {"sum": nums[0] + nums[1]}\n'
    '        return {"echo": content}\n'
    "\n"
    "async def main() -> None:\n"
    "    server = AURCServer()\n"
    "    await server.register_agent(Calculator())\n"
    "    http = HTTPTransportServer(host=__HOST__, port=__PORT__)\n"
    "    http.set_handler(server.http_handler)\n"
    "    bridge = A2ABridge()\n"
    "\n"
    "    async def a2a_handler(payload):\n"
    "        msg = await bridge.translate_to_aurc(payload)\n"
    '        msg.target = "aurc:demo/calculator:v1.0"\n'
    "        outcome = await server.router.route(msg)\n"
    '        result = outcome.get("result", outcome) if isinstance(outcome, dict) else outcome\n'
    '        return {"jsonrpc": "2.0", "id": payload.get("id"), "result": result}\n'
    "\n"
    '    http.set_route("/a2a", a2a_handler)\n'
    "    await http.start()\n"
    "\n"
    "asyncio.run(main())\n"
)


def _server_script(port: int) -> str:
    return _SERVER_SRC.replace("__HOST__", '"127.0.0.1"').replace("__PORT__", str(port))


async def _wait_for_server(url: str, timeout: float = 10.0) -> bool:
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


def _invoke_msg(skill: str, target: str, corr: str, **params: Any) -> dict[str, Any]:
    return AURCMessage(
        source="aurc:demo/orchestrator:v1.0",
        target=target,
        type=MessageDirection.REQUEST,
        correlation_id=corr,
        body=MessageBody(method="invoke", skill=skill, params=params),
    ).model_dump(mode="json")


async def main() -> int:
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    aurc_url = f"{base}/aurc"

    proc = subprocess.Popen(
        [sys.executable, "-c", _server_script(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        if not await _wait_for_server(f"{base}/health"):
            out = proc.stdout.read().decode("utf-8", "replace") if proc.stdout else ""
            err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
            print("Server did not start in time.")
            print("stdout:", out)
            print("stderr:", err)
            return 1

        print(f"[server] AURC node up at {aurc_url}")
        print("=" * 64)

        # Step 1: native AURC over real HTTP.
        client = HTTPTransportClient()
        msg = _invoke_msg("add", "aurc:demo/calculator:v1.0", "corr-1", a=7, b=35)
        resp = await client.send(aurc_url, msg)
        print("[step 1] native AURC POST /aurc -> skill add(7, 35)")
        print("         correlation_id:", msg["correlation_id"])
        print("         result:", json.dumps(resp.get("result")))
        assert resp["result"] == {"sum": 42}, resp
        print("         [OK] routed to real @skill, correlation preserved\n")

        # Step 2: bridge AURC -> A2A -> POST /a2a -> AURC response.
        delegation = AURCMessage(
            source="aurc:demo/orchestrator:v1.0",
            target="a2a:demo/calculator",
            type=MessageDirection.DELEGATION,
            correlation_id="corr-2",
            body=MessageBody(
                method="invoke",
                skill="multiply",
                params={"a": 6, "b": 7, "content": "multiply 6 and 7"},
            ),
        )
        connector = BridgeConnector(
            bridge=A2ABridge(),
            resolver=lambda tgt: base,
            path="/a2a",
        )
        bridged = await connector.forward(delegation)
        print("[step 2] bridge: AURC delegation -> A2A payload -> POST /a2a")
        print("         correlation_id:", bridged.correlation_id)
        print("         response type:", bridged.type.value)
        result = bridged.body.result
        print("         result:", json.dumps(result, default=str))
        assert bridged.correlation_id == "corr-2"
        assert bridged.type == MessageDirection.RESPONSE
        assert bridged.body.result == {"product": 42}
        print("         [OK] real network round-trip, correlation carried end-to-end\n")

        print("=" * 64)
        print("Demo complete: AURC routes real skills over HTTP and bridges A2A.")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
