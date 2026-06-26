"""Phase 4.3 tests: WebSocket ping/pong heartbeat.

Verifies the server accepts ping config, the client starts a heartbeat
task on connect, ping failure marks the connection lost, and close()
cancels the heartbeat task.
"""
from __future__ import annotations

import asyncio

from gaiaagent.transport.websocket import WebSocketTransportClient, WebSocketTransportServer


class FakeWS:
    """Minimal fake websockets connection with an async ping()."""
    def __init__(self, ping_ok=True):
        self._ping_ok = ping_ok
        self.ping_calls = 0
        self.closed = False

    async def ping(self):
        self.ping_calls += 1
        if not self._ping_ok:
            raise ConnectionError("ping failed")

    async def close(self):
        self.closed = True

    async def recv(self):
        await asyncio.sleep(100)
        return ""

    async def send(self, data):
        pass


class TestServerHeartbeatConfig:
    def test_default_ping_config(self):
        s = WebSocketTransportServer()
        assert s._ping_interval == 20.0
        assert s._ping_timeout == 10.0

    def test_custom_ping_config(self):
        s = WebSocketTransportServer(ping_interval=5, ping_timeout=3)
        assert s._ping_interval == 5
        assert s._ping_timeout == 3


class TestClientHeartbeat:
    def test_heartbeat_interval_config(self):
        c = WebSocketTransportClient(heartbeat_interval=7)
        assert c._heartbeat_interval == 7

    def test_start_heartbeat_disabled_when_zero(self):
        c = WebSocketTransportClient(heartbeat_interval=0)
        # _start_heartbeat should be a no-op when interval <= 0
        c._start_heartbeat()
        assert c._heartbeat_task is None

    async def test_heartbeat_pings_periodically(self):
        c = WebSocketTransportClient(heartbeat_interval=0)
        fake = FakeWS(ping_ok=True)
        c._ws = fake
        c._connected = True
        # interval=0 makes _start_heartbeat a no-op, so call the loop directly
        await c._heartbeat_loop.__wrapped__ if hasattr(c._heartbeat_loop, "__wrapped__") else None
        # Drive one heartbeat iteration manually via the loop body
        c._heartbeat_interval = 0.001
        c._start_heartbeat()
        # Yield to the event loop repeatedly so the task can tick
        for _ in range(50):
            await asyncio.sleep(0)
        assert fake.ping_calls >= 1
        await c.close()

    async def test_ping_failure_marks_disconnected(self):
        # Use a tiny real interval + a real wait so the heartbeat task
        # actually gets scheduled by the event loop and fires a failing ping.
        import time

        c = WebSocketTransportClient(heartbeat_interval=0.005)
        fake = FakeWS(ping_ok=False)
        c._ws = fake
        c._connected = True
        c._start_heartbeat()
        # Wait long enough for at least one heartbeat tick (interval + slack)
        deadline = time.monotonic() + 1.0
        while c._connected is True and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        assert c._connected is False  # ping failure -> marked lost
        await c.close()

    async def test_close_cancels_heartbeat(self, monkeypatch):
        async def _noop(*a, **k):
            return
        monkeypatch.setattr(asyncio, "sleep", _noop)

        c = WebSocketTransportClient(heartbeat_interval=0.001)
        fake = FakeWS(ping_ok=True)
        c._ws = fake
        c._connected = True
        c._start_heartbeat()
        assert c._heartbeat_task is not None
        await c.close()
        assert c._heartbeat_task is None
