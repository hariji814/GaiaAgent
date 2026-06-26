"""Core module — AURC identity, messaging, and capability types."""

from gaiaagent.core.capability import CapabilityMatch, CapabilityMatcher
from gaiaagent.core.identity import (
    AgentDescriptor,
    AURCId,
    AuthDeclaration,
    Capabilities,
    InputOutputSchema,
    ProtocolSupport,
    RuntimeRequirements,
    SkillDeclaration,
)
from gaiaagent.core.message import (
    AURCMessage,
    BridgeContext,
    DelegationHop,
    ErrorInfo,
    MessageBody,
    MessageSecurity,
    RoutingInfo,
    SessionInfo,
)
from gaiaagent.core.types import (
    AgentState,
    AuthMethod,
    ContextScope,
    HealthStatus,
    MessageDirection,
    Priority,
    RecoveryAction,
    RecoveryPolicy,
    RecoveryStrategy,
    ResourceLimits,
    ResourceMetrics,
    TransportType,
)

__all__ = [
    # Types
    "AgentState", "AuthMethod", "ContextScope", "HealthStatus",
    "MessageDirection", "Priority", "RecoveryAction", "RecoveryPolicy",
    "RecoveryStrategy", "ResourceLimits", "ResourceMetrics", "TransportType",
    # Identity
    "AURCId", "AgentDescriptor", "AuthDeclaration", "Capabilities",
    "InputOutputSchema", "ProtocolSupport", "RuntimeRequirements", "SkillDeclaration",
    # Message
    "AURCMessage", "BridgeContext", "DelegationHop", "ErrorInfo",
    "MessageBody", "MessageSecurity", "RoutingInfo", "SessionInfo",
    # Capability
    "CapabilityMatch", "CapabilityMatcher",
]
