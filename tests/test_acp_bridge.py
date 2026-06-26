"""Tests for ACP Bridge — Agent Communication Protocol translation.
ACP 桥接器测试 — Agent 通信协议转换
"""

import pytest

from gaiaagent.bridges.a2a import A2ABridge
from gaiaagent.bridges.acp import ACPBridge
from gaiaagent.bridges.base import BridgeRegistry, MCPBridge
from gaiaagent.core.message import AURCMessage, ErrorInfo, MessageBody
from gaiaagent.core.types import MessageDirection


class TestACPBridge:
    """Tests for ACP ↔ AURC message translation."""

    @pytest.fixture
    def bridge(self):
        return ACPBridge()

    def test_source_protocol(self, bridge):
        """ACP bridge should identify as acp/1.0"""
        assert bridge.source_protocol == "acp/1.0"

    def test_can_bridge(self, bridge):
        """ACP bridge should handle acp↔aurc protocol pairs"""
        assert bridge.can_bridge("acp/1.0", "aurc/0.1") is True
        assert bridge.can_bridge("aurc/0.1", "acp/1.0") is True
        assert bridge.can_bridge("mcp/2025-06-18", "aurc/0.1") is False
        assert bridge.can_bridge("acp/1.0", "mcp/2025-06-18") is False

    @pytest.mark.asyncio
    async def test_translate_invoke_to_aurc(self, bridge):
        """ACP invoke → AURC delegation"""
        acp_msg = {
            "method": "invoke",
            "params": {
                "agent_id": "acp:research-agent",
                "task": "Analyze AI protocols",
                "input": {"depth": "deep", "sources": ["arxiv"]},
                "session_id": "sess-001",
            },
            "id": "acp-req-1",
        }
        aurc_msg = await bridge.translate_to_aurc(acp_msg)
        assert aurc_msg.type == MessageDirection.DELEGATION
        assert aurc_msg.body.method == "invoke"
        assert aurc_msg.protocol_context.origin_protocol == "acp/1.0"
        assert aurc_msg.protocol_context.is_bridged
        assert "acp" in aurc_msg.protocol_context.bridge_chain[0]

    @pytest.mark.asyncio
    async def test_translate_cancel_to_aurc(self, bridge):
        """ACP cancel → AURC notification"""
        acp_msg = {
            "method": "cancel",
            "params": {"task_id": "task-123"},
            "id": "acp-req-2",
        }
        aurc_msg = await bridge.translate_to_aurc(acp_msg)
        assert aurc_msg.type == MessageDirection.NOTIFICATION
        assert aurc_msg.body.event == "task_cancelled"

    @pytest.mark.asyncio
    async def test_translate_get_task_to_aurc(self, bridge):
        """ACP get-task → AURC request (status query)"""
        acp_msg = {
            "method": "get-task",
            "params": {"task_id": "task-456"},
            "id": "acp-req-3",
        }
        aurc_msg = await bridge.translate_to_aurc(acp_msg)
        assert aurc_msg.type == MessageDirection.REQUEST
        assert "task_id" in aurc_msg.body.params

    @pytest.mark.asyncio
    async def test_translate_from_aurc_delegation(self, bridge):
        """AURC delegation → ACP invoke"""
        aurc_msg = AURCMessage(
            source="aurc:gaia/orchestrator:v1.0",
            target="aurc:acp/external-agent:v1.0",
            type=MessageDirection.DELEGATION,
            body=MessageBody(
                method="invoke",
                skill="research",
                params={
                    "task_id": "task-789",
                    "session_id": "sess-abc",
                    "content": "Research quantum computing",
                },
            ),
            correlation_id="corr-acp-1",
        )
        acp_msg = await bridge.translate_from_aurc(aurc_msg)
        assert acp_msg["method"] == "invoke"
        assert "params" in acp_msg

    @pytest.mark.asyncio
    async def test_translate_from_aurc_response_completed(self, bridge):
        """AURC success response → ACP completed result"""
        aurc_msg = AURCMessage(
            source="aurc:acp/agent:v1.0",
            target="aurc:gaia/orchestrator:v1.0",
            type=MessageDirection.RESPONSE,
            body=MessageBody(
                result="Analysis complete",
                metadata={"task_id": "task-789"},
            ),
            correlation_id="corr-acp-2",
        )
        acp_msg = await bridge.translate_from_aurc(aurc_msg)
        assert "result" in acp_msg or "status" in str(acp_msg)

    @pytest.mark.asyncio
    async def test_translate_from_aurc_response_failed(self, bridge):
        """AURC error response → ACP failed result"""
        aurc_msg = AURCMessage(
            source="aurc:acp/agent:v1.0",
            target="aurc:gaia/orchestrator:v1.0",
            type=MessageDirection.RESPONSE,
            body=MessageBody(
                error=ErrorInfo(code="internal_error", message="Processing failed"),
                metadata={"task_id": "task-789"},
            ),
            correlation_id="corr-acp-3",
        )
        acp_msg = await bridge.translate_from_aurc(aurc_msg)
        # Should indicate failure in ACP format
        acp_str = str(acp_msg)
        assert "failed" in acp_str.lower() or "error" in acp_str.lower()

    @pytest.mark.asyncio
    async def test_translate_from_aurc_stream(self, bridge):
        """AURC stream chunk → ACP streaming update"""
        aurc_msg = AURCMessage(
            source="aurc:acp/agent:v1.0",
            target="aurc:gaia/orchestrator:v1.0",
            type=MessageDirection.STREAM,
            body=MessageBody(
                data="Partial results...",
                chunk_index=0,
                is_final=False,
            ),
        )
        acp_msg = await bridge.translate_from_aurc(aurc_msg)
        assert acp_msg is not None

    @pytest.mark.asyncio
    async def test_translate_from_aurc_notification(self, bridge):
        """AURC notification → ACP notification"""
        aurc_msg = AURCMessage(
            source="aurc:acp/agent:v1.0",
            target="aurc:gaia/orchestrator:v1.0",
            type=MessageDirection.NOTIFICATION,
            body=MessageBody(
                event="task_completed",
                data={"task_id": "task-789"},
            ),
        )
        acp_msg = await bridge.translate_from_aurc(aurc_msg)
        assert acp_msg is not None

    @pytest.mark.asyncio
    async def test_map_capabilities(self, bridge):
        """ACP agent skills → AURC skill declarations"""
        acp_skills = [
            {
                "name": "research",
                "description": "Deep research capability",
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
            },
            {
                "name": "summarize",
                "description": "Text summarization",
                "input_schema": {"type": "object"},
            },
        ]
        skills = await bridge.map_capabilities(acp_skills)
        assert len(skills) == 2
        assert "acp" in skills[0]["skill_id"]
        assert skills[0]["name"] == "research"
        assert "acp-bridge" in skills[0]["tags"]

    @pytest.mark.asyncio
    async def test_map_agent_card(self, bridge):
        """ACP agent descriptor → AURC AgentDescriptor dict"""
        acp_card = {
            "name": "External ACP Agent",
            "description": "An ACP-compatible research agent",
            "skills": [
                {"id": "research", "name": "Research", "description": "Deep research"},
            ],
        }
        descriptor_dict = bridge.map_agent_card(acp_card)
        assert "acp" in descriptor_dict["aurc_id"].lower() or "aurc:" in descriptor_dict["aurc_id"]
        assert descriptor_dict["display_name"] == "External ACP Agent"
        assert "acp/1.0" in descriptor_dict["protocols"]["bridges"]


class TestBridgeRegistryWithACP:
    """Tests for bridge registry with all 3 bridges."""

    def test_register_all_three_bridges(self):
        """All 3 protocol bridges should coexist in the registry."""
        registry = BridgeRegistry()
        registry.register(MCPBridge())
        registry.register(A2ABridge())
        registry.register(ACPBridge())

        assert registry.count == 3
        assert registry.get_bridge("mcp/2025-06-18") is not None
        assert registry.get_bridge("a2a/1.0") is not None
        assert registry.get_bridge("acp/1.0") is not None

    def test_list_all_protocols(self):
        registry = BridgeRegistry()
        registry.register(MCPBridge())
        registry.register(A2ABridge())
        registry.register(ACPBridge())
        protocols = registry.list_protocols()
        assert len(protocols) == 3
        assert "acp/1.0" in protocols

    def test_find_acp_bridge(self):
        registry = BridgeRegistry()
        registry.register(ACPBridge())
        bridge = registry.find_bridge("acp/1.0", "aurc/0.1")
        assert bridge is not None
        assert bridge.source_protocol == "acp/1.0"
