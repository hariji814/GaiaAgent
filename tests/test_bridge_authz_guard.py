"""Phase 4.4 tests: BridgeAuthzGuard fail-closed enforcement.

Verifies that inbound bridged messages are authorized against the CapABAC
engine before reaching the core, that denial raises BridgeAuthzError (never
silently passes), and that the guarded bridge preserves outbound passthrough.
"""
from __future__ import annotations

import pytest

from gaiaagent.bridges.a2a import A2ABridge
from gaiaagent.bridges.authz_guard import BridgeAuthzError, BridgeAuthzGuard
from gaiaagent.core.message import AURCMessage, BridgeContext, MessageBody
from gaiaagent.core.types import MessageDirection
from gaiaagent.security.authz import (
    AgentPolicy,
    AuthorizationEngine,
    AuthorizationRule,
    Constraint,
)


def _make_engine_with_policy(
    agent_id: str, skill: str, action: str = "invoke"
) -> AuthorizationEngine:
    engine = AuthorizationEngine()
    engine.set_policy(
        agent_id,
        AgentPolicy(
            agent_id=agent_id,
            rules=[
                AuthorizationRule(
                    resource_type=skill,
                    actions=[action],
                )
            ],
        ),
    )
    return engine


def _aurc_msg(source: str, skill: str, method: str = "invoke") -> AURCMessage:
    return AURCMessage(
        source=source,
        target="aurc:local/orchestrator",
        type=MessageDirection.REQUEST,
        body=MessageBody(method=method, skill=skill, params={"q": "hi"}),
        protocol_context=BridgeContext(
            origin_protocol="a2a/1.0",
            bridged_from="a2a/1.0",
            bridge_chain=["a2a->aurc"],
        ),
    )


def test_guard_allows_authorized_message() -> None:
    engine = _make_engine_with_policy("alice", "web-search")
    guard = BridgeAuthzGuard(engine)
    msg = _aurc_msg("a2a:external/alice", "web-search")
    guard.authorize_message(msg)  # must not raise
    assert guard.allowed_count == 1
    assert guard.denied_count == 0


def test_guard_denies_no_policy_fail_closed() -> None:
    engine = AuthorizationEngine()  # no policies at all
    guard = BridgeAuthzGuard(engine)
    msg = _aurc_msg("a2a:external/mallory", "web-search")
    with pytest.raises(BridgeAuthzError):
        guard.authorize_message(msg)
    assert guard.denied_count == 1
    assert guard.allowed_count == 0


def test_guard_denies_wrong_skill() -> None:
    engine = _make_engine_with_policy("alice", "web-search")
    guard = BridgeAuthzGuard(engine)
    msg = _aurc_msg("a2a:external/alice", "file-delete")  # not in policy
    with pytest.raises(BridgeAuthzError):
        guard.authorize_message(msg)
    assert guard.denied_count == 1


def test_guard_denies_constraint_violation() -> None:
    engine = AuthorizationEngine()
    engine.set_policy(
        "alice",
        AgentPolicy(
            agent_id="alice",
            rules=[
                AuthorizationRule(
                    resource_type="web-search",
                    actions=["invoke"],
                    constraints=[Constraint("domain", "matches", r".*\\.edu$")],
                )
            ],
        ),
    )
    guard = BridgeAuthzGuard(engine)
    msg = _aurc_msg("a2a:external/alice", "web-search")
    msg.body.params["domain"] = "evil.com"  # fails the .edu constraint
    with pytest.raises(BridgeAuthzError):
        guard.authorize_message(msg)
    assert guard.denied_count == 1


@pytest.mark.asyncio
async def test_guard_wraps_bridge_translate_to_aurc() -> None:
    """An inbound A2A message with no matching policy is denied (fail-closed)."""
    engine_no_policy = AuthorizationEngine()
    guard = BridgeAuthzGuard(engine_no_policy)
    bridge = guard.wrap(A2ABridge())

    a2a_msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tasks/send",
        "params": {
            "id": "t1",
            "sessionId": "alice",
            "messages": [{"role": "user", "parts": [{"type": "text", "text": "search the web"}]}],
        },
    }
    with pytest.raises(BridgeAuthzError):
        await bridge.translate_to_aurc(a2a_msg)


@pytest.mark.asyncio
async def test_guard_wraps_bridge_outbound_passthrough() -> None:
    engine = _make_engine_with_policy("alice", "web-search")
    guard = BridgeAuthzGuard(engine)
    bridge = guard.wrap(A2ABridge())

    # Outbound translation should pass through unchanged (no authz on outbound)
    aurc = _aurc_msg("aurc:local/orchestrator", "web-search")
    result = await bridge.translate_from_aurc(aurc)
    assert isinstance(result, dict)


def test_extract_agent_id_strips_external_qualifier() -> None:
    engine = AuthorizationEngine()
    guard = BridgeAuthzGuard(engine)
    msg = _aurc_msg("a2a:external/bob-42", "web-search")
    assert guard._extract_agent_id(msg) == "bob-42"


def test_guard_error_carries_aurc_message() -> None:
    engine = AuthorizationEngine()
    guard = BridgeAuthzGuard(engine)
    msg = _aurc_msg("a2a:external/mallory", "web-search")
    try:
        guard.authorize_message(msg)
    except BridgeAuthzError as exc:
        assert exc.aurc_message is msg
    else:
        pytest.fail("expected BridgeAuthzError")
