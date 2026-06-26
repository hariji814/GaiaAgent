"""Tests for Health Dashboard — observability and monitoring.
健康仪表板测试 — 可观测性和监控
"""

import pytest

from gaiaagent.core.identity import AgentDescriptor
from gaiaagent.harness.lifecycle import RuntimeHarness
from gaiaagent.observability.dashboard import DashboardAPI, HealthDashboard
from gaiaagent.security.audit import AuditAction, AuditLog


class TestHealthDashboard:
    """Tests for HealthDashboard data aggregation."""

    def test_empty_harness_health(self):
        """System health with no agents."""
        harness = RuntimeHarness()
        dashboard = HealthDashboard(harness)
        health = dashboard.get_system_health()
        assert health["total_agents"] == 0
        assert "status" in health
        assert "timestamp" in health

    @pytest.mark.asyncio
    async def test_system_health_with_agents(self):
        """System health should reflect registered agents."""
        harness = RuntimeHarness()
        desc1 = AgentDescriptor(
            aurc_id="aurc:test/agent-a:v1.0",
            display_name="Agent A",
            description="Test agent A",
        )
        desc2 = AgentDescriptor(
            aurc_id="aurc:test/agent-b:v1.0",
            display_name="Agent B",
            description="Test agent B",
        )
        await harness.register(desc1)
        await harness.register(desc2)
        await harness.start("aurc:test/agent-a:v1.0")

        dashboard = HealthDashboard(harness)
        health = dashboard.get_system_health()
        assert health["total_agents"] == 2
        assert health["status"] in ("healthy", "degraded", "unhealthy", "unknown")

    @pytest.mark.asyncio
    async def test_agent_health(self):
        """Agent health should return detailed info."""
        harness = RuntimeHarness()
        desc = AgentDescriptor(
            aurc_id="aurc:test/agent-a:v1.0",
            display_name="Agent A",
            description="Test agent A",
        )
        await harness.register(desc)
        await harness.start("aurc:test/agent-a:v1.0")

        dashboard = HealthDashboard(harness)
        health = dashboard.get_agent_health("aurc:test/agent-a:v1.0")
        assert health is not None
        assert health["agent_id"] == "aurc:test/agent-a:v1.0"
        assert health["state"] == "running"
        assert "metrics" in health
        assert "state_history" in health

    def test_agent_health_not_found(self):
        """Non-existent agent should return None."""
        harness = RuntimeHarness()
        dashboard = HealthDashboard(harness)
        health = dashboard.get_agent_health("aurc:test/nonexistent:v1.0")
        assert health is None

    @pytest.mark.asyncio
    async def test_all_agents(self):
        """All agents list should return summaries."""
        harness = RuntimeHarness()
        desc1 = AgentDescriptor(
            aurc_id="aurc:test/agent-a:v1.0",
            display_name="Agent A",
            description="Test agent A",
        )
        desc2 = AgentDescriptor(
            aurc_id="aurc:test/agent-b:v1.0",
            display_name="Agent B",
            description="Test agent B",
        )
        await harness.register(desc1)
        await harness.register(desc2)

        dashboard = HealthDashboard(harness)
        agents = dashboard.get_all_agents()
        assert len(agents) == 2
        agent_ids = [a["agent_id"] for a in agents]
        assert "aurc:test/agent-a:v1.0" in agent_ids
        assert "aurc:test/agent-b:v1.0" in agent_ids

    def test_audit_summary_no_audit(self):
        """Audit summary without audit log should indicate unavailable."""
        harness = RuntimeHarness()
        dashboard = HealthDashboard(harness)
        summary = dashboard.get_audit_summary()
        assert summary["available"] is False

    def test_audit_summary_with_audit(self):
        """Audit summary should include stats and recent events."""
        harness = RuntimeHarness()
        audit = AuditLog(max_entries=100)
        audit.log(AuditAction.AGENT_REGISTERED, agent_id="aurc:test/a:v1.0")
        audit.log(AuditAction.MESSAGE_SENT, agent_id="aurc:test/a:v1.0")

        dashboard = HealthDashboard(harness, audit=audit)
        summary = dashboard.get_audit_summary()
        assert summary["available"] is True
        assert summary["total_entries"] == 2
        assert "agent_registered" in summary["action_stats"]
        assert len(summary["recent_events"]) == 2

    @pytest.mark.asyncio
    async def test_metrics(self):
        """Metrics should aggregate system-wide data."""
        harness = RuntimeHarness()
        desc = AgentDescriptor(
            aurc_id="aurc:test/agent-a:v1.0",
            display_name="Agent A",
            description="Test agent A",
        )
        await harness.register(desc)

        audit = AuditLog()
        audit.log(AuditAction.AGENT_STARTED, agent_id="aurc:test/agent-a:v1.0")

        dashboard = HealthDashboard(harness, audit=audit)
        metrics = dashboard.get_metrics()
        assert metrics["agent_count"] == 1
        assert "tasks_completed" in metrics
        assert metrics["audit_entries"] == 1

    @pytest.mark.asyncio
    async def test_dashboard_html_generation(self):
        """HTML dashboard should be a valid self-contained page."""
        harness = RuntimeHarness()
        desc = AgentDescriptor(
            aurc_id="aurc:test/agent-a:v1.0",
            display_name="Agent A",
            description="Test agent A",
        )
        await harness.register(desc)

        audit = AuditLog()
        audit.log(AuditAction.AGENT_REGISTERED, agent_id="aurc:test/agent-a:v1.0")

        dashboard = HealthDashboard(harness, audit=audit)
        html = dashboard.get_dashboard_html()

        assert "<!DOCTYPE html>" in html
        assert "Dashboard" in html or "dashboard" in html
        assert "<style>" in html
        assert "prefers-color-scheme" in html


class TestDashboardAPI:
    """Tests for DashboardAPI ASGI handler."""

    def test_api_creation(self):
        """DashboardAPI should initialize with a dashboard."""
        harness = RuntimeHarness()
        dashboard = HealthDashboard(harness)
        api = DashboardAPI(dashboard)
        assert api is not None
