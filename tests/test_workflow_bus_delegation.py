"""Workflow bus delegation: orchestration patterns route through the bus.

Verifies the RouterDelegate seam: any orchestration pattern (PromptChain,
ParallelFanOut) that accepts a SkillHandler can be handed a RouterDelegate and
will then route every hop through the AURC message bus, so each fan-out step
is covered by hot-path authorization + audit logging rather than bypassing
the security and observability layer.
"""

from __future__ import annotations

import pytest

from gaiaagent.bus.router import MessageRouter
from gaiaagent.core.message import AURCMessage
from gaiaagent.sdk.decorators import aurc_agent, skill
from gaiaagent.security.audit import AuditAction, AuditLog, AuditSeverity
from gaiaagent.security.authz import AgentPolicy, AuthorizationEngine, AuthorizationRule
from gaiaagent.server import AURCServer
from gaiaagent.workflows import (
    ParallelFanOut,
    PromptChain,
    RouterDelegate,
    RouterDelegateError,
)
from gaiaagent.workflows.orchestrator import DEFAULT_ORCH_SOURCE as ORCH_SOURCE
from gaiaagent.workflows.orchestrator import SkillHandler

PROC_ID = "aurc:local/proc:v1.0"


@aurc_agent(id=PROC_ID)
class _ProcAgent:
    @skill("upper")
    async def upper(self, text: str = "") -> str:
        return text.upper()

    @skill("exclaim")
    async def exclaim(self, text: str = "") -> str:
        return f"{text}!"

    @skill("echo")
    async def echo(self, text: str = "") -> str:
        return text


def _engine_with_skills(agent_id: str, *skills: str) -> AuthorizationEngine:
    engine = AuthorizationEngine()
    engine.set_policy(
        agent_id,
        AgentPolicy(
            agent_id=agent_id,
            rules=[AuthorizationRule(resource_type=s, actions=["invoke"]) for s in skills],
        ),
    )
    return engine


@pytest.mark.asyncio
async def test_promptchain_bus_delegation_composes_and_audits() -> None:
    """PromptChain of two RouterDelegates composes results and audits both hops."""
    audit = AuditLog()
    server = AURCServer(
        authz_engine=_engine_with_skills(ORCH_SOURCE, "upper", "exclaim"),
        audit_log=audit,
    )
    await server.register_agent(_ProcAgent())

    upper = RouterDelegate(server.router, PROC_ID, "upper", input_key="text")
    exclaim = RouterDelegate(server.router, PROC_ID, "exclaim", input_key="text")
    result = await PromptChain([upper, exclaim]).execute("hi")

    assert result.success
    assert result.output == "HI!"
    assert result.steps_completed == 2
    grants = audit.query(action=AuditAction.AUTHZ_GRANTED)
    assert len(grants) == 2
    assert all(e.severity == AuditSeverity.INFO for e in grants)
    assert audit.query(action=AuditAction.AUTHZ_DENIED) == []


@pytest.mark.asyncio
async def test_promptchain_deny_mid_chain_surfaces_as_failure() -> None:
    """An authz denial mid-chain is caught by the pattern and recorded."""
    audit = AuditLog()
    server = AURCServer(
        authz_engine=_engine_with_skills(ORCH_SOURCE, "upper", "exclaim"),
        audit_log=audit,
    )
    await server.register_agent(_ProcAgent())

    upper = RouterDelegate(server.router, PROC_ID, "upper", input_key="text")
    # Second hop uses an untrusted source with no policy -> denied.
    exclaim = RouterDelegate(
        server.router, PROC_ID, "exclaim", input_key="text", source="aurc:local/mallory"
    )
    result = await PromptChain([upper, exclaim]).execute("hi")

    assert not result.success
    assert result.errors  # the chain recorded a step failure
    assert len(audit.query(action=AuditAction.AUTHZ_GRANTED)) == 1
    denied = audit.query(action=AuditAction.AUTHZ_DENIED)
    assert len(denied) == 1
    assert denied[0].severity == AuditSeverity.WARNING
    assert denied[0].agent_id == "aurc:local/mallory"


@pytest.mark.asyncio
async def test_parallelfanout_bus_delegation_audits_each_hop() -> None:
    """ParallelFanOut through the bus produces one audit grant per fan-out task."""
    audit = AuditLog()
    server = AURCServer(
        authz_engine=_engine_with_skills(ORCH_SOURCE, "echo"),
        audit_log=audit,
    )
    await server.register_agent(_ProcAgent())

    delegates: list[SkillHandler] = [
        RouterDelegate(server.router, PROC_ID, "echo", input_key="text") for _ in range(3)
    ]
    result = await ParallelFanOut(delegates, mode="all").execute("hi")

    assert result.success
    assert result.output == ["hi", "hi", "hi"]
    assert len(audit.query(action=AuditAction.AUTHZ_GRANTED)) == 3
    assert audit.query(action=AuditAction.AUTHZ_DENIED) == []


@pytest.mark.asyncio
async def test_error_envelope_raises_router_delegate_error() -> None:
    """A {"error": ...} envelope from a routed handler surfaces as RouterDelegateError."""
    router = MessageRouter()

    async def handler(msg: AURCMessage) -> dict[str, object]:
        return {"error": {"code": "boom", "message": "kaboom", "recoverable": False}}

    router.register_handler("aurc:local/boom", handler)
    delegate = RouterDelegate(router, "aurc:local/boom", "frob")

    with pytest.raises(RouterDelegateError) as exc_info:
        await delegate("x")
    assert exc_info.value.error["message"] == "kaboom"


@pytest.mark.asyncio
async def test_dict_input_spreads_as_params() -> None:
    """Dict input spreads as skill params; scalars are wrapped under input_key."""
    router = MessageRouter()
    seen: dict[str, object] = {}

    async def handler(msg: AURCMessage) -> dict[str, object]:
        seen.update(msg.body.params)
        return {"result": dict(msg.body.params)}

    router.register_handler("aurc:local/sink", handler)

    # dict -> spread as params
    out = await RouterDelegate(router, "aurc:local/sink", "sink")({"a": 1, "b": 2})
    assert out == {"a": 1, "b": 2}
    assert seen == {"a": 1, "b": 2}

    # scalar -> wrapped under input_key
    seen.clear()
    out = await RouterDelegate(router, "aurc:local/sink", "sink", input_key="text")("hello")
    assert out == {"text": "hello"}
    assert seen == {"text": "hello"}


@pytest.mark.asyncio
async def test_promptchain_hops_share_correlation_id() -> None:
    """Both hops of a chain share one non-empty correlation_id in the audit log."""
    audit = AuditLog()
    server = AURCServer(
        authz_engine=_engine_with_skills(ORCH_SOURCE, "upper", "exclaim"),
        audit_log=audit,
    )
    await server.register_agent(_ProcAgent())

    upper = RouterDelegate(server.router, PROC_ID, "upper", input_key="text")
    exclaim = RouterDelegate(server.router, PROC_ID, "exclaim", input_key="text")
    result = await PromptChain([upper, exclaim]).execute("hi")

    assert result.success
    grants = audit.query(action=AuditAction.AUTHZ_GRANTED)
    assert len(grants) == 2
    cids = {e.correlation_id for e in grants}
    assert len(cids) == 1
    shared = cids.pop()
    assert shared  # non-empty
    assert len(audit.get_by_correlation(shared)) == 2


@pytest.mark.asyncio
async def test_standalone_delegate_has_non_empty_correlation() -> None:
    """A RouterDelegate called outside any pattern still gets a non-empty correlation."""
    audit = AuditLog()
    server = AURCServer(
        authz_engine=_engine_with_skills(ORCH_SOURCE, "echo"),
        audit_log=audit,
    )
    await server.register_agent(_ProcAgent())

    delegate = RouterDelegate(server.router, PROC_ID, "echo", input_key="text")
    out = await delegate("hi")

    assert out == "hi"
    grants = audit.query(action=AuditAction.AUTHZ_GRANTED)
    assert len(grants) == 1
    assert grants[0].correlation_id  # non-empty


@pytest.mark.asyncio
async def test_nested_pattern_inherits_outer_correlation() -> None:
    """A ParallelFanOut run inside a PromptChain step shares the chain's correlation."""
    audit = AuditLog()
    server = AURCServer(
        authz_engine=_engine_with_skills(ORCH_SOURCE, "upper", "echo"),
        audit_log=audit,
    )
    await server.register_agent(_ProcAgent())

    async def _fanout_step(text: str) -> list[str]:
        delegates: list[SkillHandler] = [
            RouterDelegate(server.router, PROC_ID, "echo", input_key="text") for _ in range(2)
        ]
        result = await ParallelFanOut(delegates, mode="all").execute(text)
        return result.output

    upper = RouterDelegate(server.router, PROC_ID, "upper", input_key="text")
    result = await PromptChain([upper, _fanout_step]).execute("hi")

    assert result.success
    grants = audit.query(action=AuditAction.AUTHZ_GRANTED)
    assert len(grants) == 3  # 1 upper + 2 echo
    cids = {e.correlation_id for e in grants}
    assert len(cids) == 1
    assert cids.pop()  # non-empty


@pytest.mark.asyncio
async def test_authz_denial_surfaces_as_forbidden_envelope() -> None:
    """A hot-path AuthzDeniedError is mapped to a forbidden RouterDelegateError."""
    audit = AuditLog()
    server = AURCServer(
        authz_engine=_engine_with_skills(ORCH_SOURCE, "echo"),
        audit_log=audit,
    )
    await server.register_agent(_ProcAgent())

    delegate = RouterDelegate(
        server.router, PROC_ID, "echo", input_key="text", source="aurc:local/mallory"
    )
    with pytest.raises(RouterDelegateError) as exc_info:
        await delegate("hi")

    err = exc_info.value.error
    assert err["code"] == "forbidden"
    assert err["recoverable"] is False
    assert err["message"]  # non-empty reason
    # Denial still recorded in audit / 拒绝仍记入审计
    denied = audit.query(action=AuditAction.AUTHZ_DENIED)
    assert len(denied) == 1
    assert denied[0].agent_id == "aurc:local/mallory"
