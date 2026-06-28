"""Ingress hardening for HTTPTransportServer (TODO P1-2).

Covers: body-size overflow -> 413, rate limiting -> 429, request timeout,
and the structured error envelope that never leaks raw exception text.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from gaiaagent.transport.http import HTTPMessageHandler, HTTPTransportServer, IngressLimits


def _build(limits: IngressLimits, handler: HTTPMessageHandler) -> Any:
    """Wire a server with the given ingress policy and handler; return its ASGI app."""
    server = HTTPTransportServer(host="127.0.0.1", port=0)
    server.set_ingress_limits(limits)
    server.set_handler(handler)
    return server._create_app()


def _client(app: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _ok(_data: dict[str, Any]) -> dict[str, Any]:
    return {"result": {"ok": True}}


async def test_body_overflow_returns_413() -> None:
    limits = IngressLimits(max_body_bytes=64, rate_limit=None)
    app = _build(limits, _ok)
    async with _client(app) as c:
        resp = await c.post("/aurc", content=b"x" * 256)
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "payload_too_large"


async def test_rate_limit_returns_429() -> None:
    # rate=1/s, burst=2 -> only ~2 requests pass before the bucket empties.
    limits = IngressLimits(rate_limit=1.0, rate_burst=2.0)
    app = _build(limits, _ok)
    codes: list[int] = []
    async with _client(app) as c:
        for _ in range(10):
            resp = await c.post("/aurc", json={})
            codes.append(resp.status_code)
    assert 429 in codes
    # The 429 body must be the structured envelope.
    body = None
    async with _client(app) as c:
        for _ in range(10):
            resp = await c.post("/aurc", json={})
            if resp.status_code == 429:
                body = resp.json()
                break
    assert body is not None
    assert body["error"]["code"] == "rate_limited"


async def test_handler_error_does_not_leak_exception_text() -> None:
    async def boom(_data: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("secret: /etc/passwd")

    app = _build(IngressLimits(rate_limit=None), boom)
    async with _client(app) as c:
        resp = await c.post("/aurc", json={})
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "internal_error"
    assert "secret" not in resp.text
    assert "/etc/passwd" not in resp.text


async def test_extra_route_error_uses_structured_envelope() -> None:
    async def boom(_data: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("secret boom")

    server = HTTPTransportServer(host="127.0.0.1", port=0)
    server.set_ingress_limits(IngressLimits(rate_limit=None))
    server.set_handler(_ok)
    server.set_route("/boom", boom)
    app = server._create_app()
    async with _client(app) as c:
        resp = await c.post("/boom", json={})
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "internal_error"
    assert "secret" not in resp.text


async def test_request_timeout_maps_to_internal_error() -> None:
    async def slow(_data: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(5)
        return {"result": "never"}

    limits = IngressLimits(rate_limit=None, request_timeout=0.1)
    app = _build(limits, slow)
    async with _client(app) as c:
        resp = await c.post("/aurc", json={})
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "internal_error"


async def test_normal_request_succeeds_under_defaults() -> None:
    async def echo(data: dict[str, Any]) -> dict[str, Any]:
        return {"result": data}

    app = _build(IngressLimits(), echo)
    async with _client(app) as c:
        resp = await c.post("/aurc", json={"hello": "world"})
    assert resp.status_code == 200
    assert resp.json()["result"]["hello"] == "world"
