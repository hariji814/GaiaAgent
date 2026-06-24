"""AURC Agent Registry — local and file-based agent discovery.
AURC Agent 注册中心 — 本地和文件级 Agent 发现

The Registry is where agents register themselves and where the Harness
looks up agents by capability, protocol, or tag.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.capability import CapabilityMatch, CapabilityMatcher
from ..core.identity import AgentDescriptor
from ..core.types import HealthStatus

logger = logging.getLogger(__name__)


class RegistryEntry:
    """A registry entry wraps an AgentDescriptor with runtime metadata.
    注册条目包装 Agent 描述文档并附加运行时元数据
    """

    def __init__(self, descriptor: AgentDescriptor):
        self.descriptor = descriptor
        self.status: HealthStatus = HealthStatus.UNKNOWN
        self.registered_at: datetime = datetime.now(timezone.utc)
        self.last_heartbeat: datetime = self.registered_at
        self.metadata: dict[str, Any] = {}

    @property
    def agent_id(self) -> str:
        return self.descriptor.aurc_id

    def heartbeat(self) -> None:
        """Update the last heartbeat timestamp."""
        self.last_heartbeat = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a registry-compatible dict. 序列化为注册中心兼容的字典"""
        return {
            **self.descriptor.to_registry_entry(),
            "status": self.status.value,
            "registered_at": self.registered_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "metadata": self.metadata,
        }


class LocalRegistry:
    """In-memory agent registry with capability-based search.
    内存中的 Agent 注册中心，支持基于能力的搜索

    This is the simplest registry implementation, suitable for:
    - Single-process deployments / 单进程部署
    - Development and testing / 开发和测试
    - Small-scale use cases / 小规模用例

    Usage / 用法:
        registry = LocalRegistry()
        registry.register(descriptor)

        # Find agents by capability / 按能力查找
        matches = registry.find_by_skills(["web-search", "summarize"])
        best = matches[0] if matches else None

        # Find by tag / 按标签查找
        agents = registry.find_by_tag("research")
    """

    def __init__(self) -> None:
        self._entries: dict[str, RegistryEntry] = {}
        self._matcher = CapabilityMatcher()

    # =========================================================================
    # Registration / 注册
    # =========================================================================

    def register(self, descriptor: AgentDescriptor) -> RegistryEntry:
        """Register an agent. 注册 Agent

        Args:
            descriptor: The agent's descriptor / Agent 描述文档

        Returns:
            The created RegistryEntry

        Raises:
            ValueError: If already registered
        """
        if descriptor.aurc_id in self._entries:
            raise ValueError(f"Agent '{descriptor.aurc_id}' already registered")

        entry = RegistryEntry(descriptor)
        self._entries[descriptor.aurc_id] = entry
        logger.info("Registry: registered '%s'", descriptor.aurc_id)
        return entry

    def unregister(self, agent_id: str) -> None:
        """Unregister an agent. 注销 Agent"""
        if agent_id not in self._entries:
            raise KeyError(f"Agent '{agent_id}' not found in registry")
        del self._entries[agent_id]
        logger.info("Registry: unregistered '%s'", agent_id)

    def update_descriptor(self, descriptor: AgentDescriptor) -> None:
        """Update an existing agent's descriptor. 更新已有 Agent 的描述文档"""
        if descriptor.aurc_id not in self._entries:
            raise KeyError(f"Agent '{descriptor.aurc_id}' not found")
        self._entries[descriptor.aurc_id].descriptor = descriptor

    # =========================================================================
    # Lookup / 查询
    # =========================================================================

    def get(self, agent_id: str) -> RegistryEntry | None:
        """Get a registry entry by agent ID."""
        return self._entries.get(agent_id)

    def list_all(self) -> list[RegistryEntry]:
        """List all registered agents. 列出所有已注册的 Agent"""
        return list(self._entries.values())

    def list_descriptors(self) -> list[AgentDescriptor]:
        """List all agent descriptors."""
        return [entry.descriptor for entry in self._entries.values()]

    @property
    def count(self) -> int:
        return len(self._entries)

    # =========================================================================
    # Search / 搜索
    # =========================================================================

    def find_by_skills(
        self,
        required_skills: list[str],
        required_protocol: str | None = None,
        tags: list[str] | None = None,
    ) -> list[CapabilityMatch]:
        """Find agents matching required skills.
        查找匹配所需技能的 Agent

        Returns:
            Sorted list of matches (best first) / 按分数排序的匹配列表
        """
        return self._matcher.find_agents(
            required_skills=required_skills,
            agents=self.list_descriptors(),
            required_protocol=required_protocol,
            tags=tags,
        )

    def find_by_tag(self, tag: str) -> list[RegistryEntry]:
        """Find agents with a specific tag. 查找包含特定标签的 Agent"""
        return [e for e in self._entries.values() if tag in e.descriptor.tags]

    def find_by_protocol(self, protocol: str) -> list[RegistryEntry]:
        """Find agents supporting a specific protocol. 查找支持特定协议的 Agent"""
        return [
            e for e in self._entries.values()
            if e.descriptor.protocols.supports(protocol)
        ]

    def find_best(
        self,
        required_skills: list[str],
        required_protocol: str | None = None,
    ) -> CapabilityMatch | None:
        """Find the single best matching agent. 查找最佳匹配 Agent"""
        return self._matcher.find_best_agent(
            required_skills=required_skills,
            agents=self.list_descriptors(),
            required_protocol=required_protocol,
        )

    # =========================================================================
    # Heartbeat / 心跳
    # =========================================================================

    def heartbeat(self, agent_id: str) -> None:
        """Record a heartbeat for an agent. 记录 Agent 心跳"""
        entry = self._entries.get(agent_id)
        if entry:
            entry.heartbeat()

    # =========================================================================
    # Import/Export / 导入导出
    # =========================================================================

    def export_to_dict(self) -> list[dict[str, Any]]:
        """Export all entries as dicts. 导出所有条目为字典"""
        return [entry.to_dict() for entry in self._entries.values()]

    def export_to_json(self, path: str | Path) -> None:
        """Export registry to a JSON file. 导出注册中心到 JSON 文件"""
        data = self.export_to_dict()
        Path(path).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        logger.info("Registry exported %d entries to %s", len(data), path)

    def import_from_json(self, path: str | Path) -> int:
        """Import agents from a JSON file.
        从 JSON 文件导入 Agent

        Returns:
            Number of agents imported / 导入的 Agent 数量
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        count = 0
        for item in data:
            try:
                descriptor = AgentDescriptor(**item)
                self.register(descriptor)
                count += 1
            except Exception:
                logger.exception("Failed to import agent from: %s", item.get("aurc_id", "unknown"))
        logger.info("Registry imported %d agents from %s", count, path)
        return count
