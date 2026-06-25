"""Tests for the AURC MCP stdio server (gaiaagent.mcp.server)."""

from __future__ import annotations

import json

import pytest

from gaiaagent.mcp.server import AURCMCPStdioServer, _load_agent
from gaiaagent.sdk.decorators import aurc_agent, skill


@aurc_agent(
    id="aurc:test/mcp-agent:v1.0",
    display_name="MCP Test Agent",
    description="test fixture",
)
class _MCPTestAgent:
    @skill("greet", description="Greet a name")
    async def greet(self, name: str) -> dict:
        return {"message": f"hello {name}"}

    @skill("boom", description="Always fails")
    async def boom(self) -> dict:
        raise RuntimeError("kaboom")


def _make_server(trace_recorder=None) -> AURCMCPStdioServer:
    return AURCMCPStdioServer(_MCPTestAgent(), trace_recorder=trace_recorder)


class TestAURCMCPStdioServer:
    @pytest.mark.asyncio
    async def test_initialize(self):
        server = _make_server()
        resp = await server.dispatch({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert resp["id"] == 1
        result = resp["result"]
        assert "protocolVersion" in result
        assert "tools" in result["capabilities"]
        assert result["serverInfo"]["name"] == "aurc-mcp"

    @pytest.mark.asyncio
    async def test_notifications_initialized_returns_none(self):
        server = _make_server()
        resp = await server.dispatch({"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert resp is None

    @pytest.mark.asyncio
    async def test_tools_list_enumerates_skills(self):
        server = _make_server()
        resp = await server.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = resp["result"]["tools"]
        names = {t["name"] for t in tools}
        assert names == {"greet", "boom"}
        greet = next(t for t in tools if t["name"] == "greet")
        assert greet["description"] == "Greet a name"
        assert "name" in greet["inputSchema"]["properties"]
        assert greet["inputSchema"]["required"] == ["name"]

    @pytest.mark.asyncio
    async def test_tools_call_routes_to_skill(self):
        server = _make_server()
        resp = await server.dispatch({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "greet", "arguments": {"name": "world"}},
        })
        result = resp["result"]
        assert result["isError"] is False
        payload = json.loads(result["content"][0]["text"])
        assert payload == {"message": "hello world"}

    @pytest.mark.asyncio
    async def test_tools_call_skill_exception_is_error(self):
        server = _make_server()
        resp = await server.dispatch({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "boom", "arguments": {}},
        })
        result = resp["result"]
        assert result["isError"] is True
        assert "kaboom" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_tools_call_unknown_skill_is_error(self):
        server = _make_server()
        resp = await server.dispatch({
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "nope", "arguments": {}},
        })
        assert resp["result"]["isError"] is True
        assert "no skill" in resp["result"]["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_unknown_method_is_method_not_found(self):
        server = _make_server()
        resp = await server.dispatch({"jsonrpc": "2.0", "id": 6, "method": "ping"})
        assert resp["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_tools_call_records_trace(self):
        from gaiaagent.observability.tracing import BridgeTraceRecorder

        recorder = BridgeTraceRecorder()
        server = _make_server(trace_recorder=recorder)
        await server.dispatch({
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "greet", "arguments": {"name": "x"}},
        })
        # translate_to_aurc sets correlation_id = str(req_id) = "7"
        spans = recorder.get_trace("7")
        assert len(spans) == 1
        assert "mcp→aurc" in spans[0].bridge_chain

    @pytest.mark.asyncio
    async def test_non_dict_request_is_parse_error(self):
        server = _make_server()
        resp = await server.dispatch("not a dict")
        assert resp["error"]["code"] == -32700


class _FakeStdin:
    """Async stdin yielding fixed lines then EOF."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)
        self._i = 0

    async def readline(self) -> bytes:
        if self._i >= len(self._lines):
            return b""
        line = self._lines[self._i]
        self._i += 1
        return line.encode("utf-8") + b"\n"


class _FakeStdout:
    def __init__(self) -> None:
        self.chunks: list[str] = []

    def write(self, s: str) -> int:
        self.chunks.append(s)
        return len(s)

    def flush(self) -> None:
        pass


class TestAURCMCPStdioLoop:
    @pytest.mark.asyncio
    async def test_serve_stdio_end_to_end(self):
        server = _make_server()
        stdin = _FakeStdin([
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": "greet", "arguments": {"name": "loop"}}}),
        ])
        stdout = _FakeStdout()
        await server.serve_stdio(stdin=stdin, stdout=stdout)
        responses = [json.loads(c) for c in stdout.chunks if c.strip()]
        assert len(responses) == 3
        assert responses[0]["result"]["serverInfo"]["name"] == "aurc-mcp"
        assert {t["name"] for t in responses[1]["result"]["tools"]} == {"greet", "boom"}
        assert json.loads(responses[2]["result"]["content"][0]["text"]) == {"message": "hello loop"}


class TestLoadAgent:
    def test_load_agent_imports_and_instantiates(self, monkeypatch):
        import sys
        import types

        # Inject a fake module so importlib.import_module finds it.
        mod = types.ModuleType("fake_mcp_agent_mod")
        mod._MCPTestAgent = _MCPTestAgent
        monkeypatch.setitem(sys.modules, "fake_mcp_agent_mod", mod)

        agent = _load_agent("fake_mcp_agent_mod:_MCPTestAgent")
        assert getattr(agent, "aurc_descriptor", None) is not None

    def test_load_agent_bad_spec_raises(self):
        with pytest.raises(ValueError):
            _load_agent("no_colon_here")
