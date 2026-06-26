"""
AURC Bridge Connector - turns bridges from translators into real network connectors.

A Bridge translates message *formats* (AURC <-> external protocol).  A
BridgeConnector wraps a Bridge and adds the missing *connectivity*: it takes an
outbound AURCMessage, translates it to the external format, sends it over the
wire (HTTP), and translates the response back to an AURC response message.

This is the piece that makes AURC a true interop runtime rather than just a
translation library: a MessageRouter registered with a BridgeConnector will
actually POST to a real external MCP/A2A/ACP server when a message targets an
``mcp:``/``a2a:``/``acp:`` address.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ..core.message import AURCMessage, ErrorInfo, MessageBody
from ..core.types import MessageDirection
from .base import ProtocolBridge

logger = logging.getLogger(__name__)

# A resolver maps an external target ID (e.g. "a2a:external/expert") to the
# real base URL of the external server (e.g. "http://localhost:9001").  This is
# pluggable so deployments can source URLs from a registry, env, config, etc.
TargetResolver = Callable[[str], str | None]
"""Resolve an external target AURC ID to a real base URL, or None if unknown."""


class BridgeConnector:
    """Connects a ProtocolBridge to the network so it can reach real servers.

    Usage::

        connector = BridgeConnector(
            bridge=A2ABridge(),
            resolver=lambda target: "http://localhost:9001",
        )
        router.register_bridge_forwarder("a2a", connector.forward)

    When the router routes a message whose target starts with `a2a:`, it will
    call `connector.forward(msg)` which:
        1. translates `msg` to the external protocol format,
        2. POSTs the translated payload to the resolved URL,
        3. builds an AURC RESPONSE from the HTTP response,
        4. returns that response (so the caller gets a real result, not a stub).
    """

    def __init__(
        self,
        bridge: ProtocolBridge,
        resolver: TargetResolver,
        *,
        path: str = "",
        timeout_seconds: float = 30.0,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._bridge = bridge
        self._resolver = resolver
        self._path = path or _default_path(bridge.source_protocol)
        self._timeout = timeout_seconds
        # Optional factory so tests can inject an httpx.MockTransport-backed
        # client without touching the network.  In production this is None and
        # we create a real httpx.AsyncClient per call.
        self._client_factory = client_factory

    @property
    def bridge(self) -> ProtocolBridge:
        return self._bridge

    async def forward(self, message: AURCMessage) -> AURCMessage:
        """Translate -> POST -> translate back. Returns an AURC response.

        On any failure (no URL, network error, bad status) a *response* AURC
        message carrying an ErrorInfo is returned rather than raising, so the
        router/delegator always gets a well-formed result it can act on.
        """
        target = message.target
        base_url = self._resolver(target)
        if not base_url:
            return _error_response(
                message,
                code="target_unresolved",
                message=f"No URL resolved for external target '{target}'",
            )
        url = base_url.rstrip("/") + self._path

        # 1. AURC -> external format
        try:
            external_payload = await self._bridge.translate_from_aurc(message)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("translate_from_aurc failed for %s", target)
            return _error_response(message, code="translation_error", message=str(exc))

        # 2. send over the wire
        try:
            response_data = await self._send(url, external_payload)
        except Exception as exc:
            logger.warning("BridgeConnector POST to %s failed: %s", url, exc)
            return _error_response(
                message, code="transport_error", message=str(exc), recoverable=True
            )

        # 3. external response -> AURC response
        return _build_response(message, response_data)

    async def _send(self, url: str, payload: Any) -> dict[str, Any]:
        """POST the translated payload and return the JSON response."""
        import json

        if self._client_factory is not None:
            client = self._client_factory()
            response = await client.post(
                url,
                content=json.dumps(payload, default=str).encode(),
                headers={
                    "Content-Type": "application/json",
                    "X-Protocol": self._bridge.source_protocol,
                },
            )
            return _json_or_raise(response)

        # Real network path (production).
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "httpx is required for bridge connectivity; "
                "install with: pip install gaiaagent[http]"
            ) from exc

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Protocol": self._bridge.source_protocol,
                },
            )
            return _json_or_raise(response)


def _json_or_raise(response: Any) -> dict[str, Any]:
    """Extract JSON from an httpx-like response, raising on HTTP errors."""
    raise_for_status = getattr(response, "raise_for_status", None)
    if callable(raise_for_status):
        raise_for_status()
    else:
        status = getattr(response, "status_code", 200)
        if status >= 400:
            raise RuntimeError(f"external server returned HTTP {status}")
    data = response.json()
    if isinstance(data, dict):
        return data
    return {"result": data}


def _build_response(original: AURCMessage, external_response: dict[str, Any]) -> AURCMessage:
    """Build an AURC RESPONSE message from an external protocol reply.

    External protocols return varied shapes (A2A: {result:{...}}, ACP:
    {status, result}, MCP: {result:{content:[...]}}).  We normalize the most
    useful field (`result` if present, else the whole payload) into the AURC
    response body and preserve the correlation chain.
    """
    if external_response.get("error"):
        err = external_response["error"]
        return AURCMessage(
            source=original.target,
            target=original.source,
            type=MessageDirection.RESPONSE,
            correlation_id=original.correlation_id or original.message_id,
            body=MessageBody(
                error=ErrorInfo(
                    code=str(err.get("code", "external_error")),
                    message=str(err.get("message", "external server error")),
                    details=err.get("details", {}) if isinstance(err, dict) else {},
                    recoverable=bool(err.get("recoverable", True)),
                ),
                metadata={"in_response_to": original.message_id},
            ),
            protocol_context=original.protocol_context,
        )

    result = external_response.get("result", external_response)
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


def _default_path(source_protocol: str) -> str:
    """Default URL path per protocol convention."""
    if source_protocol.startswith("a2a"):
        return "/"
    if source_protocol.startswith("acp"):
        return "/agents/runs"
    if source_protocol.startswith("mcp"):
        return "/mcp"
    return ""
