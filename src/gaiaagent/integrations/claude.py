"""AURC Claude Integration — use Claude as the reasoning engine for AURC agents.
AURC Claude 集成 — 将 Claude 用作 AURC Agent 的推理引擎

This module bridges the AURC runtime harness with Claude. The agentic loop
(`ClaudeLLM.agentic_loop`) has two backends (see LOOP_ROADMAP.md):
    - **Claude Code CLI** (`claude -p --output-format stream-json`) — the
      reference agentic loop, used when the `claude` binary is on PATH and no
      caller-supplied tool handlers must run in-process. See `claude_cli.py`.
    - **Built-in `anthropic`-based loop** — the fallback (CLI absent, or
      in-process tool handlers required).
Tool execution in the built-in path goes through `ClaudeLLM._execute_tool`,
the single seam Step 3 of the Loop Roadmap overrides to route via the bus.

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
    │  │  → claude CLI (primary) / Anthropic    │  │
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

import json
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


def _stringify_result(result: Any) -> str:
    """Render a tool-handler result as a string for the model.
    把工具 handler 结果渲染为给模型的字符串

    dict/list results are JSON-encoded (so the model can parse structure);
    everything else uses ``str()``. Avoids the Python-repr drift from
    ``str(dict)`` (e.g. single quotes) that breaks tool-use chains.
    """
    if isinstance(result, (dict, list)):
        try:
            return json.dumps(result, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(result)
    if isinstance(result, (bytes, bytearray)):
        return result.decode("utf-8", errors="replace")
    return str(result)


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
    def from_aurc_skill(
        cls, skill_declaration: Any, handler: Callable[..., Any] | None = None
    ) -> ClaudeTool:
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
        *,
        cli_path: str | None = None,
        cli_args: list[str] | None = None,
        permission_mode: str | None = None,
        mcp_config: str | None = None,
        allowed_tools: list[str] | None = None,
        timeout: float | None = None,
        trace_recorder: Any = None,
        agent_id: str | None = None,
        backend: str = "claude",
        codex_cli_path: str | None = None,
        codex_cli_args: list[str] | None = None,
        codex_sandbox: str | None = None,
        codex_working_dir: str | None = None,
        codex_mcp_config: list[Any] | None = None,
        codex_extra_config: list[str] | None = None,
        codex_output_last_message: str | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._max_tokens = max_tokens
        self._system_prompt = system_prompt
        self._conversation_history: list[dict[str, Any]] = []
        # Claude Code CLI backend config (Loop Roadmap Step 2). When the `claude`
        # CLI is on PATH, `agentic_loop` delegates to it; otherwise the built-in
        # hand-rolled loop is used. These fields are pass-through CLI flags /
        # AURC runtime handles.
        # Claude Code CLI 后端配置(Loop Roadmap Step 2)。
        self._cli_path = cli_path
        self._cli_args = cli_args
        self._permission_mode = permission_mode
        self._mcp_config = mcp_config
        self._allowed_tools = allowed_tools
        self._timeout = timeout
        self._trace_recorder = trace_recorder
        self._agent_id = agent_id
        # Pluggable loop backend (Loop Roadmap: vendor-lock to Claude is a non-goal).
        # backend selects which CLI drives the inner agentic loop: "claude" (default),
        # "codex", or "auto" (prefer the first CLI on PATH). The codex backend mirrors
        # the claude adapter shape (gaiaagent.integrations.codex_cli); both reduce a
        # vendor CLI stream into one ClaudeResponse.
        self._backend = backend
        # Codex-specific config; only consulted when the codex backend runs.
        self._codex_cli_path = codex_cli_path
        self._codex_cli_args = codex_cli_args
        self._codex_sandbox = codex_sandbox
        self._codex_working_dir = codex_working_dir
        self._codex_mcp_config = codex_mcp_config
        self._codex_extra_config = codex_extra_config
        self._codex_output_last_message = codex_output_last_message

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
            import anthropic  # type: ignore[import-not-found]

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
        *,
        correlation_id: str | None = None,
    ) -> ClaudeResponse:
        """Run an agentic loop — Claude calls tools until done.
        运行 Agentic 循环 — Claude 调用工具直到完成

        This implements the core "agent" pattern: Claude decides which
        tools to call, executes them, and continues reasoning with results.

        Backend selection / 后端选择 (Loop Roadmap Step 2):
        If the `claude` CLI is on PATH and no caller-supplied tool handlers
        need to run in-process, delegate to the CLI headless loop
        (`claude -p … --output-format stream-json`). Otherwise fall back to
        the built-in `anthropic`-based loop. To make the CLI's tool calls
        enter the AURC bus, set ``mcp_config`` to an AURC MCP server
        (see :mod:`gaiaagent.mcp.server`); then ``tools/call`` crosses the
        subprocess boundary at the protocol level through ``MCPBridge``.

        Args:
            prompt: Initial user message / 初始用户消息
            tools: Available tools with handlers / 带处理函数的可用工具
            max_turns: Maximum tool-use turns / 最大工具使用轮次
            system: System prompt / 系统提示词
            correlation_id: Optional AURC correlation id for trace linkage /
                可选 AURC correlation id,用于追踪关联

        Returns:
            Final ClaudeResponse after all tool calls complete
        """
        # Backend selection (Loop Roadmap: vendor-lock to Claude is a non-goal).
        # Both CLI backends (claude, codex) reduce a vendor CLI stream into one
        # ClaudeResponse; the codex backend mirrors the claude adapter shape.
        from . import claude_cli as _claude_cli
        from . import codex_cli as _codex_cli

        has_handler_tools = bool(tools) and any(
            getattr(t, "handler", None) is not None for t in (tools or [])
        )
        # A prompt too long for a CLI *argument* forces the in-process loop
        # (avoids Windows command-line truncation; long prompts should use MCP).
        if has_handler_tools or _claude_cli.prompt_too_long(prompt):
            if _claude_cli.prompt_too_long(prompt):
                logger.info("prompt exceeds CLI arg limit; using built-in loop")
            return await self._agentic_loop_builtin(
                prompt=prompt, tools=tools, max_turns=max_turns, system=system
            )

        backend = (self._backend or "claude").lower()
        if backend == "auto":
            if _codex_cli.cli_available(self._codex_cli_path):
                backend = "codex"
            elif _claude_cli.cli_available(self._cli_path):
                backend = "claude"
            else:
                backend = "builtin"

        if backend == "codex" and _codex_cli.cli_available(self._codex_cli_path):
            return await _codex_cli.run_agentic_loop(
                prompt=prompt,
                tools=tools,
                max_turns=max_turns,
                system=system or self._system_prompt,
                model=self._model,
                api_key=self._api_key,
                max_tokens=self._max_tokens,
                execute_tool=self._execute_tool,
                cli_path=self._codex_cli_path,
                cli_args=self._codex_cli_args,
                sandbox=self._codex_sandbox,
                working_dir=self._codex_working_dir,
                mcp_config=self._codex_mcp_config,
                extra_config=self._codex_extra_config,
                output_last_message=self._codex_output_last_message,
                timeout=self._timeout,
                trace_recorder=self._trace_recorder,
                agent_id=self._agent_id,
                correlation_id=correlation_id,
            )

        if backend == "claude" and _claude_cli.cli_available(self._cli_path):
            return await _claude_cli.run_agentic_loop(
                prompt=prompt,
                tools=tools,
                max_turns=max_turns,
                system=system or self._system_prompt,
                model=self._model,
                api_key=self._api_key,
                max_tokens=self._max_tokens,
                execute_tool=self._execute_tool,
                cli_path=self._cli_path,
                cli_args=self._cli_args,
                permission_mode=self._permission_mode,
                mcp_config=self._mcp_config,
                allowed_tools=self._allowed_tools,
                timeout=self._timeout,
                trace_recorder=self._trace_recorder,
                agent_id=self._agent_id,
                correlation_id=correlation_id,
            )

        return await self._agentic_loop_builtin(
            prompt=prompt, tools=tools, max_turns=max_turns, system=system
        )

    async def run_managed_loop(
        self,
        harness: Any,
        agent_id: str,
        prompt: str,
        tools: list[ClaudeTool] | None = None,
        max_turns: int = 10,
        system: str | None = None,
        *,
        correlation_id: str | None = None,
    ) -> ClaudeResponse:
        """Run agentic_loop with AURC lifecycle management.

        Wraps agentic_loop with the harness lifecycle: start -> run ->
        complete on success, or report_error -> recovery -> retry on
        failure. The stop_reason from the CLI/built-in backend is mapped
        to a RecoveryAction via stop_reason_to_recovery_action; a clean
        end_turn maps to None (nothing to recover).

        Args:
            harness: A RuntimeHarness with the agent already registered.
            agent_id: The registered agent's AURC ID.
            prompt: Initial user message.
            tools: Available tools with handlers.
            max_turns: Maximum tool-use turns.
            system: System prompt.
            correlation_id: Optional AURC correlation id for trace linkage.

        Returns:
            Final ClaudeResponse after all tool calls complete (or the
            last attempt if recovery was exhausted).
        """
        from . import claude_cli, codex_cli

        def _extract_stop_reason(resp: ClaudeResponse) -> str | None:
            # Try the active backend's mapping; fall back to claude_cli's.
            mapping = (
                codex_cli.stop_reason_to_recovery_action
                if (self._backend or "claude") == "codex"
                else claude_cli.stop_reason_to_recovery_action
            )
            action = mapping(resp.stop_reason)
            return None if action is None else resp.stop_reason

        async def _loop() -> ClaudeResponse:
            return await self.agentic_loop(
                prompt=prompt,
                tools=tools,
                max_turns=max_turns,
                system=system,
                correlation_id=correlation_id,
            )

        result: ClaudeResponse = await harness.run_with_lifecycle(
            agent_id,
            _loop,
            get_stop_reason=_extract_stop_reason,
        )
        return result

    async def _execute_tool(
        self, tool: ClaudeTool | None, tool_input: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute one tool call (built-in fallback path only).

        On the CLI path the CLI runs its own tools; bus routing there is done
        at the MCP layer via ``--mcp-config``, not by overriding this seam.
        Returns a tool_result-shaped dict: ``{"content": str, "is_error": bool}``.
        """
        name = tool.name if tool else "<unknown>"
        if not tool or not tool.handler:
            return {"content": f"Tool '{name}' not found or no handler", "is_error": True}
        logger.info("Claude calling tool: %s(%s)", name, tool_input)
        try:
            result = await tool.handler(**tool_input)
            return {"content": _stringify_result(result), "is_error": False}
        except Exception as e:
            return {"content": f"Error: {e}", "is_error": True}

    async def _agentic_loop_builtin(
        self,
        prompt: str,
        tools: list[ClaudeTool] | None = None,
        max_turns: int = 10,
        system: str | None = None,
    ) -> ClaudeResponse:
        """Built-in hand-rolled agentic loop — the fallback when the `claude` CLI is absent
        or caller-supplied tool handlers must run in-process.
        内置手写循环 —— CLI 缺失或需进程内执行 handler 时的降级路径
        """
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=self._api_key)

            messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
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

            for _turn in range(max_turns):
                response = await client.messages.create(**kwargs)
                last_response = response

                # If Claude stopped (no more tool calls), we're done / 如果 Claude 停止了
                if response.stop_reason == "end_turn":
                    return self._parse_response(response)

                # Process tool calls via the _execute_tool seam / 经 _execute_tool 缝处理工具调用
                tool_results: list[dict[str, Any]] = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool = tool_map.get(block.name)
                        tr = await self._execute_tool(tool, dict(block.input))
                        tr["tool_use_id"] = block.id
                        tr["type"] = "tool_result"
                        tool_results.append(tr)

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

            # Max turns reached — the loop exhausted without `end_turn`, so the
            # model still wanted more tool calls. Report `max_turns` consistently
            # with the CLI backend (not the raw last-response stop_reason).
            # 达到最大轮次 —— 与 CLI 后端一致地报告 max_turns
            if last_response:
                parsed = self._parse_response(last_response)
                parsed.stop_reason = "max_turns"
                return parsed
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
        *,
        cli_path: str | None = None,
        cli_args: list[str] | None = None,
        permission_mode: str | None = None,
        mcp_config: str | None = None,
        allowed_tools: list[str] | None = None,
        timeout: float | None = None,
        trace_recorder: Any = None,
        agent_id: str | None = None,
    ) -> None:
        self.claude = ClaudeLLM(
            model=model,
            api_key=api_key,
            system_prompt=system_prompt,
            cli_path=cli_path,
            cli_args=cli_args,
            permission_mode=permission_mode,
            mcp_config=mcp_config,
            allowed_tools=allowed_tools,
            timeout=timeout,
            trace_recorder=trace_recorder,
            agent_id=agent_id,
        )

    def get_claude_tools(self) -> list[ClaudeTool]:
        """Get ClaudeTool definitions from this agent's AURC skills.
        从 Agent 的 AURC 技能获取 ClaudeTool 定义

        Override this to customize which skills are exposed to Claude.
        """
        tools = []
        descriptor = (
            getattr(self, "aurc_descriptor", None)
            or getattr(self.__class__, "_aurc_descriptor", None)
        )
        if descriptor:
            for skill_decl in descriptor.capabilities.provides:
                handler = getattr(self, skill_decl.skill_id.replace("-", "_"), None)
                tools.append(ClaudeTool.from_aurc_skill(skill_decl, handler=handler))
        return tools
