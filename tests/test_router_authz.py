"""Hot-path authorization: RouteAuthzGuard on the MessageRouter.

Verifies that an attached authorizer is enforced on every routed message
(fail-closed), that denial increments RouterStats.denied, and that leaving
the authorizer unset preserves the legacy unauthenticated behavior.
"""
from __future__ import annotations

import pytest

from gaiaagent.bus.router import MessageRouter
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection
from gaiaagent.security.authz import (
    AgentPolicy,
    AuthorizationEngine,
    AuthorizationRule,
    Constraint,
)
from gaiaagent.security.message_authz import AuthzDeniedError, RouteAuthzGuard


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


def _msg(source: str, target: str, skill: str) -> AURCMessage:
    return AURCMessage(
        source=source,
        target=target,
        type=MessageDirection.REQUEST,
        body=MessageBody(method="invoke", skill=skill, params={"q": "hi"}),
    )


@pytest.mark.asyncio
async def test_no_authorizer_routes_normally() -> None:
    """Backward compat: no authorizer => identical unauthenticated behavior."""
    router = MessageRouter()

    called: list[bool] = []

    async def handler(msg: AURCMessage) -> dict[str, str]:
        called.append(True)
        return {"result": "ok"}

    router.register_handler("aurc:local/worker", handler)
    res = await router.route(_msg("aurc:local/alice", "aurc:local/worker", "greet"))
    assert res == {"result": "ok"}
    assert called == [True]
    stats = router.stats.to_dict()
    assert stats["direct"] == 1
    assert stats["denied"] == 0


@pytest.mark.asyncio
async def test_authorizer_denies_when_no_policy() -> None:
    """Fail-closed: a message with no matching policy is denied."""
    router = MessageRouter()
    router.set_authorizer(RouteAuthzGuard(AuthorizationEngine()))  # no policies

    async def handler(msg: AURCMessage) -> dict[str, str]:
        return {"result": "should-not-reach"}

    router.register_handler("aurc:local/worker", handler)
    with pytest.raises(AuthzDeniedError):
        await router.route(_msg("aurc:local/mallory", "aurc:local/worker", "greet"))

    stats = router.stats.to_dict()
    assert stats["denied"] == 1
    assert stats["direct"] == 0  # handler never reached


@pytest.mark.asyncio
async def test_authorizer_allows_when_policy_matches() -> None:
    router = MessageRouter()
    router.set_authorizer(RouteAuthzGuard(_engine_with_policy("aurc:local/alice", "greet")))

    async def handler(msg: AURCMessage) -> dict[str, str]:
        return {"result": "ok"}

    router.register_handler("aurc:local/worker", handler)
    res = await router.route(_msg("aurc:local/alice", "aurc:local/worker", "greet"))
    assert res == {"result": "ok"}
    stats = router.stats.to_dict()
    assert stats["direct"] == 1
    assert stats["denied"] == 0


@pytest.mark.asyncio
async def test_authorizer_denies_constraint_violation() -> None:
    engine = AuthorizationEngine()
    engine.set_policy(
        "aurc:local/alice",
        AgentPolicy(
            agent_id="aurc:local/alice",
            rules=[
                AuthorizationRule(
                    resource_type="greet",
                    actions=["invoke"],
                    constraints=[Constraint("domain", "matches", r".*\.edu$")],
                )
            ],
        ),
    )
    router = MessageRouter()
    router.set_authorizer(RouteAuthzGuard(engine))

    async def handler(msg: AURCMessage) -> dict[str, str]:
        return {"result": "should-not-reach"}

    router.register_handler("aurc:local/worker", handler)
    msg = _msg("aurc:local/alice", "aurc:local/worker", "greet")
    msg.body.params["domain"] = "evil.com"
    with pytest.raises(AuthzDeniedError):
        await router.route(msg)
    assert router.stats.to_dict()["denied"] == 1


@pytest.mark.asyncio
async def test_authorizer_strips_external_qualifier() -> None:
    """Bridged source 'a2a:external/<id>' is authorized as the raw agent id."""
    router = MessageRouter()
    router.set_authorizer(RouteAuthzGuard(_engine_with_policy("bob", "greet")))

    async def handler(msg: AURCMessage) -> dict[str, str]:
        return {"result": "ok"}

    router.register_handler("aurc:local/worker", handler)
    res = await router.route(_msg("a2a:external/bob", "aurc:local/worker", "greet"))
    assert res == {"result": "ok"}
    assert router.stats.to_dict()["denied"] == 0


@pytest.mark.asyncio
async def test_authorizer_denies_broadcast_too() -> None:
    """Authz applies to broadcast routing, not just direct."""
    router = MessageRouter()
    router.set_authorizer(RouteAuthzGuard(AuthorizationEngine()))  # deny all

    async def handler(msg: AURCMessage) -> None:
        pytest.fail("subscriber should not be called when denied")

    router.subscribe("aurc:group/researchers", handler)
    with pytest.raises(AuthzDeniedError):
        await router.route(_msg("aurc:local/alice", "aurc:group/researchers", "ping"))
    assert router.stats.to_dict()["denied"] == 1
