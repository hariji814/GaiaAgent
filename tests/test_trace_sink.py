"""Phase 4.2 tests: TraceSink Protocol + FileTraceSink real-time persistence.

Verifies the sink abstraction, BridgeTraceRecorder delegation, and that
FileTraceSink persists each span to JSONL in real time with rotation.
"""
from __future__ import annotations

import json

from gaiaagent.core.message import AURCMessage, BridgeContext, MessageBody
from gaiaagent.core.types import MessageDirection
from gaiaagent.observability.trace_sink import (
    FileTraceSink,
    MemoryTraceSink,
    TraceSink,
)
from gaiaagent.observability.tracing import BridgeTraceRecorder, TraceSpan


def _span(cid="corr-1", msg_id="m1"):
    return TraceSpan(
        correlation_id=cid,
        message_id=msg_id,
        source="a",
        target="b",
        type="request",
        origin_protocol="aurc",
        bridge_chain=["a2a->aurc"],
        hop_count=1,
        timestamp="2026-06-26T00:00:00+00:00",
    )


def _make_message(cid="corr-1"):
    return AURCMessage(
        source="a",
        target="b",
        type=MessageDirection.REQUEST,
        correlation_id=cid,
        body=MessageBody(method="invoke", skill="research"),
        protocol_context=BridgeContext(origin_protocol="aurc", bridge_chain=["a2a->aurc"]),
    )


class TestProtocolConformance:
    def test_memory_sink_is_trace_sink(self):
        assert isinstance(MemoryTraceSink(), TraceSink)

    def test_file_sink_is_trace_sink(self, tmp_path):
        assert isinstance(FileTraceSink(tmp_path / "t.jsonl"), TraceSink)


class TestFileTraceSink:
    def test_real_time_write(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        sink = FileTraceSink(path)
        sink.store(_span())
        assert path.exists()
        rec = json.loads(path.read_text(encoding="utf-8").strip())
        assert rec["correlation_id"] == "corr-1"
        assert rec["bridge_chain"] == ["a2a->aurc"]

    def test_rotation_on_size(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        sink = FileTraceSink(path, max_bytes=1)
        sink.store(_span(cid="c1"))
        sink.store(_span(cid="c2"))
        rotated = tmp_path / "trace.jsonl.1"
        assert rotated.exists()
        assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 1

    def test_grouped_query(self, tmp_path):
        sink = FileTraceSink(tmp_path / "t.jsonl")
        sink.store(_span(cid="c1", msg_id="m1"))
        sink.store(_span(cid="c1", msg_id="m2"))
        sink.store(_span(cid="c2", msg_id="m3"))
        assert len(sink.trace("c1")) == 2
        assert len(sink.trace("c2")) == 1
        assert sink.span_count == 3
        assert sink.trace_count == 2

    def test_clear(self, tmp_path):
        sink = FileTraceSink(tmp_path / "t.jsonl")
        sink.store(_span())
        assert sink.clear() == 1
        assert sink.span_count == 0


class TestRecorderDelegation:
    def test_default_is_memory(self):
        rec = BridgeTraceRecorder()
        rec.record(_make_message())
        assert rec.span_count == 1

    def test_file_sink_persists(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        rec = BridgeTraceRecorder(sink=FileTraceSink(path))
        rec.record(_make_message(cid="corr-x"))
        assert path.exists()
        rec_line = json.loads(path.read_text(encoding="utf-8").strip())
        assert rec_line["correlation_id"] == "corr-x"

    def test_get_trace_through_file_sink(self, tmp_path):
        rec = BridgeTraceRecorder(sink=FileTraceSink(tmp_path / "t.jsonl"))
        rec.record(_make_message(cid="c1"))
        rec.record(_make_message(cid="c1"))
        trace = rec.get_trace("c1")
        assert len(trace) == 2
        assert all(s.correlation_id == "c1" for s in trace)
