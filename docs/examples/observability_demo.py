"""AURC Observability Demo — a real multi-protocol flow under full instrumentation.
AURC 可观测性实战示例 — 一个被完整观测的真实多协议流

This is the "实战结合" piece: it wires the runtime (Harness + Router + Audit
+ Registry) together with all three protocol bridges (MCP / A2A / ACP) and the
new observability surfaces (HealthDashboard, Prometheus exporter, bridge-chain
tracer), then runs a single correlated request that crosses every protocol
boundary — exactly the scenario a production operator would scrape and trace.

这是"实战结合"部分：把运行时（Harness + Router + Audit + Registry）与三个
协议桥接（MCP / A2A / ACP）及新增的可观测面（HealthDashboard、Prometheus
导出器、桥接链追踪器）接在一起，然后跑一个跨所有协议边界的、单一关联的
请求——正是生产运维人员会去抓取与追踪的场景。

Flow / 流程 (correlation_id = "corr-demo-001"):
    1. Inbound  : MCP client → tools/call → MCPBridge → AURC (direct route)
    2. Outbound : AURC orchestrator → A2A agent (bridged route)
    3. Outbound : AURC orchestrator → ACP agent (bridged route)

Run / 运行:  python docs/examples/observability_demo.py
No third-party deps required (no httpx / websockets / anthropic).
无需第三方依赖（不需要 httpx / websockets / anthropic）。
"""

from __future__ import annotations

import asyncio
import json
import logging

from gaiaagent.bridges.a2a import A2ABridge
from gaiaagent.bridges.acp import ACPBridge
from gaiaagent.bridges.base import MCPBridge
from gaiaagent.bus.router import MessageRouter
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection
from gaiaagent.harness.lifecycle import RuntimeHarness
from gaiaagent.observability import (
    BridgeTraceRecorder,
    HealthDashboard,
    PrometheusMetricsExporter,
    TraceSpan,
)
from gaiaagent.security.audit import AuditAction, AuditLog

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("observability-demo")

CORRELATION_ID = "corr-demo-001"


async def main() -> None:
    # ---- 1. Stand up the runtime / 搭建运行时 ----
    harness = RuntimeHarness()
    router = MessageRouter()
    audit = AuditLog(max_entries=10_000)
    tracer = BridgeTraceRecorder()

    # Bridges (translators only — no live servers needed for this demo)
    # 桥接器（仅翻译，本示例不需要真实服务器）
    bridges = {"mcp": MCPBridge(), "a2a": A2ABridge(), "acp": ACPBridge()}

    # ---- 2. Local AURC handler (inbound target) / 本地 AURC 处理函数 ----
    async def local_handler(msg: AURCMessage) -> dict:
        audit.log(
            AuditAction.MESSAGE_RECEIVED,
            agent_id=msg.target,
            message_id=msg.message_id,
            correlation_id=msg.correlation_id,
            details={"skill": msg.body.skill, "origin": msg.protocol_context.origin_protocol},
        )
        return {"processed": True, "skill": msg.body.skill}

    router.register_handler("aurc:local/handler", local_handler)

    # ---- 3. Bridge forwarders (outbound) / 桥接转发函数（出站） ----
    def make_forwarder(name: str, bridge):
        async def forwarder(msg: AURCMessage) -> dict:
            # Record the outbound bridge hop as a synthetic span with an
            # augmented bridge_chain, so the trace shows AURC -> external.
            # 将出站桥接跳记录为合成 span，附加 bridge_chain，使追踪显示
            # AURC -> 外部。
            inbound_chain = list(msg.protocol_context.bridge_chain)
            outbound_chain = inbound_chain + [f"aurc→{name}"]
            tracer.record_span(
                TraceSpan(
                    correlation_id=msg.correlation_id,
                    message_id=msg.message_id,
                    source=msg.source,
                    target=msg.target,
                    type=msg.type.value,
                    origin_protocol=name,
                    bridge_chain=outbound_chain,
                    hop_count=len(outbound_chain),
                    timestamp=msg.timestamp.isoformat() if msg.timestamp else "",
                )
            )
            external = await bridge.translate_from_aurc(msg)
            audit.log(
                AuditAction.MESSAGE_BRIDGED,
                agent_id=msg.target,
                message_id=msg.message_id,
                correlation_id=msg.correlation_id,
                details={"protocol": name, "payload_keys": list(external.keys())},
            )
            logger.info("bridged out via %s -> %s", name, msg.target)
            return {"forwarded": name, "payload": external}

        return forwarder

    for name, bridge in bridges.items():
        router.register_bridge_forwarder(name, make_forwarder(name, bridge))

    # ---- 4. Run a correlated cross-protocol flow / 跑一个关联的跨协议流 ----
    audit.log(AuditAction.SESSION_CREATED, correlation_id=CORRELATION_ID)

    # 4a. Inbound: MCP tools/call -> AURC (direct route to local handler)
    # 入站：MCP tools/call -> AURC（直连路由到本地处理函数）
    mcp_request = {
        "jsonrpc": "2.0",
        "id": "mcp-1",
        "method": "tools/call",
        "params": {"name": "web-search", "arguments": {"query": "AURC protocol"}},
    }
    inbound_msg = await bridges["mcp"].translate_to_aurc(mcp_request)
    inbound_msg.correlation_id = CORRELATION_ID  # tie into the trace / 关联到追踪
    tracer.record(inbound_msg)
    await router.route(inbound_msg)
    logger.info("inbound MCP -> AURC handled (direct)")

    # 4b. Outbound: AURC orchestrator delegates to an A2A agent (bridged)
    # 出站：AURC 编排器委派给 A2A Agent（桥接）
    a2a_msg = AURCMessage(
        source="aurc:example/orchestrator:v1.0",
        target="a2a:external/expert",
        type=MessageDirection.DELEGATION,
        correlation_id=CORRELATION_ID,
        body=MessageBody(
            method="invoke",
            skill="research",
            params={"task_id": "t-2", "content": "Analyze AURC vs MCP/A2A"},
        ),
    )
    await router.route(a2a_msg)

    # 4c. Outbound: AURC orchestrator delegates to an ACP agent (bridged)
    # 出站：AURC 编排器委派给 ACP Agent（桥接）
    acp_msg = AURCMessage(
        source="aurc:example/orchestrator:v1.0",
        target="acp:external/summarizer",
        type=MessageDirection.DELEGATION,
        correlation_id=CORRELATION_ID,
        body=MessageBody(
            method="invoke",
            skill="summarize",
            params={"task_id": "t-3", "task": "Summarize the AURC spec"},
        ),
    )
    await router.route(acp_msg)

    # A deliberately undeliverable message to exercise the dead-letter queue.
    # 一条故意不可投递的消息，以触发死信队列。
    orphan = AURCMessage(
        source="aurc:example/orchestrator:v1.0",
        target="aurc:nowhere/missing",
        type=MessageDirection.REQUEST,
        correlation_id=CORRELATION_ID,
        body=MessageBody(method="invoke", skill="noop"),
    )
    tracer.record(orphan)
    await router.route(orphan)

    # ---- 5. Render the observability surfaces / 渲染可观测面 ----
    dashboard = HealthDashboard(harness, audit=audit, router=router)

    print("\n" + "=" * 72)
    print(" SYSTEM HEALTH (JSON) / 系统健康")
    print("=" * 72)
    print(json.dumps(dashboard.get_system_health(), indent=2, default=str))

    print("\n" + "=" * 72)
    print(" PROMETHEUS METRICS (scrape /metrics) / Prometheus 指标")
    print("=" * 72)
    print(PrometheusMetricsExporter(dashboard).render(), end="")

    print("\n" + "=" * 72)
    print(f" BRIDGE-CHAIN TRACE ({CORRELATION_ID}) / 桥接链追踪")
    print("=" * 72)
    print(tracer.render_trace(CORRELATION_ID))

    print("\n" + "=" * 72)
    print(" ROUTER STATS / 路由器统计")
    print("=" * 72)
    print(json.dumps(router.stats.to_dict(), indent=2))

    print(f"\nTracer: {tracer.span_count} spans across {tracer.trace_count} trace(s).")
    print(f"Audit:  {audit.count} entries recorded.")
    print("\nDone. In production, mount DashboardAPI on an ASGI server and")
    print("scrape /metrics with Prometheus; ship traces to OpenTelemetry.")


if __name__ == "__main__":
    asyncio.run(main())
