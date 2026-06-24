"""Tests for AURC Message Router and Session Manager."""

import pytest

from gaiaagent.bus.router import MessageRouter, RouterStats
from gaiaagent.bus.session import SessionManager, SessionState
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection


class TestMessageRouter:
    """Tests for the MessageRouter."""

    @pytest.fixture
    def router(self):
        return MessageRouter()

    @pytest.mark.asyncio
    async def test_register_handler(self, router):
        async def handler(msg):
            return "ok"

        router.register_handler("aurc:gaia/test:v1.0", handler)
        assert router.has_handler("aurc:gaia/test:v1.0")
        assert router.handler_count == 1

    @pytest.mark.asyncio
    async def test_direct_routing(self, router):
        received = []

        async def handler(msg):
            received.append(msg)
            return {"status": "ok"}

        router.register_handler("aurc:gaia/researcher:v1.0", handler)

        msg = AURCMessage(
            source="aurc:gaia/orchestrator:v1.0",
            target="aurc:gaia/researcher:v1.0",
            type=MessageDirection.REQUEST,
            body=MessageBody(method="invoke", skill="research", params={"query": "test"}),
        )
        result = await router.route(msg)
        assert result == {"status": "ok"}
        assert len(received) == 1
        assert router.stats.direct == 1

    @pytest.mark.asyncio
    async def test_dead_letter_queue(self, router):
        msg = AURCMessage(
            source="aurc:gaia/test:v1.0",
            target="aurc:gaia/nonexistent:v1.0",
            type=MessageDirection.REQUEST,
        )
        await router.route(msg)
        assert len(router.dead_letter_queue) == 1
        assert router.stats.dead_lettered == 1

    @pytest.mark.asyncio
    async def test_ttl_expired(self, router):
        msg = AURCMessage(
            source="aurc:gaia/test:v1.0",
            target="aurc:gaia/handler:v1.0",
            type=MessageDirection.REQUEST,
        )
        msg.routing.ttl_hops = 0  # Already expired

        async def handler(m):
            return "should not reach"

        router.register_handler("aurc:gaia/handler:v1.0", handler)
        result = await router.route(msg)
        assert result is None
        assert router.stats.dropped == 1

    @pytest.mark.asyncio
    async def test_bridge_routing(self, router):
        bridged = []

        async def bridge_forwarder(msg):
            bridged.append(msg)
            return {"bridged": True}

        router.register_bridge_forwarder("mcp", bridge_forwarder)

        msg = AURCMessage(
            source="aurc:gaia/test:v1.0",
            target="mcp:external/web-search:v1.0",
            type=MessageDirection.REQUEST,
        )
        result = await router.route(msg)
        assert result == {"bridged": True}
        assert len(bridged) == 1
        assert router.stats.bridged == 1

    @pytest.mark.asyncio
    async def test_broadcast_routing(self, router):
        received_a = []
        received_b = []

        async def handler_a(msg):
            received_a.append(msg)
            return "a"

        async def handler_b(msg):
            received_b.append(msg)
            return "b"

        router.subscribe("aurc:group/researchers", handler_a)
        router.subscribe("aurc:group/researchers", handler_b)

        msg = AURCMessage(
            source="aurc:gaia/orchestrator:v1.0",
            target="aurc:group/researchers",
            type=MessageDirection.NOTIFICATION,
        )
        results = await router.route(msg)
        assert len(received_a) == 1
        assert len(received_b) == 1
        assert router.stats.broadcast == 1

    @pytest.mark.asyncio
    async def test_clear_dead_letters(self, router):
        for i in range(5):
            msg = AURCMessage(
                source="aurc:gaia/test:v1.0",
                target=f"aurc:gaia/missing-{i}:v1.0",
                type=MessageDirection.REQUEST,
            )
            await router.route(msg)
        assert len(router.dead_letter_queue) == 5
        cleared = router.clear_dead_letters()
        assert cleared == 5
        assert len(router.dead_letter_queue) == 0


class TestSessionManager:
    """Tests for the SessionManager."""

    @pytest.fixture
    def manager(self):
        return SessionManager()

    def test_create_session(self, manager):
        session = manager.create_session("aurc:gaia/orchestrator:v1.0")
        assert session.is_active
        assert session.initiator == "aurc:gaia/orchestrator:v1.0"
        assert session.turn == 0
        assert manager.session_count == 1

    def test_advance_turn(self, manager):
        session = manager.create_session("aurc:gaia/test:v1.0")
        turn = manager.advance_turn(session.session_id, "aurc:gaia/researcher:v1.0")
        assert turn == 1
        assert "aurc:gaia/researcher:v1.0" in session.participants

    def test_close_session(self, manager):
        session = manager.create_session("aurc:gaia/test:v1.0")
        manager.close_session(session.session_id)
        assert not session.is_active
        assert manager.active_count == 0

    def test_session_context(self, manager):
        session = manager.create_session("aurc:gaia/test:v1.0")
        manager.set_context(session.session_id, "query", "AI protocols")
        assert manager.get_context(session.session_id, "query") == "AI protocols"
        assert manager.get_context(session.session_id, "missing", "default") == "default"

    def test_conversation_grouping(self, manager):
        s1 = manager.create_session("aurc:gaia/a:v1.0", conversation_id="conv-123")
        s2 = manager.create_session("aurc:gaia/b:v1.0", conversation_id="conv-123")
        sessions = manager.get_conversation_sessions("conv-123")
        assert len(sessions) == 2

    def test_get_sessions_by_participant(self, manager):
        s1 = manager.create_session("aurc:gaia/a:v1.0")
        s1.add_participant("aurc:gaia/b:v1.0")
        s2 = manager.create_session("aurc:gaia/c:v1.0")

        b_sessions = manager.get_sessions_by_participant("aurc:gaia/b:v1.0")
        assert len(b_sessions) == 1
        assert b_sessions[0].session_id == s1.session_id

    def test_cleanup_stale(self, manager):
        from datetime import datetime, timezone, timedelta

        s1 = manager.create_session("aurc:gaia/test:v1.0")
        manager.close_session(s1.session_id)
        # Manually set old timestamp
        s1.last_activity = datetime.now(timezone.utc) - timedelta(hours=2)

        removed = manager.cleanup_stale(max_age_seconds=3600)
        assert removed == 1
        assert manager.session_count == 0

    def test_session_to_dict(self, manager):
        session = manager.create_session("aurc:gaia/test:v1.0")
        d = session.to_dict()
        assert d["initiator"] == "aurc:gaia/test:v1.0"
        assert d["is_active"] is True
        assert "session_id" in d

    def test_max_sessions_eviction(self):
        manager = SessionManager(max_sessions=3)
        for i in range(4):
            s = manager.create_session(f"aurc:gaia/agent-{i}:v1.0")
            manager.close_session(s.session_id)
        assert manager.session_count <= 3
