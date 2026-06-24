"""Shared test fixtures."""

import pytest

from gaiaagent.core.identity import (
    AgentDescriptor,
    Capabilities,
    ProtocolSupport,
    RuntimeRequirements,
    SkillDeclaration,
    InputOutputSchema,
)


@pytest.fixture
def sample_descriptor() -> AgentDescriptor:
    """A sample Agent Descriptor for testing."""
    return AgentDescriptor(
        aurc_id="aurc:gaia/test-agent:v1.0",
        display_name="Test Agent",
        description="A test agent for unit testing",
        version="1.0.0",
        capabilities=Capabilities(
            provides=[
                SkillDeclaration(
                    skill_id="test-skill",
                    name="Test Skill",
                    description="A test skill",
                    input_schema=InputOutputSchema(
                        properties={"query": {"type": "string"}},
                        required=["query"],
                    ),
                ),
            ],
            consumes=["external-tool"],
        ),
        protocols=ProtocolSupport(
            bridges=["mcp/2025-06-18"],
        ),
        runtime=RuntimeRequirements(
            max_concurrency=5,
            supports_pause=True,
        ),
        tags=["test", "unit-test"],
    )
