"""Shared type definitions for the AURC Protocol.
AURC 协议共享类型定义
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# Enums / 枚举
# =============================================================================


class AgentState(str, enum.Enum):
    """Agent lifecycle states.
    Agent 生命周期状态

    State Machine / 状态机:
        REGISTERING → READY → RUNNING → PAUSED / FAILING
        FAILING → RECOVERING → READY / FAILED
        RUNNING → COMPLETED / STOPPED
    """

    REGISTERING = "registering"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    FAILING = "failing"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"

    @property
    def is_terminal(self) -> bool:
        """Whether this state is a terminal (final) state. 是否为终态"""
        return self in (AgentState.COMPLETED, AgentState.FAILED, AgentState.STOPPED)

    @property
    def is_active(self) -> bool:
        """Whether the agent is actively doing work. 是否正在工作"""
        return self in (AgentState.RUNNING, AgentState.FAILING, AgentState.RECOVERING)


class MessageDirection(str, enum.Enum):
    """Direction of message flow. 消息流向"""

    REQUEST = "request"  # 发起方 → 目标, 需要响应
    RESPONSE = "response"  # 目标 → 发起方
    NOTIFICATION = "notification"  # 单向通知
    STREAM = "stream"  # 流式数据
    DELEGATION = "delegation"  # 任务委派
    HANDOFF = "handoff"  # 任务移交
    HEARTBEAT = "heartbeat"  # 心跳保活


class ContextScope(str, enum.Enum):
    """Context visibility scopes. 上下文作用域"""

    SESSION = "session"  # 单次任务
    AGENT = "agent"  # Agent 生命周期
    SHARED = "shared"  # 跨 Agent 共享
    GLOBAL = "global"  # 全局


class Priority(str, enum.Enum):
    """Message/task priority levels. 优先级"""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class HealthStatus(str, enum.Enum):
    """Agent health status. 健康状态"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class RecoveryAction(str, enum.Enum):
    """Error recovery actions. 错误恢复动作"""

    RETRY_WITH_BACKOFF = "retry_with_backoff"
    RETRY_ALTERNATIVE = "retry_alternative"
    COMPACT_AND_RETRY = "compact_and_retry"
    REFRESH_AND_RETRY = "refresh_and_retry"
    ESCALATE = "escalate"
    FAIL = "fail"


class AuthMethod(str, enum.Enum):
    """Supported authentication methods. 认证方式"""

    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    MTLS = "mtls"
    JWT = "jwt"


class TransportType(str, enum.Enum):
    """Supported transport types. 传输方式"""

    HTTP = "http"
    WEBSOCKET = "websocket"
    STDIO = "stdio"
    GRPC = "grpc"


# =============================================================================
# Base Models / 基础模型
# =============================================================================


class Timestamp(BaseModel):
    """Standardized timestamp wrapper. 标准化时间戳"""

    value: datetime = Field(default_factory=datetime.now)

    def isoformat(self) -> str:
        return self.value.isoformat()


class ResourceLimits(BaseModel):
    """Resource limits for an agent. Agent 资源限制"""

    max_memory_mb: int = Field(default=1024, description="Maximum memory in MB / 最大内存 MB")
    max_cpu_percent: float = Field(default=100.0, description="Maximum CPU percentage / 最大 CPU 百分比")
    max_concurrency: int = Field(default=10, description="Maximum concurrent tasks / 最大并发任务数")
    timeout_seconds: int = Field(default=3600, description="Task timeout in seconds / 任务超时秒数")


class ResourceMetrics(BaseModel):
    """Current resource usage metrics. 当前资源使用指标"""

    memory_mb: float = 0.0
    cpu_percent: float = 0.0
    active_tasks: int = 0
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0
    uptime_seconds: float = 0.0


class HealthReport(BaseModel):
    """Agent health check report. Agent 健康检查报告"""

    agent_id: str
    status: HealthStatus = HealthStatus.UNKNOWN
    state: AgentState = AgentState.READY
    metrics: ResourceMetrics = Field(default_factory=ResourceMetrics)
    last_error: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class RecoveryPolicy(BaseModel):
    """Error recovery policy configuration. 错误恢复策略配置"""

    max_retries: int = Field(default=3, description="Maximum retry attempts / 最大重试次数")
    backoff_ms: list[int] = Field(
        default=[1000, 5000, 15000],
        description="Backoff intervals in milliseconds / 退避间隔毫秒",
    )
    strategies: list[RecoveryStrategy] = Field(default_factory=list)


class RecoveryStrategy(BaseModel):
    """A single recovery strategy rule. 单条恢复策略规则"""

    trigger: str = Field(description="Error type that triggers this strategy / 触发此策略的错误类型")
    action: RecoveryAction = Field(description="Action to take / 执行的动作")
    alternatives: list[str] = Field(
        default_factory=list,
        description="Alternative tools/skills for RETRY_ALTERNATIVE / 备选工具",
    )
    escalate_to: str | None = Field(
        default=None,
        description="Escalation target for ESCALATE action / 升级目标",
    )


# Resolve forward reference
RecoveryPolicy.model_rebuild()
