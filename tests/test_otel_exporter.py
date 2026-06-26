"""Tests for the OTelSpanExporter (observability/otel.py).

Verifies graceful degradation when opentelemetry is not installed, and
correct span export when it is (mocked).
"""

from __future__ import annotations

import pytest

from gaiaagent.observability.otel import OTelSpanExporter
from gaiaagent.observability.tracing import BridgeTraceRecorder, TraceSpan


def _make_span(
    correlation_id: str | None = "corr-1",
    message_id: str = "msg-1",
    source: str = "aurc:test/src:v1.0",
    target: str = "aurc:test/tgt:v1.0",
    hop_count: int = 0,
) -> TraceSpan:
    return TraceSpan(
        correlation_id=correlation_id,
        message_id=message_id,
        source=source,
        target=target,
        type="invoke",
        origin_protocol="mcp",
        bridge_chain=["mcp" + chr(0x2192) + "aurc"],
        hop_count=hop_count,
        timestamp="2026-01-01T00:00:00+00:00",
    )


class TestOTelSpanExporter:
    def test_export_without_opentelemetry_is_noop(self):
        """When opentelemetry is not installed, export returns 0 and does not raise."""
        recorder = BridgeTraceRecorder()
        recorder.record_span(_make_span())
        exporter = OTelSpanExporter(recorder)
        # If opentelemetry is not installed, available is False
        if not exporter.available:
            import asyncio
            count = asyncio.run(exporter.export())
            assert count == 0

    def test_available_property_reflects_install(self):
        recorder = BridgeTraceRecorder()
        exporter = OTelSpanExporter(recorder)
        try:
            import opentelemetry  # noqa: F401
            assert exporter.available is True
        except ImportError:
            assert exporter.available is False

    @pytest.mark.asyncio
    async def test_export_empty_recorder_returns_zero(self):
        recorder = BridgeTraceRecorder()
        exporter = OTelSpanExporter(recorder)
        count = await exporter.export()
        assert count == 0

    @pytest.mark.asyncio
    async def test_export_all_traces_returns_span_count(self):
        """When opentelemetry IS installed, export returns the number of spans."""
        recorder = BridgeTraceRecorder()
        recorder.record_span(_make_span("c1", "m1"))
        recorder.record_span(_make_span("c1", "m2"))
        recorder.record_span(_make_span("c2", "m3"))
        exporter = OTelSpanExporter(recorder)
        if exporter.available:
            count = await exporter.export()
            assert count == 3
        else:
            count = await exporter.export()
            assert count == 0  # graceful degradation

    @pytest.mark.asyncio
    async def test_export_single_correlation(self):
        """export(correlation_id) only exports spans for that trace."""
        recorder = BridgeTraceRecorder()
        recorder.record_span(_make_span("c1", "m1"))
        recorder.record_span(_make_span("c2", "m2"))
        exporter = OTelSpanExporter(recorder)
        if exporter.available:
            count = await exporter.export("c1")
            assert count == 1
            count_other = await exporter.export("c2")
            assert count_other == 1
        else:
            assert await exporter.export("c1") == 0

    def test_shutdown_does_not_raise(self):
        recorder = BridgeTraceRecorder()
        exporter = OTelSpanExporter(recorder)
        exporter.shutdown()  # should be safe regardless

    @pytest.mark.asyncio
    async def test_export_with_mocked_tracer(self, monkeypatch):
        """When opentelemetry is available, spans are emitted with correct attributes."""
        recorder = BridgeTraceRecorder()
        recorder.record_span(_make_span("c1", "m1", hop_count=0))
        recorder.record_span(_make_span("c1", "m2", hop_count=1))

        exporter = OTelSpanExporter(recorder)
        if not exporter.available:
            pytest.skip("opentelemetry not installed; skipping mocked tracer test")

        # Capture emitted spans
        emitted: list[dict] = []

        class _FakeSpan:
            def __init__(self):
                self._attrs: dict = {}
            def set_attributes(self, attrs):
                self._attrs.update(attrs)
            def __enter__(self):
                return self
            def __exit__(self, *a):
                emitted.append(self._attrs)

        class _FakeTracer:
            def start_as_current_span(self, name):
                emitted.append({"_name": name})
                return _FakeSpan()

        # Replace the tracer
        exporter._tracer = _FakeTracer()

        count = await exporter.export("c1")
        assert count == 2
        # Each span emits a name entry and an attributes entry
        assert len(emitted) == 4  # 2 names + 2 attribute dicts
