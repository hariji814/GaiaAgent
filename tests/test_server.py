"""Tests for AURCServer - the real routing + lifecycle HTTP handler."""
from __future__ import annotations

from typing import Any

from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection
from gaiaagent.sdk.decorators import aurc_agent, skill
from gaiaagent.server import AURCServer


@aurc_agent(
    id="aurc:test/greeter:v1.0",
    display_name="Greeter",
    description="test agent",
    protocols=["mcp/2025-06-18"],)
class Greeter:
    @skill("greet", description="Greet by name")
    async def greet(self, name: str) -> dict[str, Any]:
        return {"message": "Hello, " + name + "!"}

    @skill("echo", description="Echo input")
    async def echo(self, text: str) -> dict[str, Any]:
        return {"echo": text}


def _invoke_msg(skill: str, **params: Any) -> dict[str, Any]:
    return AURCMessage(
        source="aurc:test/caller:v1.0",
        target="aurc:test/greeter:v1.0",
        type=MessageDirection.REQUEST,
        body=MessageBody(method="invoke", skill=skill, params=params),
    ).model_dump(mode="json")


async def test_register_and_invoke_skill() -> None:
    server = AURCServer()
    await server.register_agent(Greeter())

    resp = await server.http_handler(_invoke_msg("greet", name="World"))

    assert resp["result"]["message"] == "Hello, World!"
    assert server.router.stats.direct == 1


async def test_unknown_skill_returns_structured_error() -> None:
    server = AURCServer()
    await server.register_agent(Greeter())

    resp = await server.http_handler(_invoke_msg("nope"))

    assert resp["error"]["code"] == "skill_not_found"


async def test_bad_params_returns_recoverable_error() -> None:
    server = AURCServer()
    await server.register_agent(Greeter())

    # greet requires `name`; omitting it should surface a bad_skill_params error.
    resp = await server.http_handler(_invoke_msg("greet"))

    assert resp["error"]["code"] == "bad_skill_params"
    assert resp["error"]["recoverable"] is True


async def test_invalid_message_returns_bad_message() -> None:
    server = AURCServer()
    resp = await server.http_handler({"not": "an aurc message"})
    assert resp["error"]["code"] == "bad_message"


async def test_agent_lifecycle_tracked_by_harness() -> None:
    server = AURCServer()
    await server.register_agent(Greeter())

    instance = server.harness.get_agent("aurc:test/greeter:v1.0")
    assert instance is not None
    from gaiaagent.core.types import AgentState
    assert instance.state == AgentState.RUNNING
