"""Tests for RuntimeHarness.run_with_lifecycle and ClaudeLLM.run_managed_loop.

Verifies that the agentic loop is wired to the AURC lifecycle state machine:
start -> RUNNING -> run -> complete/error-recovery -> retry/FAIL.
"""

from __future__ import annotations

import pytest

from gaiaagent.core.identity import AgentDescriptor, Capabilities, SkillDeclaration
from gaiaagent.core.types import AgentState, RecoveryAction, RecoveryPolicy, RecoveryStrategy
from gaiaagent.harness.lifecycle import RuntimeHarness
from gaiaagent.integrations.claude import ClaudeLLM, ClaudeResponse


def _make_descriptor(agent_id: str = "aurc:gaia/test:v1.0") -> AgentDescriptor:
    return AgentDescriptor(
        aurc_id=agent_id,
        display_name="Test Agent",
        capabilities=Capabilities(provides=[SkillDeclaration(skill_id="t", name="T")]),
    )


class TestRunWithLifecycle:
    """Tests for RuntimeHarness.run_with_lifecycle."""

    @pytest.mark.asyncio
    async def test_clean_completion_transitions_to_completed(self):
        harness = RuntimeHarness()
        await harness.register(_make_descriptor())

        call_count = {"n": 0}

        async def loop():
            call_count["n"] += 1
            return "ok"

        result = await harness.run_with_lifecycle(
            "aurc:gaia/test:v1.0", loop, get_stop_reason=lambda r: None
        )
        assert result == "ok"
        assert call_count["n"] == 1
        assert harness.get_agent("aurc:gaia/test:v1.0").state == AgentState.COMPLETED

    @pytest.mark.asyncio
    async def test_no_extractor_treats_as_clean(self):
        """Without get_stop_reason, every result is a clean completion."""
        harness = RuntimeHarness()
        await harness.register(_make_descriptor())

        async def loop():
            return {"data": 42}

        result = await harness.run_with_lifecycle("aurc:gaia/test:v1.0", loop)
        assert result == {"data": 42}
        assert harness.get_agent("aurc:gaia/test:v1.0").state == AgentState.COMPLETED

    @pytest.mark.asyncio
    async def test_error_triggers_recovery_and_retry(self):
        """Error stop_reason -> report_error -> recovery -> retry -> success."""
        policy = RecoveryPolicy(
            max_retries=2,
            backoff_ms=[1, 1],
            strategies=[
                RecoveryStrategy(
                    trigger="loop stopped",
                    action=RecoveryAction.RETRY_WITH_BACKOFF,
                ),
            ],
        )
        harness = RuntimeHarness(recovery_policy=policy)
        await harness.register(_make_descriptor())

        attempts = {"n": 0}

        async def loop():
            attempts["n"] += 1
            if attempts["n"] == 1:
                return ClaudeResponse(text="fail", stop_reason="error")
            return ClaudeResponse(text="ok", stop_reason="end_turn")

        def extract_stop_reason(resp):
            if resp.stop_reason == "end_turn":
                return None
            return resp.stop_reason

        result = await harness.run_with_lifecycle(
            "aurc:gaia/test:v1.0", loop, get_stop_reason=extract_stop_reason
        )
        assert result.text == "ok"
        assert attempts["n"] == 2
        assert harness.get_agent("aurc:gaia/test:v1.0").state == AgentState.COMPLETED

    @pytest.mark.asyncio
    async def test_error_exceeds_retries_to_failed(self):
        """When recovery is exhausted, the agent ends in FAILED state."""
        policy = RecoveryPolicy(max_retries=1, backoff_ms=[1])
        harness = RuntimeHarness(recovery_policy=policy)
        await harness.register(_make_descriptor())

        async def loop():
            return ClaudeResponse(text="err", stop_reason="error")

        result = await harness.run_with_lifecycle(
            "aurc:gaia/test:v1.0",
            loop,
            get_stop_reason=lambda r: r.stop_reason if r.stop_reason != "end_turn" else None,
        )
        assert result.stop_reason == "error"
        assert harness.get_agent("aurc:gaia/test:v1.0").state == AgentState.FAILED

    @pytest.mark.asyncio
    async def test_lifecycle_state_transitions_during_run(self):
        """Verify the agent passes through RUNNING during execution."""
        harness = RuntimeHarness()
        await harness.register(_make_descriptor())

        states_seen = []

        async def loop():
            inst = harness.get_agent("aurc:gaia/test:v1.0")
            states_seen.append(inst.state)
            return "done"

        await harness.run_with_lifecycle(
            "aurc:gaia/test:v1.0", loop, get_stop_reason=lambda r: None
        )
        assert AgentState.RUNNING in states_seen

    @pytest.mark.asyncio
    async def test_retry_resets_to_running(self):
        """After recovery, the agent should be RUNNING again for the retry."""
        policy = RecoveryPolicy(
            max_retries=2, backoff_ms=[1, 1],
            strategies=[
                RecoveryStrategy(trigger="loop stopped", action=RecoveryAction.RETRY_WITH_BACKOFF),
            ],
        )
        harness = RuntimeHarness(recovery_policy=policy)
        await harness.register(_make_descriptor())

        retry_states = []

        async def loop():
            inst = harness.get_agent("aurc:gaia/test:v1.0")
            retry_states.append(inst.state)
            if inst.metrics.total_tasks_completed == 0 and len(retry_states) == 1:
                return ClaudeResponse(text="e", stop_reason="error")
            return ClaudeResponse(text="ok", stop_reason="end_turn")

        await harness.run_with_lifecycle(
            "aurc:gaia/test:v1.0",
            loop,
            get_stop_reason=lambda r: None if r.stop_reason == "end_turn" else r.stop_reason,
        )
        assert all(s == AgentState.RUNNING for s in retry_states)


class TestRunManagedLoop:
    """Tests for ClaudeLLM.run_managed_loop."""

    @pytest.mark.asyncio
    async def test_managed_loop_clean_completion(self, monkeypatch):
        """End-to-end: agentic_loop + harness lifecycle, clean completion."""
        import gaiaagent.integrations.claude_cli as claude_cli
        import gaiaagent.integrations.codex_cli as codex_cli

        monkeypatch.setattr(claude_cli, "cli_available", lambda cli_path=None: False)
        monkeypatch.setattr(codex_cli, "cli_available", lambda cli_path=None: False)

        async def fake_builtin(**kwargs):
            return ClaudeResponse(text="hello", stop_reason="end_turn")

        llm = ClaudeLLM(api_key="k", backend="claude")
        monkeypatch.setattr(llm, "_agentic_loop_builtin", fake_builtin)

        harness = RuntimeHarness()
        await harness.register(_make_descriptor("aurc:test/managed:v1"))

        resp = await llm.run_managed_loop(
            harness=harness,
            agent_id="aurc:test/managed:v1",
            prompt="hi",
        )
        assert resp.text == "hello"
        assert resp.stop_reason == "end_turn"
        assert harness.get_agent("aurc:test/managed:v1").state == AgentState.COMPLETED

    @pytest.mark.asyncio
    async def test_managed_loop_error_recovery_retry(self, monkeypatch):
        """Error on first attempt -> recovery -> retry -> success."""
        import gaiaagent.integrations.claude_cli as claude_cli
        import gaiaagent.integrations.codex_cli as codex_cli

        monkeypatch.setattr(claude_cli, "cli_available", lambda cli_path=None: False)
        monkeypatch.setattr(codex_cli, "cli_available", lambda cli_path=None: False)

        call_count = {"n": 0}

        async def fake_builtin(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return ClaudeResponse(text="err", stop_reason="error")
            return ClaudeResponse(text="ok", stop_reason="end_turn")

        llm = ClaudeLLM(api_key="k", backend="claude")
        monkeypatch.setattr(llm, "_agentic_loop_builtin", fake_builtin)

        policy = RecoveryPolicy(
            max_retries=2, backoff_ms=[1, 1],
            strategies=[
                RecoveryStrategy(trigger="loop stopped", action=RecoveryAction.RETRY_WITH_BACKOFF),
            ],
        )
        harness = RuntimeHarness(recovery_policy=policy)
        await harness.register(_make_descriptor("aurc:test/managed:v1"))

        resp = await llm.run_managed_loop(
            harness=harness,
            agent_id="aurc:test/managed:v1",
            prompt="hi",
        )
        assert resp.text == "ok"
        assert call_count["n"] == 2
        assert harness.get_agent("aurc:test/managed:v1").state == AgentState.COMPLETED

    @pytest.mark.asyncio
    async def test_managed_loop_max_turns_is_recoverable(self, monkeypatch):
        """max_turns stop_reason maps to COMPACT_AND_RETRY (recoverable)."""
        import gaiaagent.integrations.claude_cli as claude_cli
        import gaiaagent.integrations.codex_cli as codex_cli

        monkeypatch.setattr(claude_cli, "cli_available", lambda cli_path=None: False)
        monkeypatch.setattr(codex_cli, "cli_available", lambda cli_path=None: False)

        call_count = {"n": 0}

        async def fake_builtin(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return ClaudeResponse(text="partial", stop_reason="max_turns")
            return ClaudeResponse(text="done", stop_reason="end_turn")

        llm = ClaudeLLM(api_key="k", backend="claude")
        monkeypatch.setattr(llm, "_agentic_loop_builtin", fake_builtin)

        policy = RecoveryPolicy(
            max_retries=2, backoff_ms=[1, 1],
            strategies=[
                RecoveryStrategy(trigger="loop stopped", action=RecoveryAction.COMPACT_AND_RETRY),
            ],
        )
        harness = RuntimeHarness(recovery_policy=policy)
        await harness.register(_make_descriptor("aurc:test/managed:v1"))

        resp = await llm.run_managed_loop(
            harness=harness,
            agent_id="aurc:test/managed:v1",
            prompt="hi",
        )
        assert resp.text == "done"
        assert call_count["n"] == 2
        assert harness.get_agent("aurc:test/managed:v1").state == AgentState.COMPLETED
