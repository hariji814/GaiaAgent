"""Authz auditability: RouteAuthzGuard writes decisions to an AuditLog.

Verifies the P0 audit closure: when an AuditLog is attached, denials are
recorded as AUTHZ_DENIED (WARNING) and grants as AUTHZ_GRANTED (INFO), that
log_grants=False suppresses grant records, and that AURCServer threads its
shared audit log into both the guard it constructs and a caller-supplied
guard. Because PrometheusMetricsExporter derives aurc_audit_events_total
from the audit log action stats, this is also what makes authz observable.
"""
from __future__ import annotations

import pytest

from gaiaagent.bus.router import MessageRouter
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection
from gaiaagent.sdk.decorators import aurc_agent, skill
from gaiaagent.security.audit import AuditAction, AuditLog, AuditSeverity
from gaiaagent.security.authz import (
    AgentPolicy,
    AuthorizationEngine,
    AuthorizationRule,
    Constraint,
)
from gaiaagent.security.message_authz import AuthzDeniedError, RouteAuthzGuard
from gaiaagent.server import AURCServer

WORKER_ID = "aurc:local/worker:v1.0"


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


def _engine_with_constraint(agent_id: str, skill: str) -> AuthorizationEngine:
    engine = AuthorizationEngine()
    engine.set_policy(
        agent_id,
        AgentPolicy(
            agent_id=agent_id,
            rules=[
                AuthorizationRule(
                    resource_type=skill,
                    actions=["invoke"],
                    constraints=[Constraint("domain", "matches", r".*\.edu$")],
                )
            ],
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
async def test_deny_writes_audit_entry() -> None:
    audit = AuditLog()
    router = MessageRouter()
    router.set_authorizer(
        RouteAuthzGuard(AuthorizationEngine(), audit=audit)  # deny all
    )

    async def handler(msg: AURCMessage) -> dict[str, str]:
        return {"result": "should-not-reach"}

    router.register_handler("aurc:local/worker", handler)
    msg = _msg("aurc:local/mallory", "aurc:local/worker", "greet")
    with pytest.raises(AuthzDeniedError):
        await router.route(msg)

    denied = audit.query(action=AuditAction.AUTHZ_DENIED)
    assert len(denied) == 1
    entry = denied[0]
    assert entry.severity == AuditSeverity.WARNING
    assert entry.agent_id == "aurc:local/mallory"
    assert entry.target_id == "aurc:local/worker"
    assert entry.message_id == msg.message_id
    assert entry.details["resource"] == "greet"
    assert entry.details["requested_action"] == "invoke"
    # No grant recorded for a denial.
    assert audit.query(action=AuditAction.AUTHZ_GRANTED) == []


@pytest.mark.asyncio
async def test_allow_writes_grant_entry() -> None:
    audit = AuditLog()
    router = MessageRouter()
    router.set_authorizer(
        RouteAuthzGuard(_engine_with_policy("aurc:local/alice", "greet"), audit=audit)
    )

    async def handler(msg: AURCMessage) -> dict[str, str]:
        return {"result": "ok"}

    router.register_handler("aurc:local/worker", handler)
    msg = _msg("aurc:local/alice", "aurc:local/worker", "greet")
    await router.route(msg)

    grants = audit.query(action=AuditAction.AUTHZ_GRANTED)
    assert len(grants) == 1
    assert grants[0].severity == AuditSeverity.INFO
    assert grants[0].agent_id == "aurc:local/alice"
    assert grants[0].details["resource"] == "greet"
    assert audit.query(action=AuditAction.AUTHZ_DENIED) == []


@pytest.mark.asyncio
async def test_log_grants_false_suppresses_grants() -> None:
    audit = AuditLog()
    router = MessageRouter()
    router.set_authorizer(
        RouteAuthzGuard(
            _engine_with_policy("aurc:local/alice", "greet"),
            audit=audit,
            log_grants=False,
        )
    )

    async def handler(msg: AURCMessage) -> dict[str, str]:
        return {"result": "ok"}

    router.register_handler("aurc:local/worker", handler)
    await router.route(_msg("aurc:local/alice", "aurc:local/worker", "greet"))

    # Allowed, but no grant entry written; counter still tracked on the guard.
    assert audit.query(action=AuditAction.AUTHZ_GRANTED) == []
    guard = router._authorizer  # type: ignore[attr-defined]
    assert isinstance(guard, RouteAuthzGuard)
    assert guard.allowed_count == 1


@pytest.mark.asyncio
async def test_constraint_denial_records_reason() -> None:
    audit = AuditLog()
    router = MessageRouter()
    router.set_authorizer(
        RouteAuthzGuard(_engine_with_constraint("aurc:local/alice", "greet"), audit=audit)
    )

    async def handler(msg: AURCMessage) -> dict[str, str]:
        return {"result": "should-not-reach"}

    router.register_handler("aurc:local/worker", handler)
    msg = _msg("aurc:local/alice", "aurc:local/worker", "greet")
    msg.body.params["domain"] = "evil.com"
    with pytest.raises(AuthzDeniedError):
        await router.route(msg)

    denied = audit.query(action=AuditAction.AUTHZ_DENIED)
    assert len(denied) == 1
    assert "constraint" in denied[0].details["reason"].lower() or denied[0].details["reason"]


@pytest.mark.asyncio
async def test_no_audit_log_means_no_records_but_still_enforces() -> None:
    """Backward compat: guard without an audit log still denies/allows; just no trail."""
    router = MessageRouter()
    router.set_authorizer(RouteAuthzGuard(AuthorizationEngine()))  # no audit

    async def handler(msg: AURCMessage) -> dict[str, str]:
        return {"result": "ok"}

    router.register_handler("aurc:local/worker", handler)
    with pytest.raises(AuthzDeniedError):
        await router.route(_msg("aurc:local/mallory", "aurc:local/worker", "greet"))


@pytest.mark.asyncio
async def test_attach_audit_wires_after_construction() -> None:
    """A guard built without audit can be retroactively wired via attach_audit."""
    audit = AuditLog()
    guard = RouteAuthzGuard(_engine_with_policy("aurc:local/alice", "greet"))
    guard.attach_audit(audit)  # no-op on None, wires when set
    guard.attach_audit(AuditLog())  # must NOT clobber the first one

    router = MessageRouter()
    router.set_authorizer(guard)

    async def handler(msg: AURCMessage) -> dict[str, str]:
        return {"result": "ok"}

    router.register_handler("aurc:local/worker", handler)
    await router.route(_msg("aurc:local/alice", "aurc:local/worker", "greet"))

    # The grant landed in the *first* audit log, not the second (no clobber).
    assert len(audit.query(action=AuditAction.AUTHZ_GRANTED)) == 1


# --- Server-level threading -------------------------------------------------


@aurc_agent(id=WORKER_ID)
class _WorkerAgent:
    @skill("greet")
    async def greet(self, name: str = "world") -> str:
        return f"hello {name}"


def _msg_dict(source: str, skill: str) -> dict:
    return {
        "source": source,
        "target": WORKER_ID,
        "type": "request",
        "body": {"method": "invoke", "skill": skill, "params": {"name": "world"}},
    }


@pytest.mark.asyncio
async def test_server_threads_audit_into_constructed_guard() -> None:
    """AURCServer(authz_engine=..., audit_log=...) writes authz events."""
    audit = AuditLog()
    server = AURCServer(
        authz_engine=_engine_with_policy("aurc:local/alice", "greet"),
        audit_log=audit,
    )
    await server.register_agent(_WorkerAgent())

    await server.http_handler(_msg_dict("aurc:local/alice", "greet"))  # allow
    await server.http_handler(_msg_dict("aurc:local/mallory", "greet"))  # deny

    assert len(audit.query(action=AuditAction.AUTHZ_GRANTED)) == 1
    denied = audit.query(action=AuditAction.AUTHZ_DENIED)
    assert len(denied) == 1
    assert denied[0].severity == AuditSeverity.WARNING


@pytest.mark.asyncio
async def test_server_threads_audit_into_explicit_guard() -> None:
    """A caller-supplied RouteAuthzGuard gets the shared audit log attached."""
    audit = AuditLog()
    guard = RouteAuthzGuard(_engine_with_policy("aurc:local/alice", "greet"))
    server = AURCServer(authorizer=guard, audit_log=audit)
    await server.register_agent(_WorkerAgent())

    await server.http_handler(_msg_dict("aurc:local/alice", "greet"))
    assert len(audit.query(action=AuditAction.AUTHZ_GRANTED)) == 1


@pytest.mark.asyncio
async def test_server_without_audit_log_still_works() -> None:
    """Backward compat: server with no audit_log behaves as before."""
    server = AURCServer(authz_engine=_engine_with_policy("aurc:local/alice", "greet"))
    await server.register_agent(_WorkerAgent())
    res = await server.http_handler(_msg_dict("aurc:local/alice", "greet"))
    assert res["result"] == "hello world"
    assert server.audit_log is None
