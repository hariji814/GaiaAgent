"""AURC Demo - a zero-config, cross-protocol agent showcase.
AURC 演示 - 零配置、跨协议 Agent 展示

Runs 3 agents (Researcher, Analyst, Writer) in a PromptChain workflow,
crossing MCP -> A2A -> ACP protocol boundaries, with a live dashboard
and auto-opened browser. No API key required - uses stub LLM responses.

运行 3 个 Agent（研究员、分析师、作家）的链式工作流，
跨越 MCP -> A2A -> ACP 协议边界，带实时仪表盘和自动打开的浏览器。
无需 API key - 使用桩 LLM 响应。
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import threading
import time
import webbrowser
from collections.abc import Awaitable, Callable
from typing import Any

from gaiaagent.bridges.a2a import A2ABridge
from gaiaagent.bridges.acp import ACPBridge
from gaiaagent.bridges.base import MCPBridge
from gaiaagent.bus.router import MessageRouter
from gaiaagent.core.identity import (
    AgentDescriptor,
    AuthDeclaration,
    Capabilities,
    ProtocolSupport,
    RuntimeRequirements,
    SkillDeclaration,
)
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection
from gaiaagent.harness.lifecycle import RuntimeHarness
from gaiaagent.observability.dashboard import DashboardAPI, HealthDashboard
from gaiaagent.security.audit import AuditAction, AuditLog
from gaiaagent.workflows.orchestrator import PromptChain, WorkflowResult

logger = logging.getLogger("gaiaagent.demo")

# --- Stub LLM responses (no API key needed) / 桩 LLM 响应 ---

_RESEARCH_OUTPUT = (
    "Key findings on AI agent interoperability:\n"
    "1. MCP standardizes tool-calling but lacks lifecycle management.\n"
    "2. A2A enables agent-to-agent delegation but has no bridge layer.\n"
    "3. ACP supports async task dispatch but no runtime harness.\n"
    "4. AURC unifies all three with a lifecycle state machine and bridge layer."
)

_ANALYSIS_OUTPUT = (
    "Analysis: The AURC protocol fills critical gaps:\n"
    "- Lifecycle: READY -> RUNNING -> PAUSED -> COMPLETED state machine\n"
    "- Bridging: MCP/A2A/ACP translated to canonical AURC messages\n"
    "- Observability: audit trail, health dashboard, Prometheus metrics\n"
    "- Conclusion: AURC is the missing interoperability layer."
)

_WRITER_OUTPUT = (
    "# AURC Protocol: The Interoperability Layer for AI Agents\n\n"
    "## Problem\n"
    "MCP, A2A, and ACP each solve part of the agent communication puzzle,\n"
    "but none provides lifecycle management or cross-protocol bridging.\n\n"
    "## Solution: AURC\n"
    "AURC (Agent Unified Runtime & Communication) introduces:\n"
    "1. **Lifecycle Harness** - a state machine for agent health and recovery\n"
    "2. **Protocol Bridges** - MCP, A2A, ACP all translated to one format\n"
    "3. **Observability** - audit logs, health dashboard, Prometheus metrics\n\n"
    "## Result\n"
    "Agents built for any framework can collaborate through AURC's unified\n"
    "runtime, with full observability across protocol boundaries.\n"
)


class LLMBackend:
    """Zero-dependency LLM client (urllib) for OpenAI and Anthropic.

    When an API key is provided the demo calls a real model; otherwise it
    falls back to the stub responses above so the demo always runs.
    """

    def __init__(self, api_key: str, provider: str = "openai", model: str = "auto") -> None:
        self._api_key = api_key
        self._provider = provider
        self._model = model

    @property
    def has_key(self) -> bool:
        return bool(self._api_key)

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Call the configured provider and return the text response."""
        if self._provider == "anthropic":
            return await asyncio.to_thread(self._call_anthropic, system_prompt, user_prompt)
        return await asyncio.to_thread(self._call_openai, system_prompt, user_prompt)

    def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        import urllib.request

        model = self._model if self._model != "auto" else "gpt-4o-mini"
        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }).encode()
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result: dict[str, Any] = json.loads(resp.read())
        return str(result["choices"][0]["message"]["content"])

    def _call_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        import urllib.request

        model = self._model if self._model != "auto" else "claude-3-5-sonnet-20241022"
        payload = json.dumps({
            "model": model,
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result: dict[str, Any] = json.loads(resp.read())
        return str(result["content"][0]["text"])


_llm_backend: LLMBackend | None = None


async def _llm_complete(system_prompt: str, user_prompt: str, stub: str) -> str:
    """Call the LLM when configured, otherwise return the stub response."""
    if _llm_backend and _llm_backend.has_key:
        try:
            return await _llm_backend.complete(system_prompt, user_prompt)
        except Exception as exc:
            logger.warning("LLM call failed, falling back to stub: %s", exc)
    return stub


def _make_descriptor(
    namespace: str, name: str, skills: list[str]
) -> AgentDescriptor:
    """Create a minimal AgentDescriptor for the demo."""
    aurc_id = f"aurc:{namespace}/{name}:v1.0"
    return AgentDescriptor(
        aurc_id=aurc_id,
        display_name=name.capitalize(),
        version="1.0",
        description=f"Demo {name} agent",
        capabilities=Capabilities(
            provides=[
                SkillDeclaration(
                    skill_id=s,
                    name=s.capitalize(),
                    description=f"{s} skill for demo",
                )
                for s in skills
            ],
        ),
        protocols=ProtocolSupport(bridges=[]),
        runtime=RuntimeRequirements(),
        auth=AuthDeclaration(),
    )


async def _researcher_handler(msg: AURCMessage) -> dict[str, Any]:
    """Researcher agent - calls a real LLM when configured."""
    logger.info("Researcher: processing query...")
    await asyncio.sleep(0.5)  # simulate work
    content = msg.body.params.get("content", str(msg.body.params))
    findings = await _llm_complete(
        "You are a meticulous research analyst. Produce concise, structured findings.",
        f"Research this topic and list 3-4 key findings:\n{content}",
        _RESEARCH_OUTPUT,
    )
    return {"agent": "researcher", "findings": findings}


async def _analyst_handler(msg: AURCMessage) -> dict[str, Any]:
    """Analyst agent - calls a real LLM when configured."""
    logger.info("Analyst: analyzing findings...")
    await asyncio.sleep(0.5)
    content = msg.body.params.get("content", str(msg.body.params))
    analysis = await _llm_complete(
        "You are a strategic analyst. Identify gaps and draw conclusions.",
        f"Analyze these findings and explain why they matter:\n{content}",
        _ANALYSIS_OUTPUT,
    )
    return {"agent": "analyst", "analysis": analysis}


async def _writer_handler(msg: AURCMessage) -> dict[str, Any]:
    """Writer agent - calls a real LLM when configured."""
    logger.info("Writer: composing report...")
    await asyncio.sleep(0.5)
    content = msg.body.params.get("content", str(msg.body.params))
    report = await _llm_complete(
        "You are a technical writer. Produce a clear Markdown report.",
        f"Write a structured Markdown report based on this analysis:\n{content}",
        _WRITER_OUTPUT,
    )
    return {"agent": "writer", "report": report}


# --- Workflow step functions for PromptChain / 工作流步骤 ---

async def _step_research(input_data: Any) -> str:
    """Step 1: Research (simulates MCP -> AURC inbound)."""
    return await _llm_complete(
        "You are a meticulous research analyst. Produce concise, structured findings.",
        f"Research this topic and list 3-4 key findings:\n{input_data}",
        _RESEARCH_OUTPUT,
    )


async def _step_analyze(input_data: Any) -> str:
    """Step 2: Analyze (simulates AURC -> A2A outbound delegation)."""
    return await _llm_complete(
        "You are a strategic analyst. Identify gaps and draw conclusions.",
        f"Analyze these findings and explain why they matter:\n{input_data}",
        _ANALYSIS_OUTPUT,
    )


async def _step_write(input_data: Any) -> str:
    """Step 3: Write (simulates AURC -> ACP outbound delegation)."""
    return await _llm_complete(
        "You are a technical writer. Produce a clear Markdown report.",
        f"Write a structured Markdown report based on this analysis:\n{input_data}",
        _WRITER_OUTPUT,
    )


def _open_browser_delayed(url: str, delay: float = 1.5) -> None:
    """Open browser after a short delay (let the server start)."""
    def _open() -> None:
        time.sleep(delay)
        webbrowser.open(url)
    t = threading.Thread(target=_open, daemon=True)
    t.start()


async def run_demo(
    host: str = "127.0.0.1",
    port: int = 8080,
    open_browser: bool = True,
    api_key: str | None = None,
    provider: str = "openai",
    model: str = "auto",
) -> None:
    """Run the full AURC demo.

    Sets up 3 agents, a cross-protocol message router, a health dashboard,
    runs a PromptChain workflow, then serves the dashboard on HTTP.

    When *api_key* is provided the demo calls a real LLM (OpenAI or
    Anthropic); otherwise it uses built-in stub responses so the demo
    always runs with zero configuration.
    """
    global _llm_backend
    if api_key:
        _llm_backend = LLMBackend(api_key=api_key, provider=provider, model=model)
    else:
        _llm_backend = None

    print("=" * 60)
    print("  AURC Protocol Demo - 3 Agents, Cross-Protocol Chain")
    print("=" * 60)
    if _llm_backend and _llm_backend.has_key:
        print(f"  [LLM] provider={provider}  model={model}")
    else:
        print("  [STUB] No API key - using built-in responses (add --api-key for real LLM)")
    print()

    # 1. Stand up the runtime / 搭建运行时
    harness = RuntimeHarness()
    router = MessageRouter()
    audit = AuditLog(max_entries=10_000)

    # 2. Register agents / 注册 Agent
    researcher_desc = _make_descriptor("demo", "researcher", ["research"])
    analyst_desc = _make_descriptor("demo", "analyst", ["analyze"])
    writer_desc = _make_descriptor("demo", "writer", ["write"])

    await harness.register(researcher_desc)
    await harness.register(analyst_desc)
    await harness.register(writer_desc)

    print("  [OK] Registered 3 agents:")
    print(f"       - {researcher_desc.aurc_id}")
    print(f"       - {analyst_desc.aurc_id}")
    print(f"       - {writer_desc.aurc_id}")
    print()

    # 3. Register handlers / 注册处理函数
    router.register_handler(researcher_desc.aurc_id, _researcher_handler)
    router.register_handler(analyst_desc.aurc_id, _analyst_handler)
    router.register_handler(writer_desc.aurc_id, _writer_handler)

    # 4. Set up bridge forwarders (cross-protocol) / 设置桥接转发
    bridges: dict[str, Any] = {"mcp": MCPBridge(), "a2a": A2ABridge(), "acp": ACPBridge()}
    for name, bridge in bridges.items():
        async def _make_fwd(n: str, b: Any) -> Callable[[AURCMessage], Awaitable[dict[str, Any]]]:
            async def _fwd(msg: AURCMessage) -> dict[str, Any]:
                external = await b.translate_from_aurc(msg)
                audit.log(
                    AuditAction.MESSAGE_BRIDGED,
                    agent_id=msg.target,
                    message_id=msg.message_id,
                    correlation_id=msg.correlation_id or "",
                    details={"protocol": n, "payload_keys": list(external.keys())},
                )
                return {"forwarded": n, "payload": external}
            return _fwd
        fwd = await _make_fwd(name, bridge)
        router.register_bridge_forwarder(name, fwd)

    # 4b. Register local handler for inbound bridge messages / 注册入站消息处理函数
    async def _local_handler(msg: AURCMessage) -> dict[str, Any]:
        audit.log(
            AuditAction.MESSAGE_RECEIVED,
            agent_id=msg.target,
            message_id=msg.message_id,
            correlation_id=msg.correlation_id or "",
            details={"skill": msg.body.skill},
        )
        return {"processed": True, "skill": msg.body.skill}

    router.register_handler("aurc:local/handler", _local_handler)

    # 5. Run the PromptChain workflow / 运行链式工作流
    correlation_id = "demo-chain-001"
    audit.log(AuditAction.SESSION_CREATED, correlation_id=correlation_id)

    print("  [..] Running PromptChain: Research -> Analyze -> Write")
    chain = PromptChain(
        steps=[_step_research, _step_analyze, _step_write],
        step_names=["research", "analyze", "write"],
    )

    # Start agents through the harness lifecycle
    for desc in [researcher_desc, analyst_desc, writer_desc]:
        await harness.start(desc.aurc_id)

    result: WorkflowResult = await chain.execute("AI agent interoperability")

    # Complete agents
    for desc in [researcher_desc, analyst_desc, writer_desc]:
        await harness.complete(desc.aurc_id)

    print(f"  [OK] Chain completed: {result.steps_completed}/{result.total_steps} steps")
    print()

    # 6. Run cross-protocol message flow / 运行跨协议消息流
    print("  [..] Cross-protocol flow: MCP -> AURC -> A2A -> ACP")

    # Inbound: MCP tools/call -> AURC
    mcp_request = {
        "jsonrpc": "2.0",
        "id": "mcp-demo",
        "method": "tools/call",
        "params": {"name": "web-search", "arguments": {"query": "AURC protocol"}},
    }
    inbound_msg = await bridges["mcp"].translate_to_aurc(mcp_request)
    inbound_msg.correlation_id = correlation_id
    await router.route(inbound_msg)
    print("       MCP -> AURC: routed (direct)")

    # Outbound: AURC -> A2A
    a2a_msg = AURCMessage(
        source=researcher_desc.aurc_id,
        target="a2a:external/expert",
        type=MessageDirection.DELEGATION,
        correlation_id=correlation_id,
        body=MessageBody(
            method="invoke", skill="research",
            params={"task_id": "t-2", "content": "Analyze AURC vs MCP/A2A"},
        ),
    )
    await router.route(a2a_msg)
    print("       AURC -> A2A: bridged")

    # Outbound: AURC -> ACP
    acp_msg = AURCMessage(
        source=analyst_desc.aurc_id,
        target="acp:external/summarizer",
        type=MessageDirection.DELEGATION,
        correlation_id=correlation_id,
        body=MessageBody(
            method="invoke", skill="summarize",
            params={"task_id": "t-3", "task": "Summarize the AURC spec"},
        ),
    )
    await router.route(acp_msg)
    print("       AURC -> ACP: bridged")
    print()

    # 7. Show results / 展示结果
    print("  === Final Report ===")
    print(result.output)
    print()

    # 8. Show stats / 展示统计
    print("  === Router Stats ===")
    print(f"  {json.dumps(router.stats.to_dict(), indent=2)}")
    print()

    # 9. Serve dashboard / 提供仪表盘
    dashboard = HealthDashboard(harness, audit=audit, router=router)
    api = DashboardAPI(dashboard)

    dashboard_url = f"http://{host}:{port}/dashboard"
    print(f"  [OK] Dashboard: {dashboard_url}")
    print(f"  [OK] Health:    http://{host}:{port}/health")
    print(f"  [OK] Metrics:   http://{host}:{port}/metrics")
    print()
    print("  Press Ctrl+C to stop the server.")
    print("=" * 60)

    if open_browser:
        _open_browser_delayed(dashboard_url)

    # Serve using the HTTP transport server
    from gaiaagent.transport.http import HTTPTransportServer
    server = HTTPTransportServer(host=host, port=port)
    server.set_dashboard_api(api)

    # Also set a simple handler for /aurc POST
    async def _handler(request_data: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ok", "protocol": "aurc/0.1", "echo": request_data}
    server.set_handler(_handler)

    try:
        await server.start()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        await server.stop()


def main() -> int:
    """CLI entry point for the demo."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(name)s | %(message)s",
    )
    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        print("\nDemo interrupted.")
    except Exception as exc:
        print(f"Demo failed: {exc}", file=sys.stderr)
        return 1
    return 0
