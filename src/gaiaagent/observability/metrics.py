"""AURC Prometheus Metrics Exporter — Prometheus text exposition format.
AURC Prometheus 指标导出器 — Prometheus 文本展示格式

Exposes the same observability data surfaced by HealthDashboard, but in the
Prometheus text exposition format so an AURC runtime can be scraped directly
by Prometheus (or any compatible scraper) without a sidecar.

将 HealthDashboard 暴露的同一份可观测性数据，以 Prometheus 文本展示格式
输出，使 AURC 运行时可被 Prometheus 直接抓取，无需 sidecar。

Metric families / 指标族:
    aurc_up                                   gauge     Runtime liveness
    aurc_agents_total                         gauge     Registered agents
    aurc_active_tasks                         gauge     Active in-flight tasks
    aurc_tasks_completed_total                counter   Tasks completed (cumulative)
    aurc_tasks_failed_total                   counter   Tasks failed (cumulative)
    aurc_error_rate                           gauge     Task error rate [0,1]
    aurc_memory_mb                            gauge     Aggregate memory (MB)
    aurc_cpu_percent                          gauge     Aggregate CPU (%)
    aurc_audit_entries_total                  gauge     Audit log entry count
    aurc_messages_total{route=...}            counter   Routed messages by route kind
    aurc_router_errors_total                  counter   Router errors
    aurc_agent_state{state=...}               gauge     Agents per lifecycle state
    aurc_health{status=...}                   gauge     Agents per health status
    aurc_audit_events_total{action=...}       counter   Audit events by action
"""

from __future__ import annotations

import re
from typing import Any

from .dashboard import HealthDashboard

# Prometheus exposition content type / Prometheus 展示内容类型
PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

# Characters allowed in Prometheus label values must be escaped.
# Prometheus 标签值中需要转义的字符。
_LABEL_ESCAPE = str.maketrans({"\\": "\\\\", '"': '\\"', "\n": "\\n"})


def _escape_label_value(value: Any) -> str:
    """Escape a value for safe use inside a Prometheus label.
    转义值以安全用于 Prometheus 标签
    """
    return str(value).translate(_LABEL_ESCAPE)


def _sanitize_metric_name(name: str) -> str:
    """Ensure a string is a valid Prometheus metric name ([a-zA-Z_:][a-zA-Z0-9_:]*).
    确保字符串是合法的 Prometheus 指标名
    """
    cleaned = re.sub(r"[^a-zA-Z0-9_:]", "_", str(name))
    if cleaned and cleaned[0].isdigit():
        cleaned = "_" + cleaned
    return cleaned


class PrometheusMetricsExporter:
    """Render AURC runtime metrics in Prometheus text exposition format.
    以 Prometheus 文本展示格式渲染 AURC 运行时指标

    Wraps a HealthDashboard (which already aggregates Harness + Router + Audit
    data) and emits scrape-ready text. No external dependencies — pure string
    formatting.

    包装 HealthDashboard（已聚合 Harness + Router + Audit 数据），输出可直接
    抓取的文本。无外部依赖，纯字符串格式化。

    Usage / 用法:
        exporter = PrometheusMetricsExporter(dashboard)
        text = exporter.render()                 # -> str, Prometheus format
        ct = exporter.content_type               # -> "text/plain; version=0.0.4..."
    """

    def __init__(self, dashboard: HealthDashboard, *, namespace: str = "aurc") -> None:
        self._dashboard = dashboard
        self._ns = _sanitize_metric_name(namespace)

    @property
    def content_type(self) -> str:
        """HTTP Content-Type for Prometheus responses.
        Prometheus 响应的 HTTP Content-Type"""
        return PROMETHEUS_CONTENT_TYPE

    def render(self) -> str:
        """Render all metric families as Prometheus text.
        将所有指标族渲染为 Prometheus 文本

        Returns a string terminated by a newline, suitable as an HTTP /metrics
        response body.
        返回以换行结尾的字符串，适合作为 HTTP /metrics 响应体。
        """
        health = self._dashboard.get_system_health()
        metrics = self._dashboard.get_metrics()
        router: dict[str, Any] = metrics.get("router") or {}
        audit_summary = self._dashboard.get_audit_summary()

        ns = self._ns
        out: list[str] = []

        # ---- Liveness / 存活 ----
        out.append(f"# HELP {ns}_up AURC runtime liveness (1 = up)")
        out.append(f"# TYPE {ns}_up gauge")
        out.append(f"{ns}_up 1")

        # ---- Agent / task gauges & counters ----
        out.append(f"# HELP {ns}_agents_total Number of registered agents")
        out.append(f"# TYPE {ns}_agents_total gauge")
        out.append(f"{ns}_agents_total {metrics.get('agent_count', 0)}")

        out.append(f"# HELP {ns}_active_tasks In-flight active tasks")
        out.append(f"# TYPE {ns}_active_tasks gauge")
        out.append(f"{ns}_active_tasks {metrics.get('active_tasks', 0)}")

        out.append(f"# HELP {ns}_tasks_completed_total Cumulative completed tasks")
        out.append(f"# TYPE {ns}_tasks_completed_total counter")
        out.append(f"{ns}_tasks_completed_total {metrics.get('tasks_completed', 0)}")

        out.append(f"# HELP {ns}_tasks_failed_total Cumulative failed tasks")
        out.append(f"# TYPE {ns}_tasks_failed_total counter")
        out.append(f"{ns}_tasks_failed_total {metrics.get('tasks_failed', 0)}")

        out.append(f"# HELP {ns}_error_rate Task error rate in [0,1]")
        out.append(f"# TYPE {ns}_error_rate gauge")
        out.append(f"{ns}_error_rate {metrics.get('error_rate', 0.0)}")

        out.append(f"# HELP {ns}_memory_mb Aggregate memory usage in MB")
        out.append(f"# TYPE {ns}_memory_mb gauge")
        out.append(f"{ns}_memory_mb {metrics.get('memory_mb', 0.0)}")

        out.append(f"# HELP {ns}_cpu_percent Aggregate CPU usage in percent")
        out.append(f"# TYPE {ns}_cpu_percent gauge")
        out.append(f"{ns}_cpu_percent {metrics.get('cpu_percent', 0.0)}")

        out.append(f"# HELP {ns}_audit_entries_total Audit log entry count")
        out.append(f"# TYPE {ns}_audit_entries_total gauge")
        out.append(f"{ns}_audit_entries_total {metrics.get('audit_entries', 0)}")

        # ---- Router: per-route message counters ----
        out.append(
            f"# HELP {ns}_messages_total Messages routed, by route kind"
        )
        out.append(f"# TYPE {ns}_messages_total counter")
        for route in ("direct", "bridged", "broadcast", "dead_lettered", "dropped"):
            val = router.get(route, 0)
            out.append(
                f'{ns}_messages_total{{route="{_escape_label_value(route)}"}} {val}'
            )

        out.append(f"# HELP {ns}_router_errors_total Router errors")
        out.append(f"# TYPE {ns}_router_errors_total counter")
        out.append(f"{ns}_router_errors_total {router.get('errors', 0)}")

        # ---- Agents per lifecycle state ----
        out.append(f"# HELP {ns}_agent_state Agents per lifecycle state")
        out.append(f"# TYPE {ns}_agent_state gauge")
        state_dist: dict[str, int] = health.get("state_distribution") or {}
        for state, count in state_dist.items():
            out.append(
                f'{ns}_agent_state{{state="{_escape_label_value(state)}"}} {count}'
            )

        # ---- Agents per health status ----
        out.append(f"# HELP {ns}_health Agents per health status")
        out.append(f"# TYPE {ns}_health gauge")
        health_counts: dict[str, int] = health.get("health_counts") or {}
        for status, count in health_counts.items():
            out.append(
                f'{ns}_health{{status="{_escape_label_value(status)}"}} {count}'
            )

        # ---- Audit events by action ----
        if audit_summary.get("available"):
            out.append(f"# HELP {ns}_audit_events_total Audit events by action")
            out.append(f"# TYPE {ns}_audit_events_total counter")
            action_stats: dict[str, int] = audit_summary.get("action_stats") or {}
            for action, count in action_stats.items():
                out.append(
                    f'{ns}_audit_events_total{{action="{_escape_label_value(action)}"}} {count}'
                )

        return "\n".join(out) + "\n"


__all__ = ["PrometheusMetricsExporter", "PROMETHEUS_CONTENT_TYPE"]
