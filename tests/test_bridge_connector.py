"""Tests for BridgeConnector - the real-network bridge forwarder.

These verify the full translate -> POST -> build-response loop without touching
the network, using a fake async client injected via client_factory.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from gaiaagent.bridges.a2a import A2ABridge
from gaiaagent.bridges.acp import ACPBridge
from gaiaagent.bridges.base import MCPBridge
from gaiaagent.bridges.connector import BridgeConnector
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"external server returned HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    """Records the last POST and returns a canned response (or raises)."""
    def __init__(
        self,
        response: _FakeResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.posted_url: str | None = None
        self.posted_payload: dict[str, Any] | None = None

    async def post(self, url: str, content: bytes, headers: dict[str, str]) -> _FakeResponse:
        self.posted_url = url
        self.posted_payload = json.loads(content)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def _make_delegation(target: str = "a2a:external/expert", correlation: str = "c-1") -> AURCMessage:
    return AURCMessage(
        source="aurc:demo/orchestrator:v1.0",
        target=target,
        type=MessageDirection.DELEGATION,
        correlation_id=correlation,
        body=MessageBody(
            method="invoke",
            skill="research",
            params={"task_id": "t-1", "content": "Analyze AURC"},
        ),
    )


@pytest.mark.asyncio
async def test_forward_success_round_trip() -> None:
    fake = _FakeClient(response=_FakeResponse(200, {"result": {"answer": "42"}}))
    connector = BridgeConnector(
        bridge=A2ABridge(),
        resolver=lambda tgt: "http://localhost:9001",
        client_factory=lambda: fake,
    )
    resp = await connector.forward(_make_delegation())

    assert resp.type == MessageDirection.RESPONSE
    assert resp.target == "aurc:demo/orchestrator:v1.0"
    assert resp.source == "a2a:external/expert"
    assert resp.correlation_id == "c-1"
    assert resp.body.result == {"answer": "42"}
    assert resp.body.error is None
    # The connector actually translated and POSTed a real payload.
    assert fake.posted_url == "http://localhost:9001/"
    assert fake.posted_payload is not None and "method" in fake.posted_payload


@pytest.mark.asyncio
async def test_forward_unresolved_target_returns_error_response() -> None:
    connector = BridgeConnector(
        bridge=A2ABridge(),
        resolver=lambda tgt: None,  # unknown target
        client_factory=lambda: _FakeClient(),
    )
    resp = await connector.forward(_make_delegation())

    assert resp.type == MessageDirection.RESPONSE
    assert resp.body.error is not None
    assert resp.body.error.code == "target_unresolved"
    assert resp.body.error.recoverable is True


@pytest.mark.asyncio
async def test_forward_transport_error_returns_recoverable_error() -> None:
    fake = _FakeClient(error=ConnectionError("refused"))
    connector = BridgeConnector(
        bridge=A2ABridge(),
        resolver=lambda tgt: "http://localhost:9001",
        client_factory=lambda: fake,
    )
    resp = await connector.forward(_make_delegation())

    assert resp.body.error is not None
    assert resp.body.error.code == "transport_error"
    assert resp.body.error.recoverable is True


@pytest.mark.asyncio
async def test_forward_external_error_payload() -> None:
    fake = _FakeClient(response=_FakeResponse(200, {
        "error": {"code": "agent_busy", "message": "try later"},
    }))
    connector = BridgeConnector(
        bridge=ACPBridge(),
        resolver=lambda tgt: "http://localhost:9002",
        client_factory=lambda: fake,
    )
    resp = await connector.forward(_make_delegation(target="acp:external/worker"))

    assert resp.body.error is not None
    assert resp.body.error.code == "agent_busy"
    assert resp.body.error.message == "try later"


@pytest.mark.asyncio
async def test_forward_http_4xx_is_transport_error() -> None:
    fake = _FakeClient(response=_FakeResponse(500, {"error": "boom"}))
    connector = BridgeConnector(
        bridge=A2ABridge(),
        resolver=lambda tgt: "http://localhost:9001",
        client_factory=lambda: fake,
    )
    resp = await connector.forward(_make_delegation())

    assert resp.body.error is not None
    assert resp.body.error.code == "transport_error"


@pytest.mark.asyncio
async def test_router_integration_real_forwarder() -> None:
    """End-to-end: router routes to a registered BridgeConnector forwarder and
    gets back a real AURC response, not the demo's stub dict."""
    from gaiaagent.bus.router import MessageRouter

    fake = _FakeClient(response=_FakeResponse(200, {"result": "ok-from-a2a"}))
    router = MessageRouter()
    connector = BridgeConnector(
        bridge=A2ABridge(),
        resolver=lambda tgt: "http://localhost:9001",
        client_factory=lambda: fake,
    )
    router.register_bridge_forwarder("a2a", connector.forward)

    result = await router.route(_make_delegation())

    assert isinstance(result, AURCMessage)
    assert result.type == MessageDirection.RESPONSE
    assert result.body.result == "ok-from-a2a"
    assert router.stats.bridged == 1


@pytest.mark.asyncio
async def test_default_path_per_protocol() -> None:
    assert BridgeConnector(MCPBridge(), lambda t: "http://x")._path == "/mcp"
    assert BridgeConnector(A2ABridge(), lambda t: "http://x")._path == "/"
    assert BridgeConnector(ACPBridge(), lambda t: "http://x")._path == "/agents/runs"


@pytest.mark.asyncio
async def test_acp_round_trip_preserves_correlation() -> None:
    fake = _FakeClient(response=_FakeResponse(200, {"status": "completed", "result": {"d": 1}}))
    connector = BridgeConnector(
        bridge=ACPBridge(),
        resolver=lambda tgt: "http://localhost:9002",
        client_factory=lambda: fake,
    )
    resp = await connector.forward(
        _make_delegation(target="acp:external/worker", correlation="acp-corr")
    )

    assert resp.correlation_id == "acp-corr"
    assert resp.body.result == {"d": 1}
    # ACP invoke was actually produced and sent.
    assert fake.posted_payload is not None
    assert fake.posted_payload.get("method") == "invoke"
