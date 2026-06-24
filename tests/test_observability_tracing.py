"""Tests for the bridge-chain trace recorder.
桥接链追踪记录器测试
"""


from gaiaagent.core.message import AURCMessage, BridgeContext, MessageBody
from gaiaagent.core.types import MessageDirection
from gaiaagent.observability.tracing import BridgeTraceRecorder, TraceSpan


def _make_message(
    *,
    correlation_id: str | None = "corr-1",
    source: str = "aurc:gaia/orchestrator:v1.0",
    target: str = "aurc:gaia/researcher:v1.2",
    msg_type: MessageDirection = MessageDirection.REQUEST,
    origin_protocol: str = "aurc",
    bridge_chain: list[str] | None = None,
) -> AURCMessage:
    return AURCMessage(
        source=source,
        target=target,
        type=msg_type,
        correlation_id=correlation_id,
        body=MessageBody(method="invoke", skill="research"),
        protocol_context=BridgeContext(
            origin_protocol=origin_protocol,
            bridged_from=origin_protocol if origin_protocol != "aurc" else None,
            bridge_chain=bridge_chain or [],
        ),
    )


class TestBridgeTraceRecorder:
    def test_record_returns_span(self):
        recorder = BridgeTraceRecorder()
        msg = _make_message(bridge_chain=["a2a→aurc"])
        span = recorder.record(msg)

        assert isinstance(span, TraceSpan)
        assert span.correlation_id == "corr-1"
        assert span.origin_protocol == "aurc"
        assert span.bridge_chain == ["a2a→aurc"]
        assert span.hop_count == 1
        assert span.type == "request"

    def test_groups_spans_by_correlation_id(self):
        """A multi-hop trace: A2A in -> AURC -> MCP out, same correlation_id."""
        recorder = BridgeTraceRecorder()

        # Hop 1: A2A bridge translates an inbound A2A task to AURC.
        # 跳 1：A2A 桥接将入站 A2A 任务翻译为 AURC。
        recorder.record(
            _make_message(
                correlation_id="corr-trace",
                source="a2a:external/expert",
                target="aurc:gaia/orchestrator:v1.0",
                msg_type=MessageDirection.DELEGATION,
                origin_protocol="a2a/1.0",
                bridge_chain=["a2a→aurc"],
            )
        )
        # Hop 2: Orchestrator routes to a local AURC agent.
        # 跳 2：编排器路由到本地 AURC Agent。
        recorder.record(
            _make_message(
                correlation_id="corr-trace",
                source="aurc:gaia/orchestrator:v1.0",
                target="aurc:gaia/researcher:v1.2",
                origin_protocol="aurc",
                bridge_chain=["a2a→aurc"],
            )
        )
        # Hop 3: AURC -> MCP bridge forwards to an MCP tool.
        # 跳 3：AURC -> MCP 桥接转发到 MCP 工具。
        recorder.record(
            _make_message(
                correlation_id="corr-trace",
                source="aurc:gaia/researcher:v1.2",
                target="mcp:web-search/server",
                origin_protocol="mcp/2025-06-18",
                bridge_chain=["a2a→aurc", "aurc→mcp"],
            )
        )

        trace = recorder.get_trace("corr-trace")
        assert len(trace) == 3
        assert trace[0].source == "a2a:external/expert"
        assert trace[2].target == "mcp:web-search/server"
        assert trace[2].hop_count == 2
        assert trace[2].bridge_chain == ["a2a→aurc", "aurc→mcp"]

    def test_render_trace_multi_line(self):
        recorder = BridgeTraceRecorder()
        recorder.record(
            _make_message(
                bridge_chain=["mcp→aurc"],
                origin_protocol="mcp/2025-06-18",
            )
        )
        rendered = recorder.render_trace("corr-1")
        assert "trace corr-1" in rendered
        assert "1 span" in rendered
        assert "mcp→aurc" in rendered

    def test_render_trace_empty(self):
        recorder = BridgeTraceRecorder()
        rendered = recorder.render_trace("nonexistent")
        assert "no spans" in rendered

    def test_counts(self):
        recorder = BridgeTraceRecorder()
        recorder.record(_make_message(correlation_id="a"))
        recorder.record(_make_message(correlation_id="a"))
        recorder.record(_make_message(correlation_id="b"))

        assert recorder.trace_count == 2
        assert recorder.span_count == 3

    def test_clear(self):
        recorder = BridgeTraceRecorder()
        recorder.record(_make_message())
        assert recorder.clear() == 1
        assert recorder.trace_count == 0

    def test_to_log_line_and_dict(self):
        recorder = BridgeTraceRecorder()
        span = recorder.record(_make_message(bridge_chain=["a2a→aurc"]))
        line = span.to_log_line()
        assert "trace=corr-1" in line
        assert "a2a→aurc" in line

        d = span.to_dict()
        assert d["correlation_id"] == "corr-1"
        assert d["bridge_chain"] == ["a2a→aurc"]

    def test_cap_evicts_oldest(self):
        """When the trace cap is exceeded, the oldest correlation is dropped."""
        recorder = BridgeTraceRecorder(max_traces=2)
        recorder.record(_make_message(correlation_id="c1"))
        recorder.record(_make_message(correlation_id="c2"))
        recorder.record(_make_message(correlation_id="c3"))

        assert recorder.trace_count == 2
        assert recorder.get_trace("c1") == []  # evicted / 已淘汰
        assert len(recorder.get_trace("c3")) == 1

    def test_none_correlation_grouped_separately(self):
        """Messages without a correlation_id are grouped under None and still traceable."""
        recorder = BridgeTraceRecorder()
        recorder.record(_make_message(correlation_id=None))
        assert recorder.trace_count == 1
        assert len(recorder.get_trace(None)) == 1
