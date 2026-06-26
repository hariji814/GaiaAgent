"""Phase 4.2 tests: SQLite persistence for API keys + CapABAC policies.

Verifies the KeyStore / PolicyStore Protocol conformance, in-memory behavior
parity, and real SQLite cross-restart survival (a fresh store instance backed
by the same db file sees previously-written records).
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

import pytest

from gaiaagent.security.auth import APIKeyAuthenticator
from gaiaagent.security.authz import (
    AgentPolicy,
    AuthorizationEngine,
    AuthorizationRule,
    Constraint,
    DelegationPolicy,
)
from gaiaagent.security.key_store import (
    KeyStore,
    MemoryKeyStore,
    SQLiteKeyStore,
)
from gaiaagent.security.policy_store import (
    MemoryPolicyStore,
    PolicyStore,
    SQLitePolicyStore,
)

# ---------------------------------------------------------------------------
# KeyStore Protocol conformance + parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("store_cls", [MemoryKeyStore, SQLiteKeyStore])
def test_keystore_protocol_conformance(store_cls) -> None:
    if store_cls is SQLiteKeyStore:
        store = store_cls(db_path=os.path.join(tempfile.gettempdir(), "test_keys.db"))
    else:
        store = store_cls()
    assert isinstance(store, KeyStore)


def test_memory_keystore_crud() -> None:
    store = MemoryKeyStore()
    now = datetime.now(timezone.utc)
    store.store("hash1", "aurc:a", ["s1", "s2"], now)
    assert store.count() == 1
    rec = store.lookup("hash1")
    assert rec is not None
    assert rec[0] == "aurc:a"
    assert rec[1] == ["s1", "s2"]
    assert store.delete("hash1") is True
    assert store.lookup("hash1") is None
    assert store.count() == 0


def test_sqlite_keystore_survives_restart(tmp_path) -> None:
    db = tmp_path / "keys.db"
    now = datetime.now(timezone.utc)
    store1 = SQLiteKeyStore(db_path=str(db))
    store1.store("hash1", "aurc:a", ["s1"], now)
    store1.store("hash2", "aurc:a", ["s2"], now)
    store1.store("hash3", "aurc:b", ["s3"], now)
    assert store1.count() == 3

    # A brand-new instance pointing at the same file sees the records.
    store2 = SQLiteKeyStore(db_path=str(db))
    assert store2.count() == 3
    rec = store2.lookup("hash1")
    assert rec is not None
    assert rec[0] == "aurc:a"
    assert rec[1] == ["s1"]

    # delete_agent removes by agent, not by hash
    assert store2.delete_agent("aurc:a") == 2
    assert store2.count() == 1
    assert store2.lookup("hash1") is None


def test_authenticator_with_sqlite_keystore_survives_restart(tmp_path) -> None:
    db = tmp_path / "auth_keys.db"
    store = SQLiteKeyStore(db_path=str(db))
    auth1 = APIKeyAuthenticator(store=store)
    raw_key = auth1.create_key("aurc:gaia/researcher:v1.0", scopes=["research:read"])
    assert auth1.authenticate(raw_key).authenticated is True

    # New authenticator on the same DB still recognizes the key.
    store2 = SQLiteKeyStore(db_path=str(db))
    auth2 = APIKeyAuthenticator(store=store2)
    result = auth2.authenticate(raw_key)
    assert result.authenticated is True
    assert result.agent_id == "aurc:gaia/researcher:v1.0"
    assert "research:read" in result.scopes

    # Revocation persists too.
    assert auth2.revoke_key(raw_key) is True
    store3 = SQLiteKeyStore(db_path=str(db))
    auth3 = APIKeyAuthenticator(store=store3)
    assert auth3.authenticate(raw_key).authenticated is False


# ---------------------------------------------------------------------------
# PolicyStore Protocol conformance + round-trip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("store_cls", [MemoryPolicyStore, SQLitePolicyStore])
def test_policystore_protocol_conformance(store_cls, tmp_path) -> None:
    if store_cls is SQLitePolicyStore:
        store = store_cls(db_path=str(tmp_path / "policies.db"))
    else:
        store = store_cls()
    assert isinstance(store, PolicyStore)


def _sample_policy(agent_id: str = "aurc:gaia/researcher:v1.0") -> AgentPolicy:
    return AgentPolicy(
        agent_id=agent_id,
        rules=[
            AuthorizationRule(
                resource_type="web-search",
                actions=["execute"],
                constraints=[Constraint("domain", "matches", r".*\.edu$")],
                rate_limit=100,
            ),
        ],
        delegation=DelegationPolicy(allowed=True, max_depth=2),
    )


def test_memory_policystore_crud() -> None:
    store = MemoryPolicyStore()
    policy = _sample_policy()
    store.save(policy)
    assert store.count() == 1
    loaded = store.load(policy.agent_id)
    assert loaded is not None
    assert loaded.agent_id == policy.agent_id
    assert len(loaded.rules) == 1
    assert loaded.rules[0].actions == ["execute"]
    assert loaded.delegation.max_depth == 2
    assert store.delete(policy.agent_id) is True
    assert store.load(policy.agent_id) is None


def test_sqlite_policystore_round_trips_nested_constraints(tmp_path) -> None:
    db = tmp_path / "policies.db"
    store = SQLitePolicyStore(db_path=str(db))
    policy = _sample_policy()
    store.save(policy)

    store2 = SQLitePolicyStore(db_path=str(db))
    loaded = store2.load(policy.agent_id)
    assert loaded is not None
    rule = loaded.rules[0]
    assert rule.resource_type == "web-search"
    assert rule.constraints[0].field == "domain"
    assert rule.constraints[0].operator == "matches"
    assert rule.constraints[0].value == r".*\.edu$"
    assert rule.rate_limit == 100
    assert loaded.delegation.allowed is True
    assert loaded.delegation.max_depth == 2


def test_engine_with_sqlite_policystore_survives_restart(tmp_path) -> None:
    db = tmp_path / "engine_policies.db"
    store = SQLitePolicyStore(db_path=str(db))
    engine = AuthorizationEngine(store=store)
    policy = _sample_policy()
    engine.set_policy(policy.agent_id, policy)

    # Authz works on the first engine instance.
    result = engine.authorize(
        agent_id=policy.agent_id,
        resource_type="web-search",
        action="execute",
        attributes={"domain": "mit.edu"},
    )
    assert result.allowed

    # A fresh engine on the same DB still has the policy and enforces it.
    store2 = SQLitePolicyStore(db_path=str(db))
    engine2 = AuthorizationEngine(store=store2)
    loaded = engine2.get_policy(policy.agent_id)
    assert loaded is not None
    result2 = engine2.authorize(
        agent_id=policy.agent_id,
        resource_type="web-search",
        action="execute",
        attributes={"domain": "mit.edu"},
    )
    assert result2.allowed
    # Non-.edu domain fails the constraint (fail-closed).
    result3 = engine2.authorize(
        agent_id=policy.agent_id,
        resource_type="web-search",
        action="execute",
        attributes={"domain": "evil.com"},
    )
    assert not result3.allowed


def test_sqlite_policystore_list_all(tmp_path) -> None:
    store = SQLitePolicyStore(db_path=str(tmp_path / "policies.db"))
    store.save(_sample_policy("aurc:a"))
    store.save(_sample_policy("aurc:b"))
    store.save(_sample_policy("aurc:c"))
    all_policies = store.list_all()
    assert len(all_policies) == 3
    assert {p.agent_id for p in all_policies} == {"aurc:a", "aurc:b", "aurc:c"}
