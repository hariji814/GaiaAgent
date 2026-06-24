"""AURC Unified Message Format.
AURC 统一消息格式

Defines the canonical message structure used across all AURC communications.
This format can be translated to/from MCP, A2A, ACP via Protocol Bridges.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from .types import MessageDirection, Priority


# =============================================================================
# Message Components / 消息组件
# =============================================================================


class BridgeContext(BaseModel):
    """Protocol bridge context — tracks which protocols a message has passed through.
    协议桥接上下文 — 追踪消息经过了哪些协议转换

    This enables:
    1. Understanding where a message originated (even across protocol boundaries)
    2. Debugging multi-protocol chains
    3. Applying protocol-specific security rules
    """

    origin_protocol: str = Field(
        default="aurc",
        description="Protocol where this message originated / 消息源协议",
    )
    bridged_from: str | None = Field(
        default=None,
        description="Previous protocol if bridged / 如果经过桥接，上一个协议",
    )
    bridge_chain: list[str] = Field(
        default_factory=list,
        description="Chain of bridges, e.g. ['a2a→aurc', 'aurc→mcp'] / 桥接链",
    )

    @property
    def is_bridged(self) -> bool:
        """Whether this message passed through any protocol bridge."""
        return len(self.bridge_chain) > 0

    @property
    def hop_count(self) -> int:
        """Number of protocol bridges traversed."""
        return len(self.bridge_chain)

    def add_hop(self, from_proto: str, to_proto: str) -> BridgeContext:
        """Create a new BridgeContext with an additional hop.
        创建添加了新跳数的 BridgeContext
        """
        return BridgeContext(
            origin_protocol=self.origin_protocol,
            bridged_from=from_proto,
            bridge_chain=self.bridge_chain + [f"{from_proto}→{to_proto}"],
        )


class SessionInfo(BaseModel):
    """Session and conversation tracking. 会话追踪

    Enables:
    1. Multi-turn conversations between agents
    2. Correlating related messages
    3. Context window management
    """

    session_id: str = Field(
        default_factory=lambda: f"session-{uuid.uuid4().hex[:12]}",
        description="Unique session identifier / 会话唯一标识",
    )
    conversation_id: str | None = Field(
        default=None,
        description="Conversation ID for multi-turn grouping / 多轮对话分组 ID",
    )
    turn: int = Field(default=0, description="Turn number in conversation / 对话轮次")
    parent_message_id: str | None = Field(
        default=None,
        description="ID of the message this is responding to / 响应来源消息 ID",
    )


class DelegationHop(BaseModel):
    """Single hop in a delegation chain. 委托链中的单跳

    Records: who delegated to whom, with what scopes, when.
    This is the key mechanism for solving MCP's Confused Deputy problem.
    """

    from_agent: str = Field(description="Delegating agent's AURC ID / 委托方 AURC ID")
    to_agent: str = Field(description="Receiving agent's AURC ID / 被委托方 AURC ID")
    scopes: list[str] = Field(
        default_factory=list,
        description="Permission scopes granted in this delegation / 此次委托授予的权限范围",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this delegation was made / 委托时间",
    )


class MessageSecurity(BaseModel):
    """Security context attached to a message. 消息安全上下文

    Carries authentication and authorization information needed for
    protocol-level permission enforcement (solving MCP's confused deputy).
    """

    auth_token_ref: str | None = Field(
        default=None,
        description="Reference to auth token (not the token itself) / 认证令牌引用",
    )
    scopes: list[str] = Field(
        default_factory=list,
        description="Effective permission scopes for this message / 此消息的有效权限范围",
    )
    delegation_chain: list[DelegationHop] = Field(
        default_factory=list,
        description="Full delegation chain from original requester / 从原始请求者开始的完整委托链",
    )

    def validate_delegation_chain(self) -> bool:
        """Validate that scopes only narrow (never widen) through the chain.
        验证权限范围在委托链中只缩小不扩大

        Rule: each hop's scopes must be a subset of the previous hop's scopes.
        """
        if len(self.delegation_chain) < 2:
            return True

        for i in range(1, len(self.delegation_chain)):
            prev_scopes = set(self.delegation_chain[i - 1].scopes)
            curr_scopes = set(self.delegation_chain[i].scopes)
            # Scopes should only narrow — current must be subset of previous
            if not curr_scopes.issubset(prev_scopes):
                return False
        return True


class RoutingInfo(BaseModel):
    """Message routing metadata. 消息路由元数据"""

    ttl_hops: int = Field(default=5, description="Maximum hops before message expires / 消息最大跳数")
    priority: Priority = Field(default=Priority.NORMAL, description="Message priority / 消息优先级")
    timeout_ms: int = Field(default=30000, description="Response timeout in ms / 响应超时毫秒")
    reply_to: str | None = Field(
        default=None,
        description="Where to send the response / 响应发送目标",
    )


# =============================================================================
# Message Body / 消息体
# =============================================================================


class MessageBody(BaseModel):
    """The payload of an AURC message. AURC 消息载荷

    The structure varies by message type:
    - request: { method, skill, params, capabilities_required }
    - response: { result, error, metadata }
    - notification: { event, data }
    - stream: { chunk_index, total_chunks, data, is_final }
    - delegation: { task_id, skill, context, lifecycle }
    """

    # For requests / delegations / 请求和委派
    method: str | None = Field(default=None, description="Method name: 'invoke', 'query', etc.")
    skill: str | None = Field(default=None, description="Target skill ID / 目标技能 ID")
    params: dict[str, Any] = Field(default_factory=dict, description="Method parameters / 方法参数")

    # For responses / 响应
    result: Any = Field(default=None, description="Result data / 结果数据")
    error: ErrorInfo | None = Field(default=None, description="Error details if failed / 错误详情")

    # For notifications / 通知
    event: str | None = Field(default=None, description="Event type / 事件类型")

    # For streaming / 流式
    chunk_index: int | None = Field(default=None, description="Current chunk index / 当前块索引")
    total_chunks: int | None = Field(default=None, description="Total number of chunks / 总块数")
    data: Any = Field(default=None, description="Chunk data / 块数据")
    is_final: bool = Field(default=False, description="Whether this is the final chunk / 是否为最后一块")

    # Capability requirements / 能力需求
    capabilities_required: list[str] = Field(
        default_factory=list,
        description="External capabilities needed / 需要的外部能力",
    )

    # Metadata / 元数据
    metadata: dict[str, Any] = Field(default_factory=dict)


class ErrorInfo(BaseModel):
    """Structured error information. 结构化错误信息"""

    code: str = Field(description="Error code, e.g. 'tool_not_found'")
    message: str = Field(description="Human-readable error message / 人类可读错误消息")
    details: dict[str, Any] = Field(default_factory=dict, description="Error details / 错误详情")
    recoverable: bool = Field(default=True, description="Whether the error is recoverable / 是否可恢复")
    suggested_recovery: str | None = Field(
        default=None,
        description="Suggested recovery action / 建议的恢复动作",
    )


# Resolve forward reference
MessageBody.model_rebuild()


# =============================================================================
# AURC Message / AURC 消息
# =============================================================================


class AURCMessage(BaseModel):
    """The canonical AURC message — the universal currency of agent communication.
    AURC 标准消息 — Agent 通信的通用货币

    Design rationale / 设计理由:
        - Every message, regardless of origin protocol, is normalized to this format
        - Bridges translate external protocol messages to/from AURCMessage
        - Rich metadata enables cross-protocol context tracking and security enforcement

    Message lifecycle / 消息生命周期:
        1. Created by source agent (or Bridge from external protocol)
        2. Routed by Message Bus to target agent (or Bridge to external protocol)
        3. Processed by target agent
        4. Response follows the same path back
    """

    # Protocol version / 协议版本
    aurc_version: str = Field(default="0.1", description="AURC protocol version / AURC 协议版本")

    # Identifiers / 标识
    message_id: str = Field(
        default_factory=lambda: f"msg-{uuid.uuid4().hex[:12]}",
        description="Unique message identifier / 消息唯一标识",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Groups related messages across protocol boundaries / 跨协议关联相关消息",
    )
    trace_id: str | None = Field(
        default=None,
        description="Distributed tracing ID / 分布式追踪 ID",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Message creation time (UTC) / 消息创建时间 (UTC)",
    )

    # Source and target / 源和目标
    source: str = Field(description="Source agent AURC ID / 源 Agent AURC ID")
    target: str = Field(description="Target agent AURC ID / 目标 Agent AURC ID")

    # Message type and body / 消息类型和载荷
    type: MessageDirection = Field(description="Message type / 消息类型")
    body: MessageBody = Field(default_factory=MessageBody)

    # Context layers / 上下文层
    protocol_context: BridgeContext = Field(default_factory=BridgeContext)
    session: SessionInfo = Field(default_factory=SessionInfo)
    routing: RoutingInfo = Field(default_factory=RoutingInfo)
    security: MessageSecurity = Field(default_factory=MessageSecurity)

    def create_response(
        self,
        result: Any = None,
        error: ErrorInfo | None = None,
    ) -> AURCMessage:
        """Create a response message for this request.
        为此请求创建响应消息
        """
        return AURCMessage(
            source=self.target,
            target=self.source,
            type=MessageDirection.RESPONSE,
            correlation_id=self.correlation_id or self.message_id,
            body=MessageBody(
                result=result,
                error=error,
                metadata={"in_response_to": self.message_id},
            ),
            session=SessionInfo(
                session_id=self.session.session_id,
                conversation_id=self.session.conversation_id,
                turn=self.session.turn + 1,
                parent_message_id=self.message_id,
            ),
            protocol_context=self.protocol_context,
            security=self.security,
        )

    def create_stream_chunk(
        self,
        data: Any,
        chunk_index: int,
        total_chunks: int | None = None,
        is_final: bool = False,
    ) -> AURCMessage:
        """Create a stream chunk message. 创建流式数据块消息"""
        return AURCMessage(
            source=self.target,
            target=self.source,
            type=MessageDirection.STREAM,
            correlation_id=self.correlation_id or self.message_id,
            body=MessageBody(
                chunk_index=chunk_index,
                total_chunks=total_chunks,
                data=data,
                is_final=is_final,
            ),
            session=SessionInfo(
                session_id=self.session.session_id,
                conversation_id=self.session.conversation_id,
                turn=self.session.turn,
                parent_message_id=self.message_id,
            ),
            protocol_context=self.protocol_context,
        )

    def create_notification(self, event: str, data: Any = None) -> AURCMessage:
        """Create a notification message. 创建通知消息"""
        return AURCMessage(
            source=self.source,
            target=self.target,
            type=MessageDirection.NOTIFICATION,
            body=MessageBody(event=event, data=data),
            session=self.session,
            protocol_context=self.protocol_context,
        )
