"""Tests for AURC core identity — AURC ID parsing and Agent Descriptor."""

import pytest

from gaiaagent.core.identity import (
    AURCId,
    AgentDescriptor,
    AuthDeclaration,
    Capabilities,
    InputOutputSchema,
    ProtocolSupport,
    RuntimeRequirements,
    SkillDeclaration,
)


class TestAURCId:
    """Tests for AURC ID parsing and validation."""

    def test_parse_valid_id(self):
        aid = AURCId.parse("aurc:gaia/researcher:v1.2")
        assert aid.namespace == "gaia"
        assert aid.name == "researcher"
        assert aid.version == "v1.2"
        assert str(aid) == "aurc:gaia/researcher:v1.2"

    def test_parse_valid_id_complex(self):
        aid = AURCId.parse("aurc:my-company/code-reviewer:v2.0.1")
        assert aid.namespace == "my-company"
        assert aid.name == "code-reviewer"
        assert aid.version == "v2.0.1"

    def test_parse_valid_id_single_version(self):
        aid = AURCId.parse("aurc:community/translator:v1")
        assert aid.version == "v1"

    def test_parse_invalid_no_prefix(self):
        with pytest.raises(ValueError, match="Invalid AURC ID"):
            AURCId.parse("gaia/researcher:v1.0")

    def test_parse_invalid_no_version(self):
        with pytest.raises(ValueError, match="Invalid AURC ID"):
            AURCId.parse("aurc:gaia/researcher")

    def test_parse_invalid_uppercase(self):
        with pytest.raises(ValueError, match="Invalid AURC ID"):
            AURCId.parse("aurc:Gaia/Researcher:v1.0")

    def test_parse_invalid_empty(self):
        with pytest.raises(ValueError, match="Invalid AURC ID"):
            AURCId.parse("")

    def test_equality(self):
        a = AURCId.parse("aurc:gaia/researcher:v1.0")
        b = AURCId.parse("aurc:gaia/researcher:v1.0")
        assert a == b
        assert a == "aurc:gaia/researcher:v1.0"

    def test_inequality(self):
        a = AURCId.parse("aurc:gaia/researcher:v1.0")
        b = AURCId.parse("aurc:gaia/researcher:v2.0")
        assert a != b

    def test_hash(self):
        a = AURCId.parse("aurc:gaia/researcher:v1.0")
        b = AURCId.parse("aurc:gaia/researcher:v1.0")
        assert hash(a) == hash(b)
        assert {a, b} == {a}

    def test_matches_wildcard(self):
        aid = AURCId.parse("aurc:gaia/researcher:v1.0")
        assert aid.matches("aurc:gaia/*")
        assert aid.matches("aurc:*/researcher:*")
        assert aid.matches("aurc:gaia/researcher:v1.*")
        assert not aid.matches("aurc:other/*")


class TestCapabilities:
    """Tests for capability declarations and matching."""

    def test_has_skill(self):
        caps = Capabilities(
            provides=[
                SkillDeclaration(skill_id="research", name="Research"),
                SkillDeclaration(skill_id="summarize", name="Summarize"),
            ]
        )
        assert caps.has_skill("research")
        assert caps.has_skill("summarize")
        assert not caps.has_skill("translate")

    def test_get_skill(self):
        skill = SkillDeclaration(skill_id="research", name="Research", description="Deep research")
        caps = Capabilities(provides=[skill])
        found = caps.get_skill("research")
        assert found is not None
        assert found.description == "Deep research"
        assert caps.get_skill("nonexistent") is None


class TestAgentDescriptor:
    """Tests for complete Agent Descriptor."""

    def _make_descriptor(self, **kwargs) -> AgentDescriptor:
        defaults = {
            "aurc_id": "aurc:gaia/test-agent:v1.0",
            "display_name": "Test Agent",
        }
        defaults.update(kwargs)
        return AgentDescriptor(**defaults)

    def test_create_minimal(self):
        desc = self._make_descriptor()
        assert desc.aurc_id == "aurc:gaia/test-agent:v1.0"
        assert desc.display_name == "Test Agent"
        assert desc.schema_version.startswith("aurc://")

    def test_create_full(self):
        desc = self._make_descriptor(
            description="A test agent",
            version="1.0.0",
            author="Test Author",
            capabilities=Capabilities(
                provides=[
                    SkillDeclaration(
                        skill_id="test-skill",
                        name="Test Skill",
                        input_schema=InputOutputSchema(
                            properties={"query": {"type": "string"}},
                            required=["query"],
                        ),
                    )
                ],
                consumes=["external-tool"],
            ),
            protocols=ProtocolSupport(
                bridges=["mcp/2025-06-18", "a2a/1.0"],
            ),
            runtime=RuntimeRequirements(
                max_concurrency=5,
                supports_pause=True,
            ),
            auth=AuthDeclaration(
                methods=["api_key", "oauth2"],
                scopes=["test:read"],
            ),
            tags=["test", "demo"],
        )
        assert desc.capabilities.has_skill("test-skill")
        assert desc.protocols.supports("mcp/2025-06-18")
        assert desc.protocols.supports("a2a/1.0")
        assert desc.runtime.supports_pause is True
        assert "test" in desc.tags

    def test_invalid_aurc_id(self):
        with pytest.raises(ValueError):
            self._make_descriptor(aurc_id="invalid-id")

    def test_parsed_id(self):
        desc = self._make_descriptor()
        parsed = desc.parsed_id
        assert parsed.namespace == "gaia"
        assert parsed.name == "test-agent"

    def test_to_registry_entry(self):
        desc = self._make_descriptor(
            capabilities=Capabilities(
                provides=[SkillDeclaration(skill_id="research", name="Research")],
            ),
            tags=["research"],
        )
        entry = desc.to_registry_entry()
        assert entry["aurc_id"] == "aurc:gaia/test-agent:v1.0"
        assert "research" in entry["capabilities"]["provides"]
        assert "research" in entry["tags"]
