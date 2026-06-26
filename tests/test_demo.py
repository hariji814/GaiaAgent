"""Tests for the AURC demo module.

Covers the LLM backend, stub step functions, agent handlers, the
descriptor factory, and a full cross-protocol flow that mirrors
`run_demo` without starting the blocking HTTP server.
"""

import pytest

import gaiaagent.demo as demo_mod
from gaiaagent.bridges.a2a import A2ABridge
from gaiaagent.bridges.acp import ACPBridge
from gaiaagent.bridges.base import MCPBridge
from gaiaagent.bus.router import MessageRouter
from gaiaagent.core.message import AURCMessage, MessageBody
from gaiaagent.core.types import MessageDirection
from gaiaagent.demo import (
    _ANALYSIS_OUTPUT,
    _RESEARCH_OUTPUT,
    _WRITER_OUTPUT,
    LLMBackend,
    _analyst_handler,
    _make_descriptor,
    _researcher_handler,
    _step_analyze,
    _step_research,
    _step_write,
    _writer_handler,
)
from gaiaagent.observability.dashboard import DashboardAPI, HealthDashboard
from gaiaagent.security.audit import AuditAction, AuditLog
from gaiaagent.workflows.orchestrator import PromptChain

# ---------------------------------------------------------------------------
# LLMBackend + _llm_complete
# ---------------------------------------------------------------------------


class TestLLMBackend:
    """Unit tests for the zero-dependency LLM client wrapper."""

    def test_has_key_true(self):
        backend = LLMBackend(api_key="sk-test")
        assert backend.has_key is True

    def test_has_key_false(self):
        backend = LLMBackend(api_key="")
        assert backend.has_key is False

    @pytest.mark.asyncio
    async def test_llm_complete_falls_back_to_stub_without_key(self, monkeypatch):
        # Ensure no backend is configured so _llm_complete uses the stub.
        monkeypatch.setattr(demo_mod, "_llm_backend", None)
        out = await demo_mod._llm_complete("sys", "user", "STUB-RESPONSE")
        assert out == "STUB-RESPONSE"

    @pytest.mark.asyncio
    async def test_llm_complete_falls_back_when_call_fails(self, monkeypatch):
        backend = LLMBackend(api_key="sk-test")

        async def _boom(system_prompt, user_prompt):
            raise RuntimeError("network down")

        monkeypatch.setattr(backend, "complete", _boom)
        monkeypatch.setattr(demo_mod, "_llm_backend", backend)
        out = await demo_mod._llm_complete("sys", "user", "FALLBACK")
        assert out == "FALLBACK"


# ---------------------------------------------------------------------------
# Step functions
# ---------------------------------------------------------------------------


class TestStepFunctions:
    """Each step should return a non-empty string from the stub output."""

    @pytest.mark.asyncio
    async def test_step_research(self, monkeypatch):
        monkeypatch.setattr(demo_mod, "_llm_backend", None)
        out = await _step_research("AI agent interoperability")
        assert isinstance(out, str)
        assert out == _RESEARCH_OUTPUT

    @pytest.mark.asyncio
    async def test_step_analyze(self, monkeypatch):
        monkeypatch.setattr(demo_mod, "_llm_backend", None)
        out = await _step_analyze("findings blob")
        assert out == _ANALYSIS_OUTPUT

    @pytest.mark.asyncio
    async def test_step_write(self, monkeypatch):
        monkeypatch.setattr(demo_mod, "_llm_backend", None)
        out = await _step_write("analysis blob")
        assert out == _WRITER_OUTPUT


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _make_msg(content: str = "hello") -> AURCMessage:
    return AURCMessage(
        source="aurc:gaia/orchestrator:v1.0",
        target="aurc:demo/researcher:v1.0",
        type=MessageDirection.REQUEST,
        body=MessageBody(method="invoke", skill="research", params={"content": content}),
    )


class TestHandlers:
    """Handlers return dicts with the expected top-level keys."""

    @pytest.mark.asyncio
    async def test_researcher_handler(self, monkeypatch):
        monkeypatch.setattr(demo_mod, "_llm_backend", None)
        result = await _researcher_handler(_make_msg("AURC"))
        assert result["agent"] == "researcher"
        assert isinstance(result["findings"], str)

    @pytest.mark.asyncio
    async def test_analyst_handler(self, monkeypatch):
        monkeypatch.setattr(demo_mod, "_llm_backend", None)
        result = await _analyst_handler(_make_msg("AURC"))
        assert result["agent"] == "analyst"
        assert isinstance(result["analysis"], str)

    @pytest.mark.asyncio
    async def test_writer_handler(self, monkeypatch):
        monkeypatch.setattr(demo_mod, "_llm_backend", None)
        result = await _writer_handler(_make_msg("AURC"))
        assert result["agent"] == "writer"
        assert isinstance(result["report"], str)


# ---------------------------------------------------------------------------
# Descriptor factory
# ---------------------------------------------------------------------------


class TestDescriptorCreation:
    """_make_descriptor builds correctly shaped AgentDescriptors."""

    def test_basic_descriptor(self):
        desc = _make_descriptor("demo", "researcher", ["research"])
        assert desc.aurc_id == "aurc:demo/researcher:v1.0"
        assert desc.display_name == "Researcher"
        assert len(desc.capabilities.provides) == 1
        assert desc.capabilities.provides[0].skill_id == "research"

    def test_multiple_skills(self):
        desc = _make_descriptor("demo", "multi", ["a", "b", "c"])
        skills = [s.skill_id for s in desc.capabilities.provides]
        assert skills == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# PromptChain integration
# ---------------------------------------------------------------------------


class TestPromptChain:
    """The demo's three-step chain should complete end to end."""

    @pytest.mark.asyncio
    async def test_chain_completes(self, monkeypatch):
        monkeypatch.setattr(demo_mod, "_llm_backend", None)
        chain = PromptChain(
            steps=[_step_research, _step_analyze, _step_write],
            step_names=["research", "analyze", "write"],
        )
        result = await chain.execute("AI agent interoperability")
        assert result.success is True
        assert result.steps_completed == 3
        assert result.total_steps == 3
        assert isinstance(result.output, str) and result.output


# ---------------------------------------------------------------------------
# Full demo flow (mirrors run_demo without the blocking HTTP server)
# ---------------------------------------------------------------------------


class TestDemoFlow:
    """Integration test reproducing the demo's core orchestration."""

    @pytest.mark.asyncio
    async def test_full_demo_flow(self, monkeypatch):
        monkeypatch.setattr(demo_mod, "_llm_backend", None)

        harness = demo_mod.RuntimeHarness()
        router = MessageRouter()
        audit = AuditLog(max_entries=10_000)

        # Register three demo agents.
        researcher_desc = _make_descriptor("demo", "researcher", ["research"])
        analyst_desc = _make_descriptor("demo", "analyst", ["analyze"])
        writer_desc = _make_descriptor("demo", "writer", ["write"])
        for desc in (researcher_desc, analyst_desc, writer_desc):
            await harness.register(desc)

        # Register handlers on the router.
        router.register_handler(researcher_desc.aurc_id, _researcher_handler)
        router.register_handler(analyst_desc.aurc_id, _analyst_handler)
        router.register_handler(writer_desc.aurc_id, _writer_handler)

        # Set up cross-protocol bridge forwarders.
        bridges = {
            "mcp": MCPBridge(),
            "a2a": A2ABridge(),
            "acp": ACPBridge(),
        }
        for name, bridge in bridges.items():

            async def _make_fwd(n: str, b):
                async def _fwd(msg: AURCMessage):
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

        # Local inbound handler.
        async def _local_handler(msg: AURCMessage):
            audit.log(
                AuditAction.MESSAGE_RECEIVED,
                agent_id=msg.target,
                message_id=msg.message_id,
                correlation_id=msg.correlation_id or "",
                details={"skill": msg.body.skill},
            )
            return {"processed": True, "skill": msg.body.skill}

        router.register_handler("aurc:local/handler", _local_handler)

        # Start agents through the harness lifecycle.
        for desc in (researcher_desc, analyst_desc, writer_desc):
            await harness.start(desc.aurc_id)

        # Run the PromptChain workflow.
        chain = PromptChain(
            steps=[_step_research, _step_analyze, _step_write],
            step_names=["research", "analyze", "write"],
        )
        result = await chain.execute("AI agent interoperability")
        for desc in (researcher_desc, analyst_desc, writer_desc):
            await harness.complete(desc.aurc_id)

        assert result.success is True
        assert result.steps_completed == 3

        # Cross-protocol flow: MCP inbound (direct), A2A + ACP outbound (bridged).
        correlation_id = "demo-chain-001"
        mcp_request = {
            "jsonrpc": "2.0",
            "id": "mcp-demo",
            "method": "tools/call",
            "params": {
                "name": "web-search",
                "arguments": {"query": "AURC protocol"},
            },
        }
        inbound_msg = await bridges["mcp"].translate_to_aurc(mcp_request)
        inbound_msg.target = "aurc:local/handler"
        inbound_msg.correlation_id = correlation_id
        await router.route(inbound_msg)

        a2a_msg = AURCMessage(
            source=researcher_desc.aurc_id,
            target="a2a:external/expert",
            type=MessageDirection.DELEGATION,
            correlation_id=correlation_id,
            body=MessageBody(
                method="invoke",
                skill="research",
                params={"task_id": "t-2", "content": "Analyze AURC vs MCP/A2A"},
            ),
        )
        await router.route(a2a_msg)

        acp_msg = AURCMessage(
            source=analyst_desc.aurc_id,
            target="acp:external/summarizer",
            type=MessageDirection.DELEGATION,
            correlation_id=correlation_id,
            body=MessageBody(
                method="invoke",
                skill="summarize",
                params={"task_id": "t-3", "task": "Summarize the AURC spec"},
            ),
        )
        await router.route(acp_msg)

        stats = router.stats
        # Three routed messages: one direct (inbound), two bridged (A2A, ACP).
        assert stats.total_routed >= 3
        assert stats.bridged >= 2
        assert stats.direct >= 1

        # Dashboard + API should report all three registered agents.
        dashboard = HealthDashboard(harness, audit=audit, router=router)
        api = DashboardAPI(dashboard)
        assert api is not None
        reports = await harness.health_check_all()
        assert len(reports) == 3
