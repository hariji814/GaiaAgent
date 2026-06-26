"""Tests for AURC Runtime Harness — lifecycle state machine."""


import pytest

from gaiaagent.core.identity import AgentDescriptor, Capabilities, SkillDeclaration
from gaiaagent.core.types import (
    AgentState,
    HealthStatus,
    RecoveryAction,
    RecoveryPolicy,
    RecoveryStrategy,
)
from gaiaagent.harness.lifecycle import (
    VALID_TRANSITIONS,
    AgentInstance,
    RuntimeHarness,
    StateTransitionError,
)


def _make_descriptor(agent_id: str = "aurc:gaia/test:v1.0") -> AgentDescriptor:
    return AgentDescriptor(
        aurc_id=agent_id,
        display_name="Test Agent",
        capabilities=Capabilities(
            provides=[SkillDeclaration(skill_id="test", name="Test")]
        ),
    )


class TestAgentInstance:
    """Tests for AgentInstance state management."""

    def test_initial_state(self):
        instance = AgentInstance(_make_descriptor())
        assert instance.state == AgentState.REGISTERING

    def test_valid_transition(self):
        instance = AgentInstance(_make_descriptor())
        instance.transition_to(AgentState.READY)
        assert instance.state == AgentState.READY

    def test_invalid_transition(self):
        instance = AgentInstance(_make_descriptor())
        with pytest.raises(StateTransitionError):
            # Can't go from REGISTERING to RUNNING directly
            instance.transition_to(AgentState.RUNNING)

    def test_state_history(self):
        instance = AgentInstance(_make_descriptor())
        instance.transition_to(AgentState.READY)
        instance.transition_to(AgentState.RUNNING)
        history = instance.state_history
        assert len(history) == 3  # REGISTERING + READY + RUNNING
        assert history[0][0] == AgentState.REGISTERING
        assert history[1][0] == AgentState.READY
        assert history[2][0] == AgentState.RUNNING

    def test_health_report(self):
        instance = AgentInstance(_make_descriptor())
        instance.transition_to(AgentState.READY)
        report = instance.to_health_report()
        assert report.agent_id == "aurc:gaia/test:v1.0"
        assert report.status == HealthStatus.HEALTHY
        assert report.state == AgentState.READY

    def test_health_report_failing(self):
        instance = AgentInstance(_make_descriptor())
        instance.transition_to(AgentState.READY)
        instance.transition_to(AgentState.RUNNING)
        instance.transition_to(AgentState.FAILING)
        report = instance.to_health_report()
        assert report.status == HealthStatus.UNHEALTHY

    def test_retry_counter(self):
        instance = AgentInstance(_make_descriptor())
        assert instance.increment_retry() == 1
        assert instance.increment_retry() == 2
        instance.reset_retry()
        assert instance.increment_retry() == 1


class TestStateTransitions:
    """Tests for state machine completeness."""

    def test_full_lifecycle(self):
        """Test complete: register → ready → run → complete"""
        instance = AgentInstance(_make_descriptor())
        instance.transition_to(AgentState.READY)
        instance.transition_to(AgentState.RUNNING)
        instance.transition_to(AgentState.COMPLETED)
        assert instance.state.is_terminal

    def test_pause_resume_lifecycle(self):
        """Test: register → ready → run → pause → run → complete"""
        instance = AgentInstance(_make_descriptor())
        instance.transition_to(AgentState.READY)
        instance.transition_to(AgentState.RUNNING)
        instance.transition_to(AgentState.PAUSED)
        instance.transition_to(AgentState.RUNNING)
        instance.transition_to(AgentState.COMPLETED)
        assert instance.state == AgentState.COMPLETED

    def test_error_recovery_lifecycle(self):
        """Test: register → ready → run → failing → recovering → ready → run → complete"""
        instance = AgentInstance(_make_descriptor())
        instance.transition_to(AgentState.READY)
        instance.transition_to(AgentState.RUNNING)
        instance.transition_to(AgentState.FAILING)
        instance.transition_to(AgentState.RECOVERING)
        instance.transition_to(AgentState.READY)
        instance.transition_to(AgentState.RUNNING)
        instance.transition_to(AgentState.COMPLETED)

    def test_terminal_states_have_no_transitions(self):
        """Terminal states cannot transition to anything."""
        for terminal in [AgentState.COMPLETED, AgentState.FAILED, AgentState.STOPPED]:
            assert VALID_TRANSITIONS[terminal] == set()


class TestRuntimeHarness:
    """Tests for the RuntimeHarness orchestration."""

    @pytest.fixture
    def harness(self):
        return RuntimeHarness()

    @pytest.mark.asyncio
    async def test_register(self, harness):
        desc = _make_descriptor()
        agent_id = await harness.register(desc)
        assert agent_id == "aurc:gaia/test:v1.0"
        assert harness.agent_count == 1

    @pytest.mark.asyncio
    async def test_register_duplicate(self, harness):
        desc = _make_descriptor()
        await harness.register(desc)
        with pytest.raises(ValueError, match="already registered"):
            await harness.register(desc)

    @pytest.mark.asyncio
    async def test_start_stop(self, harness):
        desc = _make_descriptor()
        await harness.register(desc)
        await harness.start("aurc:gaia/test:v1.0")
        instance = harness.get_agent("aurc:gaia/test:v1.0")
        assert instance.state == AgentState.RUNNING

        await harness.stop("aurc:gaia/test:v1.0")
        assert instance.state == AgentState.STOPPED

    @pytest.mark.asyncio
    async def test_pause_resume(self, harness):
        desc = _make_descriptor()
        await harness.register(desc)
        await harness.start("aurc:gaia/test:v1.0")

        await harness.pause("aurc:gaia/test:v1.0", reason="human approval")
        instance = harness.get_agent("aurc:gaia/test:v1.0")
        assert instance.state == AgentState.PAUSED

        await harness.resume("aurc:gaia/test:v1.0")
        assert instance.state == AgentState.RUNNING

    @pytest.mark.asyncio
    async def test_complete(self, harness):
        desc = _make_descriptor()
        await harness.register(desc)
        await harness.start("aurc:gaia/test:v1.0")
        await harness.complete("aurc:gaia/test:v1.0")

        instance = harness.get_agent("aurc:gaia/test:v1.0")
        assert instance.state == AgentState.COMPLETED
        assert instance.metrics.total_tasks_completed == 1

    @pytest.mark.asyncio
    async def test_error_recovery(self, harness):
        policy = RecoveryPolicy(
            max_retries=2,
            backoff_ms=[10, 20],
            strategies=[
                RecoveryStrategy(trigger="timeout", action=RecoveryAction.RETRY_WITH_BACKOFF),
            ],
        )
        harness._recovery_policy = policy

        desc = _make_descriptor()
        await harness.register(desc)
        await harness.start("aurc:gaia/test:v1.0")

        # Report error — should trigger recovery
        recovered = await harness.report_error("aurc:gaia/test:v1.0", "timeout error")
        assert recovered is True
        instance = harness.get_agent("aurc:gaia/test:v1.0")
        assert instance.state == AgentState.READY

    @pytest.mark.asyncio
    async def test_error_exceeds_retries(self):
        policy = RecoveryPolicy(max_retries=1, backoff_ms=[10])
        harness = RuntimeHarness(recovery_policy=policy)

        desc = _make_descriptor()
        await harness.register(desc)
        await harness.start("aurc:gaia/test:v1.0")

        # First error — should recover
        await harness.report_error("aurc:gaia/test:v1.0", "some error")
        instance = harness.get_agent("aurc:gaia/test:v1.0")
        assert instance.state == AgentState.READY

        # Restart and fail again
        await harness.start("aurc:gaia/test:v1.0")
        recovered = await harness.report_error("aurc:gaia/test:v1.0", "another error")
        assert recovered is False
        assert instance.state == AgentState.FAILED

    @pytest.mark.asyncio
    async def test_health_check(self, harness):
        desc = _make_descriptor()
        await harness.register(desc)
        report = await harness.health_check("aurc:gaia/test:v1.0")
        assert report.agent_id == "aurc:gaia/test:v1.0"
        assert report.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_health_check_all(self, harness):
        await harness.register(_make_descriptor("aurc:gaia/agent-a:v1.0"))
        await harness.register(_make_descriptor("aurc:gaia/agent-b:v1.0"))
        reports = await harness.health_check_all()
        assert len(reports) == 2

    @pytest.mark.asyncio
    async def test_list_agents_by_state(self, harness):
        await harness.register(_make_descriptor("aurc:gaia/a:v1.0"))
        await harness.register(_make_descriptor("aurc:gaia/b:v1.0"))
        await harness.start("aurc:gaia/a:v1.0")

        ready = harness.list_agents(AgentState.READY)
        running = harness.list_agents(AgentState.RUNNING)
        assert len(ready) == 1
        assert len(running) == 1

    @pytest.mark.asyncio
    async def test_shutdown(self, harness):
        await harness.register(_make_descriptor("aurc:gaia/a:v1.0"))
        await harness.register(_make_descriptor("aurc:gaia/b:v1.0"))
        await harness.start("aurc:gaia/a:v1.0")

        await harness.shutdown()
        # All non-terminal agents should be stopped
        for instance in harness.list_agents():
            assert instance.state.is_terminal

    @pytest.mark.asyncio
    async def test_unregister(self, harness):
        await harness.register(_make_descriptor())
        assert harness.agent_count == 1
        await harness.unregister("aurc:gaia/test:v1.0")
        assert harness.agent_count == 0

    @pytest.mark.asyncio
    async def test_restart_from_terminal(self, harness):
        desc = _make_descriptor()
        await harness.register(desc)
        await harness.start("aurc:gaia/test:v1.0")
        await harness.complete("aurc:gaia/test:v1.0")

        # Restart from completed state
        await harness.restart("aurc:gaia/test:v1.0")
        instance = harness.get_agent("aurc:gaia/test:v1.0")
        assert instance.state == AgentState.RUNNING
