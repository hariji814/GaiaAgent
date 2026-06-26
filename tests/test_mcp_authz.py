"""Tests for CapABAC authorization gating in AURCMCPStdioServer._handle_tools_call.

Verifies that when an authz_engine is configured, tool calls are authorized
before routing — denied calls return isError without invoking the skill.
"""

from __future__ import annotations

import json

import pytest

from gaiaagent.mcp.server import AURCMCPStdioServer
from gaiaagent.sdk.decorators import aurc_agent, skill
from gaiaagent.security.authz import (
    AgentPolicy,
    AuthorizationEngine,
    AuthorizationRule,
    Constraint,
)


@aurc_agent(
    id="aurc:test/authz-agent:v1.0",
    display_name="Authz Test Agent",
    description="test fixture",
)
class _AuthzTestAgent:
    @skill("greet", description="Greet a name")
    async def greet(self, name: str) -> dict:
        return {"message": f"hello {name}"}

    @skill("secret", description="Restricted skill")
    async def secret(self, key: str) -> dict:
        return {"secret": f"data-{key}"}


def _make_engine_with_policy(caller_id: str, allowed_tools: list[str]) -> AuthorizationEngine:
    engine = AuthorizationEngine()
    rules = [
        AuthorizationRule(
            resource_type=tool,
            actions=["call"],
        )
        for tool in allowed_tools
    ]
    engine.set_policy(caller_id, AgentPolicy(agent_id=caller_id, rules=rules))
    return engine


def _make_server_with_authz(
    caller_id: str = "aurc:test/caller:v1.0",
    allowed_tools: list[str] | None = None,
) -> AURCMCPStdioServer:
    if allowed_tools is None:
        allowed_tools = ["greet"]
    engine = _make_engine_with_policy(caller_id, allowed_tools)
    return AURCMCPStdioServer(
        _AuthzTestAgent(),
        authz_engine=engine,
        authz_caller_id=caller_id,
    )


class TestMCPAuthzGating:
    @pytest.mark.asyncio
    async def test_allowed_tool_passes_through(self):
        """Tool on the allowed list routes to the skill normally."""
        server = _make_server_with_authz(
            caller_id="aurc:test/caller:v1.0",
            allowed_tools=["greet"],
        )
        resp = await server.dispatch({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "greet", "arguments": {"name": "world"}},
        })
        result = resp["result"]
        assert result["isError"] is False
        payload = json.loads(result["content"][0]["text"])
        assert payload == {"message": "hello world"}

    @pytest.mark.asyncio
    async def test_denied_tool_returns_iserror(self):
        """Tool not on the allowed list is denied before routing."""
        server = _make_server_with_authz(
            caller_id="aurc:test/caller:v1.0",
            allowed_tools=["greet"],  # secret NOT allowed
        )
        resp = await server.dispatch({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "secret", "arguments": {"key": "k"}},
        })
        result = resp["result"]
        assert result["isError"] is True
        assert "denied" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_denied_tool_does_not_invoke_skill(self):
        """The skill handler must not be called when authz denies."""
        invoked = {"yes": False}

        @aurc_agent(
            id="aurc:test/authz-noop:v1.0",
            display_name="Noop",
            description="t",
        )
        class _NoopAgent:
            @skill("danger", description="d")
            async def danger(self) -> dict:
                invoked["yes"] = True
                return {"reached": True}

        engine = _make_engine_with_policy("caller", [])  # nothing allowed
        server = AURCMCPStdioServer(
            _NoopAgent(),
            authz_engine=engine,
            authz_caller_id="caller",
        )
        resp = await server.dispatch({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "danger", "arguments": {}},
        })
        assert resp["result"]["isError"] is True
        assert invoked["yes"] is False

    @pytest.mark.asyncio
    async def test_no_authz_engine_is_backward_compatible(self):
        """Without authz_engine, all tools are allowed (no regression)."""
        from tests.test_mcp_server import _MCPTestAgent
        server = AURCMCPStdioServer(_MCPTestAgent())  # no authz_engine
        resp = await server.dispatch({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "greet", "arguments": {"name": "x"}},
        })
        assert resp["result"]["isError"] is False

    @pytest.mark.asyncio
    async def test_constraint_based_denial(self):
        """Constraint on tool arguments can deny specific calls."""
        engine = AuthorizationEngine()
        caller = "aurc:test/constraint-caller:v1.0"
        engine.set_policy(caller, AgentPolicy(
            agent_id=caller,
            rules=[
                AuthorizationRule(
                    resource_type="greet",
                    actions=["call"],
                    constraints=[
                        Constraint("name", "ne", "forbidden"),
                    ],
                ),
            ],
        ))
        server = AURCMCPStdioServer(
            _AuthzTestAgent(),
            authz_engine=engine,
            authz_caller_id=caller,
        )

        # Allowed name
        resp_ok = await server.dispatch({
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "greet", "arguments": {"name": "alice"}},
        })
        assert resp_ok["result"]["isError"] is False

        # Denied name (constraint fails)
        resp_deny = await server.dispatch({
            "jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {"name": "greet", "arguments": {"name": "forbidden"}},
        })
        assert resp_deny["result"]["isError"] is True

    @pytest.mark.asyncio
    async def test_anonymous_caller_when_no_caller_id(self):
        """When authz_engine is set but authz_caller_id is not, uses 'mcp:anonymous'."""
        engine = AuthorizationEngine()
        # No policy for "mcp:anonymous" -> default deny
        server = AURCMCPStdioServer(
            _AuthzTestAgent(),
            authz_engine=engine,
            authz_caller_id=None,
        )
        resp = await server.dispatch({
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "greet", "arguments": {"name": "x"}},
        })
        assert resp["result"]["isError"] is True
        assert "mcp:anonymous" in resp["result"]["content"][0]["text"]
