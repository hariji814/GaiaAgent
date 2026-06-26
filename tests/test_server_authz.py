"""AURCServer authorization: forbidden envelope on denial, success when allowed.

Covers the server-level mapping of AuthzDeniedError (raised by the router's
hot-path guard) to a structured 'forbidden' error envelope, and confirms
that servers without an authz_engine keep the legacy behavior.
"""
from __future__ import annotations

import pytest

from gaiaagent.sdk.decorators import aurc_agent, skill
from gaiaagent.security.authz import (
    AgentPolicy,
    AuthorizationEngine,
    AuthorizationRule,
)
from gaiaagent.security.message_authz import RouteAuthzGuard
from gaiaagent.server import AURCServer

WORKER_ID = "aurc:local/worker:v1.0"


def _msg_dict(source: str, skill: str) -> dict:
    return {
        "source": source,
        "target": WORKER_ID,
        "type": "request",
        "body": {"method": "invoke", "skill": skill, "params": {"name": "world"}},
    }


@aurc_agent(id=WORKER_ID)
class _WorkerAgent:
    @skill("greet")
    async def greet(self, name: str = "world") -> str:
        return f"hello {name}"


def _engine_with_policy(agent_id: str, skill: str) -> AuthorizationEngine:
    engine = AuthorizationEngine()
    engine.set_policy(
        agent_id,
        AgentPolicy(
            agent_id=agent_id,
            rules=[AuthorizationRule(resource_type=skill, actions=["invoke"])],
        ),
    )
    return engine


@pytest.mark.asyncio
async def test_server_without_authz_routes_normally() -> None:
    """Backward compat: server with no authz_engine behaves as before."""
    server = AURCServer()
    await server.register_agent(_WorkerAgent())
    res = await server.http_handler(_msg_dict("aurc:local/alice", "greet"))
    assert res["result"] == "hello world"


@pytest.mark.asyncio
async def test_server_denies_with_forbidden_envelope() -> None:
    """No policy => AuthzDeniedError => 'forbidden' envelope, not a route_error."""
    server = AURCServer(authz_engine=AuthorizationEngine())  # deny all
    await server.register_agent(_WorkerAgent())
    res = await server.http_handler(_msg_dict("aurc:local/mallory", "greet"))
    assert "error" in res
    assert res["error"]["code"] == "forbidden"
    assert res["error"]["recoverable"] is False
    assert res["error"]["message"]  # non-empty reason


@pytest.mark.asyncio
async def test_server_allows_when_policy_matches() -> None:
    server = AURCServer(
        authz_engine=_engine_with_policy("aurc:local/alice", "greet")
    )
    await server.register_agent(_WorkerAgent())
    res = await server.http_handler(_msg_dict("aurc:local/alice", "greet"))
    assert res["result"] == "hello world"


@pytest.mark.asyncio
async def test_server_accepts_explicit_authorizer() -> None:
    """An explicit authorizer takes precedence over authz_engine wiring."""
    guard = RouteAuthzGuard(_engine_with_policy("aurc:local/alice", "greet"))
    server = AURCServer(authorizer=guard)
    await server.register_agent(_WorkerAgent())
    res = await server.http_handler(_msg_dict("aurc:local/alice", "greet"))
    assert res["result"] == "hello world"
    # A denial through the same guard maps to forbidden too
    res2 = await server.http_handler(_msg_dict("aurc:local/mallory", "greet"))
    assert res2["error"]["code"] == "forbidden"
