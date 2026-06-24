"""AURC Delegation Chain — validates permission delegation across agents.
AURC 委托链 — 验证跨 Agent 的权限委托

Solves MCP's Confused Deputy Problem by ensuring:
1. Every delegation hop is recorded / 每一跳委托都被记录
2. Scopes only narrow, never widen / 权限范围只缩小不扩大
3. Delegation depth is bounded / 委托深度有上限
4. Chain integrity is verifiable / 链的完整性可验证
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..core.message import DelegationHop, MessageSecurity

logger = logging.getLogger(__name__)


# =============================================================================
# Delegation Chain Validator / 委托链验证器
# =============================================================================


class DelegationValidator:
    """Validates delegation chains for security enforcement.
    验证委托链以执行安全策略

    Usage / 用法:
        validator = DelegationValidator(max_depth=5)

        result = validator.validate(security_context)
        if not result.valid:
            raise PermissionError(result.reason)
    """

    def __init__(self, max_depth: int = 5, require_signatures: bool = False) -> None:
        self._max_depth = max_depth
        self._require_signatures = require_signatures

    def validate(self, security: MessageSecurity) -> DelegationResult:
        """Validate a delegation chain.
        验证委托链

        Checks:
        1. Chain depth within limit / 链深度在限制内
        2. Scopes only narrow / 权限范围只缩小
        3. No circular delegations / 无循环委托
        4. Timestamp ordering / 时间戳顺序
        """
        chain = security.delegation_chain

        # Empty chain is valid (direct invocation) / 空链合法（直接调用）
        if not chain:
            return DelegationResult(valid=True, reason="Direct invocation, no delegation")

        # Check depth / 检查深度
        if len(chain) > self._max_depth:
            return DelegationResult(
                valid=False,
                reason=f"Delegation chain too deep: {len(chain)} > {self._max_depth}",
                depth=len(chain),
            )

        # Check scope narrowing / 检查权限范围缩小
        for i in range(1, len(chain)):
            prev_scopes = set(chain[i - 1].scopes)
            curr_scopes = set(chain[i].scopes)

            if not curr_scopes.issubset(prev_scopes):
                widened = curr_scopes - prev_scopes
                return DelegationResult(
                    valid=False,
                    reason=(
                        f"Scopes widened at hop {i}: "
                        f"{chain[i-1].from_agent} → {chain[i-1].to_agent} "
                        f"added scopes: {widened}"
                    ),
                    failed_hop=i,
                )

        # Check for circular delegations / 检查循环委托
        seen_agents: set[str] = set()
        for hop in chain:
            if hop.to_agent in seen_agents:
                return DelegationResult(
                    valid=False,
                    reason=f"Circular delegation detected: {hop.to_agent} appears twice",
                )
            seen_agents.add(hop.from_agent)

        # Check timestamp ordering / 检查时间戳顺序
        for i in range(1, len(chain)):
            if chain[i].timestamp < chain[i - 1].timestamp:
                return DelegationResult(
                    valid=False,
                    reason=f"Timestamp disorder at hop {i}: "
                           f"{chain[i].timestamp} < {chain[i-1].timestamp}",
                    failed_hop=i,
                )

        return DelegationResult(
            valid=True,
            reason=f"Valid delegation chain: {len(chain)} hops",
            depth=len(chain),
            effective_scopes=list(set(chain[-1].scopes)),
        )

    def validate_effective_scopes(
        self,
        security: MessageSecurity,
        required_scopes: list[str],
    ) -> DelegationResult:
        """Validate that the effective scopes cover the required scopes.
        验证有效权限范围覆盖所需权限范围

        The effective scopes are the intersection of all scopes in the chain.
        """
        chain_result = self.validate(security)
        if not chain_result.valid:
            return chain_result

        chain = security.delegation_chain
        if not chain:
            # No delegation — check direct scopes / 无委托 — 检查直接权限
            effective = set(security.scopes)
        else:
            effective = set(chain[-1].scopes)

        required = set(required_scopes)
        if not required.issubset(effective):
            missing = required - effective
            return DelegationResult(
                valid=False,
                reason=f"Insufficient scopes. Missing: {missing}. Have: {effective}",
                effective_scopes=list(effective),
            )

        return DelegationResult(
            valid=True,
            reason="Scopes sufficient",
            effective_scopes=list(effective),
        )


@dataclass
class DelegationResult:
    """Result of delegation chain validation. 委托链验证结果"""
    valid: bool
    reason: str = ""
    depth: int = 0
    failed_hop: int | None = None
    effective_scopes: list[str] = field(default_factory=list)


# =============================================================================
# Delegation Builder / 委托构建器
# =============================================================================


class DelegationBuilder:
    """Helper to build delegation chains correctly.
    辅助构建正确的委托链

    Ensures scopes narrow properly and timestamps are ordered.

    Usage / 用法:
        builder = DelegationBuilder()
        builder.add_hop(
            from_agent="aurc:user/alice:v1.0",
            to_agent="aurc:gaia/orchestrator:v1.0",
            scopes=["research:read", "web:search", "admin"],
        )
        builder.add_hop(
            from_agent="aurc:gaia/orchestrator:v1.0",
            to_agent="aurc:gaia/researcher:v1.0",
            scopes=["research:read", "web:search"],  # narrowed
        )
        chain = builder.build()
    """

    def __init__(self) -> None:
        self._hops: list[DelegationHop] = []

    def add_hop(
        self,
        from_agent: str,
        to_agent: str,
        scopes: list[str],
    ) -> DelegationBuilder:
        """Add a delegation hop.
        添加委托跳

        Args:
            from_agent: Delegating agent / 委托方 Agent
            to_agent: Receiving agent / 被委托方 Agent
            scopes: Scopes granted (must be subset of previous) / 授予的权限

        Returns:
            self (for chaining) / self（用于链式调用）

        Raises:
            ValueError: If scopes widen compared to previous hop / 如果权限范围扩大
        """
        if self._hops:
            prev_scopes = set(self._hops[-1].scopes)
            curr_scopes = set(scopes)
            if not curr_scopes.issubset(prev_scopes):
                widened = curr_scopes - prev_scopes
                raise ValueError(
                    f"Cannot widen scopes at hop {len(self._hops) + 1}. "
                    f"Added scopes: {widened}"
                )

        # Ensure from_agent matches previous to_agent / 确保 from_agent 匹配上一个 to_agent
        if self._hops and from_agent != self._hops[-1].to_agent:
            raise ValueError(
                f"Chain broken: expected from_agent='{self._hops[-1].to_agent}', "
                f"got '{from_agent}'"
            )

        self._hops.append(DelegationHop(
            from_agent=from_agent,
            to_agent=to_agent,
            scopes=scopes,
            timestamp=datetime.now(timezone.utc),
        ))
        return self

    def build(self) -> list[DelegationHop]:
        """Build the delegation chain. 构建委托链"""
        return list(self._hops)

    @property
    def depth(self) -> int:
        return len(self._hops)

    @property
    def effective_scopes(self) -> list[str]:
        """Get the effective (narrowest) scopes. 获取有效（最窄）权限范围"""
        if not self._hops:
            return []
        return list(self._hops[-1].scopes)


# =============================================================================
# Chain Integrity / 链完整性
# =============================================================================


def compute_chain_hash(chain: list[DelegationHop]) -> str:
    """Compute a hash of the delegation chain for integrity verification.
    计算委托链的哈希值用于完整性验证

    This hash can be stored and later compared to detect tampering.
    """
    if not chain:
        return ""

    hasher = hashlib.sha256()
    for hop in chain:
        hasher.update(hop.from_agent.encode())
        hasher.update(hop.to_agent.encode())
        hasher.update(",".join(sorted(hop.scopes)).encode())
        hasher.update(hop.timestamp.isoformat().encode())

    return hasher.hexdigest()
