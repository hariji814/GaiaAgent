"""OpenTelemetry exporter for AURC BridgeTraceSpans.
AURC BridgeTraceSpan 的 OpenTelemetry 导出器

Maps the in-process trace spans recorded by ``BridgeTraceRecorder`` onto
OpenTelemetry trace spans. This is the **OTel integration point** promised
by the observability layer (Track 4 of the roadmap): the bridge-chain
metadata that AURC already records per message becomes structured OTel
span attributes, so cross-protocol hops show up in any OTel-compatible
backend (Jaeger, Tempo, Honeycomb, …).

Graceful degradation / 优雅降级:
    The ``opentelemetry`` package is an *optional* runtime dependency. When
    it is not installed, :meth:`OTelSpanExporter.export` logs a debug message
    and returns without raising — the rest of AURC keeps working. This makes
    the exporter safe to wire unconditionally.
"""

from __future__ import annotations

import logging
from typing import Any

from .tracing import BridgeTraceRecorder, TraceSpan

logger = logging.getLogger(__name__)

# OTel attribute names — stable so downstream dashboards can filter on them.
_ATTR_CORRELATION_ID = "aurc.correlation_id"
_ATTR_MESSAGE_ID = "aurc.message_id"
_ATTR_SOURCE = "aurc.source"
_ATTR_TARGET = "aurc.target"
_ATTR_MSG_TYPE = "aurc.message_type"
_ATTR_ORIGIN_PROTOCOL = "aurc.origin_protocol"
_ATTR_BRIDGE_CHAIN = "aurc.bridge_chain"
_ATTR_HOP_COUNT = "aurc.hop_count"


class OTelSpanExporter:
    """Export recorded AURC trace spans as OpenTelemetry spans.
    把已记录的 AURC 追踪 span 导出为 OpenTelemetry span

    Usage / 用法::

        exporter = OTelSpanExporter(recorder)
        await exporter.export()            # flush all recorded spans
        await exporter.export("corr-42")   # flush one trace

    When ``opentelemetry`` is not installed, :meth:`export` is a no-op
    that logs at DEBUG level. This keeps AURC fully functional without
    forcing the OTel dependency.
    """

    def __init__(self, recorder: BridgeTraceRecorder) -> None:
        self._recorder = recorder
        self._otel_available = False
        self._tracer = None
        try:
            from opentelemetry import trace as _otel_trace  # noqa: F401
            from opentelemetry.sdk.trace import TracerProvider
            self._otel_trace = _otel_trace
            self._otel_available = True
            # Use a dedicated provider so we don't clobber a global one.
            self._provider = TracerProvider()
            self._tracer = self._provider.get_tracer("gaiaagent.aurc")
        except ImportError:
            self._otel_trace = None  # type: ignore[assignment]
            self._provider = None
            logger.debug(
                "opentelemetry not installed; OTelSpanExporter.export is a no-op"
            )

    @property
    def available(self) -> bool:
        """True when the opentelemetry package is importable.
        opentelemetry 包可导入时返回 True
        """
        return self._otel_available

    async def export(self, correlation_id: str | None = None) -> int:
        """Export spans as OTel trace spans.

        Args:
            correlation_id: If given, export only the spans for that trace.
                If ``None``, export every recorded trace.

        Returns:
            The number of spans exported (0 when OTel is unavailable or
            no spans were recorded).
        """
        if not self._otel_available or self._tracer is None:
            logger.debug("OTel export skipped (opentelemetry unavailable)")
            return 0

        if correlation_id is not None:
            spans = self._recorder.get_trace(correlation_id)
        else:
            all_traces = self._recorder.all_traces()
            spans = [s for trace in all_traces.values() for s in trace]

        if not spans:
            return 0

        count = 0
        for span in spans:
            self._emit_span(span)
            count += 1
        return count

    def _emit_span(self, span: TraceSpan) -> None:
        """Emit one TraceSpan as an OTel span with AURC attributes."""
        assert self._tracer is not None  # guarded by export()
        span_name = f"aurc.hop {span.source} -> {span.target}"
        attributes = {
            _ATTR_CORRELATION_ID: span.correlation_id or "",
            _ATTR_MESSAGE_ID: span.message_id,
            _ATTR_SOURCE: span.source,
            _ATTR_TARGET: span.target,
            _ATTR_MSG_TYPE: span.type,
            _ATTR_ORIGIN_PROTOCOL: span.origin_protocol,
            _ATTR_BRIDGE_CHAIN: " > ".join(span.bridge_chain) if span.bridge_chain else "direct",
            _ATTR_HOP_COUNT: span.hop_count,
        }
        # start_span is synchronous; it creates and immediately ends a span.
        with self._tracer.start_as_current_span(span_name) as otel_span:
            otel_span.set_attributes(attributes)

    def shutdown(self) -> None:
        """Release OTel resources (the TracerProvider) if we created one."""
        if self._provider is not None:
            try:
                self._provider.shutdown()
            except Exception:  # pragma: no cover — best-effort cleanup
                logger.debug("OTel provider shutdown failed", exc_info=True)


__all__ = ["OTelSpanExporter"]
