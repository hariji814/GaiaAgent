"""AURC Audit Log — immutable audit trail for cross-protocol interactions.
AURC 审计日志 — 跨协议交互的不可变审计追踪

Provides:
- Append-only audit entries / 仅追加的审计条目
- Cross-protocol interaction tracking / 跨协议交互追踪
- Searchable audit trail / 可搜索的审计追踪
- Export for compliance / 合规导出
"""

from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AuditAction(str, Enum):
    """Types of auditable actions. 可审计动作类型"""
    AGENT_REGISTERED = "agent_registered"
    AGENT_UNREGISTERED = "agent_unregistered"
    AGENT_STARTED = "agent_started"
    AGENT_STOPPED = "agent_stopped"
    AGENT_PAUSED = "agent_paused"
    AGENT_RESUMED = "agent_resumed"
    AGENT_ERROR = "agent_error"
    AGENT_RECOVERED = "agent_recovered"
    MESSAGE_SENT = "message_sent"
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_ROUTED = "message_routed"
    MESSAGE_BRIDGED = "message_bridged"
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    AUTHZ_GRANTED = "authz_granted"
    AUTHZ_DENIED = "authz_denied"
    DELEGATION_CREATED = "delegation_created"
    DELEGATION_VALIDATED = "delegation_validated"
    DELEGATION_REJECTED = "delegation_rejected"
    SESSION_CREATED = "session_created"
    SESSION_CLOSED = "session_closed"
    CONTEXT_MODIFIED = "context_modified"
    POLICY_CHANGED = "policy_changed"


class AuditSeverity(str, Enum):
    """Severity levels for audit entries. 审计条目严重级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEntry:
    """A single audit log entry. 单条审计日志条目"""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    action: AuditAction = AuditAction.MESSAGE_SENT
    severity: AuditSeverity = AuditSeverity.INFO
    agent_id: str = ""
    target_id: str = ""
    message_id: str = ""
    correlation_id: str = ""
    protocol: str = "aurc"
    details: dict[str, Any] = field(default_factory=dict)
    # Integrity / 完整性
    _hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "action": self.action.value,
            "severity": self.severity.value,
            "agent_id": self.agent_id,
            "target_id": self.target_id,
            "message_id": self.message_id,
            "correlation_id": self.correlation_id,
            "protocol": self.protocol,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditEntry:
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            action=AuditAction(data["action"]),
            severity=AuditSeverity(data.get("severity", "info")),
            agent_id=data.get("agent_id", ""),
            target_id=data.get("target_id", ""),
            message_id=data.get("message_id", ""),
            correlation_id=data.get("correlation_id", ""),
            protocol=data.get("protocol", "aurc"),
            details=data.get("details", {}),
        )


class AuditLog:
    """Immutable, append-only audit log.
    不可变、仅追加的审计日志

    Features / 特性:
    - In-memory ring buffer with configurable capacity / 可配置容量的内存环形缓冲区
    - File-based persistence / 基于文件的持久化
    - Query by action, agent, time range / 按动作、Agent、时间范围查询
    - JSON export for compliance / JSON 导出用于合规

    Usage / 用法:
        audit = AuditLog(max_entries=10000)

        audit.log(
            action=AuditAction.MESSAGE_BRIDGED,
            agent_id="aurc:gaia/researcher:v1.0",
            protocol="mcp/2025-06-18",
            details={"bridge": "mcp→aurc", "skill": "web-search"},
        )

        # Query / 查询
        entries = audit.query(agent_id="aurc:gaia/researcher:v1.0")
        bridge_events = audit.query(action=AuditAction.MESSAGE_BRIDGED)

        # Export / 导出
        audit.export_to_file("audit.json")
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._entries: deque[AuditEntry] = deque(maxlen=max_entries)
        self._max_entries = max_entries

    def log(
        self,
        action: AuditAction,
        agent_id: str = "",
        target_id: str = "",
        message_id: str = "",
        correlation_id: str = "",
        protocol: str = "aurc",
        severity: AuditSeverity = AuditSeverity.INFO,
        details: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Log an audit entry. 记录审计条目"""
        entry = AuditEntry(
            action=action,
            severity=severity,
            agent_id=agent_id,
            target_id=target_id,
            message_id=message_id,
            correlation_id=correlation_id,
            protocol=protocol,
            details=details or {},
        )
        self._entries.append(entry)
        return entry

    # =========================================================================
    # Queries / 查询
    # =========================================================================

    def query(
        self,
        action: AuditAction | None = None,
        agent_id: str | None = None,
        target_id: str | None = None,
        severity: AuditSeverity | None = None,
        protocol: str | None = None,
        correlation_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Query audit entries with filters.
        使用过滤器查询审计条目

        All filters are AND-combined. Results are in chronological order.
        """
        results = []
        for entry in self._entries:
            if action and entry.action != action:
                continue
            if agent_id and entry.agent_id != agent_id:
                continue
            if target_id and entry.target_id != target_id:
                continue
            if severity and entry.severity != severity:
                continue
            if protocol and entry.protocol != protocol:
                continue
            if correlation_id and entry.correlation_id != correlation_id:
                continue
            if since and entry.timestamp < since:
                continue
            if until and entry.timestamp > until:
                continue

            results.append(entry)
            if len(results) >= limit:
                break

        return results

    def get_recent(self, count: int = 50) -> list[AuditEntry]:
        """Get the most recent entries. 获取最近的条目"""
        entries = list(self._entries)
        return entries[-count:] if len(entries) > count else entries

    def get_by_correlation(self, correlation_id: str) -> list[AuditEntry]:
        """Get all entries for a correlation ID. 获取关联 ID 的所有条目"""
        return [e for e in self._entries if e.correlation_id == correlation_id]

    # =========================================================================
    # Statistics / 统计
    # =========================================================================

    def stats(self) -> dict[str, int]:
        """Get action frequency statistics. 获取动作频率统计"""
        counts: dict[str, int] = {}
        for entry in self._entries:
            key = entry.action.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    @property
    def count(self) -> int:
        return len(self._entries)

    # =========================================================================
    # Export / 导出
    # =========================================================================

    def export_to_file(self, path: str | Path) -> int:
        """Export all entries to a JSON file.
        将所有条目导出到 JSON 文件

        Returns:
            Number of entries exported / 导出的条目数
        """
        data = [entry.to_dict() for entry in self._entries]
        Path(path).write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("Audit log exported: %d entries to %s", len(data), path)
        return len(data)

    def import_from_file(self, path: str | Path) -> int:
        """Import entries from a JSON file. 从 JSON 文件导入条目"""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        count = 0
        for item in data:
            try:
                entry = AuditEntry.from_dict(item)
                self._entries.append(entry)
                count += 1
            except Exception:
                logger.exception("Failed to import audit entry")
        return count

    def clear(self) -> int:
        """Clear all entries. Returns count cleared."""
        count = len(self._entries)
        self._entries.clear()
        return count
