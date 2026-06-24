"""Observability sub-package — health dashboard and monitoring endpoints.
可观测性子包 — 健康仪表盘与监控端点
"""

from .dashboard import DashboardAPI, HealthDashboard

__all__ = ["HealthDashboard", "DashboardAPI"]
