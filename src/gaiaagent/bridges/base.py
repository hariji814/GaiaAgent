"""AURC Protocol Bridge — Base interface and MCP Bridge implementation.
AURC 协议桥接 — 基础接口和 MCP Bridge 实现

Bridges are the key interoperability mechanism in AURC.
They translate between AURC's canonical message format and external protocols.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from ..core.message import AURCMessage, BridgeContext, MessageBody
from ..core.types import MessageDirection

logger = logging.getLogger(__name__)


# =============================================================================
# Bridge Interface / 桥接器接口
# =============================================================================


@runtime_checkable
class ProtocolBridge(Protocol):
    """Protocol Bridge interface — the contract all bridges must fulfill.
    协议桥接器接口 — 所有桥接器必须遵循的契约

    A bridge translates between AURC messages and an external protocol.
    Each bridge handles exactly one external protocol (e.g., MCP, A2A).

    Implementation guide / 实现指南:
        1. Implement `source_protocol` property (e.g., "mcp/2025-06-18")
        2. Implement `translate_to_aurc()` — external → AURC
        3. Implement `translate_from_aurc()` — AURC → external
        4. Implement `map_capabilities()` — external capabilities → AURC skills
    """

    @property
    def source_protocol(self) -> str:
        """External protocol identifier, e.g. 'mcp/2025-06-18'"""
        ...

    def can_bridge(self, source_protocol: str, target_protocol: str) -> bool:
        """Check if this bridge handles the given protocol pair."""
        ...

    async def translate_to_aurc(self, external_message: Any) -> AURCMessage:
        """Translate an external protocol message to AURC format.
        将外部协议消息翻译为 AURC 格式
        """
        ...

    async def translate_from_aurc(self, aurc_message: AURCMessage) -> Any:
        """Translate an AURC message to external protocol format.
        将 AURC 消息翻译为外部协议格式
        """
        ...

    async def map_capabilities(
        self, external_capabilities: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Map external protocol capabilities to AURC skill declarations.
        将外部协议能力映射为 AURC 技能声明
        """
        ...


# =============================================================================
# Bridge Registry / 桥接器注册中心
# =============================================================================


class BridgeRegistry:
    """Registry of available protocol bridges.
    可用协议桥接器的注册中心

    Manages bridge lifecycle and provides lookup by protocol.

    Usage / 用法:
        registry = BridgeRegistry()
        registry.register(MCPBridge())
        registry.register(A2ABridge())

        # Find bridge for a protocol / 查找协议对应的桥接器
        bridge = registry.get_bridge("mcp/2025-06-18")
        if bridge:
            aurc_msg = await bridge.translate_to_aurc(mcp_msg)
    """

    def __init__(self) -> None:
        self._bridges: dict[str, ProtocolBridge] = {}

    def register(self, bridge: ProtocolBridge) -> None:
        """Register a protocol bridge. 注册协议桥接器"""
        protocol = bridge.source_protocol
        if protocol in self._bridges:
            logger.warning("Replacing existing bridge for protocol: %s", protocol)
        self._bridges[protocol] = bridge
        logger.info("Bridge registered: %s", protocol)

    def unregister(self, protocol: str) -> None:
        """Unregister a protocol bridge. 注销协议桥接器"""
        if protocol in self._bridges:
            del self._bridges[protocol]

    def get_bridge(self, protocol: str) -> ProtocolBridge | None:
        """Get bridge for a specific protocol. 获取特定协议的桥接器"""
        return self._bridges.get(protocol)

    def find_bridge(self, source: str, target: str) -> ProtocolBridge | None:
        """Find a bridge that can handle the given protocol pair.
        查找能处理指定协议对的桥接器
        """
        for bridge in self._bridges.values():
            if bridge.can_bridge(source, target):
                return bridge
        return None

    def list_protocols(self) -> list[str]:
        """List all registered protocol identifiers."""
        return list(self._bridges.keys())

    @property
    def count(self) -> int:
        return len(self._bridges)


# =============================================================================
# MCP Bridge Implementation / MCP 桥接器实现
# =============================================================================


class MCPBridge:
    """MCP ↔ AURC Bridge.
    MCP ↔ AURC 桥接器

    Translates between MCP (Model Context Protocol) and AURC message format.

    MCP uses JSON-RPC 2.0 with these key methods:
    - tools/call: Invoke a tool (→ AURC request)
    - tools/list: List available tools (→ AURC capability query)
    - resources/read: Read a resource (→ AURC context load)
    - initialize: Server handshake (→ AURC registration)

    Direction mapping / 方向映射:
    MCP Client → AURC:  translate_to_aurc()
    AURC → MCP Server:  translate_from_aurc()
    """

    @property
    def source_protocol(self) -> str:
        return "mcp/2025-06-18"

    def can_bridge(self, source_protocol: str, target_protocol: str) -> bool:
        return (
            source_protocol == self.source_protocol and target_protocol == "aurc/0.1"
        ) or (
            source_protocol == "aurc/0.1" and target_protocol == self.source_protocol
        )

    async def translate_to_aurc(self, mcp_message: dict[str, Any]) -> AURCMessage:
        """Translate an MCP JSON-RPC message to AURC format.
        将 MCP JSON-RPC 消息翻译为 AURC 格式

        Handles:
        - tools/call → AURC request (invoke)
        - tools/list → AURC notification (capability discovery)
        - resources/read → AURC request (context load)
        - initialize → AURC notification (registration)
        """
        method = mcp_message.get("method", "")
        params = mcp_message.get("params", {})
        msg_id = mcp_message.get("id")

        bridge_ctx = BridgeContext(
            origin_protocol="mcp/2025-06-18",
            bridged_from="mcp/2025-06-18",
            bridge_chain=["mcp→aurc"],
        )

        if method == "tools/call":
            # MCP tool invocation → AURC request / MCP 工具调用 → AURC 请求
            return AURCMessage(
                source="mcp:external/client",
                target=params.get("_target_agent", "aurc:local/handler"),
                type=MessageDirection.REQUEST,
                body=MessageBody(
                    method="invoke",
                    skill=params.get("name", ""),
                    params=params.get("arguments", {}),
                ),
                protocol_context=bridge_ctx,
                correlation_id=str(msg_id) if msg_id else None,
            )

        elif method == "tools/list":
            # Tool discovery → AURC capability query / 工具发现 → AURC 能力查询
            return AURCMessage(
                source="mcp:external/client",
                target="aurc:local/registry",
                type=MessageDirection.REQUEST,
                body=MessageBody(method="list_capabilities"),
                protocol_context=bridge_ctx,
                correlation_id=str(msg_id) if msg_id else None,
            )

        elif method == "resources/read":
            # Resource read → AURC context load / 资源读取 → AURC 上下文加载
            return AURCMessage(
                source="mcp:external/client",
                target=params.get("_target_agent", "aurc:local/context"),
                type=MessageDirection.REQUEST,
                body=MessageBody(
                    method="load_context",
                    params={"resource_uri": params.get("uri", "")},
                ),
                protocol_context=bridge_ctx,
                correlation_id=str(msg_id) if msg_id else None,
            )

        elif method == "initialize":
            # Server initialization → AURC registration / 服务器初始化 → AURC 注册
            return AURCMessage(
                source="mcp:external/server",
                target="aurc:local/registry",
                type=MessageDirection.NOTIFICATION,
                body=MessageBody(
                    event="mcp_server_initialized",
                    data={
                        "server_info": params.get("serverInfo", {}),
                        "capabilities": params.get("capabilities", {}),
                    },
                ),
                protocol_context=bridge_ctx,
            )

        else:
            # Generic MCP method → AURC request / 通用 MCP 方法 → AURC 请求
            return AURCMessage(
                source="mcp:external/client",
                target="aurc:local/handler",
                type=MessageDirection.REQUEST,
                body=MessageBody(
                    method=method,
                    params=params,
                ),
                protocol_context=bridge_ctx,
                correlation_id=str(msg_id) if msg_id else None,
            )

    async def translate_from_aurc(self, aurc_message: AURCMessage) -> dict[str, Any]:
        """Translate an AURC message to MCP JSON-RPC format.
        将 AURC 消息翻译为 MCP JSON-RPC 格式

        Handles:
        - AURC request (invoke) → MCP tools/call
        - AURC response → MCP JSON-RPC response
        - AURC notification → MCP notification
        """
        if aurc_message.type == MessageDirection.REQUEST:
            body = aurc_message.body
            if body.method == "invoke":
                # AURC invoke → MCP tools/call / AURC 调用 → MCP 工具调用
                return {
                    "jsonrpc": "2.0",
                    "id": aurc_message.correlation_id or aurc_message.message_id,
                    "method": "tools/call",
                    "params": {
                        "name": body.skill or "",
                        "arguments": body.params,
                    },
                }
            elif body.method == "load_context":
                # AURC context load → MCP resources/read / AURC 上下文加载 → MCP 资源读取
                return {
                    "jsonrpc": "2.0",
                    "id": aurc_message.correlation_id or aurc_message.message_id,
                    "method": "resources/read",
                    "params": {
                        "uri": body.params.get("resource_uri", ""),
                    },
                }
            elif body.method == "list_capabilities":
                # AURC capability query → MCP tools/list / AURC 能力查询 → MCP 工具列表
                return {
                    "jsonrpc": "2.0",
                    "id": aurc_message.correlation_id or aurc_message.message_id,
                    "method": "tools/list",
                    "params": {},
                }
            else:
                # Generic AURC request → MCP custom method / 通用请求 → MCP 自定义方法
                return {
                    "jsonrpc": "2.0",
                    "id": aurc_message.correlation_id or aurc_message.message_id,
                    "method": body.method or "unknown",
                    "params": body.params,
                }

        elif aurc_message.type == MessageDirection.RESPONSE:
            body = aurc_message.body
            if body.error:
                # Error response / 错误响应
                return {
                    "jsonrpc": "2.0",
                    "id": aurc_message.correlation_id,
                    "error": {
                        "code": -32000,
                        "message": body.error.message,
                        "data": body.error.details,
                    },
                }
            else:
                # Success response / 成功响应
                return {
                    "jsonrpc": "2.0",
                    "id": aurc_message.correlation_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": str(body.result)}
                        ],
                    },
                }

        elif aurc_message.type == MessageDirection.NOTIFICATION:
            return {
                "jsonrpc": "2.0",
                "method": f"notifications/{aurc_message.body.event}",
                "params": {"data": aurc_message.body.data} if aurc_message.body.data else {},
            }

        elif aurc_message.type == MessageDirection.STREAM:
            # MCP streaming → SSE events / MCP 流式 → SSE 事件
            return {
                "jsonrpc": "2.0",
                "method": "notifications/stream",
                "params": {
                    "chunk_index": aurc_message.body.chunk_index,
                    "data": aurc_message.body.data,
                    "is_final": aurc_message.body.is_final,
                },
            }

        # Fallback / 兜底
        return {
            "jsonrpc": "2.0",
            "method": "unknown",
            "params": {"aurc_message": aurc_message.model_dump()},
        }

    async def map_capabilities(self, mcp_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Map MCP tool declarations to AURC skill declarations.
        将 MCP 工具声明映射为 AURC 技能声明

        MCP tools have: name, description, inputSchema
        AURC skills need: skill_id, name, description, input_schema, output_schema
        """
        skills = []
        for tool in mcp_tools:
            skills.append({
                "skill_id": f"mcp:{tool.get('name', '')}",
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "input_schema": tool.get("inputSchema", {}),
                "output_schema": {"type": "object"},  # MCP doesn't declare output schema
                "tags": ["mcp-bridge"],
            })
        return skills
