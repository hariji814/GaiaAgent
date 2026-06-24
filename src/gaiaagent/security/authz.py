"""AURC CapABAC Authorization Engine.
AURC CapABAC 授权引擎

Combines Capability-Based Security with Attribute-Based Access Control:
- Capabilities: what actions are allowed / 能力：允许什么操作
- Attributes: under what conditions / 属性：在什么条件下

Key rules / 关键规则:
1. Default deny — everything is denied unless explicitly allowed / 默认拒绝
2. Capabilities can be delegated with narrowing / 能力可以缩小范围后委托
3. Constraints are evaluated at authorization time / 约束在授权时求值
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Policy Models / 策略模型
# =============================================================================


@dataclass
class Constraint:
    """A constraint on an authorization rule. 授权规则的约束"""
    field: str
    operator: str  # eq, ne, gt, lt, gte, lte, in, not_in, matches, contains
    value: Any

    def evaluate(self, actual_value: Any) -> bool:
        """Evaluate this constraint against an actual value. 对实际值求值"""
        match self.operator:
            case "eq":
                return actual_value == self.value
            case "ne":
                return actual_value != self.value
            case "gt":
                return actual_value > self.value
            case "lt":
                return actual_value < self.value
            case "gte":
                return actual_value >= self.value
            case "lte":
                return actual_value <= self.value
            case "in":
                return actual_value in self.value
            case "not_in":
                return actual_value not in self.value
            case "matches":
                return bool(re.match(self.value, str(actual_value)))
            case "contains":
                return self.value in actual_value
            case _:
                logger.warning("Unknown operator: %s", self.operator)
                return False


@dataclass
class AuthorizationRule:
    """A single authorization rule. 单条授权规则"""
    resource_type: str
    actions: list[str]
    constraints: list[Constraint] = field(default_factory=list)
    time_window: dict[str, str] | None = None  # {"start": "08:00", "end": "22:00", "timezone": "UTC"}
    rate_limit: int | None = None  # max operations per hour

    def matches_resource(self, resource_type: str) -> bool:
        """Check if this rule applies to a resource type."""
        return self.resource_type == resource_type or self.resource_type == "*"

    def matches_action(self, action: str) -> bool:
        """Check if this rule allows an action."""
        return action in self.actions or "*" in self.actions


@dataclass
class DelegationPolicy:
    """Policy for capability delegation. 能力委托策略"""
    allowed: bool = True
    max_depth: int = 3
    scope_reduction_required: bool = True


@dataclass
class AgentPolicy:
    """Complete authorization policy for an agent. Agent 的完整授权策略"""
    agent_id: str
    rules: list[AuthorizationRule] = field(default_factory=list)
    delegation: DelegationPolicy = field(default_factory=DelegationPolicy)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Rate Limiter / 速率限制器
# =============================================================================


class RateLimiter:
    """Simple sliding-window rate limiter. 简单滑动窗口速率限制器"""

    def __init__(self) -> None:
        # (agent_id, resource_type) → list of timestamps / (Agent ID, 资源类型) → 时间戳列表
        self._windows: dict[tuple[str, str], list[float]] = {}

    def check(self, agent_id: str, resource_type: str, max_per_hour: int) -> bool:
        """Check if a request is within rate limits. 检查请求是否在速率限制内"""
        key = (agent_id, resource_type)
        now = datetime.now(timezone.utc).timestamp()
        window_start = now - 3600  # 1 hour window

        if key not in self._windows:
            self._windows[key] = []

        # Clean old entries / 清理旧条目
        self._windows[key] = [t for t in self._windows[key] if t > window_start]

        if len(self._windows[key]) >= max_per_hour:
            return False

        self._windows[key].append(now)
        return True

    def reset(self, agent_id: str | None = None) -> None:
        """Reset rate limit counters. 重置速率限制计数器"""
        if agent_id is None:
            self._windows.clear()
        else:
            keys_to_remove = [k for k in self._windows if k[0] == agent_id]
            for k in keys_to_remove:
                del self._windows[k]


# =============================================================================
# CapABAC Authorization Engine / CapABAC 授权引擎
# =============================================================================


class AuthorizationEngine:
    """CapABAC Authorization Engine — evaluates authorization decisions.
    CapABAC 授权引擎 — 做出授权决策

    Usage / 用法:
        engine = AuthorizationEngine()

        # Define policy / 定义策略
        engine.set_policy("aurc:gaia/researcher:v1.0", AgentPolicy(
            agent_id="aurc:gaia/researcher:v1.0",
            rules=[
                AuthorizationRule(
                    resource_type="web-search",
                    actions=["execute"],
                    constraints=[
                        Constraint("domain", "matches", r".*\\.edu$"),
                    ],
                    rate_limit=100,
                ),
            ],
        ))

        # Check authorization / 检查授权
        result = engine.authorize(
            agent_id="aurc:gaia/researcher:v1.0",
            resource_type="web-search",
            action="execute",
            attributes={"domain": "mit.edu"},
        )
    """

    def __init__(self) -> None:
        self._policies: dict[str, AgentPolicy] = {}
        self._rate_limiter = RateLimiter()

    def set_policy(self, agent_id: str, policy: AgentPolicy) -> None:
        """Set authorization policy for an agent. 设置 Agent 的授权策略"""
        self._policies[agent_id] = policy
        logger.info("Policy set for agent '%s': %d rules", agent_id, len(policy.rules))

    def get_policy(self, agent_id: str) -> AgentPolicy | None:
        """Get an agent's policy. 获取 Agent 的策略"""
        return self._policies.get(agent_id)

    def remove_policy(self, agent_id: str) -> bool:
        """Remove an agent's policy. 移除 Agent 的策略"""
        return self._policies.pop(agent_id, None) is not None

    def authorize(
        self,
        agent_id: str,
        resource_type: str,
        action: str,
        attributes: dict[str, Any] | None = None,
    ) -> AuthzResult:
        """Evaluate an authorization decision.
        做出授权决策

        Args:
            agent_id: The agent requesting access / 请求访问的 Agent
            resource_type: The resource being accessed / 被访问的资源类型
            action: The action being performed / 执行的动作
            attributes: Additional attributes for constraint evaluation / 约束求值的附加属性

        Returns:
            AuthzResult with the decision / 包含决策的 AuthzResult
        """
        policy = self._policies.get(agent_id)
        if not policy:
            return AuthzResult(
                allowed=False,
                reason=f"No policy defined for agent '{agent_id}'",
            )

        attributes = attributes or {}

        # Find matching rules / 查找匹配规则
        matching_rules = [
            r for r in policy.rules
            if r.matches_resource(resource_type) and r.matches_action(action)
        ]

        if not matching_rules:
            return AuthzResult(
                allowed=False,
                reason=f"No rule allows '{action}' on '{resource_type}' for agent '{agent_id}'",
            )

        # Evaluate each matching rule / 评估每条匹配规则
        for rule in matching_rules:
            # Check time window / 检查时间窗口
            if rule.time_window and not self._check_time_window(rule.time_window):
                continue

            # Check constraints / 检查约束
            all_constraints_met = True
            for constraint in rule.constraints:
                actual_value = attributes.get(constraint.field)
                if actual_value is None:
                    all_constraints_met = False
                    break
                if not constraint.evaluate(actual_value):
                    all_constraints_met = False
                    break

            if not all_constraints_met:
                continue

            # Check rate limit / 检查速率限制
            if rule.rate_limit:
                if not self._rate_limiter.check(agent_id, resource_type, rule.rate_limit):
                    return AuthzResult(
                        allowed=False,
                        reason=f"Rate limit exceeded: {rule.rate_limit}/hour for '{resource_type}'",
                    )

            # All checks passed / 所有检查通过
            return AuthzResult(
                allowed=True,
                matched_rule=rule,
                reason=f"Authorized: '{action}' on '{resource_type}'",
            )

        return AuthzResult(
            allowed=False,
            reason=f"No matching rule passed all constraints for '{action}' on '{resource_type}'",
        )

    def authorize_scopes(
        self,
        agent_id: str,
        resource_type: str,
        action: str,
        required_scopes: list[str],
        granted_scopes: list[str],
        attributes: dict[str, Any] | None = None,
    ) -> AuthzResult:
        """Authorize with scope validation.
        带权限范围验证的授权

        Ensures the agent has the required scopes before checking rules.
        在检查规则之前确保 Agent 拥有必要的权限范围
        """
        # Check scope intersection / 检查权限范围交集
        granted_set = set(granted_scopes)
        required_set = set(required_scopes)

        if not required_set.issubset(granted_set):
            missing = required_set - granted_set
            return AuthzResult(
                allowed=False,
                reason=f"Missing required scopes: {missing}",
            )

        return self.authorize(agent_id, resource_type, action, attributes)

    @staticmethod
    def _check_time_window(window: dict[str, str]) -> bool:
        """Check if current time is within the allowed window."""
        # Simplified — in production, use proper timezone handling
        now = datetime.now(timezone.utc)
        start_str = window.get("start", "00:00")
        end_str = window.get("end", "23:59")

        start_h, start_m = map(int, start_str.split(":"))
        end_h, end_m = map(int, end_str.split(":"))

        current_minutes = now.hour * 60 + now.minute
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m

        return start_minutes <= current_minutes <= end_minutes


@dataclass
class AuthzResult:
    """Authorization decision result. 授权决策结果"""
    allowed: bool
    reason: str = ""
    matched_rule: AuthorizationRule | None = None
