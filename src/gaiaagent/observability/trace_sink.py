"""TraceSink Protocol and concrete sinks - persistence for the trace recorder.

Decouples BridgeTraceRecorder's storage from its query API, mirroring the
AuditSink pattern. MemoryTraceSink is the original in-memory grouped store;
FileTraceSink persists each span to a JSONL file in real time with rotation.
Phase 4.2 of the adoption plan: trace recorder persistence (was manual flush).
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Protocol, runtime_checkable

from .tracing import TraceSpan

logger = logging.getLogger(__name__)


@runtime_checkable
class TraceSink(Protocol):
    """Persistence contract for trace spans.

    MemoryTraceSink satisfies this today; FileTraceSink writes to disk in
    real time. A future OTel exporter needs only to implement these members.
    """

    def store(self, span: TraceSpan) -> None: ...

    def trace(self, correlation_id: str | None) -> list[TraceSpan]: ...

    def all_traces(self) -> dict[str | None, list[TraceSpan]]: ...

    def clear(self) -> int: ...

    @property
    def trace_count(self) -> int: ...

    @property
    def span_count(self) -> int: ...


class MemoryTraceSink:
    """In-memory grouped store (the original BridgeTraceRecorder behavior)."""

    def __init__(self, max_traces: int = 10_000) -> None:
        self._max_traces = max_traces
        self._traces: dict[str | None, list[TraceSpan]] = {}

    def store(self, span: TraceSpan) -> None:
        self._traces.setdefault(span.correlation_id, []).append(span)
        self._enforce_cap()

    def trace(self, correlation_id: str | None) -> list[TraceSpan]:
        return list(self._traces.get(correlation_id, []))

    def all_traces(self) -> dict[str | None, list[TraceSpan]]:
        return {cid: list(spans) for cid, spans in self._traces.items()}

    def clear(self) -> int:
        n = len(self._traces)
        self._traces.clear()
        return n

    @property
    def trace_count(self) -> int:
        return len(self._traces)

    @property
    def span_count(self) -> int:
        return sum(len(spans) for spans in self._traces.values())

    def _enforce_cap(self) -> None:
        while len(self._traces) > self._max_traces:
            oldest = next(iter(self._traces))
            del self._traces[oldest]


class FileTraceSink:
    """JSONL file sink with size-based rotation.

    Each span is written as one JSON line immediately. The in-memory grouped
    view is kept for queries; the file is the durable copy. When the file
    exceeds *max_bytes* it rotates to ``<path>.1``. Thread-safe.
    """

    def __init__(
        self,
        path: str | Path,
        max_bytes: int = 10 * 1024 * 1024,
        max_traces: int = 10_000,
    ) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._max_bytes = max_bytes
        self._mem = MemoryTraceSink(max_traces=max_traces)
        self._lock = threading.RLock()

    def _maybe_rotate(self) -> None:
        try:
            if self._path.exists() and self._path.stat().st_size >= self._max_bytes:
                rotated = self._path.with_suffix(self._path.suffix + ".1")
                self._path.replace(rotated)
        except OSError:
            logger.warning("trace rotation failed for %s", self._path, exc_info=True)

    def store(self, span: TraceSpan) -> None:
        with self._lock:
            self._mem.store(span)
            self._maybe_rotate()
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(span.to_dict(), default=str) + "\n")

    def trace(self, correlation_id: str | None) -> list[TraceSpan]:
        return self._mem.trace(correlation_id)

    def all_traces(self) -> dict[str | None, list[TraceSpan]]:
        return self._mem.all_traces()

    def clear(self) -> int:
        n = self._mem.clear()
        return n

    @property
    def trace_count(self) -> int:
        return self._mem.trace_count

    @property
    def span_count(self) -> int:
        return self._mem.span_count

    @property
    def path(self) -> Path:
        return self._path
