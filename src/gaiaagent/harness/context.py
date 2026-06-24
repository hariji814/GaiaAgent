"""AURC Context & Memory Management.
AURC 上下文与内存管理

Manages agent context across four scopes:
    - session: Per-task execution context / 单次任务的执行上下文
    - agent: Per-agent persistent context / Agent 的持久化上下文
    - shared: Cross-agent shared context / 跨 Agent 共享上下文
    - global: System-wide context / 全局系统上下文
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone
from typing import Any

from ..core.types import ContextScope

logger = logging.getLogger(__name__)


class ContextEntry:
    """A single context entry with metadata. 单条上下文条目"""

    __slots__ = ("key", "value", "scope", "agent_id", "created_at", "updated_at", "ttl_seconds")

    def __init__(
        self,
        key: str,
        value: Any,
        scope: ContextScope,
        agent_id: str | None = None,
        ttl_seconds: int | None = None,
    ):
        self.key = key
        self.value = value
        self.scope = scope
        self.agent_id = agent_id
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at
        self.ttl_seconds = ttl_seconds

    @property
    def is_expired(self) -> bool:
        """Check if this entry has exceeded its TTL. 检查是否已过期"""
        if self.ttl_seconds is None:
            return False
        age = (datetime.now(timezone.utc) - self.updated_at).total_seconds()
        return age > self.ttl_seconds

    def update(self, new_value: Any) -> None:
        """Update the entry's value and timestamp."""
        self.value = new_value
        self.updated_at = datetime.now(timezone.utc)


class ContextStore:
    """In-memory context store with scope-based isolation.
    基于作用域隔离的内存上下文存储

    Thread-safe for async operations via scope-based key partitioning.

    Usage / 用法:
        store = ContextStore()

        # Save context / 保存上下文
        store.save("search_history", ["query1", "query2"], ContextScope.AGENT, "aurc:gaia/researcher:v1.0")

        # Load context / 加载上下文
        history = store.load("search_history", ContextScope.AGENT, "aurc:gaia/researcher:v1.0")

        # List keys / 列出键
        keys = store.list_keys(ContextScope.AGENT, "aurc:gaia/researcher:v1.0")
    """

    def __init__(self) -> None:
        # Storage organized by scope → (agent_id, key) → ContextEntry
        # 按作用域组织的存储：scope → (agent_id, key) → ContextEntry
        self._store: dict[ContextScope, dict[tuple[str | None, str], ContextEntry]] = {
            scope: {} for scope in ContextScope
        }

    def save(
        self,
        key: str,
        value: Any,
        scope: ContextScope,
        agent_id: str | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        """Save a context entry.
        保存上下文条目

        Args:
            key: Context key / 上下文键
            value: Context value (any serializable type) / 上下文值
            scope: Visibility scope / 可见性作用域
            agent_id: Agent ID (required for session/agent scope) / Agent ID
            ttl_seconds: Time-to-live in seconds (None = infinite) / 生存时间秒数
        """
        self._validate_scope(scope, agent_id)

        store_key = self._make_key(scope, agent_id, key)
        scope_store = self._store[scope]

        if store_key in scope_store and not scope_store[store_key].is_expired:
            scope_store[store_key].update(value)
        else:
            scope_store[store_key] = ContextEntry(
                key=key,
                value=copy.deepcopy(value),
                scope=scope,
                agent_id=agent_id,
                ttl_seconds=ttl_seconds,
            )

        logger.debug("Context saved: scope=%s, key=%s, agent=%s", scope.value, key, agent_id)

    def load(
        self,
        key: str,
        scope: ContextScope,
        agent_id: str | None = None,
        default: Any = None,
    ) -> Any:
        """Load a context entry.
        加载上下文条目

        Returns:
            The stored value, or default if not found/expired
        """
        self._validate_scope(scope, agent_id)
        store_key = self._make_key(scope, agent_id, key)
        entry = self._store[scope].get(store_key)

        if entry is None:
            return default

        if entry.is_expired:
            del self._store[scope][store_key]
            logger.debug("Context expired: scope=%s, key=%s", scope.value, key)
            return default

        return copy.deepcopy(entry.value)

    def delete(
        self,
        key: str,
        scope: ContextScope,
        agent_id: str | None = None,
    ) -> bool:
        """Delete a context entry.
        删除上下文条目

        Returns:
            True if the entry was deleted, False if not found
        """
        self._validate_scope(scope, agent_id)
        store_key = self._make_key(scope, agent_id, key)

        if store_key in self._store[scope]:
            del self._store[scope][store_key]
            return True
        return False

    def list_keys(
        self,
        scope: ContextScope,
        agent_id: str | None = None,
    ) -> list[str]:
        """List all keys in a scope (for a specific agent).
        列出作用域内的所有键

        Args:
            scope: The scope to list / 要列出的作用域
            agent_id: Agent ID filter (for session/agent scope) / Agent ID 过滤
        """
        self._cleanup_expired(scope)

        keys = []
        for (stored_agent_id, key), entry in self._store[scope].items():
            if scope in (ContextScope.SESSION, ContextScope.AGENT):
                if stored_agent_id == agent_id:
                    keys.append(key)
            else:
                keys.append(key)
        return keys

    def clear_scope(
        self,
        scope: ContextScope,
        agent_id: str | None = None,
    ) -> int:
        """Clear all entries in a scope (for a specific agent).
        清除作用域内的所有条目

        Returns:
            Number of entries cleared / 清除的条目数
        """
        if scope in (ContextScope.SESSION, ContextScope.AGENT):
            to_delete = [
                k for k, (aid, _) in enumerate(self._store[scope].keys())
                if aid == agent_id
            ]
        else:
            to_delete = list(self._store[scope].keys())

        for key in to_delete:
            del self._store[scope][key]

        return len(to_delete)

    def get_stats(self) -> dict[str, int]:
        """Get statistics about the context store. 获取上下文存储统计"""
        return {
            scope.value: len(store)
            for scope, store in self._store.items()
        }

    # =========================================================================
    # Internal / 内部方法
    # =========================================================================

    @staticmethod
    def _make_key(scope: ContextScope, agent_id: str | None, key: str) -> tuple[str | None, str]:
        """Create a composite storage key."""
        if scope in (ContextScope.SESSION, ContextScope.AGENT):
            return (agent_id, key)
        return (None, key)

    @staticmethod
    def _validate_scope(scope: ContextScope, agent_id: str | None) -> None:
        """Validate that agent_id is provided when required."""
        if scope in (ContextScope.SESSION, ContextScope.AGENT) and not agent_id:
            raise ValueError(
                f"agent_id is required for scope '{scope.value}'. "
                f"Use 'shared' or 'global' scope for cross-agent context."
            )

    def _cleanup_expired(self, scope: ContextScope) -> None:
        """Remove expired entries from a scope."""
        expired = [
            k for k, v in self._store[scope].items()
            if v.is_expired
        ]
        for k in expired:
            del self._store[scope][k]
