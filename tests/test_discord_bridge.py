"""Tests for the DiscordBridge -- Discord Gateway / Bot API <-> AURC translation.

Covers the full ProtocolBridge contract (source_protocol / can_bridge /
translate_to_aurc / translate_from_aurc / map_capabilities), the conformance
invariants the rest of the bridge suite enforces (correlation propagation,
bridge_chain stamping, bidirectional round-trip), plus the DiscordSender
translate -> POST/PATCH -> build-response loop with an injected fake client.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from gaiaagent.bridges import DiscordBridge, DiscordSender
from gaiaagent.bridges.base import BridgeRegistry
from gaiaagent.bridges.discord import DISCORD_PROTOCOL
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection


class TestDiscordBridgeContract:
    """ProtocolBridge contract conformance."""

    @pytest.fixture
    def bridge(self) -> DiscordBridge:
        return DiscordBridge()

    def test_source_protocol(self, bridge: DiscordBridge) -> None:
        assert bridge.source_protocol == "discord/1.0"

    def test_can_bridge(self, bridge: DiscordBridge) -> None:
        assert bridge.can_bridge("discord/1.0", "aurc/0.1") is True
        assert bridge.can_bridge("aurc/0.1", "discord/1.0") is True
        assert bridge.can_bridge("mcp/2025-06-18", "aurc/0.1") is False
        assert bridge.can_bridge("discord/1.0", "mcp/2025-06-18") is False

    def test_satisfies_protocol_bridge_protocol(self, bridge: DiscordBridge) -> None:
        # ProtocolBridge is a runtime_checkable Protocol; the bridge must
        # duck-type to it so BridgeRegistry / BridgeAuthzGuard accept it.
        from gaiaagent.bridges.base import ProtocolBridge

        assert isinstance(bridge, ProtocolBridge)

    def test_registry_accepts_discord_bridge(self) -> None:
        registry = BridgeRegistry()
        registry.register(DiscordBridge())
        assert DISCORD_PROTOCOL in registry.list_protocols()
        assert registry.get_bridge(DISCORD_PROTOCOL) is not None
        assert registry.count == 1


class TestInboundTranslation:
    """Discord -> AURC."""

    @pytest.fixture
    def bridge(self) -> DiscordBridge:
        return DiscordBridge()

    @pytest.mark.asyncio
    async def test_dm_message_becomes_notification(self, bridge: DiscordBridge) -> None:
        # A DM: no guild_id, so is_dm is True and is_mention is False.
        event = {
            "type": "MESSAGE_CREATE",
            "id": "100",
            "channel_id": "456",
            "author": {"id": "U123", "username": "alice"},
            "content": "hello agent",
        }
        aurc = await bridge.translate_to_aurc(event)

        assert aurc.type == MessageDirection.NOTIFICATION
        assert aurc.body.event == "channel.message"
        assert aurc.body.data["text"] == "hello agent"
        assert aurc.body.data["user"] == "U123"
        assert aurc.body.data["channel"] == "456"
        assert aurc.body.data["is_dm"] is True
        assert aurc.body.data["is_mention"] is False
        assert aurc.source == "discord:external/U123"
        assert aurc.target == "discord:456"
        # No message_reference -> correlation falls back to the message id.
        assert aurc.correlation_id == "100"
        assert aurc.body.metadata["discord_event"] == "MESSAGE_CREATE"

    @pytest.mark.asyncio
    async def test_guild_mention_stripped_and_flagged(self, bridge: DiscordBridge) -> None:
        event = {
            "type": "MESSAGE_CREATE",
            "id": "101",
            "channel_id": "789",
            "guild_id": "42",
            "author": {"id": "U123"},
            "content": "<@999> summarize this",
        }
        aurc = await bridge.translate_to_aurc(event)

        assert aurc.body.data["is_dm"] is False
        assert aurc.body.data["is_mention"] is True
        # The mention token is stripped so the agent gets clean text.
        assert aurc.body.data["text"] == "summarize this"
        assert aurc.body.data["guild_id"] == "42"

    @pytest.mark.asyncio
    async def test_nickname_mention_form_stripped(self, bridge: DiscordBridge) -> None:
        # Discord nickname mentions render as <@!id>.
        aurc = await bridge.translate_to_aurc(
            {
                "type": "MESSAGE_CREATE",
                "id": "1",
                "channel_id": "c",
                "guild_id": "g",
                "author": {"id": "u"},
                "content": "<@!999> hey",
            }
        )
        assert aurc.body.data["text"] == "hey"
        assert aurc.body.data["is_mention"] is True

    @pytest.mark.asyncio
    async def test_gateway_envelope_unwrapped(self, bridge: DiscordBridge) -> None:
        # A Gateway dispatch envelope {"t": "...", "d": {...}} unwraps to the
        # inner event, so callers can pass the raw gateway payload.
        event = {
            "t": "MESSAGE_CREATE",
            "d": {
                "id": "200",
                "channel_id": "456",
                "author": {"id": "U123"},
                "content": "enveloped",
            },
        }
        aurc = await bridge.translate_to_aurc(event)
        assert aurc.body.event == "channel.message"
        assert aurc.body.data["text"] == "enveloped"
        assert aurc.correlation_id == "200"

    @pytest.mark.asyncio
    async def test_bare_message_dict_accepted(self, bridge: DiscordBridge) -> None:
        # No explicit type; detected by content/author shape.
        aurc = await bridge.translate_to_aurc(
            {"id": "5", "channel_id": "c", "author": {"id": "u"}, "content": "bare"}
        )
        assert aurc.body.event == "channel.message"
        assert aurc.correlation_id == "5"

    @pytest.mark.asyncio
    async def test_message_edit_flagged(self, bridge: DiscordBridge) -> None:
        aurc = await bridge.translate_to_aurc(
            {
                "type": "MESSAGE_UPDATE",
                "id": "5",
                "channel_id": "c",
                "author": {"id": "u"},
                "content": "edited",
            }
        )
        assert aurc.body.event == "channel.message_edited"
        assert aurc.body.metadata["discord_event"] == "MESSAGE_UPDATE"

    @pytest.mark.asyncio
    async def test_slash_command_interaction_becomes_invoke(
        self, bridge: DiscordBridge
    ) -> None:
        interaction = {
            "type": "INTERACTION_CREATE",
            "id": "900",
            "token": "interaction-token",
            "channel_id": "456",
            "user": {"id": "U123", "username": "alice"},
            "data": {
                "name": "summarize",
                "options": [{"name": "topic", "value": "the last meeting"}],
            },
        }
        aurc = await bridge.translate_to_aurc(interaction)

        assert aurc.type == MessageDirection.REQUEST
        assert aurc.body.method == "invoke"
        assert aurc.body.skill == "summarize"
        assert aurc.body.params["text"] == "the last meeting"
        assert aurc.body.params["args"] == ["the", "last", "meeting"]
        assert aurc.body.metadata["discord_interaction_token"] == "interaction-token"
        assert aurc.target == "discord:456"
        assert aurc.correlation_id == "900"

    @pytest.mark.asyncio
    async def test_bare_interaction_detected(self, bridge: DiscordBridge) -> None:
        # No explicit type, but has data.name -> treated as a slash command.
        aurc = await bridge.translate_to_aurc(
            {"id": "1", "channel_id": "c", "user": {"id": "u"}, "data": {"name": "ping"}}
        )
        assert aurc.type == MessageDirection.REQUEST
        assert aurc.body.skill == "ping"

    @pytest.mark.asyncio
    async def test_interaction_member_user_resolved(self, bridge: DiscordBridge) -> None:
        # Guild interactions carry user under member.user.
        aurc = await bridge.translate_to_aurc(
            {
                "type": "INTERACTION_CREATE",
                "id": "1",
                "channel_id": "c",
                "member": {"user": {"id": "U9", "username": "bob"}},
                "data": {"name": "ping"},
            }
        )
        assert aurc.source == "discord:external/U9"

    @pytest.mark.asyncio
    async def test_reply_correlation_uses_message_reference(
        self, bridge: DiscordBridge
    ) -> None:
        aurc = await bridge.translate_to_aurc(
            {
                "type": "MESSAGE_CREATE",
                "id": "201",
                "channel_id": "c",
                "author": {"id": "u"},
                "content": "a reply",
                "message_reference": {"message_id": "200"},
            }
        )
        # The referenced (replied-to) message id is the correlation anchor.
        assert aurc.correlation_id == "200"
        assert aurc.body.data["referenced_message_id"] == "200"

    @pytest.mark.asyncio
    async def test_unknown_event_not_dropped(self, bridge: DiscordBridge) -> None:
        aurc = await bridge.translate_to_aurc({"type": "GUILD_MEMBER_ADD", "user": {}})
        assert aurc.type == MessageDirection.NOTIFICATION
        assert aurc.body.event == "channel.unknown"
        assert aurc.body.data["type"] == "GUILD_MEMBER_ADD"


class TestInboundConformance:
    """Semantic invariants every bridge must preserve."""

    @pytest.fixture
    def bridge(self) -> DiscordBridge:
        return DiscordBridge()

    @pytest.mark.asyncio
    async def test_bridge_chain_stamped(self, bridge: DiscordBridge) -> None:
        aurc = await bridge.translate_to_aurc(
            {"id": "1", "channel_id": "c", "author": {"id": "u"}, "content": "x"}
        )
        assert aurc.protocol_context.origin_protocol == "discord/1.0"
        assert aurc.protocol_context.is_bridged
        assert aurc.protocol_context.hop_count == 1
        # The hop label must name both protocols (matches the MCP/A2A/ACP shape).
        assert "discord" in aurc.protocol_context.bridge_chain[0]
        assert "aurc" in aurc.protocol_context.bridge_chain[0]

    @pytest.mark.asyncio
    async def test_correlation_propagates_through_reply(
        self, bridge: DiscordBridge
    ) -> None:
        # A root message and its reply both anchor to the root id -> one trace.
        root = await bridge.translate_to_aurc(
            {"id": "200", "channel_id": "c", "author": {"id": "u"}, "content": "root"}
        )
        reply = await bridge.translate_to_aurc(
            {
                "id": "201",
                "channel_id": "c",
                "author": {"id": "u2"},
                "content": "reply",
                "message_reference": {"message_id": "200"},
            }
        )
        assert root.correlation_id == "200"
        assert reply.correlation_id == "200"  # same trace as the root

    @pytest.mark.asyncio
    async def test_inbound_is_idempotent(self, bridge: DiscordBridge) -> None:
        # Translating the same payload twice yields equivalent messages
        # (deterministic source/target/type/correlation) -- a prerequisite for
        # safe retry of a Discord event delivery.
        payload = {
            "type": "MESSAGE_CREATE",
            "id": "5",
            "channel_id": "c",
            "author": {"id": "u"},
            "content": "dup",
        }
        a = await bridge.translate_to_aurc(payload)
        b = await bridge.translate_to_aurc(payload)
        assert a.type == b.type
        assert a.source == b.source
        assert a.target == b.target
        assert a.correlation_id == b.correlation_id
        assert a.body.data["text"] == b.body.data["text"]


class TestOutboundTranslation:
    """AURC -> Discord."""

    @pytest.fixture
    def bridge(self) -> DiscordBridge:
        return DiscordBridge()

    @pytest.mark.asyncio
    async def test_notification_becomes_create_message(self, bridge: DiscordBridge) -> None:
        aurc = AURCMessage(
            source="aurc:local/comms-agent",
            target="discord:456",
            type=MessageDirection.NOTIFICATION,
            correlation_id="200",
            body=MessageBody(event="channel.message", data="Here is your summary."),
        )
        payload = await bridge.translate_from_aurc(aurc)

        assert payload["method"] == "createMessage"
        assert payload["channel_id"] == "456"
        assert payload["content"] == "Here is your summary."
        # correlation id is a numeric Discord message id -> threaded reply.
        assert payload["message_reference"] == {"message_id": "200"}

    @pytest.mark.asyncio
    async def test_response_with_result(self, bridge: DiscordBridge) -> None:
        aurc = AURCMessage(
            source="aurc:local/agent",
            target="discord:456",
            type=MessageDirection.RESPONSE,
            correlation_id="200",
            body=MessageBody(result="done"),
        )
        payload = await bridge.translate_from_aurc(aurc)
        assert payload["method"] == "createMessage"
        assert payload["content"] == "done"
        assert payload["message_reference"] == {"message_id": "200"}

    @pytest.mark.asyncio
    async def test_response_with_error(self, bridge: DiscordBridge) -> None:
        aurc = AURCMessage(
            source="aurc:local/agent",
            target="discord:456",
            type=MessageDirection.RESPONSE,
            body=MessageBody(error={"code": "no_skill", "message": "unknown skill"}),  # type: ignore[arg-type]
        )
        payload = await bridge.translate_from_aurc(aurc)
        assert "no_skill" in payload["content"]
        assert "unknown skill" in payload["content"]

    @pytest.mark.asyncio
    async def test_stream_becomes_edit_message(self, bridge: DiscordBridge) -> None:
        aurc = AURCMessage(
            source="aurc:local/agent",
            target="discord:456",
            type=MessageDirection.STREAM,
            correlation_id="200",
            body=MessageBody(data="partial chunk", chunk_index=1, is_final=False),
        )
        payload = await bridge.translate_from_aurc(aurc)
        assert payload["method"] == "editMessage"
        assert payload["message_id"] == "200"
        assert payload["channel_id"] == "456"
        assert payload["content"] == "partial chunk"
        # Edits carry no message_reference (they target the message directly).
        assert "message_reference" not in payload

    @pytest.mark.asyncio
    async def test_non_numeric_correlation_not_threaded(self, bridge: DiscordBridge) -> None:
        # A non-numeric correlation id must NOT be threaded -- Discord would
        # reject a non-snowflake message_reference.
        aurc = AURCMessage(
            source="aurc:local/agent",
            target="discord:456",
            type=MessageDirection.NOTIFICATION,
            correlation_id="not-a-snowflake",
            body=MessageBody(event="channel.message", data="hi"),
        )
        payload = await bridge.translate_from_aurc(aurc)
        assert "message_reference" not in payload

    @pytest.mark.asyncio
    async def test_channel_from_external_target(self, bridge: DiscordBridge) -> None:
        aurc = AURCMessage(
            source="aurc:local/agent",
            target="discord:external/456",
            type=MessageDirection.NOTIFICATION,
            body=MessageBody(event="channel.message", data="hi"),
        )
        payload = await bridge.translate_from_aurc(aurc)
        assert payload["channel_id"] == "456"


class TestRoundTrip:
    """Bidirectional round-trip preserves the channel identity and correlation."""

    @pytest.fixture
    def bridge(self) -> DiscordBridge:
        return DiscordBridge()

    @pytest.mark.asyncio
    async def test_message_round_trip_preserves_channel_and_thread(
        self, bridge: DiscordBridge
    ) -> None:
        inbound = {
            "type": "MESSAGE_CREATE",
            "id": "200",
            "channel_id": "456",
            "guild_id": "42",
            "author": {"id": "U123"},
            "content": "<@999> ping",
        }
        aurc = await bridge.translate_to_aurc(inbound)

        # Agent produces a notification back to the same channel/thread.
        reply = AURCMessage(
            source="aurc:local/agent",
            target=aurc.target,  # discord:456
            type=MessageDirection.NOTIFICATION,
            correlation_id=aurc.correlation_id,  # 200
            body=MessageBody(event="channel.message", data="pong"),
        )
        outbound = await bridge.translate_from_aurc(reply)

        assert outbound["channel_id"] == "456"
        assert outbound["message_reference"] == {"message_id": "200"}
        assert outbound["content"] == "pong"


class TestCapabilityMapping:
    """Discord slash commands -> AURC skill declarations."""

    @pytest.fixture
    def bridge(self) -> DiscordBridge:
        return DiscordBridge()

    @pytest.mark.asyncio
    async def test_slash_commands_mapped_to_skills(self, bridge: DiscordBridge) -> None:
        commands = [
            {
                "name": "summarize",
                "description": "Summarize a channel",
                "options": [{"name": "count", "type": 4}],
            },
            {"name": "workflow", "description": "Run a workflow"},
        ]
        skills = await bridge.map_capabilities(commands)

        assert len(skills) == 2
        assert skills[0]["skill_id"] == "discord:summarize"
        assert skills[0]["name"] == "summarize"
        assert skills[0]["description"] == "Summarize a channel"
        assert skills[0]["tags"] == ["discord-bridge"]
        assert skills[1]["skill_id"] == "discord:workflow"

    @pytest.mark.asyncio
    async def test_command_alias_field_accepted(self, bridge: DiscordBridge) -> None:
        # Some shapes use "command" instead of "name".
        skills = await bridge.map_capabilities([{"command": "/remind", "description": "d"}])
        assert skills[0]["skill_id"] == "discord:remind"
        assert skills[0]["name"] == "remind"

    @pytest.mark.asyncio
    async def test_empty_capabilities(self, bridge: DiscordBridge) -> None:
        assert await bridge.map_capabilities([]) == []

    @pytest.mark.asyncio
    async def test_skips_nameless_items(self, bridge: DiscordBridge) -> None:
        skills = await bridge.map_capabilities([{"description": "no name"}])
        assert skills == []


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"Discord API returned HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    """Supports both POST (createMessage) and PATCH (editMessage)."""

    def __init__(
        self,
        post_response: _FakeResponse | None = None,
        patch_response: _FakeResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self._post_response = post_response
        self._patch_response = patch_response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def _record(
        self, verb: str, url: str, content: bytes, headers: dict[str, str]
    ) -> _FakeResponse:
        self.calls.append(
            {"verb": verb, "url": url, "headers": headers, "body": json.loads(content)}
        )
        if self.error is not None:
            raise self.error
        if verb == "PATCH":
            assert self._patch_response is not None
            return self._patch_response
        assert self._post_response is not None
        return self._post_response

    async def post(self, url: str, content: bytes, headers: dict[str, str]) -> _FakeResponse:
        return await self._record("POST", url, content, headers)

    async def patch(self, url: str, content: bytes, headers: dict[str, str]) -> _FakeResponse:
        return await self._record("PATCH", url, content, headers)


class TestDiscordSender:
    """Translate -> POST/PATCH -> build-response loop (no network)."""

    def _notification(self) -> AURCMessage:
        return AURCMessage(
            source="aurc:local/comms-agent",
            target="discord:456",
            type=MessageDirection.NOTIFICATION,
            correlation_id="200",
            body=MessageBody(event="channel.message", data="Hello from AURC."),
        )

    def _stream(self) -> AURCMessage:
        return AURCMessage(
            source="aurc:local/agent",
            target="discord:456",
            type=MessageDirection.STREAM,
            correlation_id="200",
            body=MessageBody(data="chunk", chunk_index=0, is_final=False),
        )

    @pytest.mark.asyncio
    async def test_forward_create_success_round_trip(self) -> None:
        fake = _FakeClient(
            post_response=_FakeResponse(
                200, {"id": "999", "channel_id": "456", "content": "Hello from AURC."}
            )
        )
        sender = DiscordSender(token="MTk-test", client_factory=lambda: fake)

        response = await sender.forward(self._notification())
        call = fake.calls[0]

        # Posted to the createMessage endpoint with the bot token.
        assert call["verb"] == "POST"
        assert call["url"] == "https://discord.com/api/v10/channels/456/messages"
        assert call["headers"]["Authorization"] == "Bot MTk-test"
        assert call["body"]["content"] == "Hello from AURC."
        # The reply is threaded back onto the originating message.
        assert call["body"]["message_reference"] == {"message_id": "200"}

        # Response is a well-formed AURC RESPONSE carrying the Discord result.
        assert response.type == MessageDirection.RESPONSE
        assert response.target == "aurc:local/comms-agent"
        assert response.body.result["id"] == "999"
        assert response.correlation_id == "200"

    @pytest.mark.asyncio
    async def test_forward_edit_uses_patch(self) -> None:
        fake = _FakeClient(
            patch_response=_FakeResponse(
                200, {"id": "200", "channel_id": "456", "content": "chunk"}
            )
        )
        sender = DiscordSender(token="MTk-test", client_factory=lambda: fake)

        response = await sender.forward(self._stream())
        call = fake.calls[0]

        assert call["verb"] == "PATCH"
        assert call["url"] == "https://discord.com/api/v10/channels/456/messages/200"
        assert call["body"]["content"] == "chunk"
        assert "message_reference" not in call["body"]
        assert response.body.result["id"] == "200"

    @pytest.mark.asyncio
    async def test_forward_http_error_becomes_recoverable_error(self) -> None:
        fake = _FakeClient(post_response=_FakeResponse(500, {"message": "boom"}))
        sender = DiscordSender(token="MTk-test", client_factory=lambda: fake)

        response = await sender.forward(self._notification())

        assert response.body.error is not None
        assert response.body.error.code == "transport_error"
        assert response.body.error.recoverable is True

    @pytest.mark.asyncio
    async def test_forward_network_exception_becomes_recoverable_error(self) -> None:
        fake = _FakeClient(error=ConnectionError("dns failure"))
        sender = DiscordSender(token="MTk-test", client_factory=lambda: fake)

        response = await sender.forward(self._notification())

        assert response.body.error is not None
        assert response.body.error.code == "transport_error"
        assert "dns failure" in response.body.error.message

    @pytest.mark.asyncio
    async def test_forward_body_without_id_becomes_discord_error(self) -> None:
        # A 200 body lacking an "id" (e.g. an unexpected ack) is a Discord-level
        # failure, not a success.
        fake = _FakeClient(post_response=_FakeResponse(200, {"message": "unknown"}))
        sender = DiscordSender(token="MTk-test", client_factory=lambda: fake)

        response = await sender.forward(self._notification())

        assert response.body.error is not None
        assert response.body.error.code == "discord_error"

    @pytest.mark.asyncio
    async def test_sender_registered_as_router_forwarder(self) -> None:
        # End-to-end wiring: a router with a DiscordSender forwarder routes a
        # discord: target through the sender and returns its response.
        from gaiaagent.bus.router import MessageRouter

        fake = _FakeClient(post_response=_FakeResponse(200, {"id": "1", "channel_id": "456"}))
        sender = DiscordSender(token="MTk-test", client_factory=lambda: fake)
        router = MessageRouter()
        router.register_bridge_forwarder("discord", sender.forward)

        result = await router.route(self._notification())

        assert isinstance(result, AURCMessage)
        assert result.type == MessageDirection.RESPONSE
        assert result.body.result["id"] == "1"
        assert fake.calls[0]["url"] == "https://discord.com/api/v10/channels/456/messages"
