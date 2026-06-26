"""Tests for `aurc serve` - real routing through the ASGI app without uvicorn."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest

from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection


def _make_invoke_msg(skill: str, **params: Any) -> dict[str, Any]:
    return AURCMessage(
        source="aurc:test/caller:v1.0",
        target="aurc:builtin/echo:v1.0",
        type=MessageDirection.REQUEST,
        body=MessageBody(method="invoke", skill=skill, params=params),
    ).model_dump(mode="json")


class TestCLIServeRouting:
    def setup_method(self) -> None:
        from gaiaagent.cli import _make_echo_agent
        from gaiaagent.server import AURCServer
        from gaiaagent.transport.http import HTTPTransportServer

        self._loop = asyncio.new_event_loop()
        self.aurc = AURCServer()
        self._loop.run_until_complete(self.aurc.register_agent(_make_echo_agent()))
        self.http = HTTPTransportServer(host="127.0.0.1", port=8080)
        self.http.set_handler(self.aurc.http_handler)
        self.app = self.http._create_app()

    def teardown_method(self) -> None:
        self._loop.close()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    async def test_post_aurc_echo(self) -> None:
        async with self._client() as client:
            resp = await client.post("/aurc", json=_make_invoke_msg("echo", text="ping"))
        assert resp.status_code == 200
        assert resp.json()["result"] == {"echo": "ping"}

    async def test_post_aurc_undoc_skill(self) -> None:
        async with self._client() as client:
            resp = await client.post("/aurc", json=_make_invoke_msg("nope"))
        assert resp.status_code == 200
        assert resp.json()["error"]["code"] == "skill_not_found"

    async def test_health_endpoint(self) -> None:
        async with self._client() as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestAgentLoader:
    def test_load_agent_from_file(self, tmp_path: Path) -> None:
        from gaiaagent.cli import _load_agent_module

        agent_src = (
            "from typing import Any\n"
            "from gaiaagent.sdk.decorators import aurc_agent, skill\n"
            "\n"
            '@aurc_agent(id="aurc:test/loaded:v1.0", display_name="Loaded")\n'
            "class LoadedAgent:\n"
            '    @skill("square", description="Square a number")\n'
            "    async def square(self, n: int) -> dict[str, Any]:\n"
            '        return {"squared": n * n}\n'
        )
        agent_path = tmp_path / "agent.py"
        agent_path.write_text(agent_src, encoding="utf-8")
        agent = _load_agent_module(str(agent_path))
        assert agent.aurc_descriptor.aurc_id == "aurc:test/loaded:v1.0"
        assert hasattr(agent, "square")

    def test_load_agent_no_aurc_class(self, tmp_path: Path) -> None:
        from gaiaagent.cli import _load_agent_module

        plain_path = tmp_path / "plain.py"
        plain_path.write_text("x = 1\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            _load_agent_module(str(plain_path))
