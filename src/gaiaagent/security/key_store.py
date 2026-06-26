"""Pluggable storage for API keys (memory or SQLite).
API Key 的可插拔存储（内存或 SQLite）.

Mirrors the Sink pattern used by audit/trace persistence: a Protocol defines
the storage contract, the in-memory implementation preserves the original
behavior, and the SQLite implementation gives real cross-restart persistence
so authenticator state survives process restarts.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# A stored key record: (key_hash, agent_id, scopes, created_at)
KeyRecord = tuple[str, str, list[str], datetime]


@runtime_checkable
class KeyStore(Protocol):
    """Storage contract for API key records. API Key 存储契约."""

    def store(self, key_hash: str, agent_id: str, scopes: list[str], created_at: datetime) -> None:
        """Persist a key record. 持久化一条 Key 记录."""
        ...

    def lookup(self, key_hash: str) -> tuple[str, list[str], datetime] | None:
        """Look up a key by hash. Returns (agent_id, scopes, created_at) or None.
        按哈希查找 Key，返回 (agent_id, scopes, created_at) 或 None."""
        ...

    def delete(self, key_hash: str) -> bool:
        """Delete a single key. 删除单条 Key."""
        ...

    def delete_agent(self, agent_id: str) -> int:
        """Delete all keys for an agent; return count removed.
        删除某 Agent 的全部 Key，返回删除数。"""
        ...

    def count(self) -> int:
        """Number of stored keys. 存储 Key 数量。"""
        ...


class MemoryKeyStore:
    """In-memory KeyStore — the original authenticator behavior.

    内存 KeyStore —— 保留认证器原始行为。"""

    def __init__(self) -> None:
        self._keys: dict[str, tuple[str, list[str], datetime]] = {}
        self._lock = threading.RLock()

    def store(self, key_hash: str, agent_id: str, scopes: list[str], created_at: datetime) -> None:
        with self._lock:
            self._keys[key_hash] = (agent_id, list(scopes), created_at)

    def lookup(self, key_hash: str) -> tuple[str, list[str], datetime] | None:
        with self._lock:
            entry = self._keys.get(key_hash)
            if entry is None:
                return None
            agent_id, scopes, created_at = entry
            return (agent_id, list(scopes), created_at)

    def delete(self, key_hash: str) -> bool:
        with self._lock:
            if key_hash in self._keys:
                del self._keys[key_hash]
                return True
            return False

    def delete_agent(self, agent_id: str) -> int:
        with self._lock:
            to_remove = [h for h, (aid, _, _) in self._keys.items() if aid == agent_id]
            for h in to_remove:
                del self._keys[h]
            return len(to_remove)

    def count(self) -> int:
        with self._lock:
            return len(self._keys)


class SQLiteKeyStore:
    """SQLite-backed KeyStore with real cross-restart persistence.

    基于 SQLite 的 KeyStore，提供真正的跨重启持久化。

    Keys are stored as SHA-256 hashes (never the raw key). Scopes are JSON-
    encoded. The database is created lazily on first use with WAL mode for
    concurrency-friendly access.
    """

    def __init__(self, db_path: str = "gaiaagent_keys.db") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS api_keys (
                        key_hash TEXT PRIMARY KEY,
                        agent_id TEXT NOT NULL,
                        scopes_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )"""
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_agent ON api_keys(agent_id)")
                conn.commit()
            finally:
                conn.close()

    def store(self, key_hash: str, agent_id: str, scopes: list[str], created_at: datetime) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO api_keys"
                    " (key_hash, agent_id, scopes_json, created_at) VALUES (?, ?, ?, ?)",
                    (key_hash, agent_id, json.dumps(scopes), created_at.isoformat()),
                )
                conn.commit()
            finally:
                conn.close()

    def lookup(self, key_hash: str) -> tuple[str, list[str], datetime] | None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                row = conn.execute(
                    "SELECT agent_id, scopes_json, created_at FROM api_keys WHERE key_hash = ?",
                    (key_hash,),
                ).fetchone()
                if row is None:
                    return None
                agent_id, scopes_json, created_at_str = row
                scopes: list[str] = json.loads(scopes_json)
                created_at = datetime.fromisoformat(created_at_str)
                return (agent_id, scopes, created_at)
            finally:
                conn.close()

    def delete(self, key_hash: str) -> bool:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                cur = conn.execute("DELETE FROM api_keys WHERE key_hash = ?", (key_hash,))
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def delete_agent(self, agent_id: str) -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                cur = conn.execute("DELETE FROM api_keys WHERE agent_id = ?", (agent_id,))
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()

    def count(self) -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                row = conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()


__all__ = ["KeyStore", "KeyRecord", "MemoryKeyStore", "SQLiteKeyStore"]
