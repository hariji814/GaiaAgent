"""Telegram Bridge -- Telegram Bot API to AURC bridge.

Translates between Telegram's Bot API (getUpdates / webhook updates and the
sendMessage family) and the AURC canonical message format, so a Telegram bot
can act as a first-class channel for AURC agents -- a sibling to the Slack
bridge and the second *messaging-channel* bridge in the project.

Platform concepts modeled here (ported in shape from a production Telegram
adapter, reimplemented natively in Python with no Telegram SDK dependency):
- Bot API update payloads (``message`` / ``edited_message`` / ``callback_query``)
- Private chats vs. group chats, and group ``@bot`` mentions
- Slash-style ``/commands`` (Telegram Bot API "BotCommands")
- Rich rendering via ``parse_mode=Markdown`` (Telegram has no native embed API)
- Reply-thread correlation: ``reply_to_message.message_id`` (or the update id)
  -> AURC ``correlation_id``

Direction mapping:
    Telegram -> AURC:  translate_to_aurc()
    AURC -> Telegram:  translate_from_aurc()
"""

from __future__ import annotations

import logging
from typing import Any

from ..core.message import AURCMessage, BridgeContext, MessageBody
from ..core.types import MessageDirection

logger = logging.getLogger(__name__)

TELEGRAM_PROTOCOL = "telegram/1.0"
# Arrow kept as an escape so the source stays ASCII while the runtime string
# matches the bridge_chain convention used by the other bridges.
_ARROW = "\u2192"
# Telegram chat addresses use the ``telegram:`` prefix so MessageRouter can
# route them to the TelegramBridge forwarder, mirroring the other bridges.
TELEGRAM_PREFIX = "telegram"


# =============================================================================
# Helpers
# =============================================================================


def _strip_mention(text: str, bot_username: str | None) -> str:
    """Remove a leading/trailing ``@bot`` mention from message text."""
    if not bot_username:
        return text.strip()
    needle = f"@{bot_username}"
    cleaned = text.replace(needle, "")
    return cleaned.strip()


def _command_and_args(text: str) -> tuple[str, str]:
    """Split ``"/cmd rest of line"`` into ``(command, args_text)``.

    Returns ``("", text)`` when the text is not a command. The leading ``/`` is
    stripped from the command name. A trailing ``@bot`` on the command (group
    syntax ``/cmd@bot``) is also stripped.
    """
    stripped = text.strip()
    if not stripped.startswith("/"):
        return "", stripped
    first, _, rest = stripped.partition(" ")
    command = first.lstrip("/")
    # Group commands may be written as "/cmd@MyBot".
    if "@" in command:
        command = command.split("@", 1)[0]
    return command, rest.strip()


def _chat_from_target(target: str) -> str | None:
    """Extract the Telegram chat id from an AURC target like ``telegram:12345``."""
    if not target.startswith("telegram:"):
        return None
    rest = target[len("telegram:"):]
    if rest.startswith("external/"):
        rest = rest[len("external/"):]
    return rest or None


# =============================================================================
# TelegramBridge -- translator
# =============================================================================


class TelegramBridge:
    """Telegram -> AURC Bridge.

    Translates between Telegram (Bot API v1) and the AURC message format. Each
    bridge handles exactly one external protocol, per the :class:`ProtocolBridge`
    contract.

    Inbound (Telegram -> AURC):
        - ``message`` with text -> AURC ``notification`` (``event="channel.message"``)
          or, if the text is a ``/command``, an AURC ``request`` (``method="invoke"``)
        - ``callback_query`` (inline button press) -> AURC ``request``
        - ``edited_message`` -> AURC ``notification`` (``event="channel.message_edited"``)

    Outbound (AURC -> Telegram):
        - AURC ``notification`` / ``response`` -> Telegram ``sendMessage`` payload
          (chat_id + text + parse_mode + reply_to_message_id)
        - AURC ``stream`` -> Telegram ``editMessageText`` (streaming refresh) payload

    Correlation: Telegram has no native threads; a reply carries
    ``reply_to_message.message_id``. That id (or the update's own message id) is
    carried as the AURC ``correlation_id`` so a reply chain maps to one trace,
    and ``bridge_chain`` records the ``telegram -> aurc`` hop.
    """

    def __init__(self, *, bot_username: str | None = None) -> None:
        # Bot username is optional; when set, group ``@bot`` mentions and the
        # ``/cmd@bot`` form are stripped from message text.
        self._bot_username = bot_username

    @property
    def source_protocol(self) -> str:
        return TELEGRAM_PROTOCOL

    def can_bridge(self, source_protocol: str, target_protocol: str) -> bool:
        return (
            source_protocol == self.source_protocol and target_protocol == "aurc/0.1"
        ) or (
            source_protocol == "aurc/0.1" and target_protocol == self.source_protocol
        )

    # -------------------------------------------------------------------------
    # External -> AURC
    # -------------------------------------------------------------------------

    async def translate_to_aurc(self, update: dict[str, Any]) -> AURCMessage:
        """Translate a Telegram Bot API update to AURC format.

        Accepts a single update object (the shape delivered by ``getUpdates``
        or a webhook). ``update_id`` is ignored for routing but may be carried
        in metadata for ack offset bookkeeping.
        """
        if "callback_query" in update:
            return self._translate_callback_query(update)

        # ``edited_message`` shares the message shape but signals an edit.
        msg = update.get("message") or update.get("edited_message") or update.get("channel_post")
        if msg is None:
            logger.debug("TelegramBridge: update has no message/callback_query")
            return AURCMessage(
                source="telegram:external/bot",
                target="aurc:local/handler",
                type=MessageDirection.NOTIFICATION,
                body=MessageBody(
                    event="channel.unknown",
                    data={"update_id": update.get("update_id")},
                ),
                protocol_context=self._bridge_ctx(),
            )

        is_edit = "edited_message" in update or "channel_post" in update
        return self._translate_message(msg, update, is_edit=is_edit)

    # -- inbound helpers ------------------------------------------------------

    def _bridge_ctx(self) -> BridgeContext:
        return BridgeContext(
            origin_protocol=TELEGRAM_PROTOCOL,
            bridged_from=TELEGRAM_PROTOCOL,
            bridge_chain=[f"telegram{_ARROW}aurc"],
        )

    def _chat_ref(self, msg: dict[str, Any]) -> str:
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        return f"telegram:{chat_id}" if chat_id is not None else "aurc:local/handler"

    def _sender_ref(self, msg: dict[str, Any]) -> str:
        sender = msg.get("from") or msg.get("from_user") or {}
        sender_id = sender.get("id") or sender.get("username") or "unknown"
        return f"telegram:external/{sender_id}"

    def _correlation(self, msg: dict[str, Any]) -> str | None:
        # A reply points at the message it answers; that anchor is the natural
        # AURC correlation unit for a Telegram reply chain.
        reply_to = msg.get("reply_to_message") or {}
        return str(reply_to.get("message_id")) if reply_to.get("message_id") else str(
            msg.get("message_id") or ""
        ) or None

    def _translate_message(
        self, msg: dict[str, Any], update: dict[str, Any], *, is_edit: bool
    ) -> AURCMessage:
        text = str(msg.get("text", ""))
        chat_type = str((msg.get("chat") or {}).get("type", ""))
        # Strip a leading/trailing "@bot" mention so the agent receives clean
        # text (matches the production adapter behavior); the raw text is still
        # used for mention detection below.
        clean_text = _strip_mention(text, self._bot_username)
        command, args_text = _command_and_args(clean_text)

        if command and not is_edit:
            # ``/command`` -> AURC invoke request, mirroring the Slack slash
            # command translation.
            return AURCMessage(
                source=self._sender_ref(msg),
                target=self._chat_ref(msg),
                type=MessageDirection.REQUEST,
                body=MessageBody(
                    method="invoke",
                    skill=command,
                    params={"text": args_text, "args": args_text.split() if args_text else []},
                    metadata={
                        "telegram_update_id": update.get("update_id"),
                        "telegram_chat_type": chat_type,
                    },
                ),
                correlation_id=self._correlation(msg),
                protocol_context=self._bridge_ctx(),
            )

        # Plain text -> notification; edits are flagged separately so a handler
        # can re-process without re-triggering side effects.
        return AURCMessage(
            source=self._sender_ref(msg),
            target=self._chat_ref(msg),
            type=MessageDirection.NOTIFICATION,
            body=MessageBody(
                event="channel.message_edited" if is_edit else "channel.message",
                data={
                    "text": clean_text,
                    "user": self._user_id(msg),
                    "chat": (msg.get("chat") or {}).get("id"),
                    "chat_type": chat_type,
                    "message_id": msg.get("message_id"),
                    "reply_to_message_id": (msg.get("reply_to_message") or {}).get(
                        "message_id"
                    ),
                    "is_mention": self._bot_username is not None
                    and self._bot_username in text,
                },
                metadata={"telegram_update_id": update.get("update_id")},
            ),
            correlation_id=self._correlation(msg),
            protocol_context=self._bridge_ctx(),
        )

    def _translate_callback_query(self, update: dict[str, Any]) -> AURCMessage:
        # An inline-button press. ``data`` is the bot-defined callback payload;
        # we treat it as the skill to invoke.
        cq = update["callback_query"]
        data = str(cq.get("data", "callback"))
        msg = cq.get("message") or {}
        sender = cq.get("from") or {}

        return AURCMessage(
            source=f"telegram:external/{sender.get('id', 'unknown')}",
            target=self._chat_ref(msg),
            type=MessageDirection.REQUEST,
            body=MessageBody(
                method="invoke",
                skill=data,
                params={"callback_query_id": cq.get("id")},
                metadata={
                    "telegram_update_id": update.get("update_id"),
                    "telegram_callback_query_id": cq.get("id"),
                },
            ),
            correlation_id=str(msg.get("message_id") or "") or None,
            protocol_context=self._bridge_ctx(),
        )

    @staticmethod
    def _user_id(msg: dict[str, Any]) -> Any:
        sender = msg.get("from") or msg.get("from_user") or {}
        return sender.get("id") or sender.get("username")

    # -------------------------------------------------------------------------
    # AURC -> External
    # -------------------------------------------------------------------------

    async def translate_from_aurc(self, aurc_message: AURCMessage) -> dict[str, Any]:
        """Translate an AURC message to a Telegram Bot API payload.

        Returns a dict shaped like a Telegram ``sendMessage`` (or
        ``editMessageText`` for streams) call body, ready for a sender to POST
        to ``https://api.telegram.org/bot<token>/<method>``.
        """
        chat_id = _chat_from_target(aurc_message.target) or aurc_message.body.params.get(
            "chat_id"
        )

        if aurc_message.type == MessageDirection.STREAM:
            # Streaming chunks edit the same message in place.
            text = str(aurc_message.body.data or "")
            return {
                "method": "editMessageText",
                "chat_id": chat_id,
                "message_id": aurc_message.correlation_id,
                "text": text,
                "parse_mode": "Markdown",
            }

        if aurc_message.type == MessageDirection.RESPONSE:
            if aurc_message.body.error is not None:
                err = aurc_message.body.error
                text = f"\u274c *{err.code}*: {err.message}"
            else:
                text = _stringify_result(aurc_message.body.result)
        else:
            text = str(aurc_message.body.data or "")
            if aurc_message.body.event and aurc_message.body.event != "channel.message":
                text = f"*{aurc_message.body.event}*: {text}" if text else aurc_message.body.event

        payload: dict[str, Any] = {
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        # Thread the reply onto the anchored message when the correlation id is
        # a numeric Telegram message id.
        reply_to = self._reply_to(aurc_message)
        if reply_to is not None:
            payload["reply_to_message_id"] = reply_to
        return payload

    @staticmethod
    def _reply_to(aurc_message: AURCMessage) -> int | None:
        cid = aurc_message.correlation_id
        if cid and cid.isdigit():
            return int(cid)
        return None

    # -------------------------------------------------------------------------
    # Capability mapping
    # -------------------------------------------------------------------------

    async def map_capabilities(
        self, external_capabilities: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Map Telegram BotCommands to AURC skill declarations.

        Each Telegram BotCommand item carries ``command`` (no leading ``/``) and
        ``description``. They become AURC skills tagged ``telegram-bridge`` so
        the registry can route ``invoke`` requests back through this bridge.
        """
        skills: list[dict[str, Any]] = []
        for item in external_capabilities:
            raw_name = item.get("command") or item.get("name") or ""
            skill_name = str(raw_name).lstrip("/")
            if not skill_name:
                continue
            skills.append(
                {
                    "skill_id": f"telegram:{skill_name}",
                    "name": skill_name,
                    "description": item.get("description", ""),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "command arguments",
                            }
                        },
                    },
                    "output_schema": {"type": "object"},
                    "tags": ["telegram-bridge"],
                }
            )
        return skills


def _stringify_result(result: Any) -> str:
    """Render an AURC result / params value as Telegram markdown text."""
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list)):
        import json

        return f"```\n{json.dumps(result, default=str, ensure_ascii=False, indent=2)}\n```"
    return str(result)
