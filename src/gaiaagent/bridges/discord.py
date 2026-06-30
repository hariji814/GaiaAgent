"""Discord Bridge -- Discord Gateway / Bot API to AURC bridge.

Translates between Discord's Gateway dispatch events (MESSAGE_CREATE /
MESSAGE_UPDATE / INTERACTION_CREATE) and the Bot REST API (create / edit
message) and the AURC canonical message format, so a Discord bot can act as a
first-class channel for AURC agents -- a sibling to the Slack and Telegram
bridges and the third *messaging-channel* bridge in the project.

Platform concepts modeled here (ported in shape from a production Discord
adapter, reimplemented natively in Python with no discord.py dependency):
- Gateway dispatch events (``MESSAGE_CREATE`` / ``MESSAGE_UPDATE`` /
  ``INTERACTION_CREATE``), optionally wrapped in a ``{t, d}`` envelope
- DM vs. guild ``@mention`` handling (``guild_id`` absent => DM)
- Slash commands via ``INTERACTION_CREATE`` (``data.name`` + ``data.options``)
- Rich rendering via Discord native markdown (no separate embed API needed)
- Reply-thread correlation: ``message_reference.message_id`` (or the message
  id) -> AURC ``correlation_id``

Direction mapping:
    Discord -> AURC:  translate_to_aurc()
    AURC -> Discord:  translate_from_aurc()
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..core.message import AURCMessage, BridgeContext, MessageBody
from ..core.types import MessageDirection

logger = logging.getLogger(__name__)

DISCORD_PROTOCOL = "discord/1.0"
# Arrow kept as an escape so the source stays ASCII while the runtime string
# matches the bridge_chain convention used by the other bridges.
_ARROW = "\u2192"
# Discord channel addresses use the ``discord:`` prefix so MessageRouter can
# route them to the DiscordBridge forwarder, mirroring the other bridges.
DISCORD_PREFIX = "discord"


# =============================================================================
# Helpers
# =============================================================================


# Discord user mentions render as ``<@id>`` or ``<@!id>`` (nickname form).
_MENTION_RE = re.compile(r"<@!?\d+>")


def _strip_mention(text: str) -> str:
    """Remove Discord ``<@123>`` / ``<@!123>`` mention tokens from message text.

    Stripping them gives the agent clean text (matching the Slack / Telegram
    bridges), while the ``is_mention`` flag still records that the agent was
    addressed.
    """
    return _MENTION_RE.sub("", text).strip()


def _channel_from_target(target: str) -> str | None:
    """Extract the Discord channel id from an AURC target like ``discord:123``."""
    if not target.startswith("discord:"):
        return None
    rest = target[len("discord:"):]
    if rest.startswith("external/"):
        rest = rest[len("external/"):]
    return rest or None


# =============================================================================
# DiscordBridge -- translator
# =============================================================================


class DiscordBridge:
    """Discord -> AURC Bridge.

    Translates between Discord (Gateway / Bot API v10) and the AURC message
    format. Each bridge handles exactly one external protocol, per the
    :class:`ProtocolBridge` contract.

    Inbound (Discord -> AURC):
        - ``MESSAGE_CREATE`` (DM or guild @mention) -> AURC ``notification``
          (``event="channel.message"``)
        - ``MESSAGE_UPDATE`` -> AURC ``notification``
          (``event="channel.message_edited"``)
        - ``INTERACTION_CREATE`` (slash command) -> AURC ``request``
          (``method="invoke"``); the command name (without a leading ``/``)
          is the skill

    Outbound (AURC -> Discord):
        - AURC ``notification`` / ``response`` -> Discord ``createMessage``
          payload (channel_id + content [+ message_reference])
        - AURC ``stream`` -> Discord ``editMessage`` payload (channel_id +
          message_id + content)

    Correlation: a Discord reply carries ``message_reference.message_id``;
    that id (or the message's own id) is carried as the AURC
    ``correlation_id`` so a reply chain maps to one trace, and
    ``bridge_chain`` records the ``discord -> aurc`` hop.
    """

    def __init__(self, *, bot_id: str | None = None) -> None:
        # Bot user id is optional; when set it is informational (the bridge
        # strips *all* user mentions regardless, like the Slack bridge).
        self._bot_id = bot_id

    @property
    def source_protocol(self) -> str:
        return DISCORD_PROTOCOL

    def can_bridge(self, source_protocol: str, target_protocol: str) -> bool:
        return (
            source_protocol == self.source_protocol and target_protocol == "aurc/0.1"
        ) or (
            source_protocol == "aurc/0.1" and target_protocol == self.source_protocol
        )

    # -------------------------------------------------------------------------
    # External -> AURC
    # -------------------------------------------------------------------------

    async def translate_to_aurc(self, event: dict[str, Any]) -> AURCMessage:
        """Translate a Discord Gateway / Bot API event to AURC format.

        Accepts either a bare event (``MESSAGE_CREATE`` message dict, or an
        ``INTERACTION_CREATE`` dict) or a Gateway dispatch envelope
        ``{"t": "MESSAGE_CREATE", "d": {...}}``. A bare dict is detected by
        its shape so callers can pass whichever they have.
        """
        evt_type = str(event.get("type", ""))
        data: dict[str, Any] = event

        # Unwrap a Gateway dispatch envelope {"op": 0, "t": "...", "d": {...}}.
        if not evt_type and "t" in event and "d" in event:
            evt_type = str(event.get("t"))
            inner = event.get("d")
            if isinstance(inner, dict):
                data = inner

        if evt_type == "INTERACTION_CREATE":
            return self._translate_interaction(data)

        # A bare interaction (no envelope, no explicit type) is detected by the
        # presence of a slash-command ``data.name``.
        if evt_type == "" and isinstance(data.get("data"), dict) and data["data"].get("name"):
            return self._translate_interaction(data)

        if evt_type == "MESSAGE_UPDATE":
            return self._translate_message(data, is_edit=True)

        # MESSAGE_CREATE, or a bare message dict detected by content/author.
        if evt_type in ("MESSAGE_CREATE", "") and ("content" in data or "author" in data):
            return self._translate_message(data, is_edit=False)

        logger.debug("DiscordBridge: unrecognized event type %r", evt_type)
        # Unknown but structured -> generic notification so nothing is dropped.
        return AURCMessage(
            source="discord:external/bot",
            target="aurc:local/handler",
            type=MessageDirection.NOTIFICATION,
            body=MessageBody(event="channel.unknown", data={"type": evt_type}),
            protocol_context=self._bridge_ctx(),
        )

    # -- inbound helpers ------------------------------------------------------

    def _bridge_ctx(self) -> BridgeContext:
        return BridgeContext(
            origin_protocol=DISCORD_PROTOCOL,
            bridged_from=DISCORD_PROTOCOL,
            bridge_chain=[f"discord{_ARROW}aurc"],
        )

    def _correlation(self, msg: dict[str, Any]) -> str | None:
        # A reply points at the message it answers via message_reference; that
        # anchor is the natural AURC correlation unit for a reply chain. Fall
        # back to the message's own id for top-level messages.
        ref = msg.get("message_reference") or {}
        ref_id = ref.get("message_id")
        if ref_id:
            return str(ref_id)
        return str(msg.get("id") or "") or None

    def _translate_message(
        self, msg: dict[str, Any], *, is_edit: bool
    ) -> AURCMessage:
        raw_text = str(msg.get("content", ""))
        author = msg.get("author") or {}
        user = str(author.get("id") or author.get("username") or "")
        channel = str(msg.get("channel_id") or "")
        guild_id = msg.get("guild_id")
        # A Discord message without a guild_id is a DM.
        is_dm = guild_id is None
        clean_text = _strip_mention(raw_text)
        # In a guild, the bot only receives messages that @mention it; a DM is
        # an implicit direct address. We flag a guild message as a mention when
        # it carries any user-mention token.
        is_mention = (not is_dm) and bool(_MENTION_RE.search(raw_text))

        source = f"discord:external/{user or 'unknown'}"
        target = f"discord:{channel}" if channel else "aurc:local/handler"

        return AURCMessage(
            source=source,
            target=target,
            type=MessageDirection.NOTIFICATION,
            body=MessageBody(
                event="channel.message_edited" if is_edit else "channel.message",
                data={
                    "text": clean_text,
                    "user": user,
                    "channel": channel,
                    "guild_id": guild_id,
                    "message_id": msg.get("id"),
                    "is_mention": is_mention,
                    "is_dm": is_dm,
                    "referenced_message_id": (msg.get("message_reference") or {}).get(
                        "message_id"
                    ),
                },
                metadata={
                    "discord_event": "MESSAGE_UPDATE" if is_edit else "MESSAGE_CREATE"
                },
            ),
            correlation_id=self._correlation(msg),
            protocol_context=self._bridge_ctx(),
        )

    def _translate_interaction(self, event: dict[str, Any]) -> AURCMessage:
        # A slash-command interaction. ``data.name`` is the command (no leading
        # "/"); ``data.options`` carries the typed arguments.
        cmd_data = event.get("data") or {}
        command = str(cmd_data.get("name", ""))
        options = cmd_data.get("options") or []
        # Flatten option values into a text arg so the skill receives the same
        # ``text`` param shape as Slack / Telegram slash commands.
        args_text = " ".join(
            str(o.get("value", "")) for o in options if isinstance(o, dict)
        )
        user_obj = event.get("user") or (event.get("member") or {}).get("user") or {}
        user = str(user_obj.get("id") or user_obj.get("username") or "")
        channel = str(event.get("channel_id") or "")

        return AURCMessage(
            source=f"discord:external/{user or 'unknown'}",
            target=f"discord:{channel}" if channel else "aurc:local/handler",
            type=MessageDirection.REQUEST,
            body=MessageBody(
                method="invoke",
                skill=command,
                params={
                    "text": args_text,
                    "args": args_text.split() if args_text else [],
                    "options": options,
                },
                metadata={
                    "discord_interaction_id": event.get("id"),
                    "discord_interaction_token": event.get("token"),
                },
            ),
            correlation_id=str(event.get("id") or "") or None,
            protocol_context=self._bridge_ctx(),
        )

    # -------------------------------------------------------------------------
    # AURC -> External
    # -------------------------------------------------------------------------

    async def translate_from_aurc(self, aurc_message: AURCMessage) -> dict[str, Any]:
        """Translate an AURC message to a Discord Bot API payload.

        Returns a dict shaped like a Discord ``createMessage`` (or
        ``editMessage`` for streams) call, ready for a sender to POST / PATCH
        to ``https://discord.com/api/v10/channels/<channel_id>/messages`` with
        a ``Bot <token>`` authorization header.
        """
        channel_id = _channel_from_target(aurc_message.target) or aurc_message.body.params.get(
            "channel_id"
        )

        if aurc_message.type == MessageDirection.STREAM:
            # Streaming chunks edit the same message in place.
            text = str(aurc_message.body.data or "")
            return {
                "method": "editMessage",
                "channel_id": channel_id,
                "message_id": aurc_message.correlation_id,
                "content": text,
            }

        if aurc_message.type == MessageDirection.RESPONSE:
            if aurc_message.body.error is not None:
                err = aurc_message.body.error
                text = f":x: **{err.code}**: {err.message}"
            else:
                text = _stringify_result(aurc_message.body.result)
        else:
            text = str(aurc_message.body.data or "")
            if aurc_message.body.event and aurc_message.body.event != "channel.message":
                text = f"**{aurc_message.body.event}**: {text}" if text else aurc_message.body.event

        payload: dict[str, Any] = {
            "method": "createMessage",
            "channel_id": channel_id,
            "content": text,
        }
        # Thread the reply onto the anchored message when the correlation id is
        # a numeric Discord message id (snowflake).
        ref = self._message_reference(aurc_message)
        if ref is not None:
            payload["message_reference"] = {"message_id": ref}
        return payload

    @staticmethod
    def _message_reference(aurc_message: AURCMessage) -> str | None:
        cid = aurc_message.correlation_id
        if cid and cid.isdigit():
            return cid
        return None

    # -------------------------------------------------------------------------
    # Capability mapping
    # -------------------------------------------------------------------------

    async def map_capabilities(
        self, external_capabilities: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Map Discord slash commands to AURC skill declarations.

        Each Discord application command item carries ``name`` (no leading
        ``/``), ``description``, and optionally ``options``. They become AURC
        skills tagged ``discord-bridge`` so the registry can route ``invoke``
        requests back through this bridge.
        """
        skills: list[dict[str, Any]] = []
        for item in external_capabilities:
            raw_name = item.get("name") or item.get("command") or ""
            skill_name = str(raw_name).lstrip("/")
            if not skill_name:
                continue
            skills.append(
                {
                    "skill_id": f"discord:{skill_name}",
                    "name": skill_name,
                    "description": item.get("description", ""),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "slash-command arguments",
                            }
                        },
                    },
                    "output_schema": {"type": "object"},
                    "tags": ["discord-bridge"],
                }
            )
        return skills


def _stringify_result(result: Any) -> str:
    """Render an AURC result / params value as Discord markdown text."""
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list)):
        import json

        return f"```{json.dumps(result, default=str, ensure_ascii=False, indent=2)}```"
    return str(result)
