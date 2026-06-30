"""Tests for the SlackBridge -- Slack Platform <-> AURC translation.

Covers the full ProtocolBridge contract (source_protocol / can_bridge /
translate_to_aurc / translate_from_aurc / map_capabilities), the conformance
invariants the rest of the bridge suite enforces (correlation propagation,
bridge_chain stamping, bidirectional round-trip), plus the SlackSender
translate -> POST -> build-response loop with an injected fake client.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from gaiaagent.bridges import SlackBridge, SlackSender
from gaiaagent.bridges.base import BridgeRegistry
from gaiaagent.bridges.slack import SLACK_PROTOCOL, _render_blocks
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection


class TestSlackBridgeContract:
    """ProtocolBridge contract conformance."""

    @pytest.fixture
    def bridge(self) -> SlackBridge:
        return SlackBridge()

    def test_source_protocol(self, bridge: SlackBridge) -> None:
        assert bridge.source_protocol == "slack/1.0"

    def test_can_bridge(self, bridge: SlackBridge) -> None:
        assert bridge.can_bridge("slack/1.0", "aurc/0.1") is True
        assert bridge.can_bridge("aurc/0.1", "slack/1.0") is True
        assert bridge.can_bridge("mcp/2025-06-18", "aurc/0.1") is False
        assert bridge.can_bridge("slack/1.0", "mcp/2025-06-18") is False

    def test_satisfies_protocol_bridge_protocol(self, bridge: SlackBridge) -> None:
        # ProtocolBridge is a runtime_checkable Protocol; the bridge must duck-type
        # to it so BridgeRegistry / BridgeAuthzGuard accept it.
        from gaiaagent.bridges.base import ProtocolBridge

        assert isinstance(bridge, ProtocolBridge)

    def test_registry_accepts_slack_bridge(self) -> None:
        registry = BridgeRegistry()
        registry.register(SlackBridge())
        assert SLACK_PROTOCOL in registry.list_protocols()
        assert registry.get_bridge(SLACK_PROTOCOL) is not None
        assert registry.count == 1


class TestInboundTranslation:
    """Slack -> AURC."""

    @pytest.fixture
    def bridge(self) -> SlackBridge:
        return SlackBridge()

    @pytest.mark.asyncio
    async def test_message_event_becomes_notification(self, bridge: SlackBridge) -> None:
        event = {
            "type": "event_callback",
            "team_id": "T0001",
            "event": {
                "type": "message",
                "user": "U123",
                "channel": "C456",
                "text": "hello agent",
                "ts": "1690000000.000200",
                "channel_type": "im",
            },
        }
        aurc = await bridge.translate_to_aurc(event)

        assert aurc.type == MessageDirection.NOTIFICATION
        assert aurc.body.event == "channel.message"
        assert aurc.body.data["text"] == "hello agent"
        assert aurc.body.data["user"] == "U123"
        assert aurc.body.data["channel"] == "C456"
        assert aurc.body.data["is_mention"] is False
        assert aurc.source == "slack:external/U123"
        assert aurc.target == "slack:C456"
        # correlation falls back to the message ts when there is no thread.
        assert aurc.correlation_id == "1690000000.000200"
        assert aurc.body.metadata["slack_team_id"] == "T0001"

    @pytest.mark.asyncio
    async def test_app_mention_marks_mention_and_threads(self, bridge: SlackBridge) -> None:
        event = {
            "type": "event_callback",
            "event": {
                "type": "app_mention",
                "user": "U123",
                "channel": "C456",
                "text": "<@U999> summarize this",
                "ts": "1690000001.000300",
                "thread_ts": "1690000000.000200",
            },
        }
        aurc = await bridge.translate_to_aurc(event)

        assert aurc.body.data["is_mention"] is True
        # thread_ts wins over ts for correlation so a whole thread is one trace.
        assert aurc.correlation_id == "1690000000.000200"
        assert aurc.body.data["thread_ts"] == "1690000000.000200"

    @pytest.mark.asyncio
    async def test_bare_event_dict_accepted(self, bridge: SlackBridge) -> None:
        # Callers may pass the inner event directly (no event_callback envelope).
        aurc = await bridge.translate_to_aurc(
            {"type": "message", "user": "U1", "channel": "C1", "text": "hi", "ts": "1.1"}
        )
        assert aurc.body.event == "channel.message"
        assert aurc.correlation_id == "1.1"

    @pytest.mark.asyncio
    async def test_slash_command_becomes_invoke_request(self, bridge: SlackBridge) -> None:
        payload = {
            "type": "slash_command",
            "command": "/summarize",
            "text": "the last 10 messages",
            "user_id": "U123",
            "channel_id": "C456",
            "trigger_id": "T.trigger",
            "response_url": "https://hooks.slack.com/commands/X",
        }
        aurc = await bridge.translate_to_aurc(payload)

        assert aurc.type == MessageDirection.REQUEST
        assert aurc.body.method == "invoke"
        assert aurc.body.skill == "summarize"  # leading "/" stripped
        assert aurc.body.params["text"] == "the last 10 messages"
        assert aurc.body.params["args"] == ["the", "last", "10", "messages"]
        assert aurc.body.metadata["slack_command"] == "/summarize"
        assert aurc.target == "slack:C456"

    @pytest.mark.asyncio
    async def test_interactive_payload_becomes_invoke_request(self, bridge: SlackBridge) -> None:
        payload = {
            "type": "interactive",
            "actions": [{"action_id": "approve_report", "value": "report-42"}],
            "user": {"id": "U123"},
            "channel": {"id": "C456"},
            "trigger_id": "T.trigger",
        }
        aurc = await bridge.translate_to_aurc(payload)

        assert aurc.type == MessageDirection.REQUEST
        assert aurc.body.method == "invoke"
        assert aurc.body.skill == "approve_report"
        assert aurc.body.params["value"] == "report-42"

    @pytest.mark.asyncio
    async def test_url_verification_handshake(self, bridge: SlackBridge) -> None:
        aurc = await bridge.translate_to_aurc(
            {"type": "url_verification", "challenge": "abc-challenge"}
        )
        assert aurc.type == MessageDirection.REQUEST
        assert aurc.body.method == "url_verify"
        assert aurc.body.params["challenge"] == "abc-challenge"

    @pytest.mark.asyncio
    async def test_unknown_event_not_dropped(self, bridge: SlackBridge) -> None:
        aurc = await bridge.translate_to_aurc({"type": "team_join", "user": {"id": "U1"}})
        assert aurc.type == MessageDirection.NOTIFICATION
        assert aurc.body.event == "channel.unknown"
        assert aurc.body.data["type"] == "team_join"


class TestInboundConformance:
    """Semantic invariants every bridge must preserve."""

    @pytest.fixture
    def bridge(self) -> SlackBridge:
        return SlackBridge()

    @pytest.mark.asyncio
    async def test_bridge_chain_stamped(self, bridge: SlackBridge) -> None:
        aurc = await bridge.translate_to_aurc(
            {"type": "message", "user": "U1", "channel": "C1", "text": "x", "ts": "1.1"}
        )
        assert aurc.protocol_context.origin_protocol == "slack/1.0"
        assert aurc.protocol_context.is_bridged
        assert aurc.protocol_context.hop_count == 1
        # The hop label must name both protocols (matches the MCP/A2A/ACP shape).
        assert "slack" in aurc.protocol_context.bridge_chain[0]
        assert "aurc" in aurc.protocol_context.bridge_chain[0]

    @pytest.mark.asyncio
    async def test_correlation_propagates_through_thread(self, bridge: SlackBridge) -> None:
        # All replies in a Slack thread share thread_ts -> one correlation id.
        root = await bridge.translate_to_aurc(
            {"type": "message", "user": "U1", "channel": "C1", "text": "root", "ts": "100.1"}
        )
        reply = await bridge.translate_to_aurc(
            {
                "type": "message",
                "user": "U2",
                "channel": "C1",
                "text": "reply",
                "ts": "101.1",
                "thread_ts": "100.1",
            }
        )
        assert root.correlation_id == "100.1"
        assert reply.correlation_id == "100.1"  # same trace as the root

    @pytest.mark.asyncio
    async def test_inbound_is_idempotent(self, bridge: SlackBridge) -> None:
        # Translating the same payload twice yields equivalent messages
        # (deterministic source/target/type/correlation) -- a prerequisite for
        # safe retry of a Slack event delivery.
        payload = {
            "type": "message",
            "user": "U1",
            "channel": "C1",
            "text": "dup",
            "ts": "1.1",
            "thread_ts": "1.1",
        }
        a = await bridge.translate_to_aurc(payload)
        b = await bridge.translate_to_aurc(payload)
        assert a.type == b.type
        assert a.source == b.source
        assert a.target == b.target
        assert a.correlation_id == b.correlation_id
        assert a.body.data["text"] == b.body.data["text"]


class TestOutboundTranslation:
    """AURC -> Slack."""

    @pytest.fixture
    def bridge(self) -> SlackBridge:
        return SlackBridge()

    @pytest.mark.asyncio
    async def test_notification_becomes_post_message(self, bridge: SlackBridge) -> None:
        aurc = AURCMessage(
            source="aurc:local/comms-agent",
            target="slack:C456",
            type=MessageDirection.NOTIFICATION,
            correlation_id="1690000000.000200",
            body=MessageBody(event="channel.message", data="Here is your summary."),
        )
        payload = await bridge.translate_from_aurc(aurc)

        assert payload["method"] == "chat.postMessage"
        assert payload["channel"] == "C456"
        assert payload["text"] == "Here is your summary."
        assert payload["blocks"] == _render_blocks("Here is your summary.")
        # correlation id is a Slack ts -> threaded back into the original thread.
        assert payload["thread_ts"] == "1690000000.000200"

    @pytest.mark.asyncio
    async def test_response_with_result(self, bridge: SlackBridge) -> None:
        aurc = AURCMessage(
            source="aurc:local/agent",
            target="slack:C456",
            type=MessageDirection.RESPONSE,
            correlation_id="1690000000.000200",
            body=MessageBody(result="done"),
        )
        payload = await bridge.translate_from_aurc(aurc)
        assert payload["method"] == "chat.postMessage"
        assert payload["text"] == "done"
        assert payload["thread_ts"] == "1690000000.000200"

    @pytest.mark.asyncio
    async def test_response_with_error(self, bridge: SlackBridge) -> None:
        aurc = AURCMessage(
            source="aurc:local/agent",
            target="slack:C456",
            type=MessageDirection.RESPONSE,
            body=MessageBody(error={"code": "no_skill", "message": "unknown skill"}),  # type: ignore[arg-type]
        )
        payload = await bridge.translate_from_aurc(aurc)
        assert "no_skill" in payload["text"]
        assert "unknown skill" in payload["text"]

    @pytest.mark.asyncio
    async def test_stream_becomes_chat_update(self, bridge: SlackBridge) -> None:
        aurc = AURCMessage(
            source="aurc:local/agent",
            target="slack:C456",
            type=MessageDirection.STREAM,
            correlation_id="1690000000.000200",
            body=MessageBody(data="partial chunk", chunk_index=1, is_final=False),
        )
        payload = await bridge.translate_from_aurc(aurc)
        assert payload["method"] == "chat.update"
        assert payload["ts"] == "1690000000.000200"
        assert payload["text"] == "partial chunk"

    @pytest.mark.asyncio
    async def test_non_ts_correlation_not_threaded(self, bridge: SlackBridge) -> None:
        # A non-numeric correlation id (e.g. a slash-command response_url) must
        # NOT be threaded -- Slack would reject a non-ts thread_ts.
        aurc = AURCMessage(
            source="aurc:local/agent",
            target="slack:C456",
            type=MessageDirection.NOTIFICATION,
            correlation_id="https://hooks.slack.com/commands/X",
            body=MessageBody(event="channel.message", data="hi"),
        )
        payload = await bridge.translate_from_aurc(aurc)
        assert "thread_ts" not in payload

    @pytest.mark.asyncio
    async def test_channel_from_external_target(self, bridge: SlackBridge) -> None:
        aurc = AURCMessage(
            source="aurc:local/agent",
            target="slack:external/C456",
            type=MessageDirection.NOTIFICATION,
            body=MessageBody(event="channel.message", data="hi"),
        )
        payload = await bridge.translate_from_aurc(aurc)
        assert payload["channel"] == "C456"


class TestRoundTrip:
    """Bidirectional round-trip preserves the channel identity and correlation."""

    @pytest.fixture
    def bridge(self) -> SlackBridge:
        return SlackBridge()

    @pytest.mark.asyncio
    async def test_message_round_trip_preserves_channel_and_thread(
        self, bridge: SlackBridge
    ) -> None:
        inbound = {
            "type": "message",
            "user": "U123",
            "channel": "C456",
            "text": "ping",
            "ts": "1690000000.000200",
            "thread_ts": "1690000000.000200",
        }
        aurc = await bridge.translate_to_aurc(inbound)

        # Agent produces a notification back to the same channel/thread.
        reply = AURCMessage(
            source="aurc:local/agent",
            target=aurc.target,  # slack:C456
            type=MessageDirection.NOTIFICATION,
            correlation_id=aurc.correlation_id,  # 1690000000.000200
            body=MessageBody(event="channel.message", data="pong"),
        )
        outbound = await bridge.translate_from_aurc(reply)

        assert outbound["channel"] == "C456"
        assert outbound["thread_ts"] == "1690000000.000200"
        assert outbound["text"] == "pong"


class TestCapabilityMapping:
    """Slack slash commands -> AURC skill declarations."""

    @pytest.fixture
    def bridge(self) -> SlackBridge:
        return SlackBridge()

    @pytest.mark.asyncio
    async def test_slash_commands_mapped_to_skills(self, bridge: SlackBridge) -> None:
        commands = [
            {
                "command": "/summarize",
                "description": "Summarize a channel",
                "usage_hint": "[channel] [count]",
            },
            {"command": "/workflow", "description": "Run a workflow"},
        ]
        skills = await bridge.map_capabilities(commands)

        assert len(skills) == 2
        assert skills[0]["skill_id"] == "slack:summarize"
        assert skills[0]["name"] == "summarize"
        assert skills[0]["description"] == "Summarize a channel"
        assert skills[0]["tags"] == ["slack-bridge"]
        assert skills[0]["input_schema"]["properties"]["text"]["description"] == "[channel] [count]"
        assert skills[1]["skill_id"] == "slack:workflow"

    @pytest.mark.asyncio
    async def test_empty_capabilities(self, bridge: SlackBridge) -> None:
        assert await bridge.map_capabilities([]) == []

    @pytest.mark.asyncio
    async def test_skips_nameless_items(self, bridge: SlackBridge) -> None:
        skills = await bridge.map_capabilities([{"description": "no name"}])
        assert skills == []


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"Slack API returned HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    def __init__(self, response: _FakeResponse | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.posted_url: str | None = None
        self.posted_body: dict[str, Any] | None = None
        self.posted_headers: dict[str, str] | None = None

    async def post(self, url: str, content: bytes, headers: dict[str, str]) -> _FakeResponse:
        self.posted_url = url
        self.posted_body = json.loads(content)
        self.posted_headers = headers
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


class TestSlackSender:
    """Translate -> POST -> build-response loop (no network)."""

    def _notification(self) -> AURCMessage:
        return AURCMessage(
            source="aurc:local/comms-agent",
            target="slack:C456",
            type=MessageDirection.NOTIFICATION,
            correlation_id="1690000000.000200",
            body=MessageBody(event="channel.message", data="Hello from AURC."),
        )

    @pytest.mark.asyncio
    async def test_forward_success_round_trip(self) -> None:
        fake = _FakeClient(
            response=_FakeResponse(200, {"ok": True, "channel": "C456", "ts": "999.0"})
        )
        sender = SlackSender(token="xoxb-test", client_factory=lambda: fake)

        response = await sender.forward(self._notification())

        # Posted to the chat.postMessage endpoint with the bearer token.
        assert fake.posted_url == "https://slack.com/api/chat.postMessage"
        assert fake.posted_headers is not None
        assert fake.posted_headers["Authorization"] == "Bearer xoxb-test"
        assert fake.posted_body["channel"] == "C456"
        assert fake.posted_body["text"] == "Hello from AURC."
        assert fake.posted_body["thread_ts"] == "1690000000.000200"

        # Response is a well-formed AURC RESPONSE carrying the Slack result.
        assert response.type == MessageDirection.RESPONSE
        assert response.target == "aurc:local/comms-agent"
        assert response.body.result["channel"] == "C456"
        assert response.body.result["ts"] == "999.0"
        assert response.correlation_id == "1690000000.000200"

    @pytest.mark.asyncio
    async def test_forward_slack_ok_false_becomes_error(self) -> None:
        fake = _FakeClient(response=_FakeResponse(200, {"ok": False, "error": "channel_not_found"}))
        sender = SlackSender(token="xoxb-test", client_factory=lambda: fake)

        response = await sender.forward(self._notification())

        assert response.type == MessageDirection.RESPONSE
        assert response.body.error is not None
        assert response.body.error.code == "slack_error"
        assert response.body.error.message == "channel_not_found"

    @pytest.mark.asyncio
    async def test_forward_http_error_becomes_recoverable_error(self) -> None:
        fake = _FakeClient(response=_FakeResponse(500, {"ok": False}))
        sender = SlackSender(token="xoxb-test", client_factory=lambda: fake)

        response = await sender.forward(self._notification())

        assert response.body.error is not None
        assert response.body.error.code == "transport_error"
        assert response.body.error.recoverable is True

    @pytest.mark.asyncio
    async def test_forward_network_exception_becomes_recoverable_error(self) -> None:
        fake = _FakeClient(error=ConnectionError("dns failure"))
        sender = SlackSender(token="xoxb-test", client_factory=lambda: fake)

        response = await sender.forward(self._notification())

        assert response.body.error is not None
        assert response.body.error.code == "transport_error"
        assert "dns failure" in response.body.error.message

    @pytest.mark.asyncio
    async def test_sender_registered_as_router_forwarder(self) -> None:
        # End-to-end wiring: a router with a SlackSender forwarder routes a
        # slack: target through the sender and returns its response.
        from gaiaagent.bus.router import MessageRouter

        fake = _FakeClient(response=_FakeResponse(200, {"ok": True, "ts": "1.0"}))
        sender = SlackSender(token="xoxb-test", client_factory=lambda: fake)
        router = MessageRouter()
        router.register_bridge_forwarder("slack", sender.forward)

        result = await router.route(self._notification())

        assert isinstance(result, AURCMessage)
        assert result.type == MessageDirection.RESPONSE
        assert result.body.result["ts"] == "1.0"
        assert fake.posted_url == "https://slack.com/api/chat.postMessage"
