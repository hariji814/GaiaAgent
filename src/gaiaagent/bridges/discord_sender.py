"""Discord network sender -- turns DiscordBridge from a translator into a connector.

A :class:`DiscordBridge` only translates formats (AURC <-> Discord). A
:class:`DiscordSender` wraps a bridge and adds the missing *connectivity*: it
takes an outbound AURCMessage, translates it to a Discord Bot API payload,
POSTs (or PATCHes for edits) it to ``https://discord.com/api/v10/channels/
<channel_id>/messages`` with a ``Bot <token>`` authorization header, and builds
an AURC response from the Discord reply.

Discord's REST API differs from Slack's in three ways that earn it its own
sender rather than reusing :class:`SlackSender`:

- the channel id is in the URL path, not the body (so the endpoint is
  per-channel),
- editing an existing message is a PATCH (``createMessage`` is a POST), and
- auth is a single ``Bot <token>`` header (not a Slack bearer-in-body style).

Like :class:`SlackSender` it accepts an injectable ``client_factory`` so tests
can run the full translate -> POST/PATCH -> build-response loop with no
network.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ..core.message import AURCMessage, ErrorInfo, MessageBody
from ..core.types import MessageDirection
from .discord import DiscordBridge

logger = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"

# A fake async client shape compatible with the one used by the channel-sender
# tests: ``await client.post(url, content=..., headers=...)`` /
# ``await client.patch(url, content=..., headers=...) -> response`` with
# ``response.status_code`` / ``response.json()`` / ``response.raise_for_status``.
DiscordClientFactory = Callable[..., Any]


class DiscordSender:
    """Sends AURC messages to Discord and translates the reply back.

    Usage::

        sender = DiscordSender(token="MTk...")
        router.register_bridge_forwarder("discord", sender.forward)

    When the router routes a message whose target starts with ``discord:``, it
    calls ``sender.forward(msg)`` which:

        1. translates ``msg`` to a Discord Bot API payload (method + channel_id
           + content [+ message_reference]),
        2. POSTs it to ``/channels/<channel_id>/messages`` (or PATCHes
           ``/channels/<channel_id>/messages/<message_id>`` for edits) with the
           bot token,
        3. builds an AURC RESPONSE from the Discord reply (a message object on
           success, an error body on failure),
        4. returns that response, so the caller gets a well-formed result.
    """

    def __init__(
        self,
        *,
        token: str,
        bridge: DiscordBridge | None = None,
        timeout_seconds: float = 30.0,
        client_factory: DiscordClientFactory | None = None,
    ) -> None:
        self._token = token
        self._bridge = bridge or DiscordBridge()
        self._timeout = timeout_seconds
        self._client_factory = client_factory

    @property
    def bridge(self) -> DiscordBridge:
        return self._bridge

    async def forward(self, message: AURCMessage) -> AURCMessage:
        """Translate -> POST/PATCH -> translate back. Returns an AURC response.

        On any failure (network error, Discord error body) a *response* AURC
        message carrying an ErrorInfo is returned rather than raising, so the
        router always gets a well-formed result it can act on.
        """
        try:
            payload = await self._bridge.translate_from_aurc(message)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("DiscordSender: translate_from_aurc failed for %s", message.target)
            return _error_response(message, code="translation_error", message=str(exc))

        method = str(payload.get("method", "createMessage"))
        channel_id = payload.get("channel_id")
        # Discord takes ``content`` (and ``message_reference`` when present) in
        # the body; the channel id travels in the URL, not the body.
        body: dict[str, Any] = {}
        if "content" in payload:
            body["content"] = payload["content"]
        if payload.get("message_reference"):
            body["message_reference"] = payload["message_reference"]

        try:
            if method == "editMessage":
                message_id = payload.get("message_id")
                url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}"
                response_data = await self._send("PATCH", url, body)
            else:
                url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
                response_data = await self._send("POST", url, body)
        except Exception as exc:
            logger.warning("DiscordSender %s to %s failed: %s", method, url, exc)
            return _error_response(
                message, code="transport_error", message=str(exc), recoverable=True
            )

        return _build_response(message, response_data)

    async def _send(self, verb: str, url: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST/PATCH the translated payload with the bot token, return JSON."""
        import json

        headers = {
            "Authorization": f"Bot {self._token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        data = json.dumps(body, default=str).encode()

        if self._client_factory is not None:
            client = self._client_factory()
            if verb == "PATCH":
                response = await client.patch(url, content=data, headers=headers)
            else:
                response = await client.post(url, content=data, headers=headers)
            return _json_or_raise(response)

        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "httpx is required for Discord connectivity; "
                "install with: pip install gaiaagent[http]"
            ) from exc

        transport = httpx.AsyncClient(timeout=self._timeout)
        async with transport as client:
            if verb == "PATCH":
                response = await client.patch(url, content=data, headers=headers)
            else:
                response = await client.post(url, content=data, headers=headers)
            return _json_or_raise(response)


def _json_or_raise(response: Any) -> dict[str, Any]:
    """Extract JSON from an httpx-like response, raising on HTTP errors."""
    raise_for_status = getattr(response, "raise_for_status", None)
    if callable(raise_for_status):
        raise_for_status()
    else:
        status = getattr(response, "status_code", 200)
        if status >= 400:
            raise RuntimeError(f"Discord API returned HTTP {status}")
    data = response.json()
    if isinstance(data, dict):
        return data
    return {"result": data}


def _build_response(original: AURCMessage, discord_reply: dict[str, Any]) -> AURCMessage:
    """Build an AURC RESPONSE from a Discord Bot API reply.

    Discord returns the created/edited message object on success (``{"id": ...,
    "channel_id": ..., "content": ...}``) or an error body
    (``{"message": "...", "code": N}``) alongside an HTTP error status, which
    :func:`_json_or_raise` already turns into a raised exception (routed to a
    transport error response). A response without an ``id`` is treated as a
    Discord-level failure.
    """
    if "id" not in discord_reply:
        # No message id => Discord refused (e.g. rate-limited, bad channel).
        return _error_response(
            original,
            code="discord_error",
            message=str(discord_reply.get("message", "discord request failed")),
            recoverable=False,
        )

    result = {
        k: v
        for k, v in discord_reply.items()
        if k not in ("message", "code")
    }
    return AURCMessage(
        source=original.target,
        target=original.source,
        type=MessageDirection.RESPONSE,
        correlation_id=original.correlation_id or original.message_id,
        body=MessageBody(
            result=result,
            metadata={"in_response_to": original.message_id},
        ),
        protocol_context=original.protocol_context,
    )


def _error_response(
    original: AURCMessage, *, code: str, message: str, recoverable: bool = True
) -> AURCMessage:
    return AURCMessage(
        source=original.target,
        target=original.source,
        type=MessageDirection.RESPONSE,
        correlation_id=original.correlation_id or original.message_id,
        body=MessageBody(
            error=ErrorInfo(code=code, message=message, recoverable=recoverable),
            metadata={"in_response_to": original.message_id},
        ),
        protocol_context=original.protocol_context,
    )
