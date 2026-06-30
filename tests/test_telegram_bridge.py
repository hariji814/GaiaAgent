"""Tests for the TelegramBridge -- Telegram Bot API <-> AURC translation.

Covers the full ProtocolBridge contract (source_protocol / can_bridge /
translate_to_aurc / translate_from_aurc / map_capabilities), the conformance
invariants the rest of the bridge suite enforces (correlation propagation,
bridge_chain stamping, bidirectional round-trip), plus the TelegramSender
translate -> POST -> build-response loop with an injected fake client.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from gaiaagent.bridges import TelegramBridge, TelegramSender
from gaiaagent.bridges.base import BridgeRegistry, ProtocolBridge
from gaiaagent.bridges.telegram import TELEGRAM_PROTOCOL
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection


class TestTelegramBridgeContract:
    """ProtocolBridge contract conformance."""

    @pytest.fixture
    def bridge(self) -> TelegramBridge:
        return TelegramBridge()

    def test_source_protocol(self, bridge: TelegramBridge) -> None:
        assert bridge.source_protocol == "telegram/1.0"

    def test_can_bridge(self, bridge: TelegramBridge) -> None:
        assert bridge.can_bridge("telegram/1.0", "aurc/0.1") is True
        assert bridge.can_bridge("aurc/0.1", "telegram/1.0") is True
        assert bridge.can_bridge("mcp/2025-06-18", "aurc/0.1") is False
        assert bridge.can_bridge("telegram/1.0", "mcp/2025-06-18") is False

    def test_satisfies_protocol_bridge_protocol(self, bridge: TelegramBridge) -> None:
        # ProtocolBridge is a runtime_checkable Protocol; the bridge must
        # duck-type to it so BridgeRegistry / BridgeAuthzGuard accept it.
        assert isinstance(bridge, ProtocolBridge)

    def test_registry_accepts_telegram_bridge(self) -> None:
        registry = BridgeRegistry()
        registry.register(TelegramBridge())
        assert TELEGRAM_PROTOCOL in registry.list_protocols()
        assert registry.get_bridge(TELEGRAM_PROTOCOL) is not None
        assert registry.count == 1


class TestInboundTranslation:
    """Telegram -> AURC."""

    @pytest.fixture
    def bridge(self) -> TelegramBridge:
        return TelegramBridge()

    @pytest.mark.asyncio
    async def test_message_event_becomes_notification(self, bridge: TelegramBridge) -> None:
        update = {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "from": {"id": 100},
                "chat": {"id": 456, "type": "private"},
                "text": "hello agent",
            },
        }
        aurc = await bridge.translate_to_aurc(update)

        assert aurc.type == MessageDirection.NOTIFICATION
        assert aurc.body.event == "channel.message"
        assert aurc.body.data["text"] == "hello agent"
        assert aurc.body.data["user"] == 100
        assert aurc.body.data["chat"] == 456
        assert aurc.body.data["is_mention"] is False
        assert aurc.source == "telegram:external/100"
        assert aurc.target == "telegram:456"
        # No reply_to -> correlation falls back to the message id.
        assert aurc.correlation_id == "10"
        assert aurc.body.metadata["telegram_update_id"] == 1

    @pytest.mark.asyncio
    async def test_command_becomes_invoke_request(self, bridge: TelegramBridge) -> None:
        update = {
            "update_id": 2,
            "message": {
                "message_id": 11,
                "from": {"id": 100},
                "chat": {"id": 456, "type": "private"},
                "text": "/summarize the last 10 messages",
            },
        }
        aurc = await bridge.translate_to_aurc(update)

        assert aurc.type == MessageDirection.REQUEST
        assert aurc.body.method == "invoke"
        assert aurc.body.skill == "summarize"  # leading "/" stripped
        assert aurc.body.params["text"] == "the last 10 messages"
        assert aurc.body.params["args"] == ["the", "last", "10", "messages"]
        assert aurc.body.metadata["telegram_update_id"] == 2
        assert aurc.body.metadata["telegram_chat_type"] == "private"
        assert aurc.target == "telegram:456"

    @pytest.mark.asyncio
    async def test_group_command_with_bot_suffix(self) -> None:
        # In groups, commands are written "/cmd@MyBot" so Telegram can route
        # them to the right bot. The @-suffix must be stripped from the skill.
        bridge = TelegramBridge(bot_username="mybot")
        update = {
            "update_id": 7,
            "message": {
                "message_id": 14,
                "from": {"id": 100},
                "chat": {"id": 456, "type": "group"},
                "text": "/summarize@mybot args here",
            },
        }
        aurc = await bridge.translate_to_aurc(update)

        assert aurc.body.skill == "summarize"
        assert aurc.body.params["text"] == "args here"

    @pytest.mark.asyncio
    async def test_group_mention_is_stripped(self) -> None:
        # A leading "@bot" mention is removed from the text, but the mention
        # flag is preserved so the handler can treat it as a direct address.
        bridge = TelegramBridge(bot_username="mybot")
        update = {
            "update_id": 6,
            "message": {
                "message_id": 13,
                "from": {"id": 100},
                "chat": {"id": 456, "type": "group"},
                "text": "@mybot hello",
            },
        }
        aurc = await bridge.translate_to_aurc(update)

        assert aurc.body.event == "channel.message"
        assert aurc.body.data["text"] == "hello"
        assert aurc.body.data["is_mention"] is True

    @pytest.mark.asyncio
    async def test_callback_query_becomes_invoke_request(self, bridge: TelegramBridge) -> None:
        update = {
            "update_id": 3,
            "callback_query": {
                "id": "cq1",
                "data": "approve",
                "from": {"id": 100},
                "message": {"message_id": 20, "chat": {"id": 456, "type": "private"}},
            },
        }
        aurc = await bridge.translate_to_aurc(update)

        assert aurc.type == MessageDirection.REQUEST
        assert aurc.body.method == "invoke"
        assert aurc.body.skill == "approve"
        assert aurc.body.params["callback_query_id"] == "cq1"
        assert aurc.body.metadata["telegram_callback_query_id"] == "cq1"
        assert aurc.target == "telegram:456"

    @pytest.mark.asyncio
    async def test_edited_message_becomes_edited_notification(
        self, bridge: TelegramBridge
    ) -> None:
        update = {
            "update_id": 4,
            "edited_message": {
                "message_id": 12,
                "from": {"id": 100},
                "chat": {"id": 456, "type": "private"},
                "text": "edited",
            },
        }
        aurc = await bridge.translate_to_aurc(update)

        assert aurc.type == MessageDirection.NOTIFICATION
        assert aurc.body.event == "channel.message_edited"
        assert aurc.body.data["text"] == "edited"

    @pytest.mark.asyncio
    async def test_unknown_update_not_dropped(self, bridge: TelegramBridge) -> None:
        aurc = await bridge.translate_to_aurc({"update_id": 5, "poll": {"id": "1"}})
        assert aurc.type == MessageDirection.NOTIFICATION
        assert aurc.body.event == "channel.unknown"
        assert aurc.body.data["update_id"] == 5


class TestInboundConformance:
    """Semantic invariants every bridge must preserve."""

    @pytest.fixture
    def bridge(self) -> TelegramBridge:
        return TelegramBridge()

    @pytest.mark.asyncio
    async def test_bridge_chain_stamped(self, bridge: TelegramBridge) -> None:
        update = {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "from": {"id": 100},
                "chat": {"id": 456, "type": "private"},
                "text": "x",
            },
        }
        aurc = await bridge.translate_to_aurc(update)
        assert aurc.protocol_context.origin_protocol == "telegram/1.0"
        assert aurc.protocol_context.is_bridged
        assert aurc.protocol_context.hop_count == 1
        # The hop label must name both protocols (matches MCP/A2A/ACP/Slack).
        assert "telegram" in aurc.protocol_context.bridge_chain[0]
        assert "aurc" in aurc.protocol_context.bridge_chain[0]

    @pytest.mark.asyncio
    async def test_correlation_propagates_through_reply(self, bridge: TelegramBridge) -> None:
        # A reply points at the message it answers via reply_to_message; that
        # anchor is the natural AURC correlation unit for a Telegram thread.
        root = await bridge.translate_to_aurc(
            {
                "update_id": 1,
                "message": {
                    "message_id": 100,
                    "from": {"id": 1},
                    "chat": {"id": 456, "type": "private"},
                    "text": "root",
                },
            }
        )
        reply = await bridge.translate_to_aurc(
            {
                "update_id": 2,
                "message": {
                    "message_id": 101,
                    "from": {"id": 2},
                    "chat": {"id": 456, "type": "private"},
                    "text": "reply",
                    "reply_to_message": {"message_id": 100},
                },
            }
        )
        assert root.correlation_id == "100"
        assert reply.correlation_id == "100"  # same trace as the root

    @pytest.mark.asyncio
    async def test_inbound_is_idempotent(self, bridge: TelegramBridge) -> None:
        # Translating the same payload twice yields equivalent messages
        # (deterministic source/target/type/correlation) -- a prerequisite for
        # safe retry of a Telegram webhook delivery.
        payload = {
            "update_id": 9,
            "message": {
                "message_id": 50,
                "from": {"id": 1},
                "chat": {"id": 456, "type": "private"},
                "text": "dup",
                "reply_to_message": {"message_id": 50},
            },
        }
        a = await bridge.translate_to_aurc(payload)
        b = await bridge.translate_to_aurc(payload)
        assert a.type == b.type
        assert a.source == b.source
        assert a.target == b.target
        assert a.correlation_id == b.correlation_id
        assert a.body.data["text"] == b.body.data["text"]


class TestOutboundTranslation:
    """AURC -> Telegram."""

    @pytest.fixture
    def bridge(self) -> TelegramBridge:
        return TelegramBridge()

    @pytest.mark.asyncio
    async def test_notification_becomes_send_message(self, bridge: TelegramBridge) -> None:
        aurc = AURCMessage(
            source="aurc:local/comms-agent",
            target="telegram:456",
            type=MessageDirection.NOTIFICATION,
            correlation_id="100",
            body=MessageBody(event="channel.message", data="Here is your summary."),
        )
        payload = await bridge.translate_from_aurc(aurc)

        assert payload["method"] == "sendMessage"
        assert payload["chat_id"] == "456"
        assert payload["text"] == "Here is your summary."
        assert payload["parse_mode"] == "Markdown"
        # numeric correlation id -> threaded back onto the anchored message.
        assert payload["reply_to_message_id"] == 100

    @pytest.mark.asyncio
    async def test_response_with_result(self, bridge: TelegramBridge) -> None:
        aurc = AURCMessage(
            source="aurc:local/agent",
            target="telegram:456",
            type=MessageDirection.RESPONSE,
            correlation_id="100",
            body=MessageBody(result="done"),
        )
        payload = await bridge.translate_from_aurc(aurc)
        assert payload["method"] == "sendMessage"
        assert payload["text"] == "done"
        assert payload["reply_to_message_id"] == 100

    @pytest.mark.asyncio
    async def test_response_with_error(self, bridge: TelegramBridge) -> None:
        aurc = AURCMessage(
            source="aurc:local/agent",
            target="telegram:456",
            type=MessageDirection.RESPONSE,
            body=MessageBody(error={"code": "no_skill", "message": "unknown skill"}),  # type: ignore[arg-type]
        )
        payload = await bridge.translate_from_aurc(aurc)
        assert "no_skill" in payload["text"]
        assert "unknown skill" in payload["text"]

    @pytest.mark.asyncio
    async def test_stream_becomes_edit_message_text(self, bridge: TelegramBridge) -> None:
        aurc = AURCMessage(
            source="aurc:local/agent",
            target="telegram:456",
            type=MessageDirection.STREAM,
            correlation_id="100",
            body=MessageBody(data="partial chunk", chunk_index=1, is_final=False),
        )
        payload = await bridge.translate_from_aurc(aurc)
        assert payload["method"] == "editMessageText"
        assert payload["message_id"] == "100"
        assert payload["text"] == "partial chunk"

    @pytest.mark.asyncio
    async def test_non_numeric_correlation_not_threaded(self, bridge: TelegramBridge) -> None:
        # A non-numeric correlation id must NOT set reply_to_message_id --
        # Telegram would reject a non-integer there.
        aurc = AURCMessage(
            source="aurc:local/agent",
            target="telegram:456",
            type=MessageDirection.NOTIFICATION,
            correlation_id="abc-not-numeric",
            body=MessageBody(event="channel.message", data="hi"),
        )
        payload = await bridge.translate_from_aurc(aurc)
        assert "reply_to_message_id" not in payload

    @pytest.mark.asyncio
    async def test_chat_id_from_external_target(self, bridge: TelegramBridge) -> None:
        aurc = AURCMessage(
            source="aurc:local/agent",
            target="telegram:external/456",
            type=MessageDirection.NOTIFICATION,
            body=MessageBody(event="channel.message", data="hi"),
        )
        payload = await bridge.translate_from_aurc(aurc)
        assert payload["chat_id"] == "456"


class TestRoundTrip:
    """Bidirectional round-trip preserves the chat identity and correlation."""

    @pytest.fixture
    def bridge(self) -> TelegramBridge:
        return TelegramBridge()

    @pytest.mark.asyncio
    async def test_message_round_trip_preserves_chat_and_reply(
        self, bridge: TelegramBridge
    ) -> None:
        inbound = {
            "update_id": 1,
            "message": {
                "message_id": 100,
                "from": {"id": 100},
                "chat": {"id": 456, "type": "private"},
                "text": "ping",
                "reply_to_message": {"message_id": 100},
            },
        }
        aurc = await bridge.translate_to_aurc(inbound)

        # Agent produces a notification back to the same chat/reply anchor.
        reply = AURCMessage(
            source="aurc:local/agent",
            target=aurc.target,  # telegram:456
            type=MessageDirection.NOTIFICATION,
            correlation_id=aurc.correlation_id,  # 100
            body=MessageBody(event="channel.message", data="pong"),
        )
        outbound = await bridge.translate_from_aurc(reply)

        assert outbound["chat_id"] == "456"
        assert outbound["reply_to_message_id"] == 100
        assert outbound["text"] == "pong"


class TestCapabilityMapping:
    """Telegram BotCommands -> AURC skill declarations."""

    @pytest.fixture
    def bridge(self) -> TelegramBridge:
        return TelegramBridge()

    @pytest.mark.asyncio
    async def test_bot_commands_mapped_to_skills(self, bridge: TelegramBridge) -> None:
        commands = [
            {"command": "/summarize", "description": "Summarize a chat"},
            {"command": "workflow", "description": "Run a workflow"},
        ]
        skills = await bridge.map_capabilities(commands)

        assert len(skills) == 2
        assert skills[0]["skill_id"] == "telegram:summarize"
        assert skills[0]["name"] == "summarize"
        assert skills[0]["description"] == "Summarize a chat"
        assert skills[0]["tags"] == ["telegram-bridge"]
        assert skills[0]["input_schema"]["properties"]["text"]["description"] == "command arguments"
        assert skills[1]["skill_id"] == "telegram:workflow"

    @pytest.mark.asyncio
    async def test_empty_capabilities(self, bridge: TelegramBridge) -> None:
        assert await bridge.map_capabilities([]) == []

    @pytest.mark.asyncio
    async def test_skips_nameless_items(self, bridge: TelegramBridge) -> None:
        skills = await bridge.map_capabilities([{"description": "no name"}])
        assert skills == []


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"Telegram API returned HTTP {self.status_code}")

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


class TestTelegramSender:
    """Translate -> POST -> build-response loop (no network)."""

    def _notification(self) -> AURCMessage:
        return AURCMessage(
            source="aurc:local/comms-agent",
            target="telegram:456",
            type=MessageDirection.NOTIFICATION,
            correlation_id="100",
            body=MessageBody(event="channel.message", data="Hello from AURC."),
        )

    @pytest.mark.asyncio
    async def test_forward_success_round_trip(self) -> None:
        fake = _FakeClient(
            response=_FakeResponse(
                200,
                {"ok": True, "result": {"message_id": 999, "chat": {"id": 456}, "text": "Hello"}},
            )
        )
        sender = TelegramSender(token="123:ABC", client_factory=lambda: fake)

        response = await sender.forward(self._notification())

        # Posted to the sendMessage endpoint with the bot token in the URL path.
        assert fake.posted_url == "https://api.telegram.org/bot123:ABC/sendMessage"
        assert fake.posted_headers is not None
        assert fake.posted_headers["Content-Type"] == "application/json; charset=utf-8"
        assert fake.posted_body["chat_id"] == "456"
        assert fake.posted_body["text"] == "Hello from AURC."
        assert fake.posted_body["reply_to_message_id"] == 100

        # Response is a well-formed AURC RESPONSE carrying the Telegram result.
        assert response.type == MessageDirection.RESPONSE
        assert response.target == "aurc:local/comms-agent"
        assert response.body.result["message_id"] == 999
        assert response.correlation_id == "100"

    @pytest.mark.asyncio
    async def test_forward_telegram_ok_false_becomes_error(self) -> None:
        fake = _FakeClient(
            response=_FakeResponse(
                200, {"ok": False, "error_code": 400, "description": "Bad Request: chat not found"}
            )
        )
        sender = TelegramSender(token="123:ABC", client_factory=lambda: fake)

        response = await sender.forward(self._notification())

        assert response.type == MessageDirection.RESPONSE
        assert response.body.error is not None
        assert response.body.error.code == "telegram_error"
        assert response.body.error.message == "Bad Request: chat not found"

    @pytest.mark.asyncio
    async def test_forward_http_error_becomes_recoverable_error(self) -> None:
        fake = _FakeClient(response=_FakeResponse(500, {"ok": False}))
        sender = TelegramSender(token="123:ABC", client_factory=lambda: fake)

        response = await sender.forward(self._notification())

        assert response.body.error is not None
        assert response.body.error.code == "transport_error"
        assert response.body.error.recoverable is True

    @pytest.mark.asyncio
    async def test_forward_network_exception_becomes_recoverable_error(self) -> None:
        fake = _FakeClient(error=ConnectionError("dns failure"))
        sender = TelegramSender(token="123:ABC", client_factory=lambda: fake)

        response = await sender.forward(self._notification())

        assert response.body.error is not None
        assert response.body.error.code == "transport_error"
        assert "dns failure" in response.body.error.message

    @pytest.mark.asyncio
    async def test_sender_registered_as_router_forwarder(self) -> None:
        # End-to-end wiring: a router with a TelegramSender forwarder routes a
        # telegram: target through the sender and returns its response.
        from gaiaagent.bus.router import MessageRouter

        fake = _FakeClient(
            response=_FakeResponse(200, {"ok": True, "result": {"message_id": 1}})
        )
        sender = TelegramSender(token="123:ABC", client_factory=lambda: fake)
        router = MessageRouter()
        router.register_bridge_forwarder("telegram", sender.forward)

        result = await router.route(self._notification())

        assert isinstance(result, AURCMessage)
        assert result.type == MessageDirection.RESPONSE
        assert result.body.result["message_id"] == 1
        assert fake.posted_url == "https://api.telegram.org/bot123:ABC/sendMessage"
