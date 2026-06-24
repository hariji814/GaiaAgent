"""AURC Runtime Harness — Agent lifecycle state machine.
AURC 运行时 Harness — Agent 生命周期状态机

This is the CORE INNOVATION of the AURC protocol.
Neither MCP, A2A, nor ACP provides agent lifecycle management.
AURC's Harness manages:
    - Agent registration and initialization
    - State transitions (ready → running → paused → etc.)
    - Health monitoring
    - Context and memory management
    - Error recovery
    - Graceful shutdown
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from ..core.identity import AgentDescriptor
from ..core.types import (
    AgentState,
    HealthReport,
    HealthStatus,
    RecoveryAction,
    RecoveryPolicy,
    RecoveryStrategy,
    ResourceLimits,
    ResourceMetrics,
)

logger = logging.getLogger(__name__)


# =============================================================================
# State Transition Rules / 状态转换规则
# =============================================================================

# Defines which transitions are legal in the state machine.
# Key: current state → Set of allowed next states
# 定义状态机中合法的转换：当前状态 → 允许的下一状态集合
VALID_TRANSITIONS: dict[AgentState, set[AgentState]] = {
    AgentState.REGISTERING: {AgentState.READY, AgentState.FAILED},
    AgentState.READY: {AgentState.RUNNING, AgentState.STOPPED},
    AgentState.RUNNING: {
        AgentState.PAUSED,
        AgentState.FAILING,
        AgentState.COMPLETED,
        AgentState.STOPPED,
    },
    AgentState.PAUSED: {AgentState.RUNNING, AgentState.STOPPED, AgentState.READY},
    AgentState.FAILING: {AgentState.RECOVERING, AgentState.FAILED, AgentState.STOPPED},
    AgentState.RECOVERING: {AgentState.READY, AgentState.FAILED},
    # Terminal states have no outgoing transitions / 终态没有出向转换
    AgentState.COMPLETED: set(),
    AgentState.FAILED: set(),
    AgentState.STOPPED: set(),
}


class StateTransitionError(Exception):
    """Raised when an invalid state transition is attempted.
    尝试非法状态转换时抛出
    """

    def __init__(self, current: AgentState, target: AgentState, agent_id: str):
        self.current = current
        self.target = target
        self.agent_id = agent_id
        allowed = VALID_TRANSITIONS.get(current, set())
        super().__init__(
            f"Invalid state transition for agent '{agent_id}': "
            f"{current.value} → {target.value}. "
            f"Allowed: {[s.value for s in allowed]}"
        )


# =============================================================================
# Agent Instance / Agent 实例
# =============================================================================


class AgentInstance:
    """Runtime wrapper around a registered agent.
    注册 Agent 的运行时包装

    Tracks the agent's current state, metrics, and execution context.
    This is what the Harness manages internally.
    """

    def __init__(self, descriptor: AgentDescriptor):
        self.descriptor = descriptor
        self.state: AgentState = AgentState.REGISTERING
        self._state_history: list[tuple[AgentState, datetime]] = [
            (AgentState.REGISTERING, datetime.now(timezone.utc))
        ]
        self.metrics = ResourceMetrics()
        self.last_error: str | None = None
        self._retry_count: int = 0
        self._started_at: datetime | None = None
        self._task_handle: asyncio.Task | None = None
        self._pause_event: asyncio.Event = asyncio.Event()
        self._pause_event.set()  # Not paused initially / 初始未暂停
        self._stop_requested: bool = False

    @property
    def agent_id(self) -> str:
        return self.descriptor.aurc_id

    @property
    def state_history(self) -> list[tuple[AgentState, datetime]]:
        """Get the full state transition history. 获取完整状态转换历史"""
        return list(self._state_history)

    def can_transition_to(self, target: AgentState) -> bool:
        """Check if a transition to target state is valid. 检查转换是否合法"""
        return target in VALID_TRANSITIONS.get(self.state, set())

    def transition_to(self, target: AgentState) -> None:
        """Execute a state transition. 执行状态转换

        Raises:
            StateTransitionError: If the transition is not valid
        """
        if not self.can_transition_to(target):
            raise StateTransitionError(self.state, target, self.agent_id)

        old_state = self.state
        self.state = target
        now = datetime.now(timezone.utc)
        self._state_history.append((target, now))

        logger.info(
            "Agent '%s' state: %s → %s",
            self.agent_id,
            old_state.value,
            target.value,
        )

        # Track timing / 追踪时间
        if target == AgentState.RUNNING:
            self._started_at = now
        elif target.is_terminal:
            if self._started_at:
                self.metrics.uptime_seconds = (now - self._started_at).total_seconds()

    def reset_retry(self) -> None:
        """Reset retry counter (for new tasks). 重置重试计数器"""
        self._retry_count = 0

    def increment_retry(self) -> int:
        """Increment and return retry count. 增加并返回重试计数"""
        self._retry_count += 1
        return self._retry_count

    def to_health_report(self) -> HealthReport:
        """Generate a health report for this agent. 生成此 Agent 的健康报告"""
        return HealthReport(
            agent_id=self.agent_id,
            status=self._infer_health_status(),
            state=self.state,
            metrics=self.metrics,
            last_error=self.last_error,
        )

    def _infer_health_status(self) -> HealthStatus:
        """Infer health status from current state and metrics.
        从当前状态和指标推断健康状态
        """
        if self.state.is_terminal:
            return HealthStatus.UNKNOWN
        if self.state == AgentState.FAILING:
            return HealthStatus.UNHEALTHY
        if self.state in (AgentState.PAUSED, AgentState.RECOVERING):
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY


# =============================================================================
# State Change Listener / 状态变化监听器
# =============================================================================

StateListener = Callable[[str, AgentState, AgentState], Any]
"""Callback: (agent_id, old_state, new_state) -> Any"""


# =============================================================================
# Runtime Harness / 运行时 Harness
# =============================================================================


class RuntimeHarness:
    """AURC Runtime Harness — manages agent lifecycles.
    AURC 运行时 Harness — 管理 Agent 生命周期

    This is the central orchestration component of AURC.
    It acts as a 'container' for agents, managing their:
    - Registration and discovery
    - State transitions
    - Health monitoring
    - Error recovery
    - Graceful shutdown

    Usage / 用法:
        harness = RuntimeHarness()
        await harness.register(descriptor)
        handle = await harness.start(agent_id, task_params)
        await harness.pause(handle, "waiting for human approval")
        await harness.resume(handle)
        await harness.stop(handle)
    """

    def __init__(
        self,
        recovery_policy: RecoveryPolicy | None = None,
        resource_limits: ResourceLimits | None = None,
    ):
        self._agents: dict[str, AgentInstance] = {}
        self._listeners: list[StateListener] = []
        self._recovery_policy = recovery_policy or RecoveryPolicy()
        self._resource_limits = resource_limits or ResourceLimits()
        self._running = False

    # =========================================================================
    # Registration / 注册
    # =========================================================================

    async def register(self, descriptor: AgentDescriptor) -> str:
        """Register an agent with the harness.
        向 Harness 注册 Agent

        Args:
            descriptor: The agent's descriptor / Agent 描述文档

        Returns:
            The registered agent's AURC ID

        Raises:
            ValueError: If agent is already registered
        """
        agent_id = descriptor.aurc_id
        if agent_id in self._agents:
            raise ValueError(f"Agent '{agent_id}' is already registered")

        instance = AgentInstance(descriptor)
        self._agents[agent_id] = instance

        # Transition to READY / 转换到就绪状态
        instance.transition_to(AgentState.READY)

        logger.info("Registered agent: %s", agent_id)
        return agent_id

    async def unregister(self, agent_id: str) -> None:
        """Unregister an agent from the harness.
        从 Harness 注销 Agent
        """
        if agent_id not in self._agents:
            raise KeyError(f"Agent '{agent_id}' not found")

        instance = self._agents[agent_id]
        if instance.state.is_active:
            await self.stop(agent_id)

        del self._agents[agent_id]
        logger.info("Unregistered agent: %s", agent_id)

    # =========================================================================
    # Lifecycle Control / 生命周期控制
    # =========================================================================

    async def start(self, agent_id: str, task_params: dict[str, Any] | None = None, *, new_task: bool = False) -> str:
        """Start an agent's task execution.
        启动 Agent 的任务执行

        Args:
            agent_id: The agent's AURC ID
            task_params: Parameters for the task to execute / 任务参数
            new_task: If True, reset retry counter (new task, not recovery) / 是否为新任务

        Returns:
            Task handle ID for tracking / 用于追踪的任务句柄 ID
        """
        instance = self._get_agent(agent_id)

        if instance.state != AgentState.READY:
            raise RuntimeError(
                f"Agent '{agent_id}' is in state '{instance.state.value}', "
                f"must be 'ready' to start"
            )

        if new_task:
            instance.reset_retry()
        instance.transition_to(AgentState.RUNNING)
        instance.metrics.active_tasks += 1

        return agent_id  # Task handle = agent ID for now

    async def pause(self, agent_id: str, reason: str = "") -> None:
        """Pause a running agent.
        暂停运行中的 Agent

        Common reasons / 常见原因:
        - Waiting for human approval (HITL) / 等待人类审批
        - Resource contention / 资源争用
        - Rate limiting / 速率限制
        """
        instance = self._get_agent(agent_id)
        instance.transition_to(AgentState.PAUSED)
        instance._pause_event.clear()
        logger.info("Agent '%s' paused: %s", agent_id, reason)

    async def resume(self, agent_id: str) -> None:
        """Resume a paused agent.
        恢复暂停的 Agent
        """
        instance = self._get_agent(agent_id)
        instance.transition_to(AgentState.RUNNING)
        instance._pause_event.set()
        logger.info("Agent '%s' resumed", agent_id)

    async def stop(self, agent_id: str, graceful: bool = True) -> None:
        """Stop an agent.
        停止 Agent

        Args:
            agent_id: The agent's AURC ID
            graceful: If True, wait for current operation to complete / 是否等待当前操作完成
        """
        instance = self._get_agent(agent_id)
        instance._stop_requested = True

        # If paused, resume first so it can process the stop / 如果暂停，先恢复
        if instance.state == AgentState.PAUSED:
            instance._pause_event.set()

        instance.transition_to(AgentState.STOPPED)
        instance.metrics.active_tasks = max(0, instance.metrics.active_tasks - 1)
        logger.info("Agent '%s' stopped (graceful=%s)", agent_id, graceful)

    async def complete(self, agent_id: str) -> None:
        """Mark an agent's task as completed.
        标记 Agent 的任务为已完成
        """
        instance = self._get_agent(agent_id)
        instance.transition_to(AgentState.COMPLETED)
        instance.metrics.active_tasks = max(0, instance.metrics.active_tasks - 1)
        instance.metrics.total_tasks_completed += 1

    async def restart(self, agent_id: str) -> str:
        """Restart an agent (stop then start fresh).
        重启 Agent（停止后重新以 READY 状态启动）
        """
        instance = self._get_agent(agent_id)

        # Force to READY if in terminal state / 如果处于终态则强制回到 READY
        if instance.state.is_terminal:
            instance.state = AgentState.READY
            instance._state_history.append(
                (AgentState.READY, datetime.now(timezone.utc))
            )
        elif instance.state != AgentState.READY:
            await self.stop(agent_id, graceful=False)
            instance.state = AgentState.READY
            instance._state_history.append(
                (AgentState.READY, datetime.now(timezone.utc))
            )

        return await self.start(agent_id)

    # =========================================================================
    # Error Recovery / 错误恢复
    # =========================================================================

    async def report_error(self, agent_id: str, error: str) -> bool:
        """Report an error for an agent, triggering recovery if possible.
        报告 Agent 错误，如可能则触发恢复

        Returns:
            True if recovery was attempted, False if agent was failed directly
        """
        instance = self._get_agent(agent_id)
        instance.last_error = error
        instance.transition_to(AgentState.FAILING)

        # Check recovery policy / 检查恢复策略
        retry_count = instance.increment_retry()
        policy = self._recovery_policy

        if retry_count > policy.max_retries:
            logger.error(
                "Agent '%s' exceeded max retries (%d), failing",
                agent_id,
                policy.max_retries,
            )
            instance.transition_to(AgentState.FAILED)
            instance.metrics.total_tasks_failed += 1
            return False

        # Attempt recovery / 尝试恢复
        strategy = self._find_strategy(error, policy)
        instance.transition_to(AgentState.RECOVERING)

        if strategy:
            logger.info(
                "Agent '%s' recovering (attempt %d/%d): %s",
                agent_id,
                retry_count,
                policy.max_retries,
                strategy.action.value,
            )
            await self._execute_recovery(instance, strategy)
        else:
            # Default recovery: simple backoff retry / 默认恢复：简单退避重试
            logger.info(
                "Agent '%s' recovering (attempt %d/%d): default retry_with_backoff",
                agent_id,
                retry_count,
                policy.max_retries,
            )
            delay_ms = policy.backoff_ms[
                min(retry_count - 1, len(policy.backoff_ms) - 1)
            ] if policy.backoff_ms else 1000
            await asyncio.sleep(delay_ms / 1000)

        # Return to READY for retry / 恢复到 READY 以便重试
        if instance.state == AgentState.RECOVERING:
            instance.transition_to(AgentState.READY)
        return True

    # =========================================================================
    # Health Monitoring / 健康监控
    # =========================================================================

    async def health_check(self, agent_id: str) -> HealthReport:
        """Get health report for a specific agent.
        获取特定 Agent 的健康报告
        """
        instance = self._get_agent(agent_id)
        return instance.to_health_report()

    async def health_check_all(self) -> list[HealthReport]:
        """Get health reports for all registered agents.
        获取所有已注册 Agent 的健康报告
        """
        return [inst.to_health_report() for inst in self._agents.values()]

    # =========================================================================
    # State Listeners / 状态监听器
    # =========================================================================

    def add_listener(self, listener: StateListener) -> None:
        """Add a state change listener.
        添加状态变化监听器

        The listener is called with (agent_id, old_state, new_state)
        on every state transition.
        """
        self._listeners.append(listener)

    def remove_listener(self, listener: StateListener) -> None:
        """Remove a state change listener."""
        self._listeners.remove(listener)

    async def _notify_listeners(
        self, agent_id: str, old_state: AgentState, new_state: AgentState
    ) -> None:
        """Notify all listeners of a state change."""
        for listener in self._listeners:
            try:
                result = listener(agent_id, old_state, new_state)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("Error in state listener for agent '%s'", agent_id)

    # =========================================================================
    # Queries / 查询
    # =========================================================================

    def get_agent(self, agent_id: str) -> AgentInstance | None:
        """Get an agent instance by ID (read-only access)."""
        return self._agents.get(agent_id)

    def list_agents(self, state: AgentState | None = None) -> list[AgentInstance]:
        """List registered agents, optionally filtered by state.
        列出已注册的 Agent，可按状态过滤
        """
        agents = list(self._agents.values())
        if state is not None:
            agents = [a for a in agents if a.state == state]
        return agents

    @property
    def agent_count(self) -> int:
        """Number of registered agents."""
        return len(self._agents)

    # =========================================================================
    # Shutdown / 关闭
    # =========================================================================

    async def shutdown(self, graceful: bool = True) -> None:
        """Shutdown the harness and all agents.
        关闭 Harness 和所有 Agent
        """
        logger.info("Harness shutting down (graceful=%s)...", graceful)
        for agent_id in list(self._agents.keys()):
            instance = self._agents[agent_id]
            if not instance.state.is_terminal:
                try:
                    await self.stop(agent_id, graceful=graceful)
                except Exception:
                    logger.exception("Error stopping agent '%s' during shutdown", agent_id)
        self._running = False

    # =========================================================================
    # Internal Helpers / 内部辅助
    # =========================================================================

    def _get_agent(self, agent_id: str) -> AgentInstance:
        """Get an agent instance, raising if not found."""
        if agent_id not in self._agents:
            raise KeyError(f"Agent '{agent_id}' not registered in harness")
        return self._agents[agent_id]

    def _find_strategy(
        self, error: str, policy: RecoveryPolicy
    ) -> RecoveryStrategy | None:
        """Find a matching recovery strategy for an error."""
        for strategy in policy.strategies:
            if strategy.trigger in error.lower():
                return strategy
        # Default: use retry_with_backoff if strategies exist / 默认使用退避重试
        if policy.strategies:
            return policy.strategies[0]
        return None

    async def _execute_recovery(
        self, instance: AgentInstance, strategy: RecoveryStrategy
    ) -> None:
        """Execute a recovery strategy. 执行恢复策略"""
        action = strategy.action

        if action == RecoveryAction.RETRY_WITH_BACKOFF:
            policy = self._recovery_policy
            retry_idx = min(instance._retry_count - 1, len(policy.backoff_ms) - 1)
            delay_ms = policy.backoff_ms[max(0, retry_idx)]
            logger.info("Recovery: retry with %dms backoff", delay_ms)
            await asyncio.sleep(delay_ms / 1000)

        elif action == RecoveryAction.ESCALATE:
            target = strategy.escalate_to or "human_operator"
            logger.warning(
                "Recovery: escalating agent '%s' to %s",
                instance.agent_id,
                target,
            )
            # In production, this would trigger a HITL request / 生产环境中会触发人类介入请求

        elif action == RecoveryAction.FAIL:
            instance.transition_to(AgentState.FAILED)

        else:
            logger.info("Recovery: executing %s", action.value)
            # Other recovery actions would be implemented here / 其他恢复动作在此实现
