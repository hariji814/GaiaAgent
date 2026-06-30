"""Slack Bridge -- Slack Platform to AURC bridge.

Translates between Slack's Events API / Web API and the AURC canonical message
format, so a Slack workspace can act as a first-class channel for AURC agents.

This is the first *messaging-channel* bridge in the project: the existing
bridges cover MCP / A2A / ACP, which are agent protocols rather than chat
channels. It extends the "bridges, not walls" thesis to a protocol family that
real users live in every day -- an inbound Slack message becomes an AURC
notification; an outbound AURC notification becomes a Slack ``chat.postMessage``
payload.

Platform concepts modeled here (ported in shape from a production Slack
adapter, reimplemented natively in Python with no Slack SDK dependency):
- Events API envelope (``url_verification`` challenge + ``event_callback``)
- ``message`` / ``app_mention`` / ``im`` message events
- Slash commands (ack-then-respond) and interactive payloads (block_actions)
- Rich rendering via Slack Block Kit (markdown section blocks)
- Thread correlation: ``thread_ts`` (or message ``ts``) -> AURC ``correlation_id``

Direction mapping:
    Slack -> AURC:  translate_to_aurc()
    AURC -> Slack:  translate_from_aurc()
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..core.message import AURCMessage, BridgeContext, MessageBody
from ..core.types import MessageDirection

logger = logging.getLogger(__name__)

SLACK_PROTOCOL = "slack/1.0"
# Arrow kept as an escape so the source stays ASCII while the runtime string
# matches the bridge_chain convention used by the MCP/A2A/ACP bridges.
_ARROW = "\u2192"
# Slack channel addresses use the ``slack:`` prefix so MessageRouter can route
# them to the SlackBridge forwarder, mirroring ``mcp:`` / ``a2a:`` / ``acp:``.
SLACK_PREFIX = "slack"


# =============================================================================
# Rich message rendering
# =============================================================================


def _markdown_section(text: str) -> dict[str, Any]:
    """A Slack Block Kit section block holding markdown text."""
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _render_blocks(text: str, *, fallback_text: str | None = None) -> list[dict[str, Any]]:
    """Render an AURC text payload as Slack Block Kit blocks.

    Slack has no native embed API, so rich content is markdown inside section
    blocks. ``fallback_text`` is the plain-text mirror used when a client
    cannot render blocks.
    """
    body = text if text else (fallback_text or "")
    return [_markdown_section(body)] if body else []


def _channel_from_target(target: str) -> str | None:
    """Extract the Slack channel id from an AURC target like ``slack:C123``."""
    if not target.startswith("slack:"):
        return None
    rest = target[len("slack:"):]
    if rest.startswith("external/"):
        rest = rest[len("external/"):]
    return rest or None

_MENTION_RE = re.compile(r"<@[UWB][0-9A-Z]+>")


def _strip_mention(text: str) -> str:
    """Remove Slack ``<@U123>`` mention tokens from message text.

    Slack renders mentions as ``<@U123>`` (or ``<@U123|name>``) tokens. Stripping
    them gives the agent clean text (matching the Telegram bridge's behavior),
    while the ``is_mention`` flag still records that the agent was addressed.
    """
    return _MENTION_RE.sub("", text).strip()


# =============================================================================
# SlackBridge -- translator
# =============================================================================


class SlackBridge:
    """Slack -> AURC Bridge.

    Translates between Slack (Platform/Web API v1) and the AURC message format.
    Each bridge handles exactly one external protocol, per the
    :class:`ProtocolBridge` contract.

    Inbound (Slack -> AURC):
        - ``event_callback`` of ``message`` / ``app_mention`` / ``im`` -> AURC
          ``notification`` (``event="channel.message"``)
        - ``slash_command`` -> AURC ``request`` (``method="invoke"``)
        - ``interactive`` (block_actions / view_submission) -> AURC ``request``
        - ``url_verification`` challenge -> AURC ``request`` (``method="url_verify"``)

    Outbound (AURC -> Slack):
        - AURC ``notification`` (``event="channel.message"``) -> Slack
          ``chat.postMessage`` payload (text + blocks + thread_ts)
        - AURC ``response`` -> Slack ``chat.postMessage`` payload
        - AURC ``stream`` -> Slack ``chat.update`` (streaming refresh) payload

    Correlation: Slack ``thread_ts`` (or the message ``ts``) is carried as the
    AURC ``correlation_id`` so a multi-turn thread maps to a single trace, and
    ``bridge_chain`` records the ``slack -> aurc`` hop.
    """

    @property
    def source_protocol(self) -> str:
        return SLACK_PROTOCOL

    def can_bridge(self, source_protocol: str, target_protocol: str) -> bool:
        return (
            source_protocol == self.source_protocol and target_protocol == "aurc/0.1"
        ) or (
            source_protocol == "aurc/0.1" and target_protocol == self.source_protocol
        )

    # -------------------------------------------------------------------------
    # External -> AURC
    # -------------------------------------------------------------------------

    async def translate_to_aurc(self, slack_event: dict[str, Any]) -> AURCMessage:
        """Translate a Slack Events API payload to AURC format.

        Recognized Slack payload shapes:
            - Events API envelope: ``{"type": "event_callback", "event": {...}}``
            - Slash command form fields: ``{"type": "slash_command", ...}``
            - Interactive payload: ``{"type": "interactive", "actions": [...], ...}``
            - URL verification: ``{"type": "url_verification", "challenge": "..."}``
            - Bare event dict (``{"type": "message", ...}``) is also accepted.
        """
        evt_type = slack_event.get("type", "")

        if evt_type == "url_verification":
            return self._translate_url_verification(slack_event)

        if evt_type == "slash_command":
            return self._translate_slash_command(slack_event)

        if evt_type == "interactive":
            return self._translate_interactive(slack_event)

        # Events API envelope unwraps to the inner event; a bare event dict is
        # accepted directly so callers can pass either shape.
        if evt_type == "event_callback":
            inner = slack_event.get("event") or {}
            return self._translate_message_event(inner, slack_event)

        if evt_type in ("message", "app_mention") or "text" in slack_event:
            return self._translate_message_event(slack_event, slack_event)

        logger.debug("SlackBridge: unrecognized event type %r", evt_type)
        # Unknown but structured -> generic notification so nothing is silently
        # dropped.
        return AURCMessage(
            source="slack:external/workspace",
            target="aurc:local/handler",
            type=MessageDirection.NOTIFICATION,
            body=MessageBody(event="channel.unknown", data={"type": evt_type}),
            protocol_context=self._bridge_ctx(),
        )

    # -- inbound helpers ------------------------------------------------------

    def _bridge_ctx(self) -> BridgeContext:
        return BridgeContext(
            origin_protocol=SLACK_PROTOCOL,
            bridged_from=SLACK_PROTOCOL,
            bridge_chain=[f"slack{_ARROW}aurc"],
        )

    def _correlation(self, event: dict[str, Any]) -> str | None:
        # Threads are the natural AURC correlation unit: every reply in a
        # thread shares the root ts. Fall back to the message ts for
        # top-level messages.
        return event.get("thread_ts") or event.get("ts")

    def _translate_message_event(
        self, event: dict[str, Any], envelope: dict[str, Any]
    ) -> AURCMessage:
        text = _strip_mention(str(event.get("text", "")))
        user = str(event.get("user", ""))
        channel = str(event.get("channel", ""))
        evt_type = event.get("type", "message")
        # app_mention carries the same fields as message but signals an
        # explicit @- invocation of the agent.
        is_mention = evt_type == "app_mention"

        source = f"slack:external/{user or 'unknown'}"
        target = f"slack:{channel}" if channel else "aurc:local/handler"

        return AURCMessage(
            source=source,
            target=target,
            type=MessageDirection.NOTIFICATION,
            body=MessageBody(
                event="channel.message",
                data={
                    "text": text,
                    "user": user,
                    "channel": channel,
                    "thread_ts": event.get("thread_ts"),
                    "message_ts": event.get("ts"),
                    "is_mention": is_mention,
                    "channel_type": event.get("channel_type"),
                },
                metadata={"slack_team_id": envelope.get("team_id")},
            ),
            correlation_id=self._correlation(event),
            protocol_context=self._bridge_ctx(),
        )

    def _translate_slash_command(self, payload: dict[str, Any]) -> AURCMessage:
        # Slash commands are ack-then-respond: Slack requires a 200 within 3s;
        # the real answer is a follow-up chat.postMessage. Modeled as a
        # request whose skill is the command (without the leading "/").
        command = str(payload.get("command", "")).lstrip("/")
        text = str(payload.get("text", ""))
        channel = str(payload.get("channel_id", ""))
        user = str(payload.get("user_id", ""))

        return AURCMessage(
            source=f"slack:external/{user or 'unknown'}",
            target=f"slack:{channel}" if channel else "aurc:local/handler",
            type=MessageDirection.REQUEST,
            body=MessageBody(
                method="invoke",
                skill=command,
                params={"text": text, "args": text.split() if text else []},
                metadata={
                    "slack_command": payload.get("command"),
                    "slack_trigger_id": payload.get("trigger_id"),
                    "slack_response_url": payload.get("response_url"),
                },
            ),
            correlation_id=payload.get("response_url") or payload.get("trigger_id"),
            protocol_context=self._bridge_ctx(),
        )

    def _translate_interactive(self, payload: dict[str, Any]) -> AURCMessage:
        # A button / select submission. The first action's action_id is the
        # skill; view_submission carries a view state instead.
        actions = payload.get("actions") or []
        first_action = actions[0] if actions else {}
        action_id = str(first_action.get("action_id", "interaction"))
        user = str((payload.get("user") or {}).get("id", ""))
        channel = str((payload.get("channel") or {}).get("id", ""))

        return AURCMessage(
            source=f"slack:external/{user or 'unknown'}",
            target=f"slack:{channel}" if channel else "aurc:local/handler",
            type=MessageDirection.REQUEST,
            body=MessageBody(
                method="invoke",
                skill=action_id,
                params={
                    "value": first_action.get("value"),
                    "actions": actions,
                    "view": payload.get("view"),
                },
                metadata={"slack_trigger_id": payload.get("trigger_id")},
            ),
            correlation_id=payload.get("trigger_id"),
            protocol_context=self._bridge_ctx(),
        )

    def _translate_url_verification(self, payload: dict[str, Any]) -> AURCMessage:
        return AURCMessage(
            source="slack:external/workspace",
            target="aurc:local/handler",
            type=MessageDirection.REQUEST,
            body=MessageBody(
                method="url_verify",
                params={"challenge": payload.get("challenge", "")},
            ),
            protocol_context=self._bridge_ctx(),
        )

    # -------------------------------------------------------------------------
    # AURC -> External
    # -------------------------------------------------------------------------

    async def translate_from_aurc(self, aurc_message: AURCMessage) -> dict[str, Any]:
        """Translate an AURC message to a Slack Web API payload.

        Returns a dict shaped like a Slack ``chat.postMessage`` (or
        ``chat.update`` for streams) call body, ready for a sender to POST to
        ``https://slack.com/api/<method>`` with a Bearer token.
        """
        channel = _channel_from_target(aurc_message.target) or aurc_message.body.params.get(
            "channel"
        )
        # Only thread onto an existing Slack thread when the correlation id
        # looks like a Slack message ts (numeric "1".substring -> truthy).
        thread_ts = self._thread_ts(aurc_message)

        if aurc_message.type == MessageDirection.STREAM:
            # Streaming chunks refresh the same message via chat.update.
            text = str(aurc_message.body.data or "")
            return {
                "method": "chat.update",
                "channel": channel,
                "ts": aurc_message.correlation_id,
                "text": text,
                "blocks": _render_blocks(text),
            }

        if aurc_message.type == MessageDirection.NOTIFICATION:
            text = str(aurc_message.body.data or "")
            if aurc_message.body.event and aurc_message.body.event != "channel.message":
                text = (
                    f"*{aurc_message.body.event}*: {text}" if text else aurc_message.body.event
                )
            payload: dict[str, Any] = {
                "method": "chat.postMessage",
                "channel": channel,
                "text": text,
                "blocks": _render_blocks(text),
            }
            if thread_ts:
                payload["thread_ts"] = thread_ts
            return payload

        if aurc_message.type == MessageDirection.RESPONSE:
            if aurc_message.body.error is not None:
                err = aurc_message.body.error
                text = f":x: *{err.code}*: {err.message}"
            else:
                text = _stringify_result(aurc_message.body.result)
            payload = {
                "method": "chat.postMessage",
                "channel": channel,
                "text": text,
                "blocks": _render_blocks(text),
            }
            if thread_ts:
                payload["thread_ts"] = thread_ts
            return payload

        # Fall back to a plain post for delegation / handoff / heartbeat.
        text = _stringify_result(aurc_message.body.result or aurc_message.body.params)
        return {
            "method": "chat.postMessage",
            "channel": channel,
            "text": text,
            "blocks": _render_blocks(text),
        }

    @staticmethod
    def _thread_ts(aurc_message: AURCMessage) -> str | None:
        """A Slack thread_ts is a numeric string starting with a unix epoch."""
        cid = aurc_message.correlation_id
        if cid and cid.split(".")[0].isdigit():
            return cid
        return None

    # -------------------------------------------------------------------------
    # Capability mapping
    # -------------------------------------------------------------------------

    async def map_capabilities(
        self, external_capabilities: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Map Slack slash commands / workflows to AURC skill declarations.

        Each Slack command / workflow item may carry ``command`` (``"/x"``) or
        ``name``, plus ``description`` and ``usage_hint``. They become AURC
        skills tagged ``slack-bridge`` so the registry can route ``invoke``
        requests back through this bridge.
        """
        skills: list[dict[str, Any]] = []
        for item in external_capabilities:
            raw_name = item.get("command") or item.get("name") or ""
            skill_name = str(raw_name).lstrip("/")
            if not skill_name:
                continue
            skills.append(
                {
                    "skill_id": f"slack:{skill_name}",
                    "name": skill_name,
                    "description": item.get("description", ""),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": item.get("usage_hint", "command arguments"),
                            }
                        },
                    },
                    "output_schema": {"type": "object"},
                    "tags": ["slack-bridge"],
                }
            )
        return skills


def _stringify_result(result: Any) -> str:
    """Render an AURC result / params value as Slack markdown text."""
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list)):
        import json

        return f"```{json.dumps(result, default=str, ensure_ascii=False, indent=2)}```"
    return str(result)
