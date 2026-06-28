"""Tests for RuntimeHarness state-listener fire-and-forget scheduling.

Covers the P2-1 fix: async state listeners are scheduled on the running
loop via ``get_running_loop`` (not the deprecated ``get_event_loop``), the
task is tracked so the GC cannot collect it mid-flight, listener
exceptions are surfaced, and a sync caller outside any event loop closes
the coroutine instead of leaving it un-awaited.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from gaiaagent.core.identity import AgentDescriptor, Capabilities, SkillDeclaration
from gaiaagent.core.types import AgentState
from gaiaagent.harness.lifecycle import RuntimeHarness


def _make_descriptor(agent_id: str = "aurc:gaia/test:v1.0") -> AgentDescriptor:
    return AgentDescriptor(
        aurc_id=agent_id,
        display_name="Test Agent",
        capabilities=Capabilities(provides=[SkillDeclaration(skill_id="t", name="T")]),
    )


class TestFireAndForgetListeners:
    """Async listeners scheduled as tracked fire-and-forget tasks."""

    @pytest.mark.asyncio
    async def test_async_listener_runs_when_state_changes(self):
        harness = RuntimeHarness()
        await harness.register(_make_descriptor())
        seen: list[tuple[str, AgentState, AgentState]] = []

        async def listener(agent_id, old, new):
            seen.append((agent_id, old, new))

        harness.add_listener(listener)
        await harness.start("aurc:gaia/test:v1.0")  # READY -> RUNNING
        # Yield so the fire-and-forget task actually runs.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert seen == [("aurc:gaia/test:v1.0", AgentState.READY, AgentState.RUNNING)]

    @pytest.mark.asyncio
    async def test_async_listener_task_is_tracked_then_released(self):
        harness = RuntimeHarness()
        await harness.register(_make_descriptor())
        started = asyncio.Event()

        async def slow_listener(agent_id, old, new):
            started.set()
            await asyncio.sleep(0.05)

        harness.add_listener(slow_listener)
        await harness.start("aurc:gaia/test:v1.0")
        await started.wait()
        # While the task is in-flight it must be retained (no GC risk).
        assert len(harness._pending_listener_tasks) == 1
        await asyncio.sleep(0.1)
        # After completion the done callback must have released it.
        assert len(harness._pending_listener_tasks) == 0

    @pytest.mark.asyncio
    async def test_failing_async_listener_surfaces_exception(self, caplog):
        harness = RuntimeHarness()
        await harness.register(_make_descriptor())

        async def bad_listener(agent_id, old, new):
            raise RuntimeError("listener blew up")

        harness.add_listener(bad_listener)
        with caplog.at_level(logging.ERROR, logger="gaiaagent.harness.lifecycle"):
            await harness.start("aurc:gaia/test:v1.0")
            # Let the task run and its done-callback fire.
            for _ in range(5):
                await asyncio.sleep(0)
        assert any("async state listener" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_sync_and_async_listeners_coexist(self):
        harness = RuntimeHarness()
        await harness.register(_make_descriptor())
        sync_seen: list[str] = []
        async_seen: list[str] = []

        def sync_listener(agent_id, old, new):
            sync_seen.append(agent_id)

        async def async_listener(agent_id, old, new):
            async_seen.append(agent_id)

        harness.add_listener(sync_listener)
        harness.add_listener(async_listener)
        await harness.start("aurc:gaia/test:v1.0")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert sync_seen == ["aurc:gaia/test:v1.0"]
        assert async_seen == ["aurc:gaia/test:v1.0"]

    def test_no_running_loop_closes_coroutine(self):
        """A transition fired outside any event loop must not crash and must
        not leave a 'coroutine was never awaited' warning."""
        harness = RuntimeHarness()

        async def listener(agent_id, old, new):
            pass

        harness.add_listener(listener)
        # _fire_listeners is normally driven via _apply_transition from async
        # lifecycle methods; here we drive it directly with no running loop.
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            harness._fire_listeners("aurc:gaia/test:v1.0", AgentState.READY, AgentState.RUNNING)
        # Coroutine was closed, not scheduled.
        assert len(harness._pending_listener_tasks) == 0

    def test_get_event_loop_not_used_on_hot_path(self):
        """Regression guard: the deprecated API must no longer be on the path."""
        import inspect

        src = inspect.getsource(RuntimeHarness._fire_listeners)
        src += inspect.getsource(RuntimeHarness._schedule_listener_task)
        # Guard against the actual deprecated *call*. The docstring may
        # mention ``asyncio.get_event_loop`` (no parens) by name; that is fine.
        assert "asyncio.get_event_loop()" not in src
        assert "get_running_loop" in src
