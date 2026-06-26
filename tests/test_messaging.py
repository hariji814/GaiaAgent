"""Tests for AURC messaging — message creation, responses, and streaming."""


from gaiaagent.core.message import (
    AURCMessage,
    BridgeContext,
    DelegationHop,
    ErrorInfo,
    MessageBody,
    MessageSecurity,
)
from gaiaagent.core.types import MessageDirection


class TestBridgeContext:
    """Tests for protocol bridge context tracking."""

    def test_not_bridged(self):
        ctx = BridgeContext()
        assert not ctx.is_bridged
        assert ctx.hop_count == 0

    def test_bridged(self):
        ctx = BridgeContext(
            origin_protocol="mcp/2025-06-18",
            bridged_from="mcp/2025-06-18",
            bridge_chain=["mcp→aurc"],
        )
        assert ctx.is_bridged
        assert ctx.hop_count == 1

    def test_add_hop(self):
        ctx = BridgeContext(origin_protocol="a2a/1.0")
        ctx2 = ctx.add_hop("a2a/1.0", "aurc/0.1")
        ctx3 = ctx2.add_hop("aurc/0.1", "mcp/2025-06-18")
        assert ctx3.hop_count == 2
        assert ctx3.bridge_chain == ["a2a/1.0→aurc/0.1", "aurc/0.1→mcp/2025-06-18"]


class TestDelegationChain:
    """Tests for delegation chain validation."""

    def test_valid_narrowing_chain(self):
        security = MessageSecurity(
            scopes=["read", "write"],
            delegation_chain=[
                DelegationHop(
                    from_agent="aurc:user/alice:v1.0",
                    to_agent="aurc:gaia/orchestrator:v1.0",
                    scopes=["read", "write", "admin"],
                ),
                DelegationHop(
                    from_agent="aurc:gaia/orchestrator:v1.0",
                    to_agent="aurc:gaia/researcher:v1.0",
                    scopes=["read", "write"],  # Narrowed — valid
                ),
                DelegationHop(
                    from_agent="aurc:gaia/researcher:v1.0",
                    to_agent="aurc:gaia/web-search:v1.0",
                    scopes=["read"],  # Further narrowed — valid
                ),
            ],
        )
        assert security.validate_delegation_chain() is True

    def test_invalid_widening_chain(self):
        security = MessageSecurity(
            delegation_chain=[
                DelegationHop(
                    from_agent="aurc:user/alice:v1.0",
                    to_agent="aurc:gaia/orchestrator:v1.0",
                    scopes=["read"],
                ),
                DelegationHop(
                    from_agent="aurc:gaia/orchestrator:v1.0",
                    to_agent="aurc:gaia/researcher:v1.0",
                    scopes=["read", "write"],  # Widened — invalid!
                ),
            ],
        )
        assert security.validate_delegation_chain() is False

    def test_single_hop_always_valid(self):
        security = MessageSecurity(
            delegation_chain=[
                DelegationHop(
                    from_agent="aurc:user/alice:v1.0",
                    to_agent="aurc:gaia/orchestrator:v1.0",
                    scopes=["read", "write", "admin"],
                ),
            ],
        )
        assert security.validate_delegation_chain() is True


class TestAURCMessage:
    """Tests for AURC message creation and manipulation."""

    def _make_request(self) -> AURCMessage:
        return AURCMessage(
            source="aurc:gaia/orchestrator:v1.0",
            target="aurc:gaia/researcher:v1.0",
            type=MessageDirection.REQUEST,
            body=MessageBody(
                method="invoke",
                skill="deep-research",
                params={"query": "AI protocols", "depth": "deep"},
            ),
        )

    def test_create_request(self):
        msg = self._make_request()
        assert msg.type == MessageDirection.REQUEST
        assert msg.body.method == "invoke"
        assert msg.body.skill == "deep-research"
        assert msg.body.params["query"] == "AI protocols"
        assert msg.aurc_version == "0.1"

    def test_create_response(self):
        request = self._make_request()
        response = request.create_response(result={"report": "AI protocols report..."})
        assert response.type == MessageDirection.RESPONSE
        assert response.source == request.target
        assert response.target == request.source
        assert response.body.result == {"report": "AI protocols report..."}
        assert response.body.error is None
        assert response.correlation_id is not None

    def test_create_error_response(self):
        request = self._make_request()
        error = ErrorInfo(code="tool_not_found", message="Web search tool unavailable")
        response = request.create_response(error=error)
        assert response.type == MessageDirection.RESPONSE
        assert response.body.error is not None
        assert response.body.error.code == "tool_not_found"

    def test_create_stream_chunk(self):
        request = self._make_request()
        chunk = request.create_stream_chunk(
            data="Partial result text...",
            chunk_index=0,
            total_chunks=5,
            is_final=False,
        )
        assert chunk.type == MessageDirection.STREAM
        assert chunk.body.chunk_index == 0
        assert chunk.body.total_chunks == 5
        assert chunk.body.is_final is False

    def test_create_notification(self):
        msg = AURCMessage(
            source="aurc:gaia/researcher:v1.0",
            target="aurc:gaia/orchestrator:v1.0",
            type=MessageDirection.NOTIFICATION,
        )
        notification = msg.create_notification("task_progress", {"percent": 50})
        assert notification.type == MessageDirection.NOTIFICATION
        assert notification.body.event == "task_progress"
        assert notification.body.data == {"percent": 50}

    def test_session_tracking(self):
        msg = self._make_request()
        assert msg.session.session_id.startswith("session-")
        response = msg.create_response(result="ok")
        assert response.session.session_id == msg.session.session_id
        assert response.session.turn == msg.session.turn + 1

    def test_message_serialization(self):
        msg = self._make_request()
        data = msg.model_dump()
        assert data["source"] == "aurc:gaia/orchestrator:v1.0"
        assert data["type"] == "request"

        # Can deserialize back
        restored = AURCMessage(**data)
        assert restored.source == msg.source
        assert restored.body.skill == "deep-research"
