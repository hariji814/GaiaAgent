"""Tests for AURC Codex CLI backend (Loop Roadmap Step 2 parity with the claude CLI)."""

from __future__ import annotations

import pytest

from gaiaagent.integrations.claude import ClaudeLLM, ClaudeResponse, ClaudeTool
from gaiaagent.integrations.codex_cli import (
    CodexMCPConfig,
    _build_argv,
    run_agentic_loop,
)


class _FakeProc:
    """Fake asyncio subprocess for codex_cli.run_agentic_loop (communicate-based)."""

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


class TestCodexCLIBackend:
    """Tests for the codex CLI backend adapter and its event-stream parser."""

    def test_cli_available_detection(self, monkeypatch):
        import gaiaagent.integrations.codex_cli as cli_mod

        monkeypatch.setattr(cli_mod.shutil, "which", lambda b: "/usr/bin/codex")
        assert cli_mod.cli_available() is True
        monkeypatch.setattr(cli_mod.shutil, "which", lambda b: None)
        assert cli_mod.cli_available() is False

    def test_prompt_too_long_boundary(self):
        import gaiaagent.integrations.codex_cli as cli_mod

        assert cli_mod.prompt_too_long("x" * 8001) is True
        assert cli_mod.prompt_too_long("x" * 8000) is False

    def test_stop_reason_to_recovery_action_mapping(self):
        import gaiaagent.integrations.codex_cli as cli_mod
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

    def test_codex_mcp_config_overrides_with_args_env(self):
        cfg = CodexMCPConfig(
            name="aurc",
            command="python",
            args=["-m", "gaiaagent.mcp.server"],
            env={"AURC_KEY": "secret"},
        )
        overrides = cfg.to_config_overrides()
        assert "mcp_servers.aurc.command=python" in overrides
        assert "mcp_servers.aurc.type=stdio" in overrides
        assert "mcp_servers.aurc.args+=-m" in overrides
        assert "mcp_servers.aurc.args+=gaiaagent.mcp.server" in overrides
        assert "mcp_servers.aurc.env.AURC_KEY=secret" in overrides

    def test_codex_mcp_config_overrides_no_args_no_env(self):
        cfg = CodexMCPConfig(name="aurc", command="python")
        overrides = cfg.to_config_overrides()
        assert overrides == [
            "mcp_servers.aurc.command=python",
            "mcp_servers.aurc.type=stdio",
        ]

    def test_build_argv_minimal(self):
        argv = _build_argv(
            prompt="hi",
            model=None,
            max_turns=None,
            system=None,
            cli_path=None,
            cli_args=None,
            sandbox=None,
            working_dir=None,
            mcp_config=None,
            extra_config=None,
            output_last_message=None,
        )
        assert argv[0:4] == ["codex", "exec", "--json", "--skip-git-repo-check"]
        assert argv[-1] == "hi"

    def test_build_argv_with_system_prepend(self):
        argv = _build_argv(
            prompt="do the thing",
            model=None,
            max_turns=None,
            system="You are AURC.",
            cli_path=None,
            cli_args=None,
            sandbox=None,
            working_dir=None,
            mcp_config=None,
            extra_config=None,
            output_last_message=None,
        )
        assert "You are AURC.\n\n---\n\ndo the thing" in argv[-1]

    def test_build_argv_with_mcp_overrides_and_flags(self):
        cfg = CodexMCPConfig(name="aurc", command="python", args=["-m", "server"])
        argv = _build_argv(
            prompt="hi",
            model="gpt-5",
            max_turns=5,
            system=None,
            cli_path=None,
            cli_args=None,
            sandbox="read-only",
            working_dir="/repo",
            mcp_config=[cfg],
            extra_config=["model_reasoning_effort=high"],
            output_last_message="/tmp/out.txt",
        )
        assert "--model" in argv
        assert "gpt-5" in argv
        assert "--sandbox" in argv
        assert "read-only" in argv
        assert "--cd" in argv
        assert "/repo" in argv
        assert "-c" in argv
        assert "exec.max_turns=5" in argv
        assert "mcp_servers.aurc.command=python" in argv
        assert "mcp_servers.aurc.enabled=true" in argv
        assert "model_reasoning_effort=high" in argv
        assert "--output-last-message" in argv
        assert "/tmp/out.txt" in argv

    @pytest.mark.asyncio
    async def test_run_agentic_loop_parses_stream(self, monkeypatch):
        import gaiaagent.integrations.codex_cli as cli_mod

        stdout = (
            b'{"type":"thread.started"}\n'
            b'{"type":"turn.started"}\n'
            b'{"type":"item.started","item":{"type":"agent_message","text":"Hello"}}\n'
            b'{"type":"item.completed","item":{"type":"agent_message","text":"Hello world"}}\n'
            b'{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}\n'
        )

        async def fake_spawn(argv, env, cwd):  # noqa: ANN001
            return _FakeProc(stdout_bytes=stdout, returncode=0)

        monkeypatch.setattr(cli_mod, "_spawn", fake_spawn)

        resp = await run_agentic_loop(
            prompt="hi",
            tools=None,
            max_turns=5,
            system=None,
            model="m",
            api_key=None,
            max_tokens=None,
            execute_tool=None,
        )

        assert resp.text == "Hello world"
        assert resp.stop_reason == "end_turn"
        assert resp.usage["input_tokens"] == 10
        assert resp.usage["output_tokens"] == 5

    @pytest.mark.asyncio
    async def test_run_agentic_loop_handles_turn_failed(self, monkeypatch):
        import gaiaagent.integrations.codex_cli as cli_mod

        stdout = (
            b'{"type":"turn.started"}\n'
            b'{"type":"turn.failed","error":"rate limit"}\n'
        )

        async def fake_spawn(argv, env, cwd):  # noqa: ANN001
            return _FakeProc(stdout_bytes=stdout, returncode=0)

        monkeypatch.setattr(cli_mod, "_spawn", fake_spawn)

        resp = await run_agentic_loop(
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

    @pytest.mark.asyncio
    async def test_run_agentic_loop_handles_mcp_tool_call(self, monkeypatch):
        import gaiaagent.integrations.codex_cli as cli_mod

        stdout = (
            b'{"type":"item.completed","item":{"type":"mcp_tool_call",'
            b'"name":"aurc.search","arguments":{"q":"x"},"id":"mt1"}}\n'
            b'{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\n'
        )

        async def fake_spawn(argv, env, cwd):  # noqa: ANN001
            return _FakeProc(stdout_bytes=stdout, returncode=0)

        monkeypatch.setattr(cli_mod, "_spawn", fake_spawn)

        resp = await run_agentic_loop(
            prompt="hi",
            tools=None,
            max_turns=5,
            system=None,
            model="m",
            api_key=None,
            max_tokens=None,
            execute_tool=None,
        )

        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].tool_name == "aurc.search"
        assert resp.tool_calls[0].tool_input == {"q": "x"}
        assert resp.tool_calls[0].tool_use_id == "mt1"

    @pytest.mark.asyncio
    async def test_run_agentic_loop_handles_command_execution(self, monkeypatch):
        """command_execution items are surfaced as tool calls for observability."""
        import gaiaagent.integrations.codex_cli as cli_mod

        stdout = (
            b'{"type":"item.completed","item":{"type":"command_execution",'
            b'"command":"ls -la","id":"cmd1"}}\n'
            b'{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\n'
        )

        async def fake_spawn(argv, env, cwd):  # noqa: ANN001
            return _FakeProc(stdout_bytes=stdout, returncode=0)

        monkeypatch.setattr(cli_mod, "_spawn", fake_spawn)

        resp = await run_agentic_loop(
            prompt="hi",
            tools=None,
            max_turns=5,
            system=None,
            model="m",
            api_key=None,
            max_tokens=None,
            execute_tool=None,
        )

        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].tool_input["command"] == "ls -la"

    @pytest.mark.asyncio
    async def test_run_agentic_loop_handles_nonzero_exit(self, monkeypatch):
        import gaiaagent.integrations.codex_cli as cli_mod

        async def fake_spawn(argv, env, cwd):  # noqa: ANN001
            return _FakeProc(stderr_bytes=b"boom", returncode=1)

        monkeypatch.setattr(cli_mod, "_spawn", fake_spawn)

        resp = await run_agentic_loop(
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
        import gaiaagent.integrations.codex_cli as cli_mod

        async def fake_spawn(argv, env, cwd):  # noqa: ANN001
            return _FakeProc(stdout_bytes=b"not-json banner\n", returncode=0)

        monkeypatch.setattr(cli_mod, "_spawn", fake_spawn)

        resp = await run_agentic_loop(
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
        assert "no JSONL events" in resp.text

    @pytest.mark.asyncio
    async def test_run_agentic_loop_timeout_kills_proc(self, monkeypatch):
        """A timeout must kill the subprocess, not orphan it."""
        import asyncio as _asyncio

        import gaiaagent.integrations.codex_cli as cli_mod

        proc = _FakeProc(comm_exc=_asyncio.TimeoutError())

        async def fake_spawn(argv, env, cwd):  # noqa: ANN001
            return proc

        monkeypatch.setattr(cli_mod, "_spawn", fake_spawn)

        resp = await run_agentic_loop(
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
        import gaiaagent.integrations.codex_cli as cli_mod
        from gaiaagent.observability.tracing import BridgeTraceRecorder

        stdout = (
            b'{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":2}}\n'
        )

        async def fake_spawn(argv, env, cwd):  # noqa: ANN001
            return _FakeProc(stdout_bytes=stdout, returncode=0)

        monkeypatch.setattr(cli_mod, "_spawn", fake_spawn)

        recorder = BridgeTraceRecorder()
        before = recorder.span_count
        await run_agentic_loop(
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

        assert recorder.span_count == before + 1
        spans = recorder.get_trace("corr-42")
        assert len(spans) == 1
        assert spans[0].source == "aurc:test/agent:v1"

    @pytest.mark.asyncio
    async def test_run_agentic_loop_sets_api_key_env(self, monkeypatch):
        """The CODEX_API_KEY env var must be injected for the subprocess."""
        import gaiaagent.integrations.codex_cli as cli_mod

        captured_env: dict = {}

        async def fake_spawn(argv, env, cwd):  # noqa: ANN001
            captured_env.update(env)
            return _FakeProc(stdout_bytes=b'{"type":"turn.completed","usage":{}}\n', returncode=0)

        monkeypatch.setattr(cli_mod, "_spawn", fake_spawn)

        await run_agentic_loop(
            prompt="hi",
            tools=None,
            max_turns=5,
            system=None,
            model="m",
            api_key="sk-test-42",
            max_tokens=None,
            execute_tool=None,
        )

        assert captured_env["CODEX_API_KEY"] == "sk-test-42"


class TestCodexDispatch:
    """Tests for ClaudeLLM.agentic_loop backend dispatch (codex / auto / fallback)."""

    @pytest.mark.asyncio
    async def test_dispatch_uses_codex_backend(self, monkeypatch):
        import gaiaagent.integrations.codex_cli as cli_mod

        monkeypatch.setattr(cli_mod, "cli_available", lambda cli_path=None: True)
        captured: dict = {}

        async def fake_run(**kwargs):
            captured.update(kwargs)
            return ClaudeResponse(text="from-codex", stop_reason="end_turn")

        monkeypatch.setattr(cli_mod, "run_agentic_loop", fake_run)

        async def fake_builtin(**kwargs):  # should NOT be called
            return ClaudeResponse(text="builtin")

        llm = ClaudeLLM(
            model="gpt-5",
            api_key="k",
            system_prompt="sys",
            backend="codex",
            codex_cli_path="/usr/bin/codex",
            codex_sandbox="read-only",
        )
        monkeypatch.setattr(llm, "_agentic_loop_builtin", fake_builtin)

        resp = await llm.agentic_loop(prompt="hi", max_turns=5, correlation_id="cid-1")

        assert resp.text == "from-codex"
        assert captured["prompt"] == "hi"
        assert captured["model"] == "gpt-5"
        assert captured["system"] == "sys"
        assert captured["cli_path"] == "/usr/bin/codex"
        assert captured["sandbox"] == "read-only"
        assert captured["correlation_id"] == "cid-1"

    @pytest.mark.asyncio
    async def test_dispatch_auto_prefers_codex(self, monkeypatch):
        import gaiaagent.integrations.claude_cli as claude_mod
        import gaiaagent.integrations.codex_cli as cli_mod

        monkeypatch.setattr(cli_mod, "cli_available", lambda cli_path=None: True)
        monkeypatch.setattr(claude_mod, "cli_available", lambda cli_path=None: True)

        codex_called: dict = {"v": False}
        claude_called: dict = {"v": False}

        async def fake_codex_run(**kwargs):
            codex_called["v"] = True
            return ClaudeResponse(text="from-codex", stop_reason="end_turn")

        async def fake_claude_run(**kwargs):
            claude_called["v"] = True
            return ClaudeResponse(text="from-claude")

        monkeypatch.setattr(cli_mod, "run_agentic_loop", fake_codex_run)
        monkeypatch.setattr(claude_mod, "run_agentic_loop", fake_claude_run)

        async def fake_builtin(**kwargs):
            return ClaudeResponse(text="builtin")

        llm = ClaudeLLM(api_key="k", backend="auto")
        monkeypatch.setattr(llm, "_agentic_loop_builtin", fake_builtin)

        resp = await llm.agentic_loop(prompt="hi")

        assert codex_called["v"] is True
        assert claude_called["v"] is False
        assert resp.text == "from-codex"

    @pytest.mark.asyncio
    async def test_dispatch_auto_falls_back_to_claude(self, monkeypatch):
        """auto should prefer codex, then claude, then builtin."""
        import gaiaagent.integrations.claude_cli as claude_mod
        import gaiaagent.integrations.codex_cli as cli_mod

        monkeypatch.setattr(cli_mod, "cli_available", lambda cli_path=None: False)
        monkeypatch.setattr(claude_mod, "cli_available", lambda cli_path=None: True)

        codex_called: dict = {"v": False}
        claude_called: dict = {"v": False}

        async def fake_codex_run(**kwargs):
            codex_called["v"] = True
            return ClaudeResponse(text="from-codex")

        async def fake_claude_run(**kwargs):
            claude_called["v"] = True
            return ClaudeResponse(text="from-claude", stop_reason="end_turn")

        monkeypatch.setattr(cli_mod, "run_agentic_loop", fake_codex_run)
        monkeypatch.setattr(claude_mod, "run_agentic_loop", fake_claude_run)

        async def fake_builtin(**kwargs):
            return ClaudeResponse(text="builtin")

        llm = ClaudeLLM(api_key="k", backend="auto")
        monkeypatch.setattr(llm, "_agentic_loop_builtin", fake_builtin)

        resp = await llm.agentic_loop(prompt="hi")

        assert codex_called["v"] is False
        assert claude_called["v"] is True
        assert resp.text == "from-claude"

    @pytest.mark.asyncio
    async def test_dispatch_handler_tools_force_builtin(self, monkeypatch):
        """Caller-supplied Python handlers can't run in a subprocess CLI -> fall back."""
        import gaiaagent.integrations.codex_cli as cli_mod

        monkeypatch.setattr(cli_mod, "cli_available", lambda cli_path=None: True)
        codex_called: dict = {"v": False}

        async def fake_run(**kwargs):
            codex_called["v"] = True
            return ClaudeResponse(text="codex")

        monkeypatch.setattr(cli_mod, "run_agentic_loop", fake_run)

        async def handler(query: str) -> str:
            return query

        tool = ClaudeTool(
            name="search",
            description="d",
            input_schema={"type": "object", "properties": {}},
            handler=handler,
        )
        llm = ClaudeLLM(api_key="k", backend="codex")
        builtin_called: dict = {"v": False}

        async def fake_builtin(**kwargs):
            builtin_called["v"] = True
            return ClaudeResponse(text="builtin", stop_reason="end_turn")

        monkeypatch.setattr(llm, "_agentic_loop_builtin", fake_builtin)

        resp = await llm.agentic_loop(prompt="hi", tools=[tool])

        assert codex_called["v"] is False
        assert builtin_called["v"] is True
        assert resp.text == "builtin"

    @pytest.mark.asyncio
    async def test_dispatch_codex_missing_falls_to_builtin(self, monkeypatch):
        """When codex is selected but not on PATH (and claude also absent), use builtin."""
        import gaiaagent.integrations.claude_cli as claude_mod
        import gaiaagent.integrations.codex_cli as cli_mod

        monkeypatch.setattr(cli_mod, "cli_available", lambda cli_path=None: False)
        monkeypatch.setattr(claude_mod, "cli_available", lambda cli_path=None: False)

        async def fake_codex_run(**kwargs):  # should NOT be called
            return ClaudeResponse(text="codex")

        async def fake_claude_run(**kwargs):  # should NOT be called
            return ClaudeResponse(text="claude")

        monkeypatch.setattr(cli_mod, "run_agentic_loop", fake_codex_run)
        monkeypatch.setattr(claude_mod, "run_agentic_loop", fake_claude_run)

        builtin_called: dict = {"v": False}

        async def fake_builtin(**kwargs):
            builtin_called["v"] = True
            return ClaudeResponse(text="builtin", stop_reason="end_turn")

        llm = ClaudeLLM(api_key="k", backend="codex")
        monkeypatch.setattr(llm, "_agentic_loop_builtin", fake_builtin)

        resp = await llm.agentic_loop(prompt="hi")

        assert builtin_called["v"] is True
        assert resp.text == "builtin"

    @pytest.mark.asyncio
    async def test_dispatch_prompt_too_long_forces_builtin(self, monkeypatch):
        """A prompt exceeding the CLI arg limit forces the built-in loop."""
        import gaiaagent.integrations.codex_cli as cli_mod

        monkeypatch.setattr(cli_mod, "cli_available", lambda cli_path=None: True)
        codex_called: dict = {"v": False}

        async def fake_run(**kwargs):
            codex_called["v"] = True
            return ClaudeResponse(text="codex")

        monkeypatch.setattr(cli_mod, "run_agentic_loop", fake_run)

        llm = ClaudeLLM(api_key="k", backend="codex")
        builtin_called: dict = {"v": False}

        async def fake_builtin(**kwargs):
            builtin_called["v"] = True
            return ClaudeResponse(text="builtin", stop_reason="end_turn")

        monkeypatch.setattr(llm, "_agentic_loop_builtin", fake_builtin)

        await llm.agentic_loop(prompt="x" * 9000)

        assert codex_called["v"] is False
        assert builtin_called["v"] is True
