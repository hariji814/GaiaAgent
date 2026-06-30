"""Slack network sender -- turns SlackBridge from a translator into a connector.

A :class:`SlackBridge` only translates formats (AURC <-> Slack).  A
:class:`SlackSender` wraps a bridge and adds the missing *connectivity*: it
takes an outbound AURCMessage, translates it to a Slack Web API payload, POSTs
it to ``https://slack.com/api/<method>`` with a Bearer token, and builds an
AURC response from the Slack reply.

Slack's API differs from the MCP/A2A/ACP servers that :class:`BridgeConnector`
targets: the host is fixed (``slack.com``), auth is a single bearer token, and
the method is chosen per-message (``chat.postMessage`` / ``chat.update``), so
it gets its own thin sender rather than reusing the base ``BridgeConnector``.

Like ``BridgeConnector`` it accepts an injectable ``client_factory`` so tests
can run the full translate -> POST -> build-response loop with no network.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ..core.message import AURCMessage, ErrorInfo, MessageBody
from ..core.types import MessageDirection
from .slack import SlackBridge

logger = logging.getLogger(__name__)

SLACK_API_BASE = "https://slack.com/api"

# A fake async client shape compatible with the one used by BridgeConnector
# tests: ``await client.post(url, content=..., headers=...) -> response`` with
# ``response.status_code`` / ``response.json()`` / ``response.raise_for_status``.
SlackClientFactory = Callable[..., Any]


class SlackSender:
    """Sends AURC messages to Slack and translates the reply back.

    Usage::

        sender = SlackSender(token="xoxb-...")
        router.register_bridge_forwarder("slack", sender.forward)

    When the router routes a message whose target starts with ``slack:``, it
    calls ``sender.forward(msg)`` which:
        1. translates ``msg`` to a Slack Web API payload (method + body),
        2. POSTs it to ``https://slack.com/api/<method>`` with the bearer token,
        3. builds an AURC RESPONSE from the Slack reply (ok/ok=false),
        4. returns that response, so the caller gets a well-formed result.
    """

    def __init__(
        self,
        *,
        token: str,
        bridge: SlackBridge | None = None,
        timeout_seconds: float = 30.0,
        client_factory: SlackClientFactory | None = None,
    ) -> None:
        self._token = token
        self._bridge = bridge or SlackBridge()
        self._timeout = timeout_seconds
        self._client_factory = client_factory

    @property
    def bridge(self) -> SlackBridge:
        return self._bridge

    async def forward(self, message: AURCMessage) -> AURCMessage:
        """Translate -> POST -> translate back. Returns an AURC response.

        On any failure (network error, Slack ``ok=false``) a *response* AURC
        message carrying an ErrorInfo is returned rather than raising, so the
        router always gets a well-formed result it can act on.
        """
        try:
            payload = await self._bridge.translate_from_aurc(message)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("SlackSender: translate_from_aurc failed for %s", message.target)
            return _error_response(message, code="translation_error", message=str(exc))

        method = str(payload.get("method", "chat.postMessage"))
        url = f"{SLACK_API_BASE}/{method}"
        body = {k: v for k, v in payload.items() if k != "method"}

        try:
            response_data = await self._send(url, body)
        except Exception as exc:
            logger.warning("SlackSender POST to %s failed: %s", url, exc)
            return _error_response(
                message, code="transport_error", message=str(exc), recoverable=True
            )

        return _build_response(message, response_data)

    async def _send(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST the translated payload with the bearer token, return JSON."""
        import json

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        if self._client_factory is not None:
            client = self._client_factory()
            response = await client.post(
                url,
                content=json.dumps(body, default=str).encode(),
                headers=headers,
            )
            return _json_or_raise(response)

        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "httpx is required for Slack connectivity; "
                "install with: pip install gaiaagent[http]"
            ) from exc

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, json=body, headers=headers)
            return _json_or_raise(response)


def _json_or_raise(response: Any) -> dict[str, Any]:
    """Extract JSON from an httpx-like response, raising on HTTP errors."""
    raise_for_status = getattr(response, "raise_for_status", None)
    if callable(raise_for_status):
        raise_for_status()
    else:
        status = getattr(response, "status_code", 200)
        if status >= 400:
            raise RuntimeError(f"Slack API returned HTTP {status}")
    data = response.json()
    if isinstance(data, dict):
        return data
    return {"result": data}


def _build_response(original: AURCMessage, slack_reply: dict[str, Any]) -> AURCMessage:
    """Build an AURC RESPONSE from a Slack Web API reply.

    Slack replies are ``{"ok": true, "channel": ..., "ts": ...}`` on success or
    ``{"ok": false, "error": "..."}`` on failure.
    """
    if not slack_reply.get("ok", False):
        return _error_response(
            original,
            code="slack_error",
            message=str(slack_reply.get("error", "slack request failed")),
            recoverable=False,
        )

    result = {
        k: v
        for k, v in slack_reply.items()
        if k not in ("ok", "error")
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
