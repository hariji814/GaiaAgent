"""AURC Bridge-Chain Tracing — structured correlation across protocol hops.
AURC 桥接链追踪 — 跨协议跳的结构化关联

Every AURC message carries a `correlation_id` and a `bridge_chain` (e.g.
`["a2a→aurc", "aurc→mcp"]`). This module turns that raw metadata into a
queryable trace: record each message that flows through the bus, group by
`correlation_id`, and reconstruct the cross-protocol path a request took.

每条 AURC 消息携带 `correlation_id` 与 `bridge_chain`（如
`["a2a→aurc", "aurc→mcp"]`）。本模块将原始元数据转为可查询的追踪：记录
流经总线的每条消息，按 `correlation_id` 分组，重建一个请求跨协议的路径。

This is the in-process foundation for the OpenTelemetry integration on the
roadmap (Track 4): the spans it records map directly onto OTel trace spans.
这是路线图（赛道 4）OpenTelemetry 集成的进程内基础：其记录的 span 可直接
映射为 OTel 追踪 span。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.message import AURCMessage


@dataclass
class TraceSpan:
    """A single recorded hop in a cross-protocol trace.
    跨协议追踪中记录的单个跳
    """

    correlation_id: str | None
    message_id: str
    source: str
    target: str
    type: str
    origin_protocol: str
    bridge_chain: list[str]
    hop_count: int
    timestamp: str

    def to_log_line(self) -> str:
        """Render the span as a single structured log line.
        将 span 渲染为单行结构化日志
        """
        chain = " > ".join(self.bridge_chain) if self.bridge_chain else "direct"
        return (
            f"trace={self.correlation_id or '-'} "
            f"msg={self.message_id} "
            f"{self.source} -> {self.target} "
            f"type={self.type} proto={self.origin_protocol} "
            f"chain=[{chain}] hops={self.hop_count}"
        )

    def to_dict(self) -> dict[str, Any]:
        """Render the span as a dict (for JSON export / OTel mapping).
        将 span 渲染为字典（用于 JSON 导出 / OTel 映射）
        """
        return {
            "correlation_id": self.correlation_id,
            "message_id": self.message_id,
            "source": self.source,
            "target": self.target,
            "type": self.type,
            "origin_protocol": self.origin_protocol,
            "bridge_chain": list(self.bridge_chain),
            "hop_count": self.hop_count,
            "timestamp": self.timestamp,
        }


class BridgeTraceRecorder:
    """Records AURC messages and groups them by correlation_id.
    记录 AURC 消息并按 correlation_id 分组

    Usage / 用法:
        recorder = BridgeTraceRecorder()
        span = recorder.record(message)        # record a hop
        trace = recorder.get_trace("corr-1")   # all hops for a correlation
        for span in trace:
            print(span.to_log_line())
    """

    def __init__(self, max_traces: int = 10_000) -> None:
        self._max_traces = max_traces
        self._traces: dict[str | None, list[TraceSpan]] = {}

    def record(self, message: AURCMessage) -> TraceSpan:
        """Record a message as a trace span, keyed by its correlation_id.
        将一条消息记录为追踪 span，按 correlation_id 索引

        Returns the recorded TraceSpan.
        返回已记录的 TraceSpan。
        """
        ctx = message.protocol_context
        span = TraceSpan(
            correlation_id=message.correlation_id,
            message_id=message.message_id,
            source=message.source,
            target=message.target,
            type=message.type.value,
            origin_protocol=ctx.origin_protocol,
            bridge_chain=list(ctx.bridge_chain),
            hop_count=ctx.hop_count,
            timestamp=message.timestamp.isoformat() if message.timestamp else "",
        )
        return self.record_span(span)

    def record_span(self, span: TraceSpan) -> TraceSpan:
        """Record a pre-built span (e.g. a synthetic outbound bridge hop).
        记录一个已构建的 span（如合成的出站桥接跳）

        Use this when a span does not correspond 1:1 to an inbound AURCMessage —
        for example, a bridge forwarder that wants to record the *outbound* hop
        it just performed (AURC → external) with an augmented bridge_chain.
        当 span 与入站 AURCMessage 非一一对应时使用——例如桥接转发器想记录
        它刚执行的*出站*跳（AURC → 外部），并附加 bridge_chain。
        """
        self._traces.setdefault(span.correlation_id, []).append(span)
        self._enforce_cap()
        return span

    def get_trace(self, correlation_id: str | None) -> list[TraceSpan]:
        """Return all spans sharing a correlation_id, in insertion order.
        返回共享同一 correlation_id 的所有 span（按插入顺序）
        """
        return list(self._traces.get(correlation_id, []))

    def all_traces(self) -> dict[str | None, list[TraceSpan]]:
        """Return a snapshot of every recorded trace.
        返回所有已记录追踪的快照
        """
        return {cid: list(spans) for cid, spans in self._traces.items()}

    def render_trace(self, correlation_id: str | None) -> str:
        """Render a full trace as multi-line structured logs.
        将完整追踪渲染为多行结构化日志
        """
        spans = self.get_trace(correlation_id)
        if not spans:
            return f"trace={correlation_id or '-'} (no spans recorded)"
        max_hops = max(s.hop_count for s in spans)
        header = (
            f"=== trace {correlation_id or '-'} : "
            f"{len(spans)} span(s), deepest {max_hops} hop(s) ==="
        )
        return "\n".join([header, *(s.to_log_line() for s in spans)])

    @property
    def trace_count(self) -> int:
        """Number of distinct correlation IDs recorded.
        已记录的不同 correlation ID 数量
        """
        return len(self._traces)

    @property
    def span_count(self) -> int:
        """Total spans recorded across all traces.
        所有追踪中记录的 span 总数
        """
        return sum(len(spans) for spans in self._traces.values())

    def clear(self) -> int:
        """Clear all recorded traces. Returns the number of traces dropped.
        清除所有已记录追踪。返回被丢弃的追踪数量
        """
        dropped = len(self._traces)
        self._traces.clear()
        return dropped

    def _enforce_cap(self) -> None:
        """Evict the oldest traces when the cap is exceeded.
        超出上限时淘汰最旧的追踪
        """
        # dict preserves insertion order in Python 3.7+; drop oldest keys first.
        # dict 在 Python 3.7+ 保持插入顺序；优先丢弃最早的 key。
        while len(self._traces) > self._max_traces:
            oldest = next(iter(self._traces))
            del self._traces[oldest]


__all__ = ["TraceSpan", "BridgeTraceRecorder"]
