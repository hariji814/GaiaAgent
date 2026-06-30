"""End-to-end messaging-channel interop demo: Slack & Telegram <-> AURC.

The sibling demos (``e2e_mcp_a2a_interop.py``, ``e2e_acp_interop.py``) prove
AURC bridges real *agent* protocols (MCP / A2A / ACP). This demo closes the
other half of the "bridges, not walls" thesis: real *messaging channels* -- the
chat surfaces users live in -- reach a real AURC agent and get a reply back,
with correlation carried end-to-end.

Unlike the agent-protocol demos, chat platforms have no local SDK server to
spawn, so the channel "wire" is simulated by a fake HTTP client that records
what the sender would POST. Everything else is real:

    REAL Slack/Telegram event  (platform-shaped payload, Events API / Bot API)
        --> SlackBridge/TelegramBridge.translate_to_aurc  (event -> AURC)
        MessageRouter.route -> a REAL @aurc_agent skill (EchoChannel)
        <-- skill result {"reply": "..."}
        <-- SlackSender/TelegramSender.translate_from_aurc + POST (fake client)
    REAL Slack/Telegram API call body  (chat.postMessage / sendMessage)

Two channels, one agent, no network. The fake client asserts the outbound
payload lands on the right platform endpoint with the right auth and threading.

Run:
    python examples/e2e_channel_interop.py
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from gaiaagent.bridges import (
    DiscordBridge,
    DiscordSender,
    SlackBridge,
    SlackSender,
    TelegramBridge,
    TelegramSender,
)
from gaiaagent.bus.router import MessageRouter
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection
from gaiaagent.sdk.decorators import aurc_agent, skill

# ---------------------------------------------------------------------------
# A real AURC agent. The skill does real work: it turns the inbound channel
# text into an echoed reply, simulating an assistant that answers in-channel.
# ---------------------------------------------------------------------------


@aurc_agent(
    id="aurc:demo/echo-channel:v1.0",
    display_name="EchoChannel",
    description="Answers chat-channel messages through AURC",
    protocols=["slack/1.0", "telegram/1.0", "discord/1.0"],
)
class EchoChannel:
    @skill("reply", description="Echo an inbound channel message back as a reply")
    async def reply(self, text: str = "", **extra: Any) -> dict[str, Any]:
        # A real assistant would call an LLM here; the demo keeps it deterministic
        # so the assertion is stable, but the skill plumbing (discovery, routing,
        # capability mapping) is identical to a production agent.
        incoming = (text or "").strip() or "(empty)"
        return {"reply": f"[echo] {incoming}"}


# ---------------------------------------------------------------------------
# A fake channel HTTP client. It stands in for Slack's / Telegram's servers so
# the demo runs with no network, while asserting the sender hit the real
# platform endpoint shape (URL, auth, body).
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"channel API returned HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeChannelClient:
    """Records every POST the sender would make; returns a canned success."""

    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []

    async def post(self, url: str, content: bytes, headers: dict[str, str]) -> _FakeResponse:
        body = json.loads(content)
        self.posts.append({"url": url, "headers": headers, "body": body})
        # Platform-shaped success replies.
        if "slack.com" in url:
            return _FakeResponse(200, {"ok": True, "channel": body.get("channel"), "ts": "999.0"})
        if "discord.com" in url:
            return _FakeResponse(
                200,
                {"id": "999", "channel_id": body.get("channel_id"), "content": body.get("content")},
            )
        return _FakeResponse(
            200, {"ok": True, "result": {"message_id": 999, "text": body.get("text")}}
        )


# ---------------------------------------------------------------------------
# The end-to-end flow for one channel.
# ---------------------------------------------------------------------------


async def _channel_round_trip(
    *,
    name: str,
    bridge: SlackBridge | TelegramBridge | DiscordBridge,
    sender: SlackSender | TelegramSender | DiscordSender,
    fake: _FakeChannelClient,
    router: MessageRouter,
    inbound_event: dict[str, Any],
    expected_text: str,
) -> None:
    print(f"[{name}] inbound event -> AURC")

    # 1. REAL platform event -> AURC message (notification or invoke request).
    aurc = await bridge.translate_to_aurc(inbound_event)
    print(f"      translated: type={aurc.type.value} event={aurc.body.event}"
          f" correlation={aurc.correlation_id}")

    # 2. Route to the real agent skill. A plain text message becomes a
    # notification; the demo wraps it into an invoke request so the skill runs,
    # mirroring how a channel handler dispatches a mention to a skill.
    # A plain message carries text in body.data["text"]; a /command carries the
    # argument text in body.params["text"]. Read from whichever is present.
    if isinstance(aurc.body.data, dict) and aurc.body.data.get("text"):
        text = str(aurc.body.data["text"])
    else:
        text = str(aurc.body.params.get("text", ""))
    invoke = AURCMessage(
        source=aurc.source,
        target="aurc:demo/echo-channel:v1.0",
        type=MessageDirection.REQUEST,
        correlation_id=aurc.correlation_id,
        body=MessageBody(
            method="invoke",
            skill="reply",
            params={"text": text},
        ),
        protocol_context=aurc.protocol_context,
    )
    outcome = await router.route(invoke)
    result = outcome.get("result", outcome) if isinstance(outcome, dict) else outcome
    reply_text = str((result or {}).get("reply", "")) if isinstance(result, dict) else str(result)
    print(f"      agent skill ran: reply={reply_text!r}")
    assert reply_text == expected_text, (reply_text, expected_text)

    # 3. Build the outbound AURC reply to the channel and forward it through
    # the sender (translate -> POST -> build-response), all real except the wire.
    reply = AURCMessage(
        source="aurc:demo/echo-channel:v1.0",
        target=aurc.target,  # back to the originating channel/chat
        type=MessageDirection.NOTIFICATION,
        correlation_id=aurc.correlation_id,
        body=MessageBody(event="channel.message", data=reply_text),
        protocol_context=aurc.protocol_context,
    )
    response = await sender.forward(reply)
    assert response.type == MessageDirection.RESPONSE, response
    assert response.body.error is None, response.body.error
    print(f"      posted to channel; AURC response correlation={response.correlation_id}")


async def run_demo() -> int:
    print("=" * 64)
    print("  AURC Messaging-Channel Interop - Slack, Telegram & Discord round-trip")
    print("=" * 64)

    # Stand up the runtime: one real agent, one router. AURCServer wires the
    # agent's @skill methods onto the router under the agent's AURC ID.
    router = MessageRouter()
    agent = EchoChannel()
    from gaiaagent.server import AURCServer

    server = AURCServer(router=router)
    await server.register_agent(agent)

    # Two channel bridges + senders, each with the same fake client.
    slack_bridge = SlackBridge()
    tg_bridge = TelegramBridge(bot_username="aurcbot")
    slack_fake = _FakeChannelClient()
    tg_fake = _FakeChannelClient()
    slack_sender = SlackSender(token="xoxb-demo", client_factory=lambda: slack_fake)
    tg_sender = TelegramSender(token="123:ABC", client_factory=lambda: tg_fake)
    discord_bridge = DiscordBridge()
    discord_fake = _FakeChannelClient()
    discord_sender = DiscordSender(token="discord-demo", client_factory=lambda: discord_fake)

    # --- Slack: an app_mention in a thread -------------------------------
    slack_event = {
        "type": "event_callback",
        "team_id": "T0001",
        "event": {
            "type": "app_mention",
            "user": "U123",
            "channel": "C456",
            "text": "<@U999> hello there",
            "ts": "1690000001.000300",
            "thread_ts": "1690000000.000200",
        },
    }
    await _channel_round_trip(
        name="slack",
        bridge=slack_bridge,
        sender=slack_sender,
        fake=slack_fake,
        router=router,
        inbound_event=slack_event,
        expected_text="[echo] hello there",
    )

    # --- Telegram: a /reply command in a private chat -------------------
    tg_event = {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "from": {"id": 100},
            "chat": {"id": 456, "type": "private"},
            "text": "/reply hi from telegram",
        },
    }
    await _channel_round_trip(
        name="telegram",
        bridge=tg_bridge,
        sender=tg_sender,
        fake=tg_fake,
        router=router,
        inbound_event=tg_event,
        expected_text="[echo] hi from telegram",
    )

    # --- Discord: a DM (no guild_id) from a user -----------------------
    discord_event = {
        "type": "MESSAGE_CREATE",
        "id": "300",
        "channel_id": "789",
        "author": {"id": "D123"},
        "content": "hello from discord",
    }
    await _channel_round_trip(
        name="discord",
        bridge=discord_bridge,
        sender=discord_sender,
        fake=discord_fake,
        router=router,
        inbound_event=discord_event,
        expected_text="[echo] hello from discord",
    )

    print("=" * 64)
    # Assert the senders hit the real platform endpoints with real auth.
    assert slack_fake.posts[0]["url"] == "https://slack.com/api/chat.postMessage"
    assert slack_fake.posts[0]["headers"]["Authorization"] == "Bearer xoxb-demo"
    assert slack_fake.posts[0]["body"]["channel"] == "C456"
    assert slack_fake.posts[0]["body"]["thread_ts"] == "1690000000.000200"
    print("[slack] posted chat.postMessage to slack.com (Bearer auth, threaded)")

    assert tg_fake.posts[0]["url"] == "https://api.telegram.org/bot123:ABC/sendMessage"
    assert tg_fake.posts[0]["body"]["chat_id"] == "456"
    assert tg_fake.posts[0]["body"]["reply_to_message_id"] == 10
    print("[telegram] posted sendMessage to api.telegram.org (token in URL, reply_to)")

    assert discord_fake.posts[0]["url"] == "https://discord.com/api/v10/channels/789/messages"
    assert discord_fake.posts[0]["headers"]["Authorization"] == "Bot discord-demo"
    assert discord_fake.posts[0]["body"]["content"] == "[echo] hello from discord"
    assert discord_fake.posts[0]["body"]["message_reference"] == {"message_id": "300"}
    print("[discord] posted createMessage to discord.com (Bot auth, threaded)")

    print("Demo complete: a Slack mention, a Telegram /command, and a Discord DM")
    print("all reached a real AURC agent skill and were answered back in-channel,")
    print("with correlation carried end-to-end across three channel boundaries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_demo()))
