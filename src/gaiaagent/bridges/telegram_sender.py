"""Telegram network sender -- turns TelegramBridge from a translator into a connector.

A :class:`TelegramBridge` only translates formats (AURC <-> Telegram). A
:class:`TelegramSender` wraps a bridge and adds the missing *connectivity*: it
takes an outbound AURCMessage, translates it to a Telegram Bot API payload,
POSTs it to ``https://api.telegram.org/bot<token>/<method>``, and builds an
AURC response from the Telegram reply.

Telegram's Bot API differs from the MCP/A2A/ACP servers that
:class:`BridgeConnector` targets: the host is fixed (``api.telegram.org``),
auth is the bot token embedded in the URL path (not a bearer header), and the
method is chosen per-message (``sendMessage`` / ``editMessageText``), so it
gets its own thin sender rather than reusing the base ``BridgeConnector``.

Like ``BridgeConnector`` it accepts an injectable ``client_factory`` so tests
can run the full translate -> POST -> build-response loop with no network.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ..core.message import AURCMessage, ErrorInfo, MessageBody
from ..core.types import MessageDirection
from .telegram import TelegramBridge

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"

# A fake async client shape compatible with the one used by BridgeConnector
# tests: ``await client.post(url, content=..., headers=...) -> response`` with
# ``response.status_code`` / ``response.json()`` / ``response.raise_for_status``.
TelegramClientFactory = Callable[..., Any]


class TelegramSender:
    """Sends AURC messages to Telegram and translates the reply back.

    Usage::

        sender = TelegramSender(token="123456:ABC-DEF")
        router.register_bridge_forwarder("telegram", sender.forward)

    When the router routes a message whose target starts with ``telegram:``,
    it calls ``sender.forward(msg)`` which:
        1. translates ``msg`` to a Telegram Bot API payload (method + body),
        2. POSTs it to ``https://api.telegram.org/bot<token>/<method>``,
        3. builds an AURC RESPONSE from the Telegram reply (ok/ok=false),
        4. returns that response, so the caller gets a well-formed result.
    """

    def __init__(
        self,
        *,
        token: str,
        bridge: TelegramBridge | None = None,
        timeout_seconds: float = 30.0,
        client_factory: TelegramClientFactory | None = None,
    ) -> None:
        self._token = token
        self._bridge = bridge or TelegramBridge()
        self._timeout = timeout_seconds
        self._client_factory = client_factory

    @property
    def bridge(self) -> TelegramBridge:
        return self._bridge

    async def forward(self, message: AURCMessage) -> AURCMessage:
        """Translate -> POST -> translate back. Returns an AURC response.

        On any failure (network error, Telegram ``ok=false``) a *response* AURC
        message carrying an ErrorInfo is returned rather than raising, so the
        router always gets a well-formed result it can act on.
        """
        try:
            payload = await self._bridge.translate_from_aurc(message)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception(
                "TelegramSender: translate_from_aurc failed for %s", message.target
            )
            return _error_response(message, code="translation_error", message=str(exc))

        method = str(payload.get("method", "sendMessage"))
        url = f"{TELEGRAM_API_BASE}/bot{self._token}/{method}"
        body = {k: v for k, v in payload.items() if k != "method"}

        try:
            response_data = await self._send(url, body)
        except Exception as exc:
            logger.warning("TelegramSender POST to %s failed: %s", url, exc)
            return _error_response(
                message, code="transport_error", message=str(exc), recoverable=True
            )

        return _build_response(message, response_data)

    async def _send(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST the translated payload with the bot token in the URL, return JSON."""
        import json

        headers = {"Content-Type": "application/json; charset=utf-8"}

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
                "httpx is required for Telegram connectivity; "
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
            raise RuntimeError(f"Telegram API returned HTTP {status}")
    data = response.json()
    if isinstance(data, dict):
        return data
    return {"result": data}


def _build_response(original: AURCMessage, telegram_reply: dict[str, Any]) -> AURCMessage:
    """Build an AURC RESPONSE from a Telegram Bot API reply.

    Telegram replies are ``{"ok": true, "result": {...}}`` on success or
    ``{"ok": false, "error_code": 400, "description": "..."}`` on failure.
    """
    if not telegram_reply.get("ok", False):
        return _error_response(
            original,
            code="telegram_error",
            message=str(
                telegram_reply.get("description", "telegram request failed")
            ),
            recoverable=False,
        )

    result = telegram_reply.get("result")
    if result is None:
        result = {k: v for k, v in telegram_reply.items() if k != "ok"}
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
