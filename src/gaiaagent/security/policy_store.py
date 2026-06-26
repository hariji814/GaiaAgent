"""Pluggable storage for CapABAC authorization policies (memory or SQLite).
CapABAC 授权策略的可插拔存储（内存或 SQLite）.

Follows the Sink/Store pattern: a Protocol defines the contract, the in-memory
implementation preserves the original AuthorizationEngine behavior, and the
SQLite implementation persists policies across process restarts.

AgentPolicy is a nested dataclass (rules -> constraints, delegation policy).
Serialization uses dataclasses.asdict + JSON; deserialization reconstructs the
nested structure field-by-field so the engine receives real dataclass objects.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .authz import AgentPolicy, AuthorizationRule, DelegationPolicy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serialization helpers / 序列化辅助
# ---------------------------------------------------------------------------


def _policy_to_json(policy: AgentPolicy) -> str:
    """Serialize an AgentPolicy to a JSON string. 序列化 AgentPolicy 为 JSON。"""
    data = asdict(policy)
    # dataclasses.asdict keeps datetime as datetime; JSON needs isoformat strings.
    return json.dumps(data, default=_json_default, ensure_ascii=False)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Cannot serialize {type(obj)}")


def _policy_from_json(raw: str) -> AgentPolicy:
    """Reconstruct an AgentPolicy from its JSON string. 从 JSON 重建 AgentPolicy。"""
    data = json.loads(raw)
    return _policy_from_dict(data)


def _policy_from_dict(data: dict[str, Any]) -> AgentPolicy:
    """Build an AgentPolicy from a plain dict (nested dataclasses reconstructed).
    从普通 dict 构建 AgentPolicy（嵌套 dataclass 逐层重建）。"""
    from .authz import AgentPolicy  # deferred to avoid circular import
    # noqa below: helpers _rule_from_dict / _delegation_from_dict also import lazily

    rules = [_rule_from_dict(r) for r in data.get("rules", [])]
    delegation = _delegation_from_dict(data.get("delegation", {}))
    created_at = _parse_dt(data.get("created_at"))
    updated_at = _parse_dt(data.get("updated_at"))
    return AgentPolicy(
        agent_id=data["agent_id"],
        rules=rules,
        delegation=delegation,
        created_at=created_at,
        updated_at=updated_at,
    )


def _rule_from_dict(data: dict[str, Any]) -> AuthorizationRule:
    from .authz import AuthorizationRule, Constraint

    constraints = [
        Constraint(field=c["field"], operator=c["operator"], value=c["value"])
        for c in data.get("constraints", [])
    ]
    return AuthorizationRule(
        resource_type=data["resource_type"],
        actions=list(data.get("actions", [])),
        constraints=constraints,
        time_window=data.get("time_window"),
        rate_limit=data.get("rate_limit"),
    )


def _delegation_from_dict(data: dict[str, Any]) -> DelegationPolicy:
    from .authz import DelegationPolicy

    return DelegationPolicy(
        allowed=data.get("allowed", True),
        max_depth=data.get("max_depth", 3),
        scope_reduction_required=data.get("scope_reduction_required", True),
    )


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value)
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Protocol + implementations / 协议与实现
# ---------------------------------------------------------------------------


@runtime_checkable
class PolicyStore(Protocol):
    """Storage contract for authorization policies. 授权策略存储契约。"""

    def save(self, policy: AgentPolicy) -> None:
        """Persist (upsert) a policy. 持久化（upsert）一条策略。"""
        ...

    def load(self, agent_id: str) -> AgentPolicy | None:
        """Load a policy by agent_id. 按 agent_id 加载策略。"""
        ...

    def delete(self, agent_id: str) -> bool:
        """Delete a policy. 删除策略。"""
        ...

    def list_all(self) -> list[AgentPolicy]:
        """List all stored policies. 列出全部策略。"""
        ...

    def count(self) -> int:
        """Number of stored policies. 策略数量。"""
        ...


class MemoryPolicyStore:
    """In-memory PolicyStore — the original engine behavior.

    内存 PolicyStore —— 保留引擎原始行为。"""

    def __init__(self) -> None:
        self._policies: dict[str, AgentPolicy] = {}
        self._lock = threading.RLock()

    def save(self, policy: AgentPolicy) -> None:
        with self._lock:
            self._policies[policy.agent_id] = policy

    def load(self, agent_id: str) -> AgentPolicy | None:
        with self._lock:
            return self._policies.get(agent_id)

    def delete(self, agent_id: str) -> bool:
        with self._lock:
            if agent_id in self._policies:
                del self._policies[agent_id]
                return True
            return False

    def list_all(self) -> list[AgentPolicy]:
        with self._lock:
            return list(self._policies.values())

    def count(self) -> int:
        with self._lock:
            return len(self._policies)


class SQLitePolicyStore:
    """SQLite-backed PolicyStore with real cross-restart persistence.

    基于 SQLite 的 PolicyStore，提供真正的跨重启持久化。

    Each policy is stored as a JSON blob keyed by agent_id, so the nested
    dataclass structure (rules, constraints, delegation) round-trips exactly.
    """

    def __init__(self, db_path: str = "gaiaagent_policies.db") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS policies (
                        agent_id TEXT PRIMARY KEY,
                        policy_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )"""
                )
                conn.commit()
            finally:
                conn.close()

    def save(self, policy: AgentPolicy) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO policies"
                    " (agent_id, policy_json, updated_at) VALUES (?, ?, ?)",
                    (policy.agent_id, _policy_to_json(policy), policy.updated_at.isoformat()),
                )
                conn.commit()
            finally:
                conn.close()

    def load(self, agent_id: str) -> AgentPolicy | None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                row = conn.execute(
                    "SELECT policy_json FROM policies WHERE agent_id = ?",
                    (agent_id,),
                ).fetchone()
                if row is None:
                    return None
                return _policy_from_json(row[0])
            finally:
                conn.close()

    def delete(self, agent_id: str) -> bool:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                cur = conn.execute("DELETE FROM policies WHERE agent_id = ?", (agent_id,))
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def list_all(self) -> list[AgentPolicy]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                rows = conn.execute("SELECT policy_json FROM policies").fetchall()
                return [_policy_from_json(r[0]) for r in rows]
            finally:
                conn.close()

    def count(self) -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                row = conn.execute("SELECT COUNT(*) FROM policies").fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()


__all__ = [
    "PolicyStore",
    "MemoryPolicyStore",
    "SQLitePolicyStore",
]
