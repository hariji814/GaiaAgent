"""Tests for HTTPTransportServer routing: POST /aurc, extra routes, health."""
from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

import httpx
import pytest

from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection


def _make_aurc(skill: str, **params: Any) -> dict[str, Any]:
    return AURCMessage(
        source="aurc:test/caller:v1.0",
        target="aurc:builtin/echo:v1.0",
        type=MessageDirection.REQUEST,
        body=MessageBody(method="invoke", skill=skill, params=params),
    ).model_dump(mode="json")


class _ServerHarness:
    """Wires AURCServer + HTTPTransportServer without uvicorn."""

    def __init__(self) -> None:
        import asyncio

        from gaiaagent.cli import _make_echo_agent
        from gaiaagent.server import AURCServer
        from gaiaagent.transport.http import HTTPTransportServer

        self._loop = asyncio.new_event_loop()
        self.aurc = AURCServer()
        self._loop.run_until_complete(self.aurc.register_agent(_make_echo_agent()))
        self.http = HTTPTransportServer(host="127.0.0.1", port=8080)
        self.http.set_handler(self.aurc.http_handler)
        self.app = self.http._create_app()

    def close(self) -> None:
        self._loop.close()

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )


@pytest.fixture()
def server() -> Generator[_ServerHarness, None, None]:
    h = _ServerHarness()
    yield h
    h.close()


async def test_post_aurc_routes_to_skill(server: _ServerHarness) -> None:
    async with server.client() as client:
        resp = await client.post("/aurc", json=_make_aurc("echo", text="hi"))
    assert resp.status_code == 200
    assert resp.json()["result"] == {"echo": "hi"}


async def test_extra_route_via_set_route(server: _ServerHarness) -> None:
    async def a2a_handler(payload: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": payload.get("id"), "result": {"ok": True}}

    server.http.set_route("/a2a", a2a_handler)
    async with server.client() as client:
        resp = await client.post("/a2a", json={"jsonrpc": "2.0", "id": "1", "method": "ping"})
    assert resp.status_code == 200
    assert resp.json()["result"] == {"ok": True}


async def test_extra_route_error_returns_500(server: _ServerHarness) -> None:
    async def boom(payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("boom")

    server.http.set_route("/boom", boom)
    async with server.client() as client:
        resp = await client.post("/boom", json={})
    assert resp.status_code == 500
    # Ingress hardening (TODO P1-2): errors exit via a structured envelope that
    # never echoes raw exception text to the wire.
    assert resp.json()["error"]["code"] == "internal_error"
    assert "boom" not in resp.text


async def test_health_endpoint(server: _ServerHarness) -> None:
    async with server.client() as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_unknown_path_returns_404(server: _ServerHarness) -> None:
    async with server.client() as client:
        resp = await client.get("/nope")
    assert resp.status_code == 404


def test_free_port_helper(tmp_path: Path) -> None:
    """Sanity: the examples helper returns a bindable port."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_e2e", Path("examples/e2e_cross_process.py")
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    port = mod._free_port()
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", port))
