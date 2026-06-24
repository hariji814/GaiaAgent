"""AURC Health Dashboard — observability endpoints for runtime monitoring.
AURC 健康仪表盘 — 运行时监控的可观测性端点

Provides:
- HealthDashboard: aggregates health data from Harness, AuditLog, and Router
  健康仪表盘：聚合来自 Harness、AuditLog 和 Router 的健康数据
- DashboardAPI: ASGI handler exposing JSON API and HTML dashboard
  仪表盘 API：暴露 JSON API 和 HTML 仪表盘的 ASGI 处理器
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote

from ..core.types import AgentState, HealthStatus
from ..harness.lifecycle import AgentInstance, RuntimeHarness
from ..security.audit import AuditLog, AuditSeverity

logger = logging.getLogger(__name__)


# =============================================================================
# HTML Dashboard Template / HTML 仪表盘模板
# =============================================================================

_DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>AURC Dashboard</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{--bg:#f8f9fa;--fg:#1a1a2e;--card:#fff;--border:#e2e8f0;--accent:#3b82f6;
--ok:#22c55e;--warn:#f59e0b;--err:#ef4444;--dim:#94a3b8}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f172a;--fg:#e2e8f0;--card:#1e293b;
--border:#334155;--dim:#64748b}}}}
body{{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);
color:var(--fg);padding:1rem 2rem;line-height:1.5}}
h1{{font-size:1.4rem;margin-bottom:.25rem}}
h2{{font-size:1rem;color:var(--dim);margin:1.5rem 0 .5rem;font-weight:600}}
.bar{{display:flex;gap:.75rem;flex-wrap:wrap;margin:.75rem 0}}
.chip{{padding:.35rem .7rem;border-radius:6px;font-size:.85rem;font-weight:500;
background:var(--card);border:1px solid var(--border)}}
.chip.ok{{border-left:3px solid var(--ok)}}
.chip.warn{{border-left:3px solid var(--warn)}}
.chip.err{{border-left:3px solid var(--err)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));
gap:.75rem;margin:.5rem 0}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:8px;
padding:.9rem}}
.card h3{{font-size:.9rem;margin-bottom:.4rem;word-break:break-all}}
.card .row{{display:flex;justify-content:space-between;font-size:.8rem;
padding:.15rem 0}}
.card .lbl{{color:var(--dim)}}
.badge{{display:inline-block;padding:.1rem .4rem;border-radius:4px;
font-size:.75rem;font-weight:600}}
.b-ok{{background:#22c55e22;color:var(--ok)}}
.b-deg{{background:#f59e0b22;color:var(--warn)}}
.b-unh{{background:#ef444422;color:var(--err)}}
.b-unk{{background:#94a3b822;color:var(--dim)}}
table{{width:100%;border-collapse:collapse;margin:.5rem 0;font-size:.8rem}}
th,td{{text-align:left;padding:.4rem .6rem;border-bottom:1px solid var(--border)}}
th{{color:var(--dim);font-weight:600;font-size:.75rem;text-transform:uppercase}}
.sev-info{{color:var(--accent)}}.sev-warning{{color:var(--warn)}}
.sev-error{{color:var(--err)}}.sev-critical{{color:#dc2626;font-weight:700}}
.empty{{color:var(--dim);font-style:italic;padding:1rem 0}}
</style>
</head>
<body>
<h1>AURC Runtime Dashboard</h1>
<p style="color:var(--dim);font-size:.8rem">Auto-refresh every 30s &middot; {timestamp}</p>

<h2>System Health</h2>
<div class="bar">
  <span class="chip ok">Healthy: {healthy}</span>
  <span class="chip warn">Degraded: {degraded}</span>
  <span class="chip err">Unhealthy: {unhealthy}</span>
  <span class="chip">Total Agents: {total_agents}</span>
  <span class="chip">Msgs Routed: {total_routed}</span>
  <span class="chip {error_class}">Errors: {total_errors}</span>
</div>

<h2>Agents</h2>
<div class="grid">{agent_cards}</div>

<h2>Recent Audit Events</h2>
<table>
<thead><tr><th>Time</th><th>Action</th><th>Severity</th><th>Agent</th><th>Details</th></tr></thead>
<tbody>{audit_rows}</tbody>
</table>
</body>
</html>"""


# =============================================================================
# Health Dashboard / 健康仪表盘
# =============================================================================


class HealthDashboard:
    """Aggregates observability data from AURC runtime components.
    聚合来自 AURC 运行时组件的可观测性数据

    Combines data from RuntimeHarness (agent states/health), AuditLog
    (event trail), and MessageRouter (message statistics) into unified
    health views suitable for dashboards and API responses.

    组合来自 RuntimeHarness（Agent 状态/健康）、AuditLog（事件追踪）
    和 MessageRouter（消息统计）的数据，形成适用于仪表盘和 API 响应的统一健康视图。

    Usage / 用法:
        dashboard = HealthDashboard(harness, audit, router)
        health = dashboard.get_system_health()
        html = dashboard.get_dashboard_html()
    """

    def __init__(
        self,
        harness: RuntimeHarness,
        audit: AuditLog | None = None,
        router: Any | None = None,  # MessageRouter — avoid circular import
    ) -> None:
        self._harness = harness
        self._audit = audit
        self._router = router

    # =========================================================================
    # System Health / 系统健康
    # =========================================================================

    def get_system_health(self) -> dict[str, Any]:
        """Get overall system health summary.
        获取整体系统健康摘要

        Returns a dict with health counts, agent state distribution,
        router statistics, and an overall health status string.
        """
        agents = self._harness.list_agents()
        reports = [inst.to_health_report() for inst in agents]

        # Count agents by health status / 按健康状态统计 Agent 数量
        health_counts: dict[str, int] = {}
        for report in reports:
            key = report.status.value
            health_counts[key] = health_counts.get(key, 0) + 1

        # Count agents by lifecycle state / 按生命周期状态统计
        state_dist: dict[str, int] = {}
        for inst in agents:
            key = inst.state.value
            state_dist[key] = state_dist.get(key, 0) + 1

        # Router statistics / 路由器统计
        router_stats: dict[str, Any] = {}
        if self._router is not None:
            router_stats = self._router.stats.to_dict()

        # Overall health assessment / 整体健康评估
        overall = self._compute_overall_health(health_counts, len(agents))

        return {
            "status": overall,
            "total_agents": len(agents),
            "health_counts": health_counts,
            "state_distribution": state_dist,
            "router_stats": router_stats,
            "audit_entries": self._audit.count if self._audit else 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # =========================================================================
    # Agent Health / Agent 健康
    # =========================================================================

    def get_agent_health(self, agent_id: str) -> dict[str, Any] | None:
        """Get detailed health for a single agent.
        获取单个 Agent 的详细健康信息

        Returns None if the agent is not registered in the harness.
        """
        instance = self._harness.get_agent(agent_id)
        if instance is None:
            return None

        report = instance.to_health_report()

        # Build state transition history / 构建状态转换历史
        history = [
            {"state": state.value, "timestamp": ts.isoformat()}
            for state, ts in instance.state_history
        ]

        result: dict[str, Any] = {
            "agent_id": agent_id,
            "state": instance.state.value,
            "health": report.status.value,
            "metrics": self._metrics_to_dict(instance.metrics),
            "last_error": instance.last_error,
            "state_history": history,
            "descriptor": {
                "name": getattr(instance.descriptor, "name", ""),
                "version": getattr(instance.descriptor, "version", ""),
            },
        }

        # Append agent-specific audit events / 附加 Agent 相关的审计事件
        if self._audit is not None:
            entries = self._audit.query(agent_id=agent_id, limit=20)
            result["recent_events"] = [e.to_dict() for e in entries]

        return result

    # =========================================================================
    # All Agents / 所有 Agent
    # =========================================================================

    def get_all_agents(self) -> list[dict[str, Any]]:
        """Get summary of all registered agents.
        获取所有已注册 Agent 的概要信息

        Returns a list of dicts, each containing agent_id, state,
        health status, and key metrics.
        """
        agents = self._harness.list_agents()
        return [self._agent_summary(inst) for inst in agents]

    # =========================================================================
    # Audit Summary / 审计摘要
    # =========================================================================

    def get_audit_summary(self) -> dict[str, Any]:
        """Get audit log statistics and recent events.
        获取审计日志统计信息和最近事件

        Returns severity counts, action frequency, and the most recent
        50 audit entries.  Returns a minimal dict when no AuditLog is
        configured.
        """
        if self._audit is None:
            return {"available": False, "message": "Audit log not configured"}

        recent = self._audit.get_recent(50)

        # Severity distribution / 严重级别分布
        severity_counts: dict[str, int] = {}
        for entry in recent:
            key = entry.severity.value
            severity_counts[key] = severity_counts.get(key, 0) + 1

        return {
            "available": True,
            "total_entries": self._audit.count,
            "severity_counts": severity_counts,
            "action_stats": self._audit.stats(),
            "recent_events": [e.to_dict() for e in recent],
        }

    # =========================================================================
    # Metrics / 指标
    # =========================================================================

    def get_metrics(self) -> dict[str, Any]:
        """Get system-wide metrics aggregation.
        获取系统级指标汇总

        Aggregates resource metrics across all agents, combines router
        statistics, and computes overall error rates.
        """
        agents = self._harness.list_agents()

        # Aggregate resource metrics across agents / 聚合所有 Agent 的资源指标
        total_tasks_completed = 0
        total_tasks_failed = 0
        total_active_tasks = 0
        total_memory_mb = 0.0
        total_cpu_percent = 0.0

        for inst in agents:
            m = inst.metrics
            total_tasks_completed += m.total_tasks_completed
            total_tasks_failed += m.total_tasks_failed
            total_active_tasks += m.active_tasks
            total_memory_mb += m.memory_mb
            total_cpu_percent += m.cpu_percent

        total_tasks = total_tasks_completed + total_tasks_failed
        error_rate = (total_tasks_failed / total_tasks) if total_tasks > 0 else 0.0

        # Router stats / 路由器统计
        router_stats: dict[str, Any] = {}
        if self._router is not None:
            router_stats = self._router.stats.to_dict()

        router_errors = router_stats.get("errors", 0) if router_stats else 0

        return {
            "agent_count": len(agents),
            "active_tasks": total_active_tasks,
            "tasks_completed": total_tasks_completed,
            "tasks_failed": total_tasks_failed,
            "error_rate": round(error_rate, 4),
            "memory_mb": round(total_memory_mb, 2),
            "cpu_percent": round(total_cpu_percent, 2),
            "router": router_stats,
            "router_errors": router_errors,
            "audit_entries": self._audit.count if self._audit else 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # =========================================================================
    # HTML Dashboard / HTML 仪表盘
    # =========================================================================

    def get_dashboard_html(self) -> str:
        """Generate a self-contained HTML dashboard page.
        生成自包含的 HTML 仪表盘页面

        The page includes inline CSS with dark/light theme support via
        prefers-color-scheme, agent status cards, a system health overview
        bar, and a recent audit events table.  Auto-refreshes every 30
        seconds via a meta tag.
        """
        health = self.get_system_health()
        metrics = self.get_metrics()
        agents = self.get_all_agents()
        audit = self.get_audit_summary()

        # Build agent status cards HTML / 构建 Agent 状态卡片 HTML
        if agents:
            cards_parts: list[str] = []
            for a in agents:
                cards_parts.append(self._render_agent_card(a))
            agent_cards = "\n".join(cards_parts)
        else:
            agent_cards = '<p class="empty">No agents registered</p>'

        # Build audit event rows / 构建审计事件行
        events = audit.get("recent_events", [])
        if events:
            rows_parts: list[str] = []
            for ev in events[-20:]:
                rows_parts.append(self._render_audit_row(ev))
            audit_rows = "\n".join(rows_parts)
        else:
            audit_rows = '<tr><td colspan="5" class="empty">No audit events</td></tr>'

        error_class = "err" if metrics.get("router_errors", 0) > 0 else ""

        return _DASHBOARD_HTML.format(
            timestamp=health.get("timestamp", "")[:19],
            healthy=health.get("health_counts", {}).get("healthy", 0),
            degraded=health.get("health_counts", {}).get("degraded", 0),
            unhealthy=health.get("health_counts", {}).get("unhealthy", 0),
            total_agents=health.get("total_agents", 0),
            total_routed=metrics.get("router", {}).get("total_routed", 0),
            total_errors=metrics.get("router_errors", 0),
            error_class=error_class,
            agent_cards=agent_cards,
            audit_rows=audit_rows,
        )

    # =========================================================================
    # Internal Helpers / 内部辅助方法
    # =========================================================================

    @staticmethod
    def _compute_overall_health(
        health_counts: dict[str, int], total: int
    ) -> str:
        """Derive an overall health string from component counts.
        从组件计数推导整体健康状态字符串
        """
        if total == 0:
            return "unknown"
        unhealthy = health_counts.get("unhealthy", 0)
        degraded = health_counts.get("degraded", 0)
        if unhealthy > 0:
            return "unhealthy"
        if degraded > 0:
            return "degraded"
        return "healthy"

    @staticmethod
    def _metrics_to_dict(m: Any) -> dict[str, Any]:
        """Convert ResourceMetrics to a plain dict.
        将 ResourceMetrics 转换为普通字典
        """
        return {
            "memory_mb": m.memory_mb,
            "cpu_percent": m.cpu_percent,
            "active_tasks": m.active_tasks,
            "tasks_completed": m.total_tasks_completed,
            "tasks_failed": m.total_tasks_failed,
            "uptime_seconds": m.uptime_seconds,
        }

    @classmethod
    def _agent_summary(cls, inst: AgentInstance) -> dict[str, Any]:
        """Build a lightweight summary dict for an AgentInstance.
        为 AgentInstance 构建轻量级摘要字典
        """
        report = inst.to_health_report()
        return {
            "agent_id": inst.agent_id,
            "state": inst.state.value,
            "health": report.status.value,
            "active_tasks": inst.metrics.active_tasks,
            "tasks_completed": inst.metrics.total_tasks_completed,
            "tasks_failed": inst.metrics.total_tasks_failed,
            "uptime_seconds": inst.metrics.uptime_seconds,
        }

    @staticmethod
    def _render_agent_card(agent: dict[str, Any]) -> str:
        """Render a single agent card as HTML.
        渲染单个 Agent 卡片的 HTML
        """
        health = agent.get("health", "unknown")
        badge_map = {
            "healthy": "b-ok",
            "degraded": "b-deg",
            "unhealthy": "b-unh",
        }
        badge_cls = badge_map.get(health, "b-unk")

        return (
            f'<div class="card">'
            f'<h3>{_esc(agent.get("agent_id", ""))}</h3>'
            f'<span class="badge {badge_cls}">{_esc(health)}</span>'
            f'<div class="row"><span class="lbl">State</span>'
            f'<span>{_esc(agent.get("state", ""))}</span></div>'
            f'<div class="row"><span class="lbl">Active</span>'
            f'<span>{agent.get("active_tasks", 0)}</span></div>'
            f'<div class="row"><span class="lbl">Completed</span>'
            f'<span>{agent.get("tasks_completed", 0)}</span></div>'
            f'<div class="row"><span class="lbl">Failed</span>'
            f'<span>{agent.get("tasks_failed", 0)}</span></div>'
            f'<div class="row"><span class="lbl">Uptime</span>'
            f'<span>{agent.get("uptime_seconds", 0):.0f}s</span></div>'
            f"</div>"
        )

    @staticmethod
    def _render_audit_row(event: dict[str, Any]) -> str:
        """Render a single audit event as an HTML table row.
        渲染单条审计事件为 HTML 表格行
        """
        ts = event.get("timestamp", "")[:19]
        sev = event.get("severity", "info")
        return (
            f"<tr>"
            f'<td>{_esc(ts)}</td>'
            f'<td>{_esc(event.get("action", ""))}</td>'
            f'<td class="sev-{_esc(sev)}">{_esc(sev)}</td>'
            f'<td>{_esc(event.get("agent_id", ""))}</td>'
            f'<td>{_esc(str(event.get("details", "")))}</td>'
            f"</tr>"
        )


# =============================================================================
# HTML Escaping Utility / HTML 转义工具
# =============================================================================


def _esc(value: str) -> str:
    """Escape a string for safe HTML embedding.
    转义字符串以安全嵌入 HTML
    """
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# =============================================================================
# Dashboard API (ASGI) / 仪表盘 API（ASGI）
# =============================================================================


class DashboardAPI:
    """ASGI application exposing dashboard endpoints.
    暴露仪表盘端点的 ASGI 应用

    Routes / 路由:
        GET /dashboard         — HTML dashboard page / HTML 仪表盘页面
        GET /api/health        — JSON system health / JSON 系统健康
        GET /api/agents        — JSON agent list / JSON Agent 列表
        GET /api/agents/{id}   — JSON single agent / JSON 单个 Agent
        GET /api/audit         — JSON audit summary / JSON 审计摘要
        GET /api/metrics       — JSON system metrics / JSON 系统指标
        GET /api/stats         — JSON combined statistics / JSON 组合统计

    Usage / 用法:
        api = DashboardAPI(dashboard)
        # Mount in an ASGI server (uvicorn, etc.) / 挂载到 ASGI 服务器
    """

    def __init__(self, dashboard: HealthDashboard) -> None:
        self._dashboard = dashboard

    async def handle_request(
        self, scope: dict[str, Any], receive: Any, send: Any
    ) -> None:
        """ASGI request handler — routes requests to dashboard methods.
        ASGI 请求处理器 — 将请求路由到仪表盘方法

        Only HTTP GET requests are handled.  All other methods receive
        a 405 Method Not Allowed response.
        """
        if scope.get("type") != "http":
            return

        # Consume the request body (required by ASGI spec) / 消费请求体
        while True:
            message = await receive()
            if not message.get("more_body", False):
                break

        method = scope.get("method", "GET")
        path: str = scope.get("path", "")

        if method != "GET":
            await self._send_json(send, 405, {"error": "Method not allowed"})
            return

        # ---- Route matching / 路由匹配 ----

        if path in ("/dashboard", "/dashboard/"):
            html = self._dashboard.get_dashboard_html()
            await self._send_html(send, 200, html)

        elif path in ("/api/health", "/api/health/"):
            data = self._dashboard.get_system_health()
            await self._send_json(send, 200, data)

        elif path in ("/api/agents", "/api/agents/"):
            data = self._dashboard.get_all_agents()
            await self._send_json(send, 200, data)

        elif path.startswith("/api/agents/"):
            agent_id = self._parse_agent_id(path)
            data = self._dashboard.get_agent_health(agent_id)
            if data is not None:
                await self._send_json(send, 200, data)
            else:
                await self._send_json(
                    send, 404, {"error": f"Agent not found: {agent_id}"}
                )

        elif path in ("/api/audit", "/api/audit/"):
            data = self._dashboard.get_audit_summary()
            await self._send_json(send, 200, data)

        elif path in ("/api/metrics", "/api/metrics/"):
            data = self._dashboard.get_metrics()
            await self._send_json(send, 200, data)

        elif path in ("/api/stats", "/api/stats/"):
            # Combined statistics / 组合统计
            data = {
                "health": self._dashboard.get_system_health(),
                "metrics": self._dashboard.get_metrics(),
                "audit": self._dashboard.get_audit_summary(),
            }
            await self._send_json(send, 200, data)

        else:
            await self._send_json(send, 404, {"error": "Not found"})

    # =========================================================================
    # Response Helpers / 响应辅助方法
    # =========================================================================

    @staticmethod
    async def _send_json(
        send: Any, status: int, data: Any
    ) -> None:
        """Send a JSON HTTP response.
        发送 JSON HTTP 响应

        Args:
            send: ASGI send callable / ASGI 发送可调用对象
            status: HTTP status code / HTTP 状态码
            data: Response payload (will be JSON-serialized) / 响应负载
        """
        body = json.dumps(data, default=str).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                [b"content-type", b"application/json; charset=utf-8"],
                [b"cache-control", b"no-cache"],
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })

    @staticmethod
    async def _send_html(
        send: Any, status: int, html: str
    ) -> None:
        """Send an HTML HTTP response.
        发送 HTML HTTP 响应

        Args:
            send: ASGI send callable / ASGI 发送可调用对象
            status: HTTP status code / HTTP 状态码
            html: HTML content string / HTML 内容字符串
        """
        body = html.encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                [b"content-type", b"text/html; charset=utf-8"],
                [b"cache-control", b"no-cache"],
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })

    # =========================================================================
    # Internal / 内部方法
    # =========================================================================

    @staticmethod
    def _parse_agent_id(path: str) -> str:
        """Extract and URL-decode agent ID from the request path.
        从请求路径中提取并 URL 解码 Agent ID

        The agent ID occupies the path segment after /api/agents/.
        E.g. /api/agents/aurc%3Agaia%2Fresearcher%3Av1.0
          -> aurc:gaia/researcher:v1.0
        """
        raw = path[len("/api/agents/"):].rstrip("/")
        return unquote(raw)
