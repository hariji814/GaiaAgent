"""GaiaAgent — AURC Protocol End-to-End Demo
GaiaAgent — AURC 协议端到端演示

This demo showcases the full AURC protocol stack:
1. Define agents with @aurc_agent / @skill decorators
2. Register agents in the Harness and Registry
3. Route messages between agents
4. Bridge MCP and A2A protocol messages
5. Authenticate and authorize with CapABAC
6. Validate delegation chains
7. Track everything in the audit log

Run / 运行: uv run python main.py
"""

import asyncio
import json
import logging

# =============================================================================
# Setup logging / 设置日志
# =============================================================================
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("gaiaagent.demo")


async def main() -> None:
    print("=" * 70)
    print("  GaiaAgent — AURC Protocol End-to-End Demo")
    print("  AURC 协议端到端演示")
    print("=" * 70)

    # =========================================================================
    # 1. Define Agents / 定义 Agent
    # =========================================================================
    print("\n[Step] Step 1: Define agents with decorators / 使用装饰器定义 Agent\n")

    from gaiaagent.sdk.decorators import aurc_agent, skill

    @aurc_agent(
        id="aurc:demo/orchestrator:v1.0",
        display_name="Demo Orchestrator",
        description="Orchestrates research tasks across agents",
        tags=["orchestrator", "demo"],
        protocols=["mcp/2025-06-18", "a2a/1.0"],
    )
    class OrchestratorAgent:
        @skill("orchestrate", description="Orchestrate a multi-agent research task")
        async def orchestrate(self, query: str) -> dict:
            return {"status": "orchestrating", "query": query}

    @aurc_agent(
        id="aurc:demo/researcher:v1.0",
        display_name="Demo Researcher",
        description="Deep research with multi-source analysis",
        tags=["research", "demo"],
        consumes=["web-search"],
    )
    class ResearcherAgent:
        @skill("deep-research", description="Multi-source research and synthesis")
        async def research(self, query: str, depth: str = "medium") -> dict:
            return {
                "report": f"Research report for: '{query}' (depth={depth})",
                "sources": ["arxiv", "web", "academic-db"],
                "confidence": 0.87,
                "citations": 12,
            }

        @skill("summarize", description="Summarize research findings")
        async def summarize(self, text: str, max_length: int = 500) -> dict:
            return {"summary": text[:max_length], "original_length": len(text)}

    orchestrator = OrchestratorAgent()
    researcher = ResearcherAgent()
    print(f"  OK Orchestrator: {orchestrator.aurc_descriptor.aurc_id}")
    skills = [s.skill_id for s in orchestrator.aurc_descriptor.capabilities.provides]
    print(f"     Skills: {skills}")
    print(f"  OK Researcher:   {researcher.aurc_descriptor.aurc_id}")
    print(f"     Skills: {[s.skill_id for s in researcher.aurc_descriptor.capabilities.provides]}")

    # =========================================================================
    # 2. Register in Harness + Registry / 注册到 Harness 和 Registry
    # =========================================================================
    print("\n[Step] Step 2: Register in Harness & Registry / 注册到 Harness 和 Registry\n")

    from gaiaagent.core.types import RecoveryAction, RecoveryPolicy, RecoveryStrategy
    from gaiaagent.harness.lifecycle import RuntimeHarness
    from gaiaagent.registry.local import LocalRegistry

    recovery = RecoveryPolicy(
        max_retries=3,
        backoff_ms=[100, 500, 2000],
        strategies=[
            RecoveryStrategy(trigger="timeout", action=RecoveryAction.RETRY_WITH_BACKOFF),
            RecoveryStrategy(
                trigger="unrecoverable",
                action=RecoveryAction.ESCALATE,
                escalate_to="human",
            ),
        ],
    )
    harness = RuntimeHarness(recovery_policy=recovery)
    registry = LocalRegistry()

    await harness.register(orchestrator.aurc_descriptor)
    await harness.register(researcher.aurc_descriptor)
    registry.register(orchestrator.aurc_descriptor)
    registry.register(researcher.aurc_descriptor)

    print(f"  OK Harness: {harness.agent_count} agents registered")
    print(f"  OK Registry: {registry.count} agents indexed")

    # =========================================================================
    # 3. Capability Matching / 能力匹配
    # =========================================================================
    print("\n[Step] Step 3: Capability matching / 能力匹配\n")

    matches = registry.find_by_skills(["deep-research", "summarize"])
    for match in matches:
        print(f"  [STAT] {match.agent.aurc_id}")
        print(
            f"     Score: {match.score:.2f} | "
            f"Matched: {[s.skill_id for s in match.matched_skills]} | "
            f"Missing: {match.missing_skills}"
        )

    best = registry.find_best(["deep-research"])
    if best:
        best_id = best.agent.aurc_id
        print(f"  [BEST] Best match for 'deep-research': {best_id} (score={best.score:.2f})")

    # =========================================================================
    # 4. Message Routing / 消息路由
    # =========================================================================
    print("\n[Step] Step 4: Message routing / 消息路由\n")

    from gaiaagent.bus.router import MessageRouter
    from gaiaagent.core.message import AURCMessage, MessageBody
    from gaiaagent.core.types import MessageDirection

    router = MessageRouter()
    results_store: list[dict] = []

    async def orchestrator_handler(msg: AURCMessage) -> dict:
        results_store.append({"agent": "orchestrator", "msg_id": msg.message_id})
        return {"status": "received", "from": msg.source}

    async def researcher_handler(msg: AURCMessage) -> dict:
        results_store.append({"agent": "researcher", "msg_id": msg.message_id})
        # Simulate research / 模拟研究
        result = await researcher.research(**msg.body.params)
        return result

    router.register_handler("aurc:demo/orchestrator:v1.0", orchestrator_handler)
    router.register_handler("aurc:demo/researcher:v1.0", researcher_handler)

    # Send a request to researcher / 向 Researcher 发送请求
    request = AURCMessage(
        source="aurc:demo/orchestrator:v1.0",
        target="aurc:demo/researcher:v1.0",
        type=MessageDirection.REQUEST,
        body=MessageBody(
            method="invoke",
            skill="deep-research",
            params={"query": "2026 AI Agent protocol interoperability", "depth": "deep"},
        ),
    )
    result = await router.route(request)
    print("  [Step] Request: orchestrator → researcher")
    print(f"  [STAT] Result: {json.dumps(result, indent=2, default=str)[:200]}...")
    print(f"  [STAT] Router stats: {router.stats.to_dict()}")

    # =========================================================================
    # 5. Protocol Bridges / 协议桥接
    # =========================================================================
    print("\n[Step] Step 5: Protocol bridges — MCP, A2A & ACP / 协议桥接\n")

    from gaiaagent.bridges.a2a import A2ABridge
    from gaiaagent.bridges.acp import ACPBridge
    from gaiaagent.bridges.base import BridgeRegistry, MCPBridge

    bridge_registry = BridgeRegistry()
    mcp_bridge = MCPBridge()
    a2a_bridge = A2ABridge()
    acp_bridge = ACPBridge()
    bridge_registry.register(mcp_bridge)
    bridge_registry.register(a2a_bridge)
    bridge_registry.register(acp_bridge)

    # MCP → AURC / MCP 转 AURC
    mcp_tool_call = {
        "jsonrpc": "2.0",
        "id": "mcp-req-1",
        "method": "tools/call",
        "params": {"name": "web-search", "arguments": {"query": "AI protocols"}},
    }
    aurc_from_mcp = await mcp_bridge.translate_to_aurc(mcp_tool_call)
    print("  [Step] MCP → AURC:")
    print("     MCP method: tools/call")
    print(f"     AURC type:  {aurc_from_mcp.type.value}")
    print(f"     AURC skill: {aurc_from_mcp.body.skill}")
    print(f"     Bridge chain: {aurc_from_mcp.protocol_context.bridge_chain}")

    # AURC → MCP / AURC 转 MCP
    mcp_from_aurc = await mcp_bridge.translate_from_aurc(aurc_from_mcp)
    print("  [Step] AURC → MCP:")
    print(f"     MCP output: {json.dumps(mcp_from_aurc, default=str)[:150]}")

    # A2A → AURC / A2A 转 AURC
    a2a_task = {
        "jsonrpc": "2.0",
        "id": "a2a-req-1",
        "method": "tasks/send",
        "params": {
            "id": "task-001",
            "sessionId": "session-xyz",
            "messages": [
                {
                    "role": "user",
                    "parts": [{"type": "text", "text": "Research quantum computing"}],
                }
            ],
        },
    }
    aurc_from_a2a = await a2a_bridge.translate_to_aurc(a2a_task)
    print("  [Step] A2A → AURC:")
    print("     A2A method:  tasks/send")
    print(f"     AURC type:   {aurc_from_a2a.type.value}")
    print(f"     Bridge chain: {aurc_from_a2a.protocol_context.bridge_chain}")

    # ACP → AURC / ACP 转 AURC
    acp_invoke = {
        "method": "invoke",
        "params": {
            "agent_id": "acp:research-agent",
            "task": "Analyze 2026 AI agent interoperability trends",
            "input": {"depth": "deep", "sources": ["arxiv", "web"]},
            "session_id": "sess-acp-001",
        },
        "id": "acp-req-1",
    }
    aurc_from_acp = await acp_bridge.translate_to_aurc(acp_invoke)
    print("  [Step] ACP → AURC:")
    print("     ACP method:  invoke")
    print(f"     AURC type:   {aurc_from_acp.type.value}")
    print(f"     AURC skill:  {aurc_from_acp.body.skill}")
    print(f"     Bridge chain: {aurc_from_acp.protocol_context.bridge_chain}")

    # AURC → ACP / AURC 转 ACP
    acp_from_aurc = await acp_bridge.translate_from_aurc(aurc_from_acp)
    print("  [Step] AURC → ACP:")
    print(f"     ACP output: {json.dumps(acp_from_aurc, default=str)[:150]}")

    print(f"  [STAT] Bridge registry: {bridge_registry.list_protocols()}")

    # =========================================================================
    # 6. Session Management / 会话管理
    # =========================================================================
    print("\n[Step] Step 6: Session management / 会话管理\n")

    from gaiaagent.bus.session import SessionManager

    sessions = SessionManager()
    session = sessions.create_session("aurc:demo/orchestrator:v1.0")
    session.add_participant("aurc:demo/researcher:v1.0")
    sessions.set_context(session.session_id, "query", "AI protocols")
    sessions.advance_turn(session.session_id, "aurc:demo/orchestrator:v1.0")
    sessions.advance_turn(session.session_id, "aurc:demo/researcher:v1.0")

    print(f"  [Step] Session: {session.session_id}")
    print(f"     Conversation: {session.conversation_id}")
    print(f"     Participants: {session.participants}")
    print(f"     Turns: {session.turn}")
    print(f"     Context: query = {session.get_context('query')}")
    print(f"     Active sessions: {sessions.active_count}")

    # =========================================================================
    # 7. Security — Authentication + CapABAC + Delegation / 安全
    # =========================================================================
    print("\n[Step] Step 7: Security — Auth + CapABAC + Delegation / 安全\n")

    from gaiaagent.security.auth import APIKeyAuthenticator, JWTAuthenticator
    from gaiaagent.security.authz import (
        AgentPolicy,
        AuthorizationEngine,
        AuthorizationRule,
        Constraint,
    )
    from gaiaagent.security.delegation import DelegationBuilder, DelegationValidator

    # API Key auth / API Key 认证
    api_auth = APIKeyAuthenticator()
    api_key = api_auth.create_key(
        "aurc:demo/researcher:v1.0",
        scopes=["research:read", "research:write"],
    )
    auth_result = api_auth.authenticate(api_key)
    print(f"  [KEY] API Key auth: {'OK' if auth_result.authenticated else 'X'}")
    print(f"     Agent: {auth_result.agent_id}")
    print(f"     Scopes: {auth_result.scopes}")

    # JWT auth / JWT 认证
    jwt_auth = JWTAuthenticator()
    token = jwt_auth.create_token("aurc:demo/orchestrator:v1.0", scopes=["orchestrate"])
    jwt_result = jwt_auth.authenticate(token)
    print(f"  [JWT] JWT auth: {'OK' if jwt_result.authenticated else 'X'}")

    # CapABAC authorization / CapABAC 授权
    engine = AuthorizationEngine()
    engine.set_policy(
        "aurc:demo/researcher:v1.0",
        AgentPolicy(
            agent_id="aurc:demo/researcher:v1.0",
            rules=[
                AuthorizationRule(
                    resource_type="web-search",
                    actions=["execute"],
                    constraints=[
                        Constraint("domain", "matches", r".*\.(edu|gov|org)$"),
                    ],
                    rate_limit=100,
                ),
                AuthorizationRule(
                    resource_type="database",
                    actions=["read"],
                    constraints=[],
                ),
            ],
        ),
    )

    authz_allowed = engine.authorize(
        agent_id="aurc:demo/researcher:v1.0",
        resource_type="web-search",
        action="execute",
        attributes={"domain": "mit.edu"},
    )
    authz_denied = engine.authorize(
        agent_id="aurc:demo/researcher:v1.0",
        resource_type="web-search",
        action="execute",
        attributes={"domain": "suspicious.com"},
    )
    mit_label = "OK ALLOWED" if authz_allowed.allowed else "X DENIED"
    print(f"  [AUTHZ] CapABAC (mit.edu):       {mit_label} - {authz_allowed.reason}")
    sus_label = "OK ALLOWED" if authz_denied.allowed else "X DENIED"
    print(f"  [AUTHZ] CapABAC (suspicious.com): {sus_label} - {authz_denied.reason}")

    # Delegation chain / 委托链
    builder = DelegationBuilder()
    builder.add_hop(
        "aurc:user/alice:v1.0",
        "aurc:demo/orchestrator:v1.0",
        ["research:read", "web:search", "admin"],
    )
    builder.add_hop(
        "aurc:demo/orchestrator:v1.0", "aurc:demo/researcher:v1.0", ["research:read", "web:search"]
    )
    chain = builder.build()

    validator = DelegationValidator(max_depth=5)
    from gaiaagent.core.message import MessageSecurity

    security_ctx = MessageSecurity(
        scopes=["research:read", "web:search"],
        delegation_chain=chain,
    )
    delegation_result = validator.validate(security_ctx)
    print(f"  [CHAIN] Delegation chain: {'OK VALID' if delegation_result.valid else 'X INVALID'}")
    print(f"     Depth: {delegation_result.depth} hops")
    print(f"     Effective scopes: {delegation_result.effective_scopes}")

    # =========================================================================
    # 8. Audit Log / 审计日志
    # =========================================================================
    print("\n[Step] Step 8: Audit logging / 审计日志\n")

    from gaiaagent.security.audit import AuditAction, AuditLog, AuditSeverity

    audit = AuditLog(max_entries=1000)
    audit.log(AuditAction.AGENT_REGISTERED, agent_id="aurc:demo/orchestrator:v1.0")
    audit.log(AuditAction.AGENT_REGISTERED, agent_id="aurc:demo/researcher:v1.0")
    audit.log(
        AuditAction.MESSAGE_ROUTED,
        agent_id="aurc:demo/orchestrator:v1.0",
        target_id="aurc:demo/researcher:v1.0",
        protocol="aurc",
    )
    audit.log(
        AuditAction.MESSAGE_BRIDGED,
        agent_id="aurc:demo/researcher:v1.0",
        protocol="mcp/2025-06-18",
        details={"bridge": "mcp→aurc"},
    )
    audit.log(
        AuditAction.AUTHZ_GRANTED,
        agent_id="aurc:demo/researcher:v1.0",
        details={"resource": "web-search", "domain": "mit.edu"},
    )
    audit.log(
        AuditAction.AUTHZ_DENIED,
        agent_id="aurc:demo/researcher:v1.0",
        severity=AuditSeverity.WARNING,
        details={"resource": "web-search", "domain": "suspicious.com"},
    )
    audit.log(
        AuditAction.DELEGATION_VALIDATED,
        agent_id="aurc:demo/researcher:v1.0",
        details={"chain_depth": 2, "valid": True},
    )

    print(f"  [STAT] Audit entries: {audit.count}")
    print(f"  [STAT] Statistics: {audit.stats()}")
    recent = audit.get_recent(3)
    for entry in recent:
        print(f"     [{entry.severity.value}] {entry.action.value} — {entry.agent_id}")

    # =========================================================================
    # 9. Lifecycle Demo / 生命周期演示
    # =========================================================================
    print("\n[Step] Step 9: Agent lifecycle / Agent 生命周期\n")

    await harness.start("aurc:demo/researcher:v1.0")
    agent = harness.get_agent("aurc:demo/researcher:v1.0")
    print(f"  [RUN]  Started: {agent.state.value}")

    await harness.pause("aurc:demo/researcher:v1.0", reason="waiting for human approval")
    print(f"  [PAUSE]  Paused:  {agent.state.value}")

    await harness.resume("aurc:demo/researcher:v1.0")
    print(f"  [RUN]  Resumed: {agent.state.value}")

    await harness.complete("aurc:demo/researcher:v1.0")
    print(f"  OK Completed: {agent.state.value}")

    health = await harness.health_check("aurc:demo/researcher:v1.0")
    completed = health.metrics.total_tasks_completed
    print(f"  [HEALTH] Health: {health.status.value} | Tasks: completed={completed}")

    # =========================================================================
    # 10. Codec Demo / 编解码演示
    # =========================================================================
    print("\n[Step] Step 10: Message codec / 消息编解码\n")

    from gaiaagent.bus.codec import JSONCodec, MessageFrame, NDJSONCodec

    # JSON roundtrip / JSON 往返
    json_str = JSONCodec.encode(request, pretty=True)
    decoded = JSONCodec.decode(json_str)
    print(f"  [DOC] JSON encode: {len(json_str)} bytes")
    print(f"  [DOC] JSON decode: source={decoded.source}, skill={decoded.body.skill}")

    # NDJSON streaming / NDJSON 流式
    ndjson = NDJSONCodec.encode(request)
    print(f"  [DOC] NDJSON line: {len(ndjson)} bytes")

    # Message framing / 消息帧
    framed = MessageFrame.frame_message(request)
    unframed_msg, remaining = MessageFrame.unframe_message(framed)
    header = MessageFrame.HEADER_SIZE
    payload = len(framed) - header
    print(f"  [Step] Framed: {len(framed)} bytes (header={header} + payload={payload})")
    print(f"  [Step] Unframed: source={unframed_msg.source}")

    # =========================================================================
    # Summary / 总结
    # =========================================================================
    print("\n" + "=" * 70)
    print("  OK AURC Protocol Demo Complete!")
    print("  AURC 协议演示完成！")
    print("=" * 70)
    print()
    print("  Components demonstrated / 演示的组件:")
    print("  ┌─────────────────────────────────────────────────────┐")
    print("  │  OK SDK Decorators (@aurc_agent, @skill)             │")
    print("  │  OK Runtime Harness (lifecycle state machine)        │")
    print("  │  OK Agent Registry (capability matching)             │")
    print("  │  OK Message Router (direct routing)                  │")
    print("  │  OK Session Manager (conversation tracking)          │")
    print("  │  OK MCP Bridge (tools/call ↔ AURC request)          │")
    print("  │  OK A2A Bridge (tasks/send ↔ AURC delegation)       │")
    print("  │  OK ACP Bridge (invoke ↔ AURC delegation)           │")
    print("  │  OK API Key + JWT Authentication                     │")
    print("  │  OK CapABAC Authorization Engine                     │")
    print("  │  OK Delegation Chain Validation                      │")
    print("  │  OK Audit Log (cross-protocol tracking)              │")
    print("  │  OK Message Codec (JSON, NDJSON, Framing)            │")
    print("  └─────────────────────────────────────────────────────┘")
    print()
    print("  Next steps / 后续步骤:")
    print("  • Deploy with HTTP transport for real multi-process agents")
    print("  • Connect to real MCP servers and A2A agents")
    print("  • Build custom bridges for proprietary protocols")
    print("  • Publish AURC Agent Descriptors to the community registry")
    print()


if __name__ == "__main__":
    asyncio.run(main())
