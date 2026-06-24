"""AURC Capability System — matching, scoring, and validation.
AURC 能力系统 — 匹配、评分和验证

Provides the logic for:
1. Matching agent capabilities to task requirements
2. Scoring how well an agent fits a requested task
3. Validating that required capabilities are available
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .identity import AgentDescriptor, SkillDeclaration


@dataclass
class CapabilityMatch:
    """Result of matching a task requirement against available agents.
    任务需求与可用 Agent 的匹配结果
    """

    agent: AgentDescriptor
    matched_skills: list[SkillDeclaration] = field(default_factory=list)
    score: float = 0.0
    missing_skills: list[str] = field(default_factory=list)
    protocol_compatible: bool = True

    @property
    def is_full_match(self) -> bool:
        """Whether all required skills are matched."""
        return len(self.missing_skills) == 0

    @property
    def match_ratio(self) -> float:
        """Ratio of matched skills to total required skills."""
        total = len(self.matched_skills) + len(self.missing_skills)
        if total == 0:
            return 1.0
        return len(self.matched_skills) / total


class CapabilityMatcher:
    """Matches task requirements against agent capabilities.
    将任务需求与 Agent 能力进行匹配

    Usage / 用法:
        matcher = CapabilityMatcher()
        matches = matcher.find_agents(
            required_skills=["web-search", "summarize"],
            agents=registry.list_agents(),
            required_protocol="aurc/0.1"
        )
        best = matches[0]  # Highest scoring match
    """

    def find_agents(
        self,
        required_skills: list[str],
        agents: list[AgentDescriptor],
        required_protocol: str | None = None,
        tags: list[str] | None = None,
        min_score: float = 0.0,
    ) -> list[CapabilityMatch]:
        """Find agents that match the required capabilities.
        查找匹配所需能力的 Agent

        Args:
            required_skills: List of skill IDs needed / 需要的技能 ID 列表
            agents: Available agents to search / 可搜索的 Agent 列表
            required_protocol: Protocol that must be supported / 必须支持的协议
            tags: Tags that must be present / 必须存在的标签
            min_score: Minimum match score (0.0-1.0) / 最低匹配分数

        Returns:
            List of matches sorted by score (highest first) / 按分数排序的匹配列表
        """
        matches = []

        for agent in agents:
            match = self._score_agent(agent, required_skills, required_protocol, tags)
            if match.score >= min_score:
                matches.append(match)

        matches.sort(key=lambda m: m.score, reverse=True)
        return matches

    def _score_agent(
        self,
        agent: AgentDescriptor,
        required_skills: list[str],
        required_protocol: str | None,
        tags: list[str] | None,
    ) -> CapabilityMatch:
        """Score a single agent against requirements.
        对单个 Agent 进行评分
        """
        matched_skills: list[SkillDeclaration] = []
        missing_skills: list[str] = []

        # Skill matching / 技能匹配
        for skill_id in required_skills:
            skill = agent.capabilities.get_skill(skill_id)
            if skill:
                matched_skills.append(skill)
            else:
                missing_skills.append(skill_id)

        # Protocol compatibility / 协议兼容性
        protocol_compatible = True
        if required_protocol:
            protocol_compatible = agent.protocols.supports(required_protocol)

        # Tag matching / 标签匹配
        tag_match = True
        if tags:
            agent_tags = set(agent.tags)
            tag_match = all(t in agent_tags for t in tags)

        # Calculate composite score / 计算综合分数
        score = self._calculate_score(
            matched_count=len(matched_skills),
            total_required=len(required_skills),
            protocol_compatible=protocol_compatible,
            tag_match=tag_match,
            agent=agent,
        )

        return CapabilityMatch(
            agent=agent,
            matched_skills=matched_skills,
            score=score,
            missing_skills=missing_skills,
            protocol_compatible=protocol_compatible,
        )

    def _calculate_score(
        self,
        matched_count: int,
        total_required: int,
        protocol_compatible: bool,
        tag_match: bool,
        agent: AgentDescriptor,
    ) -> float:
        """Calculate a composite match score (0.0 to 1.0).
        计算综合匹配分数 (0.0 到 1.0)

        Score weights / 评分权重:
        - Skill match: 70% (primary factor / 主要因素)
        - Protocol compatibility: 20% (must-have for bridging / 桥接必要条件)
        - Tag match: 10% (soft preference / 软偏好)
        """
        if total_required == 0:
            skill_score = 1.0
        else:
            skill_score = matched_count / total_required

        protocol_score = 1.0 if protocol_compatible else 0.0
        tag_score = 1.0 if tag_match else 0.5  # Partial credit for no tag filter

        # Weighted composite / 加权综合
        score = skill_score * 0.7 + protocol_score * 0.2 + tag_score * 0.1

        # Zero out if protocol is required but incompatible / 协议不兼容则归零
        if not protocol_compatible:
            score *= 0.1  # Heavy penalty but not zero (agent might still be useful)

        return round(score, 4)

    def find_best_agent(
        self,
        required_skills: list[str],
        agents: list[AgentDescriptor],
        required_protocol: str | None = None,
    ) -> CapabilityMatch | None:
        """Find the single best matching agent.
        查找最佳匹配的单个 Agent
        """
        matches = self.find_agents(
            required_skills=required_skills,
            agents=agents,
            required_protocol=required_protocol,
            min_score=0.1,
        )
        return matches[0] if matches else None
