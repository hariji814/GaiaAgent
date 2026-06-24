"""Tests for AURC Protocol Bridges — MCP and A2A translation."""

import pytest

from gaiaagent.bridges.base import MCPBridge, BridgeRegistry
from gaiaagent.bridges.a2a import A2ABridge
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection


class TestMCPBridge:
    """Tests for MCP ↔ AURC message translation."""

    @pytest.fixture
    def bridge(self):
        return MCPBridge()

    @pytest.mark.asyncio
    async def test_translate_tool_call_to_aurc(self, bridge):
        mcp_msg = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "tools/call",
            "params": {
                "name": "web-search",
                "arguments": {"query": "AI protocols"},
            },
        }
        aurc_msg = await bridge.translate_to_aurc(mcp_msg)
        assert aurc_msg.type == MessageDirection.REQUEST
        assert aurc_msg.body.method == "invoke"
        assert aurc_msg.body.skill == "web-search"
        assert aurc_msg.body.params["query"] == "AI protocols"
        assert aurc_msg.protocol_context.origin_protocol == "mcp/2025-06-18"
        assert aurc_msg.protocol_context.is_bridged

    @pytest.mark.asyncio
    async def test_translate_tools_list_to_aurc(self, bridge):
        mcp_msg = {
            "jsonrpc": "2.0",
            "id": "req-2",
            "method": "tools/list",
            "params": {},
        }
        aurc_msg = await bridge.translate_to_aurc(mcp_msg)
        assert aurc_msg.body.method == "list_capabilities"

    @pytest.mark.asyncio
    async def test_translate_initialize_to_aurc(self, bridge):
        mcp_msg = {
            "jsonrpc": "2.0",
            "id": "init-1",
            "method": "initialize",
            "params": {
                "serverInfo": {"name": "test-server", "version": "1.0"},
                "capabilities": {"tools": {}},
            },
        }
        aurc_msg = await bridge.translate_to_aurc(mcp_msg)
        assert aurc_msg.type == MessageDirection.NOTIFICATION
        assert aurc_msg.body.event == "mcp_server_initialized"

    @pytest.mark.asyncio
    async def test_translate_from_aurc_invoke(self, bridge):
        aurc_msg = AURCMessage(
            source="aurc:gaia/orchestrator:v1.0",
            target="aurc:mcp/web-search:v1.0",
            type=MessageDirection.REQUEST,
            body=MessageBody(
                method="invoke",
                skill="web-search",
                params={"query": "test"},
            ),
            correlation_id="corr-123",
        )
        mcp_msg = await bridge.translate_from_aurc(aurc_msg)
        assert mcp_msg["jsonrpc"] == "2.0"
        assert mcp_msg["method"] == "tools/call"
        assert mcp_msg["params"]["name"] == "web-search"
        assert mcp_msg["params"]["arguments"]["query"] == "test"
        assert mcp_msg["id"] == "corr-123"

    @pytest.mark.asyncio
    async def test_translate_from_aurc_error_response(self, bridge):
        from gaiaagent.core.message import ErrorInfo

        aurc_msg = AURCMessage(
            source="aurc:mcp/web-search:v1.0",
            target="aurc:gaia/orchestrator:v1.0",
            type=MessageDirection.RESPONSE,
            body=MessageBody(
                error=ErrorInfo(code="timeout", message="Search timed out"),
            ),
            correlation_id="corr-456",
        )
        mcp_msg = await bridge.translate_from_aurc(aurc_msg)
        assert "error" in mcp_msg
        assert mcp_msg["error"]["message"] == "Search timed out"

    @pytest.mark.asyncio
    async def test_map_capabilities(self, bridge):
        mcp_tools = [
            {
                "name": "web-search",
                "description": "Search the web",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            },
            {
                "name": "file-reader",
                "description": "Read files",
                "inputSchema": {"type": "object"},
            },
        ]
        skills = await bridge.map_capabilities(mcp_tools)
        assert len(skills) == 2
        assert skills[0]["skill_id"] == "mcp:web-search"
        assert skills[0]["name"] == "web-search"
        assert "mcp-bridge" in skills[0]["tags"]


class TestA2ABridge:
    """Tests for A2A ↔ AURC message translation."""

    @pytest.fixture
    def bridge(self):
        return A2ABridge()

    @pytest.mark.asyncio
    async def test_translate_task_send_to_aurc(self, bridge):
        a2a_msg = {
            "jsonrpc": "2.0",
            "id": "a2a-req-1",
            "method": "tasks/send",
            "params": {
                "id": "task-001",
                "sessionId": "session-abc",
                "messages": [
                    {
                        "role": "user",
                        "parts": [{"type": "text", "text": "Research AI protocols"}],
                    }
                ],
            },
        }
        aurc_msg = await bridge.translate_to_aurc(a2a_msg)
        assert aurc_msg.type == MessageDirection.DELEGATION
        assert aurc_msg.body.skill == "research"  # Inferred from content
        assert aurc_msg.body.params["task_id"] == "task-001"
        assert aurc_msg.protocol_context.origin_protocol == "a2a/1.0"

    @pytest.mark.asyncio
    async def test_translate_task_get_to_aurc(self, bridge):
        a2a_msg = {
            "jsonrpc": "2.0",
            "id": "a2a-req-2",
            "method": "tasks/get",
            "params": {"id": "task-001"},
        }
        aurc_msg = await bridge.translate_to_aurc(a2a_msg)
        assert aurc_msg.type == MessageDirection.REQUEST
        assert aurc_msg.body.method == "query_task_status"

    @pytest.mark.asyncio
    async def test_translate_from_aurc_delegation(self, bridge):
        aurc_msg = AURCMessage(
            source="aurc:gaia/orchestrator:v1.0",
            target="aurc:a2a/external-agent:v1.0",
            type=MessageDirection.DELEGATION,
            body=MessageBody(
                method="invoke",
                skill="research",
                params={
                    "task_id": "task-999",
                    "session_id": "session-xyz",
                    "content": "Analyze quantum computing trends",
                },
            ),
            correlation_id="corr-789",
        )
        a2a_msg = await bridge.translate_from_aurc(aurc_msg)
        assert a2a_msg["method"] == "tasks/send"
        assert a2a_msg["params"]["id"] == "task-999"
        assert len(a2a_msg["params"]["messages"]) == 1

    @pytest.mark.asyncio
    async def test_translate_from_aurc_completed_response(self, bridge):
        aurc_msg = AURCMessage(
            source="aurc:a2a/agent:v1.0",
            target="aurc:gaia/orchestrator:v1.0",
            type=MessageDirection.RESPONSE,
            body=MessageBody(
                result="Quantum computing analysis complete.",
                metadata={"task_id": "task-999"},
            ),
            correlation_id="corr-789",
        )
        a2a_msg = await bridge.translate_from_aurc(aurc_msg)
        assert a2a_msg["result"]["status"]["state"] == "completed"

    @pytest.mark.asyncio
    async def test_map_agent_card(self, bridge):
        agent_card = {
            "name": "External Research Agent",
            "description": "An external A2A research agent",
            "skills": [
                {"id": "research", "name": "Research", "description": "Deep research"},
            ],
            "authentication": {"schemes": ["oauth2"]},
        }
        descriptor_dict = bridge.map_agent_card(agent_card)
        assert "research" in descriptor_dict["capabilities"]["provides"][0]["skill_id"]
        assert descriptor_dict["protocols"]["bridges"] == ["a2a/1.0"]


class TestBridgeRegistry:
    """Tests for the bridge registry."""

    def test_register_and_lookup(self):
        registry = BridgeRegistry()
        mcp = MCPBridge()
        a2a = A2ABridge()

        registry.register(mcp)
        registry.register(a2a)

        assert registry.count == 2
        assert registry.get_bridge("mcp/2025-06-18") is mcp
        assert registry.get_bridge("a2a/1.0") is a2a
        assert registry.get_bridge("unknown/1.0") is None

    def test_list_protocols(self):
        registry = BridgeRegistry()
        registry.register(MCPBridge())
        registry.register(A2ABridge())
        protocols = registry.list_protocols()
        assert "mcp/2025-06-18" in protocols
        assert "a2a/1.0" in protocols

    def test_find_bridge(self):
        registry = BridgeRegistry()
        registry.register(MCPBridge())
        bridge = registry.find_bridge("mcp/2025-06-18", "aurc/0.1")
        assert bridge is not None
        assert bridge.source_protocol == "mcp/2025-06-18"
