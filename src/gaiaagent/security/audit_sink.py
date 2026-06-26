"""AuditSink Protocol and concrete sinks - persistence for the audit trail.

Decouples AuditLog's storage from its query API, so the in-memory ring
buffer and a rotating file sink are interchangeable. Phase 4.2 of the
adoption plan: real-time file persistence + rotation for the audit log.
"""
from __future__ import annotations

import json
import logging
import threading
from collections import deque
from pathlib import Path
from typing import Protocol, runtime_checkable

from .audit import AuditEntry

logger = logging.getLogger(__name__)


@runtime_checkable
class AuditSink(Protocol):
    """Persistence contract for audit entries.

    MemoryAuditSink satisfies this today; FileAuditSink writes to disk in
    real time with size-based rotation. A future SQLite/OTel sink needs
    only to implement these members.
    """

    def append(self, entry: AuditEntry) -> None: ...

    def entries(self) -> list[AuditEntry]: ...

    def clear(self) -> int: ...

    @property
    def count(self) -> int: ...


class MemoryAuditSink:
    """In-memory ring buffer (the original AuditLog behavior)."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._entries: deque[AuditEntry] = deque(maxlen=max_entries)

    def append(self, entry: AuditEntry) -> None:
        self._entries.append(entry)

    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    def clear(self) -> int:
        n = len(self._entries)
        self._entries.clear()
        return n

    @property
    def count(self) -> int:
        return len(self._entries)


class FileAuditSink:
    """Append-only file sink with size-based rotation.

    Each entry is written as one JSON line immediately (real-time
    persistence). When the current file exceeds *max_bytes*, it is rotated
    to ``<path>.1`` (overwriting any prior rotation) and a fresh file
    starts. Thread-safe via a re-entrant lock.
    """

    def __init__(
        self,
        path: str | Path,
        max_bytes: int = 10 * 1024 * 1024,
        max_entries: int = 10000,
    ) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._max_bytes = max_bytes
        self._buffer: deque[AuditEntry] = deque(maxlen=max_entries)
        self._lock = threading.RLock()

    def _maybe_rotate(self) -> None:
        """Rotate the file if it has grown past *max_bytes*."""
        try:
            if self._path.exists() and self._path.stat().st_size >= self._max_bytes:
                rotated = self._path.with_suffix(self._path.suffix + ".1")
                self._path.replace(rotated)
        except OSError:
            logger.warning("audit rotation failed for %s", self._path, exc_info=True)

    def append(self, entry: AuditEntry) -> None:
        line = json.dumps(entry.to_dict(), default=str)
        with self._lock:
            self._buffer.append(entry)
            self._maybe_rotate()
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def entries(self) -> list[AuditEntry]:
        return list(self._buffer)

    def clear(self) -> int:
        n = len(self._buffer)
        self._buffer.clear()
        return n

    @property
    def count(self) -> int:
        return len(self._buffer)

    @property
    def path(self) -> Path:
        return self._path
