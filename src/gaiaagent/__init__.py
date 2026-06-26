"""GaiaAgent — AURC Protocol Implementation
Agent Unified Runtime & Communication Protocol
Agent 统一运行时与通信协议
"""

__version__ = "0.1.0"

# Re-export key types for convenience / 导出关键类型
from gaiaagent.core.identity import AgentDescriptor, AURCId
from gaiaagent.core.message import AURCMessage
from gaiaagent.core.types import (
    AgentState,
    ContextScope,
    HealthStatus,
    MessageDirection,
    Priority,
)
from gaiaagent.harness.lifecycle import RuntimeHarness

__all__ = [
    "__version__",
    "AgentState",
    "ContextScope",
    "HealthStatus",
    "MessageDirection",
    "Priority",
    "AURCId",
    "AgentDescriptor",
    "AURCMessage",
    "RuntimeHarness",
]
