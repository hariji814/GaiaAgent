"""Tests for AURC ContextStore and LocalRegistry."""

import pytest

from gaiaagent.core.identity import (
    AgentDescriptor,
    Capabilities,
    ProtocolSupport,
    SkillDeclaration,
)
from gaiaagent.core.types import ContextScope
from gaiaagent.harness.context import ContextStore
from gaiaagent.registry.local import LocalRegistry

# =============================================================================
# ContextStore Tests / 上下文存储测试
# =============================================================================


class TestContextStore:
    @pytest.fixture
    def store(self):
        return ContextStore()

    def test_save_and_load_session(self, store):
        store.save("key1", "value1", ContextScope.SESSION, agent_id="agent-1")
        assert store.load("key1", ContextScope.SESSION, agent_id="agent-1") == "value1"

    def test_save_and_load_agent(self, store):
        store.save("prefs", {"theme": "dark"}, ContextScope.AGENT, agent_id="agent-1")
        assert store.load("prefs", ContextScope.AGENT, agent_id="agent-1") == {"theme": "dark"}

    def test_save_and_load_shared(self, store):
        store.save("knowledge", ["fact1", "fact2"], ContextScope.SHARED)
        assert store.load("knowledge", ContextScope.SHARED) == ["fact1", "fact2"]

    def test_save_and_load_global(self, store):
        store.save("config", {"version": "0.1"}, ContextScope.GLOBAL)
        assert store.load("config", ContextScope.GLOBAL) == {"version": "0.1"}

    def test_load_missing_returns_default(self, store):
        assert store.load("missing", ContextScope.GLOBAL) is None
        assert store.load("missing", ContextScope.GLOBAL, default="fallback") == "fallback"

    def test_session_scope_isolation(self, store):
        """Different agents can't see each other's session context."""
        store.save("data", "agent1-data", ContextScope.SESSION, agent_id="agent-1")
        store.save("data", "agent2-data", ContextScope.SESSION, agent_id="agent-2")
        assert store.load("data", ContextScope.SESSION, agent_id="agent-1") == "agent1-data"
        assert store.load("data", ContextScope.SESSION, agent_id="agent-2") == "agent2-data"

    def test_update_existing(self, store):
        store.save("key", "v1", ContextScope.GLOBAL)
        store.save("key", "v2", ContextScope.GLOBAL)
        assert store.load("key", ContextScope.GLOBAL) == "v2"

    def test_delete(self, store):
        store.save("key", "value", ContextScope.GLOBAL)
        assert store.delete("key", ContextScope.GLOBAL) is True
        assert store.load("key", ContextScope.GLOBAL) is None

    def test_delete_nonexistent(self, store):
        assert store.delete("missing", ContextScope.GLOBAL) is False

    def test_list_keys(self, store):
        store.save("a", 1, ContextScope.GLOBAL)
        store.save("b", 2, ContextScope.GLOBAL)
        store.save("c", 3, ContextScope.GLOBAL)
        keys = store.list_keys(ContextScope.GLOBAL)
        assert sorted(keys) == ["a", "b", "c"]

    def test_list_keys_session_scope(self, store):
        store.save("x", 1, ContextScope.SESSION, agent_id="a1")
        store.save("y", 2, ContextScope.SESSION, agent_id="a1")
        store.save("z", 3, ContextScope.SESSION, agent_id="a2")
        assert sorted(store.list_keys(ContextScope.SESSION, agent_id="a1")) == ["x", "y"]
        assert store.list_keys(ContextScope.SESSION, agent_id="a2") == ["z"]

    def test_clear_scope(self, store):
        store.save("a", 1, ContextScope.GLOBAL)
        store.save("b", 2, ContextScope.GLOBAL)
        cleared = store.clear_scope(ContextScope.GLOBAL)
        assert cleared == 2
        assert store.list_keys(ContextScope.GLOBAL) == []

    def test_session_requires_agent_id(self, store):
        with pytest.raises(ValueError, match="agent_id is required"):
            store.save("key", "val", ContextScope.SESSION)

    def test_agent_requires_agent_id(self, store):
        with pytest.raises(ValueError, match="agent_id is required"):
            store.save("key", "val", ContextScope.AGENT)

    def test_get_stats(self, store):
        store.save("a", 1, ContextScope.GLOBAL)
        store.save("b", 2, ContextScope.SHARED)
        stats = store.get_stats()
        assert stats["global"] == 1
        assert stats["shared"] == 1
        assert stats["session"] == 0

    def test_deep_copy_isolation(self, store):
        """Values should be deep-copied on save."""
        original = {"list": [1, 2, 3]}
        store.save("data", original, ContextScope.GLOBAL)
        original["list"].append(4)
        loaded = store.load("data", ContextScope.GLOBAL)
        assert loaded == {"list": [1, 2, 3]}  # Not affected by mutation


# =============================================================================
# LocalRegistry Tests / 本地注册中心测试
# =============================================================================


def _make_descriptor(
    agent_id: str,
    skills: list[str] | None = None,
    tags: list[str] | None = None,
) -> AgentDescriptor:
    return AgentDescriptor(
        aurc_id=agent_id,
        display_name=f"Agent {agent_id}",
        capabilities=Capabilities(
            provides=[SkillDeclaration(skill_id=s, name=s) for s in (skills or [])],
        ),
        protocols=ProtocolSupport(bridges=["mcp/2025-06-18"]),
        tags=tags or [],
    )


class TestLocalRegistry:
    @pytest.fixture
    def registry(self):
        return LocalRegistry()

    def test_register(self, registry):
        desc = _make_descriptor("aurc:gaia/test:v1.0")
        entry = registry.register(desc)
        assert entry.agent_id == "aurc:gaia/test:v1.0"
        assert registry.count == 1

    def test_register_duplicate(self, registry):
        desc = _make_descriptor("aurc:gaia/test:v1.0")
        registry.register(desc)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(desc)

    def test_unregister(self, registry):
        desc = _make_descriptor("aurc:gaia/test:v1.0")
        registry.register(desc)
        registry.unregister("aurc:gaia/test:v1.0")
        assert registry.count == 0

    def test_unregister_nonexistent(self, registry):
        with pytest.raises(KeyError):
            registry.unregister("aurc:gaia/nonexistent:v1.0")

    def test_get(self, registry):
        desc = _make_descriptor("aurc:gaia/test:v1.0")
        registry.register(desc)
        entry = registry.get("aurc:gaia/test:v1.0")
        assert entry is not None
        assert entry.agent_id == "aurc:gaia/test:v1.0"

    def test_get_nonexistent(self, registry):
        assert registry.get("aurc:gaia/nonexistent:v1.0") is None

    def test_list_all(self, registry):
        registry.register(_make_descriptor("aurc:gaia/a:v1.0"))
        registry.register(_make_descriptor("aurc:gaia/b:v1.0"))
        assert len(registry.list_all()) == 2

    def test_find_by_skills(self, registry):
        registry.register(
            _make_descriptor("aurc:gaia/researcher:v1.0", skills=["research", "summarize"])
        )
        registry.register(_make_descriptor("aurc:gaia/coder:v1.0", skills=["code", "debug"]))
        matches = registry.find_by_skills(["research"])
        assert len(matches) >= 1
        assert matches[0].agent.aurc_id == "aurc:gaia/researcher:v1.0"

    def test_find_by_tag(self, registry):
        registry.register(_make_descriptor("aurc:gaia/a:v1.0", tags=["research", "nlp"]))
        registry.register(_make_descriptor("aurc:gaia/b:v1.0", tags=["code"]))
        found = registry.find_by_tag("research")
        assert len(found) == 1
        assert found[0].descriptor.aurc_id == "aurc:gaia/a:v1.0"

    def test_find_by_protocol(self, registry):
        registry.register(_make_descriptor("aurc:gaia/a:v1.0"))
        found = registry.find_by_protocol("mcp/2025-06-18")
        assert len(found) == 1

    def test_find_best(self, registry):
        registry.register(_make_descriptor("aurc:gaia/a:v1.0", skills=["research"]))
        registry.register(_make_descriptor("aurc:gaia/b:v1.0", skills=["research", "summarize"]))
        best = registry.find_best(["research", "summarize"])
        assert best is not None
        assert best.agent.aurc_id == "aurc:gaia/b:v1.0"

    def test_heartbeat(self, registry):
        desc = _make_descriptor("aurc:gaia/test:v1.0")
        registry.register(desc)
        old_heartbeat = registry.get("aurc:gaia/test:v1.0").last_heartbeat
        registry.heartbeat("aurc:gaia/test:v1.0")
        new_heartbeat = registry.get("aurc:gaia/test:v1.0").last_heartbeat
        assert new_heartbeat >= old_heartbeat

    def test_update_descriptor(self, registry):
        desc1 = _make_descriptor("aurc:gaia/test:v1.0", tags=["old"])
        registry.register(desc1)
        desc2 = _make_descriptor("aurc:gaia/test:v1.0", tags=["new"])
        registry.update_descriptor(desc2)
        entry = registry.get("aurc:gaia/test:v1.0")
        assert entry.descriptor.tags == ["new"]

    def test_export_to_dict(self, registry):
        registry.register(_make_descriptor("aurc:gaia/test:v1.0"))
        data = registry.export_to_dict()
        assert len(data) == 1
        assert data[0]["aurc_id"] == "aurc:gaia/test:v1.0"
