"""AURC Claude Integration — use Claude as the reasoning engine for AURC agents.
AURC Claude 集成 — 将 Claude 用作 AURC Agent 的推理引擎

This module bridges the AURC runtime harness with Anthropic's Claude,
enabling AURC agents to use Claude for:
    - Natural language understanding and generation
    - Dynamic tool selection and routing
    - Multi-step reasoning and planning
    - Evaluator-optimizer patterns

Integration Architecture / 集成架构:

    ┌──────────────────────────────────────────────┐
    │  AURC Runtime Harness (lifecycle, security)  │
    │  ┌────────────────────────────────────────┐  │
    │  │  AURC Agent                            │  │
    │  │  ┌──────────────┐  ┌────────────────┐  │  │
    │  │  │ @skill       │  │ ClaudeLLM      │  │  │
    │  │  │ (your code)  │←→│ (Claude query) │  │  │
    │  │  └──────────────┘  └───────┬────────┘  │  │
    │  └────────────────────────────┼───────────┘  │
    │                               │               │
    │  ┌────────────────────────────▼───────────┐  │
    │  │  Claude Agent SDK / Anthropic API      │  │
    │  └────────────────────────────────────────┘  │
    └──────────────────────────────────────────────┘

Usage / 用法:

    from gaiaagent.integrations.claude import ClaudeLLM, ClaudeAgent

    # Simple: use Claude as a reasoning engine / 简单：用 Claude 做推理引擎
    llm = ClaudeLLM(model="claude-sonnet-4-20250514")

    @aurc_agent(id="aurc:myproject/smart-agent:v1.0")
    class SmartAgent(ClaudeAgent):
        @skill("answer-question")
        async def answer(self, question: str) -> dict:
            response = await self.claude.ask(
                prompt=question,
                tools=self.available_tools,
            )
            return {"answer": response}
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


# =============================================================================
# Claude Tool Definition / Claude 工具定义
# =============================================================================


@dataclass
class ClaudeTool:
    """A tool definition compatible with Claude's tool use API.
    兼容 Claude tool use API 的工具定义

    Maps between AURC skills and Claude tools, enabling Claude
    to invoke AURC agent skills during its reasoning process.

    Claude Tool Use format / Claude 工具使用格式:
    {
        "name": "tool_name",
        "description": "What the tool does",
        "input_schema": {
            "type": "object",
            "properties": { ... },
            "required": [...]
        }
    }
    """

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    handler: Callable[..., Awaitable[Any]] | None = None

    def to_claude_format(self) -> dict[str, Any]:
        """Convert to Claude API tool definition format.
        转换为 Claude API 工具定义格式
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema or {
                "type": "object",
                "properties": {},
            },
        }

    @classmethod
    def from_aurc_skill(cls, skill_declaration: Any, handler: Callable | None = None) -> ClaudeTool:
        """Create a ClaudeTool from an AURC SkillDeclaration.
        从 AURC SkillDeclaration 创建 ClaudeTool
        """
        input_schema = {
            "type": "object",
            "properties": skill_declaration.input_schema.properties,
            "required": skill_declaration.input_schema.required,
        }
        return cls(
            name=skill_declaration.skill_id,
            description=skill_declaration.description or skill_declaration.name,
            input_schema=input_schema,
            handler=handler,
        )


# =============================================================================
# Claude Response Models / Claude 响应模型
# =============================================================================


@dataclass
class ClaudeResponse:
    """Structured response from a Claude query. Claude 查询的结构化响应"""

    text: str = ""
    tool_calls: list[ClaudeToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: dict[str, int] = field(default_factory=dict)
    raw_response: dict[str, Any] = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


@dataclass
class ClaudeToolCall:
    """A tool call made by Claude during reasoning. Claude 推理过程中的工具调用"""

    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str = ""


# =============================================================================
# Claude LLM Interface / Claude LLM 接口
# =============================================================================


class ClaudeLLM:
    """Claude as a reasoning engine for AURC agents.
    作为 AURC Agent 推理引擎的 Claude

    Provides a high-level interface to Claude's capabilities:
    - Single-turn queries / 单轮查询
    - Multi-turn conversations with tool use / 带工具使用的多轮对话
    - Dynamic tool selection / 动态工具选择
    - Streaming responses / 流式响应

    Usage / 用法:
        llm = ClaudeLLM(model="claude-sonnet-4-20250514")

        # Simple query / 简单查询
        response = await llm.ask("What is the AURC protocol?")

        # Query with tools / 带工具的查询
        response = await llm.ask(
            prompt="Search for recent papers on AI agents",
            tools=[
                ClaudeTool(
                    name="web-search",
                    description="Search the web",
                    input_schema={...},
                    handler=search_function,
                ),
            ],
        )

        # Multi-turn with agentic loop / 多轮 Agentic 循环
        response = await llm.agentic_loop(
            prompt="Research and summarize AI agent protocols",
            tools=[...],
            max_turns=10,
        )
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._max_tokens = max_tokens
        self._system_prompt = system_prompt
        self._conversation_history: list[dict] = []

    async def ask(
        self,
        prompt: str,
        tools: list[ClaudeTool] | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> ClaudeResponse:
        """Send a single query to Claude.
        向 Claude 发送单次查询

        Args:
            prompt: The user message / 用户消息
            tools: Available tools Claude can use / Claude 可用的工具
            system: System prompt override / 系统提示词覆盖
            max_tokens: Max response tokens / 最大响应 token 数

        Returns:
            ClaudeResponse with text and/or tool calls
        """
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=self._api_key)

            messages = [{"role": "user", "content": prompt}]
            kwargs: dict[str, Any] = {
                "model": self._model,
                "max_tokens": max_tokens or self._max_tokens,
                "messages": messages,
            }

            if system or self._system_prompt:
                kwargs["system"] = system or self._system_prompt

            if tools:
                kwargs["tools"] = [t.to_claude_format() for t in tools]

            response = await client.messages.create(**kwargs)

            return self._parse_response(response)

        except ImportError:
            logger.warning(
                "anthropic package not installed. "
                "Install with: pip install anthropic"
            )
            return ClaudeResponse(
                text="[Claude not available: anthropic package not installed]",
                stop_reason="error",
            )
        except Exception as e:
            logger.error("Claude API error: %s", e)
            return ClaudeResponse(
                text=f"[Claude error: {e}]",
                stop_reason="error",
            )

    async def agentic_loop(
        self,
        prompt: str,
        tools: list[ClaudeTool] | None = None,
        max_turns: int = 10,
        system: str | None = None,
    ) -> ClaudeResponse:
        """Run an agentic loop — Claude calls tools until done.
        运行 Agentic 循环 — Claude 调用工具直到完成

        This implements the core "agent" pattern: Claude decides which
        tools to call, executes them, and continues reasoning with results.

        Args:
            prompt: Initial user message / 初始用户消息
            tools: Available tools with handlers / 带处理函数的可用工具
            max_turns: Maximum tool-use turns / 最大工具使用轮次
            system: System prompt / 系统提示词

        Returns:
            Final ClaudeResponse after all tool calls complete
        """
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=self._api_key)

            messages: list[dict] = [{"role": "user", "content": prompt}]
            tool_map = {t.name: t for t in (tools or [])}

            kwargs: dict[str, Any] = {
                "model": self._model,
                "max_tokens": self._max_tokens,
                "messages": messages,
            }
            if system or self._system_prompt:
                kwargs["system"] = system or self._system_prompt
            if tools:
                kwargs["tools"] = [t.to_claude_format() for t in tools]

            last_response = None

            for turn in range(max_turns):
                response = await client.messages.create(**kwargs)
                last_response = response

                # If Claude stopped (no more tool calls), we're done / 如果 Claude 停止了
                if response.stop_reason == "end_turn":
                    return self._parse_response(response)

                # Process tool calls / 处理工具调用
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool = tool_map.get(block.name)
                        if tool and tool.handler:
                            logger.info("Claude calling tool: %s(%s)", block.name, block.input)
                            try:
                                result = await tool.handler(**block.input)
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": str(result),
                                })
                            except Exception as e:
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": f"Error: {e}",
                                    "is_error": True,
                                })
                        else:
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": f"Tool '{block.name}' not found or no handler",
                                "is_error": True,
                            })

                # Add assistant response and tool results to conversation
                # 将助手响应和工具结果添加到对话
                messages.append({
                    "role": "assistant",
                    "content": [b.model_dump() for b in response.content],
                })
                messages.append({
                    "role": "user",
                    "content": tool_results,
                })
                kwargs["messages"] = messages

            # Max turns reached / 达到最大轮次
            if last_response:
                return self._parse_response(last_response)
            return ClaudeResponse(text="[Max turns reached]", stop_reason="max_turns")

        except ImportError:
            return ClaudeResponse(
                text="[Claude not available: anthropic package not installed]",
                stop_reason="error",
            )

    async def converse(
        self,
        message: str,
        tools: list[ClaudeTool] | None = None,
        system: str | None = None,
    ) -> ClaudeResponse:
        """Multi-turn conversation with history tracking.
        带历史追踪的多轮对话

        Maintains conversation state across calls.
        """
        self._conversation_history.append({"role": "user", "content": message})

        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=self._api_key)

            kwargs: dict[str, Any] = {
                "model": self._model,
                "max_tokens": self._max_tokens,
                "messages": self._conversation_history,
            }
            if system or self._system_prompt:
                kwargs["system"] = system or self._system_prompt
            if tools:
                kwargs["tools"] = [t.to_claude_format() for t in tools]

            response = await client.messages.create(**kwargs)
            parsed = self._parse_response(response)

            # Store assistant response in history / 存储助手响应到历史
            self._conversation_history.append({
                "role": "assistant",
                "content": parsed.text,
            })

            return parsed

        except ImportError:
            return ClaudeResponse(
                text="[Claude not available]",
                stop_reason="error",
            )

    def clear_history(self) -> None:
        """Clear conversation history. 清除对话历史"""
        self._conversation_history.clear()

    @staticmethod
    def _parse_response(response: Any) -> ClaudeResponse:
        """Parse an Anthropic API response into ClaudeResponse."""
        text_parts = []
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ClaudeToolCall(
                    tool_name=block.name,
                    tool_input=block.input,
                    tool_use_id=block.id,
                ))

        return ClaudeResponse(
            text="\n".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )


# =============================================================================
# Claude Agent Base Class / Claude Agent 基类
# =============================================================================


class ClaudeAgent:
    """Base class for AURC agents powered by Claude.
    由 Claude 驱动的 AURC Agent 基类

    Inherit from this class and use `self.claude` to access Claude's
    reasoning capabilities within your @skill methods.

    Usage / 用法:
        @aurc_agent(id="aurc:myproject/smart-agent:v1.0")
        class SmartAgent(ClaudeAgent):

            def __init__(self):
                super().__init__(model="claude-sonnet-4-20250514")

            @skill("smart-answer")
            async def answer(self, question: str) -> dict:
                response = await self.claude.ask(
                    prompt=question,
                    system="You are a helpful research assistant.",
                )
                return {"answer": response.text}
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self.claude = ClaudeLLM(
            model=model,
            api_key=api_key,
            system_prompt=system_prompt,
        )

    def get_claude_tools(self) -> list[ClaudeTool]:
        """Get ClaudeTool definitions from this agent's AURC skills.
        从 Agent 的 AURC 技能获取 ClaudeTool 定义

        Override this to customize which skills are exposed to Claude.
        """
        tools = []
        descriptor = getattr(self, "aurc_descriptor", None) or getattr(self.__class__, "_aurc_descriptor", None)
        if descriptor:
            for skill_decl in descriptor.capabilities.provides:
                handler = getattr(self, skill_decl.skill_id.replace("-", "_"), None)
                tools.append(ClaudeTool.from_aurc_skill(skill_decl, handler=handler))
        return tools
