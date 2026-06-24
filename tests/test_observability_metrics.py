"""Tests for the Prometheus metrics exporter and /metrics endpoint.
Prometheus 指标导出器与 /metrics 端点测试
"""

import pytest

from gaiaagent.core.identity import AgentDescriptor
from gaiaagent.harness.lifecycle import RuntimeHarness
from gaiaagent.observability.dashboard import DashboardAPI, HealthDashboard
from gaiaagent.observability.metrics import (
    PROMETHEUS_CONTENT_TYPE,
    PrometheusMetricsExporter,
)
from gaiaagent.security.audit import AuditAction, AuditLog


class TestPrometheusExporter:
    def test_renders_valid_prometheus_text(self):
        """Output should contain TYPE/HELP lines and well-formed samples."""
        harness = RuntimeHarness()
        dashboard = HealthDashboard(harness)
        text = PrometheusMetricsExporter(dashboard).render()

        assert "# TYPE aurc_up gauge" in text
        assert "# TYPE aurc_agents_total gauge" in text
        assert "# TYPE aurc_messages_total counter" in text
        assert "aurc_up 1" in text
        # Each sample line ends with a numeric value.
        assert 'aurc_messages_total{route="direct"} 0' in text
        assert text.endswith("\n")

    def test_content_type(self):
        harness = RuntimeHarness()
        exporter = PrometheusMetricsExporter(HealthDashboard(harness))
        assert exporter.content_type == PROMETHEUS_CONTENT_TYPE
        assert "text/plain" in exporter.content_type

    def test_empty_harness_is_valid(self):
        """An empty runtime should still render scrape-ready text."""
        text = PrometheusMetricsExporter(HealthDashboard(RuntimeHarness())).render()
        # No agent/health labels emitted when empty, but core gauges are present.
        assert "aurc_agents_total 0" in text
        assert "aurc_router_errors_total 0" in text

    @pytest.mark.asyncio
    async def test_includes_agent_state_and_health_labels(self):
        harness = RuntimeHarness()
        await harness.register(
            AgentDescriptor(
                aurc_id="aurc:test/agent-a:v1.0",
                display_name="Agent A",
                description="Test agent A",
            )
        )
        await harness.start("aurc:test/agent-a:v1.0")

        text = PrometheusMetricsExporter(HealthDashboard(harness)).render()
        assert '# TYPE aurc_agent_state gauge' in text
        assert 'aurc_agent_state{state="running"}' in text

    def test_includes_audit_action_counters(self):
        harness = RuntimeHarness()
        audit = AuditLog()
        audit.log(AuditAction.AGENT_REGISTERED, agent_id="aurc:test/a:v1.0")
        audit.log(AuditAction.MESSAGE_SENT, agent_id="aurc:test/a:v1.0")
        audit.log(AuditAction.MESSAGE_SENT, agent_id="aurc:test/a:v1.0")

        text = PrometheusMetricsExporter(HealthDashboard(harness, audit=audit)).render()
        assert '# TYPE aurc_audit_events_total counter' in text
        assert 'aurc_audit_events_total{action="message_sent"} 2' in text
        assert 'aurc_audit_events_total{action="agent_registered"} 1' in text

    def test_no_audit_omits_action_counters(self):
        """Without an audit log, the audit_events_total family is omitted."""
        text = PrometheusMetricsExporter(HealthDashboard(RuntimeHarness())).render()
        assert "aurc_audit_events_total" not in text

    def test_namespace_is_sanitized(self):
        """A namespace with invalid chars must be sanitized to a valid metric prefix."""
        harness = RuntimeHarness()
        exporter = PrometheusMetricsExporter(HealthDashboard(harness), namespace="my-app 1")
        text = exporter.render()
        assert "_up 1" in text  # sanitized prefix still yields valid samples
        # No whitespace or dashes leak into metric names.
        assert "my-app_up" not in text


class TestMetricsEndpoint:
    """Exercise the /metrics route on DashboardAPI via a minimal ASGI call."""

    @staticmethod
    async def _call(api: DashboardAPI, path: str) -> tuple[int, bytes, str]:
        status_box: dict = {}
        body_box: dict = {}
        ct_box: dict = {}

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                status_box["status"] = message["status"]
                for k, v in message.get("headers", []):
                    if k == b"content-type":
                        ct_box["ct"] = v.decode("utf-8")
            elif message["type"] == "http.response.body":
                body_box["body"] = message.get("body", b"")

        await api.handle_request(
            {"type": "http", "method": "GET", "path": path}, receive, send
        )
        return status_box["status"], body_box["body"], ct_box["ct"]

    @pytest.mark.asyncio
    async def test_metrics_endpoint(self):
        harness = RuntimeHarness()
        audit = AuditLog()
        audit.log(AuditAction.AGENT_REGISTERED, agent_id="aurc:test/a:v1.0")

        api = DashboardAPI(HealthDashboard(harness, audit=audit))
        status, body, ct = await self._call(api, "/metrics")

        assert status == 200
        assert ct == PROMETHEUS_CONTENT_TYPE
        text = body.decode("utf-8")
        assert "# TYPE aurc_up gauge" in text
        assert 'aurc_audit_events_total{action="agent_registered"} 1' in text

    @pytest.mark.asyncio
    async def test_metrics_endpoint_trailing_slash(self):
        api = DashboardAPI(HealthDashboard(RuntimeHarness()))
        status, body, _ = await self._call(api, "/metrics/")
        assert status == 200
        assert b"aurc_up" in body
