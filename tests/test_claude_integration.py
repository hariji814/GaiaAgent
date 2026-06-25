"""Tests for AURC Claude Integration."""

from __future__ import annotations

import pytest

from gaiaagent.core.identity import InputOutputSchema, SkillDeclaration
from gaiaagent.integrations.claude import (
    ClaudeAgent,
    ClaudeLLM,
    ClaudeResponse,
    ClaudeTool,
    ClaudeToolCall,
)


class TestClaudeTool:
    """Tests for Claude tool definitions."""

    def test_to_claude_format(self):
        tool = ClaudeTool(
            name="web-search",
            description="Search the web for information",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer"},
                },
                "required": ["query"],
            },
        )
        fmt = tool.to_claude_format()
        assert fmt["name"] == "web-search"
        assert fmt["description"] == "Search the web for information"
        assert "query" in fmt["input_schema"]["properties"]

    def test_from_aurc_skill(self):
        skill = SkillDeclaration(
            skill_id="research",
            name="Deep Research",
            description="Multi-source research and synthesis",
            input_schema=InputOutputSchema(
                properties={"query": {"type": "string"}},
                required=["query"],
            ),
        )

        async def handler(query: str) -> dict:
            return {"result": query}

        tool = ClaudeTool.from_aurc_skill(skill, handler=handler)
        assert tool.name == "research"
        assert tool.description == "Multi-source research and synthesis"
        assert tool.handler is not None

    def test_empty_input_schema(self):
        tool = ClaudeTool(name="ping", description="Ping")
        fmt = tool.to_claude_format()
        assert fmt["input_schema"]["type"] == "object"


class TestClaudeResponse:
    """Tests for Claude response models."""

    def test_response_no_tools(self):
        resp = ClaudeResponse(text="Hello!", stop_reason="end_turn")
        assert resp.has_tool_calls is False
        assert resp.text == "Hello!"

    def test_response_with_tools(self):
        resp = ClaudeResponse(
            text="Let me search for that.",
            tool_calls=[
                ClaudeToolCall(tool_name="web-search", tool_input={"query": "test"}),
            ],
            stop_reason="tool_use",
        )
        assert resp.has_tool_calls is True
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].tool_name == "web-search"

    def test_response_with_usage(self):
        resp = ClaudeResponse(
            text="OK",
            usage={"input_tokens": 100, "output_tokens": 50},
        )
        assert resp.usage["input_tokens"] == 100


class TestClaudeLLM:
    """Tests for Claude LLM interface (without actual API calls)."""

    def test_create_default(self):
        llm = ClaudeLLM()
        assert llm._model == "claude-sonnet-4-20250514"
        assert llm._max_tokens == 4096

    def test_create_custom(self):
        llm = ClaudeLLM(
            model="claude-sonnet-4-20250514",
            api_key="test-key",
            max_tokens=8192,
            system_prompt="You are a helpful assistant.",
        )
        assert llm._model == "claude-sonnet-4-20250514"
        assert llm._api_key == "test-key"
        assert llm._system_prompt == "You are a helpful assistant."

    def test_clear_history(self):
        llm = ClaudeLLM()
        llm._conversation_history = [{"role": "user", "content": "hi"}]
        llm.clear_history()
        assert len(llm._conversation_history) == 0

    @pytest.mark.asyncio
    async def test_ask_without_anthropic_package(self):
        """Test graceful degradation when anthropic is not installed."""
        llm = ClaudeLLM(api_key="fake-key")
        # This should not crash — it returns an error message
        # (actual behavior depends on whether anthropic is installed)
        # We test that the method signature is correct
        assert hasattr(llm, "ask")
        assert hasattr(llm, "agentic_loop")
        assert hasattr(llm, "converse")


class TestClaudeAgent:
    """Tests for ClaudeAgent base class."""

    def test_create_agent(self):
        agent = ClaudeAgent(model="claude-sonnet-4-20250514")
        assert agent.claude is not None
        assert agent.claude._model == "claude-sonnet-4-20250514"

    def test_get_claude_tools_empty(self):
        agent = ClaudeAgent()
        tools = agent.get_claude_tools()
        assert isinstance(tools, list)


# ---------------------------------------------------------------------------
# Claude Code CLI backend (Loop Roadmap Step 2)
# ---------------------------------------------------------------------------


class _FakeProc:
    """Fake asyncio subprocess for claude_cli.run_agentic_loop (communicate-based)."""

    def __init__(
        self,
        stdout_bytes: bytes = b"",
        stderr_bytes: bytes = b"",
        returncode: int = 0,
        *,
        comm_exc: BaseException | None = None,
    ) -> None:
        self._stdout = stdout_bytes
        self._stderr = stderr_bytes
        self.returncode = returncode
        self.killed = False
        self._comm_exc = comm_exc

    async def communicate(self) -> tuple[bytes, bytes]:
        if self._comm_exc is not None:
            raise self._comm_exc
        return (self._stdout, self._stderr)

    def kill(self) -> None:
        self.killed = True


class TestClaudeCLIBackend:
    """Tests for the `claude` CLI backend and the agentic_loop delegation logic."""

    def test_cli_available_detection(self, monkeypatch):
        import gaiaagent.integrations.claude_cli as cli_mod

        monkeypatch.setattr(cli_mod.shutil, "which", lambda b: "/usr/bin/claude")
        assert cli_mod.cli_available() is True
        monkeypatch.setattr(cli_mod.shutil, "which", lambda b: None)
        assert cli_mod.cli_available() is False

    def test_prompt_too_long_boundary(self):
        import gaiaagent.integrations.claude_cli as cli_mod

        assert cli_mod.prompt_too_long("x" * 8001) is True
        assert cli_mod.prompt_too_long("x" * 8000) is False

    def test_stop_reason_to_recovery_action_mapping(self):
        import gaiaagent.integrations.claude_cli as cli_mod
        from gaiaagent.core.types import RecoveryAction

        assert cli_mod.stop_reason_to_recovery_action("end_turn") is None
        assert (
            cli_mod.stop_reason_to_recovery_action("max_turns")
            == RecoveryAction.COMPACT_AND_RETRY
        )
        assert (
            cli_mod.stop_reason_to_recovery_action("error")
            == RecoveryAction.RETRY_WITH_BACKOFF
        )
        assert (
            cli_mod.stop_reason_to_recovery_action("tool_use")
            == RecoveryAction.RETRY_ALTERNATIVE
        )
        assert cli_mod.stop_reason_to_recovery_action("???") == RecoveryAction.ESCALATE

    @pytest.mark.asyncio
    async def test_agentic_loop_uses_cli_when_available(self, monkeypatch):
        import gaiaagent.integrations.claude_cli as cli_mod

        monkeypatch.setattr(cli_mod, "cli_available", lambda cli_path=None: True)
        captured: dict = {}

        async def fake_run(**kwargs):
            captured.update(kwargs)
            return ClaudeResponse(text="from-cli", stop_reason="end_turn")

        monkeypatch.setattr(cli_mod, "run_agentic_loop", fake_run)

        async def fake_builtin(**kwargs):  # should NOT be called
            return ClaudeResponse(text="builtin")

        llm = ClaudeLLM(
            model="claude-sonnet-4-20250514",
            api_key="k",
            system_prompt="sys",
            cli_path="/usr/bin/claude",
        )
        monkeypatch.setattr(llm, "_agentic_loop_builtin", fake_builtin)

        resp = await llm.agentic_loop(prompt="hi", max_turns=5, correlation_id="cid-1")

        assert resp.text == "from-cli"
        assert captured["prompt"] == "hi"
        assert captured["model"] == "claude-sonnet-4-20250514"
        assert captured["system"] == "sys"
        assert captured["cli_path"] == "/usr/bin/claude"
        assert captured["max_turns"] == 5
        assert captured["correlation_id"] == "cid-1"
        assert captured["allowed_tools"] is None

    @pytest.mark.asyncio
    async def test_agentic_loop_falls_back_when_cli_missing(self, monkeypatch):
        import gaiaagent.integrations.claude_cli as cli_mod

        monkeypatch.setattr(cli_mod, "cli_available", lambda cli_path=None: False)

        async def fake_run(**kwargs):  # should NOT be called
            return ClaudeResponse(text="cli")

        monkeypatch.setattr(cli_mod, "run_agentic_loop", fake_run)

        builtin_called: dict = {"v": False}

        async def fake_builtin(**kwargs):
            builtin_called["v"] = True
            return ClaudeResponse(text="builtin", stop_reason="end_turn")

        llm = ClaudeLLM(api_key="k")
        monkeypatch.setattr(llm, "_agentic_loop_builtin", fake_builtin)

        resp = await llm.agentic_loop(prompt="hi")

        assert builtin_called["v"] is True
        assert resp.text == "builtin"

    @pytest.mark.asyncio
    async def test_agentic_loop_falls_back_with_handler_tools(self, monkeypatch):
        """Caller-supplied Python handlers can't run in a subprocess CLI → fall back."""
        import gaiaagent.integrations.claude_cli as cli_mod

        monkeypatch.setattr(cli_mod, "cli_available", lambda cli_path=None: True)
        cli_called: dict = {"v": False}

        async def fake_run(**kwargs):
            cli_called["v"] = True
            return ClaudeResponse(text="cli")

        monkeypatch.setattr(cli_mod, "run_agentic_loop", fake_run)

        async def handler(query: str) -> str:
            return query

        tool = ClaudeTool(
            name="search",
            description="d",
            input_schema={"type": "object", "properties": {}},
            handler=handler,
        )
        llm = ClaudeLLM(api_key="k")
        builtin_called: dict = {"v": False}

        async def fake_builtin(**kwargs):
            builtin_called["v"] = True
            return ClaudeResponse(text="builtin", stop_reason="end_turn")

        monkeypatch.setattr(llm, "_agentic_loop_builtin", fake_builtin)

        resp = await llm.agentic_loop(prompt="hi", tools=[tool])

        assert cli_called["v"] is False
        assert builtin_called["v"] is True
        assert resp.text == "builtin"

    @pytest.mark.asyncio
    async def test_agentic_loop_falls_back_when_prompt_too_long(self, monkeypatch):
        """A prompt exceeding the CLI arg limit forces the built-in loop."""
        import gaiaagent.integrations.claude_cli as cli_mod

        monkeypatch.setattr(cli_mod, "cli_available", lambda cli_path=None: True)
        cli_called: dict = {"v": False}

        async def fake_run(**kwargs):
            cli_called["v"] = True
            return ClaudeResponse(text="cli")

        monkeypatch.setattr(cli_mod, "run_agentic_loop", fake_run)

        llm = ClaudeLLM(api_key="k")
        builtin_called: dict = {"v": False}

        async def fake_builtin(**kwargs):
            builtin_called["v"] = True
            return ClaudeResponse(text="builtin", stop_reason="end_turn")

        monkeypatch.setattr(llm, "_agentic_loop_builtin", fake_builtin)

        await llm.agentic_loop(prompt="x" * 9000)

        assert cli_called["v"] is False
        assert builtin_called["v"] is True

    @pytest.mark.asyncio
    async def test_run_agentic_loop_parses_stream(self, monkeypatch):
        import gaiaagent.integrations.claude_cli as cli_mod

        stdout = (
            b'{"type":"system","subtype":"init"}\n'
            b'{"type":"assistant","message":{"content":[{"type":"text","text":"Hello"}],"stop_reason":"end_turn"}}\n'
            b'{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"search","input":{"q":"x"}}]}}\n'
            b'{"type":"result","result":"final answer",'
            b'"usage":{"input_tokens":10,"output_tokens":5},"is_error":false}\n'
        )

        async def fake_spawn(argv, env):  # noqa: ANN001
            return _FakeProc(stdout_bytes=stdout, returncode=0)

        monkeypatch.setattr(cli_mod, "_spawn", fake_spawn)

        resp = await cli_mod.run_agentic_loop(
            prompt="hi",
            tools=None,
            max_turns=5,
            system=None,
            model="m",
            api_key=None,
            max_tokens=None,
            execute_tool=None,
        )

        assert resp.text == "final answer"
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].tool_name == "search"
        assert resp.tool_calls[0].tool_input == {"q": "x"}
        assert resp.usage["input_tokens"] == 10
        assert resp.usage["output_tokens"] == 5
        assert resp.stop_reason == "end_turn"

    @pytest.mark.asyncio
    async def test_run_agentic_loop_handles_nonzero_exit(self, monkeypatch):
        import gaiaagent.integrations.claude_cli as cli_mod

        async def fake_spawn(argv, env):  # noqa: ANN001
            return _FakeProc(stderr_bytes=b"boom", returncode=1)

        monkeypatch.setattr(cli_mod, "_spawn", fake_spawn)

        resp = await cli_mod.run_agentic_loop(
            prompt="hi",
            tools=None,
            max_turns=5,
            system=None,
            model="m",
            api_key=None,
            max_tokens=None,
            execute_tool=None,
        )

        assert resp.stop_reason == "error"
        assert "exited 1" in resp.text
        assert "boom" in resp.text

    @pytest.mark.asyncio
    async def test_run_agentic_loop_empty_stream_is_error(self, monkeypatch):
        """No parseable events + exit 0 must NOT be masked as a successful empty turn."""
        import gaiaagent.integrations.claude_cli as cli_mod

        async def fake_spawn(argv, env):  # noqa: ANN001
            return _FakeProc(stdout_bytes=b"not-json banner\n", returncode=0)

        monkeypatch.setattr(cli_mod, "_spawn", fake_spawn)

        resp = await cli_mod.run_agentic_loop(
            prompt="hi",
            tools=None,
            max_turns=5,
            system=None,
            model="m",
            api_key=None,
            max_tokens=None,
            execute_tool=None,
        )

        assert resp.stop_reason == "error"
        assert "no stream-json events" in resp.text

    @pytest.mark.asyncio
    async def test_run_agentic_loop_timeout_kills_proc(self, monkeypatch):
        """A timeout (or cancellation) must kill the subprocess, not orphan it."""
        import asyncio as _asyncio

        import gaiaagent.integrations.claude_cli as cli_mod

        proc = _FakeProc(comm_exc=_asyncio.TimeoutError())

        async def fake_spawn(argv, env):  # noqa: ANN001
            return proc

        monkeypatch.setattr(cli_mod, "_spawn", fake_spawn)

        resp = await cli_mod.run_agentic_loop(
            prompt="hi",
            tools=None,
            max_turns=5,
            system=None,
            model="m",
            api_key=None,
            max_tokens=None,
            execute_tool=None,
            timeout=0.01,
        )

        assert resp.stop_reason == "error"
        assert proc.killed is True

    @pytest.mark.asyncio
    async def test_run_agentic_loop_records_trace(self, monkeypatch):
        """When a BridgeTraceRecorder is passed, the CLI loop leaves a trace span."""
        import gaiaagent.integrations.claude_cli as cli_mod
        from gaiaagent.observability.tracing import BridgeTraceRecorder

        stdout = (
            b'{"type":"result","result":"ok",'
            b'"usage":{"input_tokens":1,"output_tokens":2},"is_error":false}\n'
        )

        async def fake_spawn(argv, env):  # noqa: ANN001
            return _FakeProc(stdout_bytes=stdout, returncode=0)

        monkeypatch.setattr(cli_mod, "_spawn", fake_spawn)

        recorder = BridgeTraceRecorder()
        before = recorder.span_count
        resp = await cli_mod.run_agentic_loop(
            prompt="hi",
            tools=None,
            max_turns=5,
            system=None,
            model="m",
            api_key=None,
            max_tokens=None,
            execute_tool=None,
            trace_recorder=recorder,
            agent_id="aurc:test/agent:v1",
            correlation_id="corr-42",
        )

        assert resp.text == "ok"
        assert recorder.span_count == before + 1
        spans = recorder.get_trace("corr-42")
        assert len(spans) == 1
        assert spans[0].source == "aurc:test/agent:v1"

    @pytest.mark.asyncio
    async def test_execute_tool_seam_handles_missing_handler(self):
        llm = ClaudeLLM(api_key="k")
        result = await llm._execute_tool(None, {})
        assert result["is_error"] is True
        assert "not found" in result["content"]

    @pytest.mark.asyncio
    async def test_execute_tool_seam_runs_handler(self):
        llm = ClaudeLLM(api_key="k")

        async def echo(x: str) -> str:
            return f"echo:{x}"

        tool = ClaudeTool(name="echo", description="d", handler=echo)
        result = await llm._execute_tool(tool, {"x": "hi"})
        assert result["is_error"] is False
        assert result["content"] == "echo:hi"

    @pytest.mark.asyncio
    async def test_execute_tool_dict_result_is_json(self):
        """dict handler results must be JSON (not Python repr) for the model to parse."""
        import json as _json

        llm = ClaudeLLM(api_key="k")

        async def lookup(key: str) -> dict:
            return {"answer": key, "n": 3}

        tool = ClaudeTool(name="lookup", description="d", handler=lookup)
        result = await llm._execute_tool(tool, {"key": "q"})
        # Must be valid JSON with double quotes, not Python dict repr.
        parsed = _json.loads(result["content"])
        assert parsed == {"answer": "q", "n": 3}
