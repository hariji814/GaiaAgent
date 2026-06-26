"""Phase 4.3 tests: HTTPTransportServer graceful drain + force-exit + signal hooks.

Verifies that stop() sets should_exit and awaits the serve task to drain,
that a slow drain is force-exited after the timeout, and that the best-effort
signal handler installation never crashes on unsupported platforms.
"""
from __future__ import annotations

import asyncio

import pytest

from gaiaagent.transport.http import HTTPTransportServer


class FakeServer:
    """Stand-in for a uvicorn Server with the drain semantics we rely on."""

    def __init__(self, drain_delay: float = 0.0) -> None:
        self.should_exit = False
        self.force_exit = False
        self.started = asyncio.Event()
        self._drain_delay = drain_delay
        self.drained = False

    async def serve(self) -> None:
        self.started.set()
        while not self.should_exit:
            await asyncio.sleep(0.005)
        # drain phase: completes after drain_delay, or immediately when force_exit set
        elapsed = 0.0
        while elapsed < self._drain_delay:
            if self.force_exit:
                break
            await asyncio.sleep(0.01)
            elapsed += 0.01
        self.drained = True


@pytest.mark.asyncio
async def test_stop_awaits_graceful_drain() -> None:
    """stop() sets should_exit and waits for serve() to finish draining."""
    server = HTTPTransportServer()
    fake = FakeServer(drain_delay=0.0)
    server._server = fake
    server._serve_task = asyncio.create_task(fake.serve())
    server._running = True
    await fake.started.wait()

    await server.stop(timeout=1.0)

    assert fake.should_exit is True
    assert fake.drained is True
    assert server.is_running is False
    assert server._serve_task.done()


@pytest.mark.asyncio
async def test_stop_force_exit_on_timeout() -> None:
    """A drain that exceeds timeout flips force_exit for a hard shutdown."""
    server = HTTPTransportServer()
    # drain_delay far exceeds the stop timeout
    fake = FakeServer(drain_delay=10.0)
    server._server = fake
    server._serve_task = asyncio.create_task(fake.serve())
    server._running = True
    await fake.started.wait()

    await server.stop(timeout=0.1)

    assert fake.force_exit is True
    assert server.is_running is False
    assert server._serve_task.done()


@pytest.mark.asyncio
async def test_stop_no_server_is_noop() -> None:
    """stop() is a safe no-op when start() was never called."""
    server = HTTPTransportServer()
    await server.stop()  # must not raise
    assert server.is_running is False


@pytest.mark.asyncio
async def test_stop_idempotent() -> None:
    """Calling stop() twice does not error and keeps running=False."""
    server = HTTPTransportServer()
    fake = FakeServer(drain_delay=0.0)
    server._server = fake
    server._serve_task = asyncio.create_task(fake.serve())
    server._running = True
    await fake.started.wait()

    await server.stop(timeout=1.0)
    await server.stop(timeout=1.0)  # second call: task already done

    assert server.is_running is False
    assert server._serve_task.done()


@pytest.mark.asyncio
async def test_install_signal_handlers_does_not_crash() -> None:
    """Signal handler installation is best-effort and never raises."""
    server = HTTPTransportServer()
    # No running loop inside the server object; call within an event loop.
    server.install_signal_handlers()  # should not raise even on Windows


def test_serve_task_defaults_none() -> None:
    """A fresh server has no tracked serve task."""
    server = HTTPTransportServer()
    assert server._serve_task is None
    assert server._server is None
    assert server.is_running is False
