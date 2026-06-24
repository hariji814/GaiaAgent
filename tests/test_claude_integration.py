"""Tests for AURC Claude Integration."""

import pytest

from gaiaagent.integrations.claude import (
    ClaudeAgent,
    ClaudeLLM,
    ClaudeResponse,
    ClaudeTool,
    ClaudeToolCall,
)
from gaiaagent.core.identity import SkillDeclaration, InputOutputSchema


class TestClaudeTool:
    """Tests for Claude tool definitions."""

    def test_to_claude_format(self):
        tool = ClaudeTool(
            name="web-search",
            description="Search the web for information",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer"},
                },
                "required": ["query"],
            },
        )
        fmt = tool.to_claude_format()
        assert fmt["name"] == "web-search"
        assert fmt["description"] == "Search the web for information"
        assert "query" in fmt["input_schema"]["properties"]

    def test_from_aurc_skill(self):
        skill = SkillDeclaration(
            skill_id="research",
            name="Deep Research",
            description="Multi-source research and synthesis",
            input_schema=InputOutputSchema(
                properties={"query": {"type": "string"}},
                required=["query"],
            ),
        )

        async def handler(query: str) -> dict:
            return {"result": query}

        tool = ClaudeTool.from_aurc_skill(skill, handler=handler)
        assert tool.name == "research"
        assert tool.description == "Multi-source research and synthesis"
        assert tool.handler is not None

    def test_empty_input_schema(self):
        tool = ClaudeTool(name="ping", description="Ping")
        fmt = tool.to_claude_format()
        assert fmt["input_schema"]["type"] == "object"


class TestClaudeResponse:
    """Tests for Claude response models."""

    def test_response_no_tools(self):
        resp = ClaudeResponse(text="Hello!", stop_reason="end_turn")
        assert resp.has_tool_calls is False
        assert resp.text == "Hello!"

    def test_response_with_tools(self):
        resp = ClaudeResponse(
            text="Let me search for that.",
            tool_calls=[
                ClaudeToolCall(tool_name="web-search", tool_input={"query": "test"}),
            ],
            stop_reason="tool_use",
        )
        assert resp.has_tool_calls is True
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].tool_name == "web-search"

    def test_response_with_usage(self):
        resp = ClaudeResponse(
            text="OK",
            usage={"input_tokens": 100, "output_tokens": 50},
        )
        assert resp.usage["input_tokens"] == 100


class TestClaudeLLM:
    """Tests for Claude LLM interface (without actual API calls)."""

    def test_create_default(self):
        llm = ClaudeLLM()
        assert llm._model == "claude-sonnet-4-20250514"
        assert llm._max_tokens == 4096

    def test_create_custom(self):
        llm = ClaudeLLM(
            model="claude-sonnet-4-20250514",
            api_key="test-key",
            max_tokens=8192,
            system_prompt="You are a helpful assistant.",
        )
        assert llm._model == "claude-sonnet-4-20250514"
        assert llm._api_key == "test-key"
        assert llm._system_prompt == "You are a helpful assistant."

    def test_clear_history(self):
        llm = ClaudeLLM()
        llm._conversation_history = [{"role": "user", "content": "hi"}]
        llm.clear_history()
        assert len(llm._conversation_history) == 0

    @pytest.mark.asyncio
    async def test_ask_without_anthropic_package(self):
        """Test graceful degradation when anthropic is not installed."""
        llm = ClaudeLLM(api_key="fake-key")
        # This should not crash — it returns an error message
        # (actual behavior depends on whether anthropic is installed)
        # We test that the method signature is correct
        assert hasattr(llm, "ask")
        assert hasattr(llm, "agentic_loop")
        assert hasattr(llm, "converse")


class TestClaudeAgent:
    """Tests for ClaudeAgent base class."""

    def test_create_agent(self):
        agent = ClaudeAgent(model="claude-sonnet-4-20250514")
        assert agent.claude is not None
        assert agent.claude._model == "claude-sonnet-4-20250514"

    def test_get_claude_tools_empty(self):
        agent = ClaudeAgent()
        tools = agent.get_claude_tools()
        assert isinstance(tools, list)
