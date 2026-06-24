"""AURC Multi-Agent Research Example
AURC 多 Agent 研究示例

Demonstrates a multi-agent research workflow:
1. Orchestrator delegates research tasks
2. Researcher performs deep research
3. Summarizer condenses findings
4. Results flow back through the router

Run / 运行: uv run python docs/examples/multi_agent_research.py
"""

import asyncio
import logging

from gaiaagent.sdk.decorators import aurc_agent, skill
from gaiaagent.harness.lifecycle import RuntimeHarness
from gaiaagent.registry.local import LocalRegistry
from gaiaagent.bus.router import MessageRouter
from gaiaagent.bus.session import SessionManager
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")


# =============================================================================
# Agent Definitions / Agent 定义
# =============================================================================


@aurc_agent(
    id="aurc:example/orchestrator:v1.0",
    display_name="Research Orchestrator",
    description="Coordinates multi-agent research workflows",
    tags=["orchestrator"],
)
class Orchestrator:
    @skill("orchestrate-research", description="Plan and coordinate research")
    async def orchestrate(self, topic: str) -> dict:
        return {
            "plan": [
                {"step": 1, "agent": "researcher", "action": "deep-research"},
                {"step": 2, "agent": "summarizer", "action": "summarize"},
            ],
            "topic": topic,
        }


@aurc_agent(
    id="aurc:example/researcher:v1.0",
    display_name="Deep Researcher",
    description="Performs multi-source deep research",
    tags=["research"],
)
class Researcher:
    @skill("deep-research", description="Multi-source research and analysis")
    async def research(self, topic: str, sources: list[str] | None = None) -> dict:
        # Simulated research / 模拟研究
        return {
            "topic": topic,
            "findings": [
                f"Finding 1: {topic} is an emerging field...",
                f"Finding 2: Key players include...",
                f"Finding 3: Recent developments show...",
            ],
            "sources_consulted": sources or ["web", "arxiv", "academic-db"],
            "confidence": 0.85,
        }


@aurc_agent(
    id="aurc:example/summarizer:v1.0",
    display_name="Research Summarizer",
    description="Summarizes research findings into concise reports",
    tags=["summarize"],
)
class Summarizer:
    @skill("summarize", description="Create executive summary from findings")
    async def summarize(self, findings: list[str], max_length: int = 300) -> dict:
        summary = " | ".join(findings)[:max_length]
        return {
            "summary": summary,
            "finding_count": len(findings),
            "compressed_ratio": len(summary) / sum(len(f) for f in findings),
        }


# =============================================================================
# Workflow / 工作流
# =============================================================================


async def main():
    print("=" * 60)
    print("  Multi-Agent Research Workflow / 多 Agent 研究工作流")
    print("=" * 60)

    # Initialize components / 初始化组件
    harness = RuntimeHarness()
    registry = LocalRegistry()
    router = MessageRouter()
    sessions = SessionManager()

    # Create agents / 创建 Agent
    orchestrator = Orchestrator()
    researcher = Researcher()
    summarizer = Summarizer()

    # Register all agents / 注册所有 Agent
    for agent_obj in [orchestrator, researcher, summarizer]:
        desc = agent_obj.aurc_descriptor
        await harness.register(desc)
        registry.register(desc)

    print(f"\n  Registered {harness.agent_count} agents\n")

    # Setup message handlers / 设置消息处理函数
    async def handle_research(msg: AURCMessage) -> dict:
        result = await researcher.research(**msg.body.params)
        return result

    async def handle_summarize(msg: AURCMessage) -> dict:
        result = await summarizer.summarize(**msg.body.params)
        return result

    router.register_handler("aurc:example/researcher:v1.0", handle_research)
    router.register_handler("aurc:example/summarizer:v1.0", handle_summarize)

    # --- Workflow Execution / 工作流执行 ---

    # Step 1: Create session / 创建会话
    session = sessions.create_session("aurc:example/orchestrator:v1.0")
    topic = "2026 AI Agent Protocol Interoperability"
    sessions.set_context(session.session_id, "topic", topic)
    print(f"  [1] Session created for topic: {topic}")

    # Step 2: Orchestrator plans / 编排器规划
    plan = await orchestrator.orchestrate(topic)
    print(f"  [2] Plan: {len(plan['plan'])} steps")

    # Step 3: Delegate research / 委派研究
    research_msg = AURCMessage(
        source="aurc:example/orchestrator:v1.0",
        target="aurc:example/researcher:v1.0",
        type=MessageDirection.REQUEST,
        body=MessageBody(
            method="invoke",
            skill="deep-research",
            params={"topic": topic},
        ),
    )
    sessions.advance_turn(session.session_id, "aurc:example/researcher:v1.0")
    research_result = await router.route(research_msg)
    print(f"  [3] Research complete: {len(research_result['findings'])} findings")

    # Step 4: Delegate summarization / 委派摘要
    summarize_msg = AURCMessage(
        source="aurc:example/orchestrator:v1.0",
        target="aurc:example/summarizer:v1.0",
        type=MessageDirection.REQUEST,
        body=MessageBody(
            method="invoke",
            skill="summarize",
            params={"findings": research_result["findings"]},
        ),
    )
    sessions.advance_turn(session.session_id, "aurc:example/summarizer:v1.0")
    summary_result = await router.route(summarize_msg)
    print(f"  [4] Summary: {summary_result['summary'][:100]}...")

    # Step 5: Final report / 最终报告
    print(f"\n  === Final Report / 最终报告 ===")
    print(f"  Topic:     {topic}")
    print(f"  Findings:  {research_result['finding_count'] if 'finding_count' in research_result else len(research_result['findings'])}")
    print(f"  Confidence: {research_result.get('confidence', 'N/A')}")
    print(f"  Summary:   {summary_result['summary'][:200]}")
    print(f"  Turns:     {session.turn}")
    print(f"  Routing:   {router.stats.to_dict()}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
