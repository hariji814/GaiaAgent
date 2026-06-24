"""Tests for AURC SDK decorators (@aurc_agent, @skill)."""

import pytest

from gaiaagent.sdk.decorators import aurc_agent, skill
from gaiaagent.core.identity import AgentDescriptor


class TestSkillDecorator:
    def test_basic_skill(self):
        class MyAgent:
            @skill("my-skill", description="Does something")
            async def do_something(self, query: str) -> dict:
                return {"result": query}

        agent = MyAgent()
        assert hasattr(agent.do_something, "_aurc_skill")
        meta = agent.do_something._aurc_skill
        assert meta.skill_id == "my-skill"
        assert meta.description == "Does something"

    def test_skill_default_id(self):
        class MyAgent:
            @skill()
            async def my_method(self) -> dict:
                return {}

        meta = MyAgent.my_method._aurc_skill
        assert meta.skill_id == "my_method"
        assert meta.name == "My Method"

    def test_skill_with_tags(self):
        class MyAgent:
            @skill("search", tags=["web", "nlp"])
            async def search(self) -> dict:
                return {}

        meta = MyAgent.search._aurc_skill
        assert meta.tags == ["web", "nlp"]

    def test_skill_input_schema_extraction(self):
        class MyAgent:
            @skill("test")
            async def test_method(self, query: str, depth: str = "medium") -> dict:
                return {}

        meta = MyAgent.test_method._aurc_skill
        assert "query" in meta.input_schema.properties
        assert "depth" in meta.input_schema.properties
        assert "query" in meta.input_schema.required
        assert "depth" not in meta.input_schema.required  # Has default

    def test_skill_to_declaration(self):
        class MyAgent:
            @skill("research", name="Research", description="Deep research")
            async def research(self) -> dict:
                return {}

        decl = MyAgent.research._aurc_skill.to_declaration()
        assert decl.skill_id == "research"
        assert decl.name == "Research"
        assert decl.description == "Deep research"

    @pytest.mark.asyncio
    async def test_skill_callable(self):
        class MyAgent:
            @skill("add")
            async def add(self, a: int, b: int) -> dict:
                return {"sum": a + b}

        agent = MyAgent()
        result = await agent.add(a=3, b=5)
        assert result == {"sum": 8}


class TestAURCAgentDecorator:
    def test_basic_agent(self):
        @aurc_agent(id="aurc:test/agent:v1.0", display_name="Test Agent")
        class TestAgent:
            @skill("do-stuff")
            async def do_stuff(self) -> dict:
                return {}

        assert hasattr(TestAgent, "_aurc_descriptor")
        desc = TestAgent._aurc_descriptor
        assert desc.aurc_id == "aurc:test/agent:v1.0"
        assert desc.display_name == "Test Agent"

    def test_agent_collects_skills(self):
        @aurc_agent(id="aurc:test/multi:v1.0")
        class MultiAgent:
            @skill("skill-a")
            async def a(self) -> dict:
                return {}

            @skill("skill-b")
            async def b(self) -> dict:
                return {}

        desc = MultiAgent._aurc_descriptor
        assert len(desc.capabilities.provides) == 2
        skill_ids = {s.skill_id for s in desc.capabilities.provides}
        assert skill_ids == {"skill-a", "skill-b"}

    def test_agent_with_protocols(self):
        @aurc_agent(
            id="aurc:test/bridged:v1.0",
            protocols=["mcp/2025-06-18", "a2a/1.0"],
        )
        class BridgedAgent:
            pass

        desc = BridgedAgent._aurc_descriptor
        assert desc.protocols.bridges == ["mcp/2025-06-18", "a2a/1.0"]
        assert desc.protocols.supports("mcp/2025-06-18") is True

    def test_agent_with_tags(self):
        @aurc_agent(id="aurc:test/tagged:v1.0", tags=["research", "nlp"])
        class TaggedAgent:
            pass

        desc = TaggedAgent._aurc_descriptor
        assert desc.tags == ["research", "nlp"]

    def test_agent_with_consumes(self):
        @aurc_agent(id="aurc:test/consumer:v1.0", consumes=["web-search", "db-reader"])
        class ConsumerAgent:
            pass

        desc = ConsumerAgent._aurc_descriptor
        assert desc.capabilities.consumes == ["web-search", "db-reader"]

    def test_agent_runtime_config(self):
        @aurc_agent(
            id="aurc:test/runtime:v1.0",
            max_concurrency=5,
            supports_pause=True,
            timeout_seconds=1800,
        )
        class RuntimeAgent:
            pass

        desc = RuntimeAgent._aurc_descriptor
        assert desc.runtime.max_concurrency == 5
        assert desc.runtime.supports_pause is True
        assert desc.runtime.timeout_seconds == 1800

    def test_agent_auth_config(self):
        @aurc_agent(
            id="aurc:test/auth:v1.0",
            auth_methods=["api_key", "oauth2"],
        )
        class AuthAgent:
            pass

        desc = AuthAgent._aurc_descriptor
        assert desc.auth.methods == ["api_key", "oauth2"]

    def test_agent_descriptor_property(self):
        @aurc_agent(id="aurc:test/prop:v1.0")
        class PropAgent:
            pass

        agent = PropAgent()
        assert agent.aurc_descriptor.aurc_id == "aurc:test/prop:v1.0"

    def test_agent_skills_dict(self):
        @aurc_agent(id="aurc:test/dict:v1.0")
        class DictAgent:
            @skill("alpha")
            async def alpha(self) -> dict:
                return {}

        assert "alpha" in DictAgent._aurc_skills
