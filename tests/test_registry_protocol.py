"""Phase 4.1 tests: registry/bus Protocol contracts + TTL eviction.

Verifies that LocalRegistry satisfies the AgentRegistry Protocol and
MessageRouter satisfies the MessageBus Protocol (so a persistent backend
can drop in later), and that stale agents are evicted by TTL.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from gaiaagent.bus.protocol import MessageBus
from gaiaagent.bus.router import MessageRouter
from gaiaagent.core.identity import AgentDescriptor
from gaiaagent.registry.local import LocalRegistry
from gaiaagent.registry.protocol import AgentRegistry


def _descriptor(sample_descriptor: AgentDescriptor, aid: str) -> AgentDescriptor:
    """Clone the shared fixture descriptor with a different aurc_id."""
    return sample_descriptor.model_copy(update={"aurc_id": aid})


class TestProtocolConformance:
    """LocalRegistry/MessageRouter satisfy their Protocol contracts."""

    def test_local_registry_is_agent_registry(self):
        reg: AgentRegistry = LocalRegistry()
        assert isinstance(reg, AgentRegistry)

    def test_message_router_is_message_bus(self):
        bus: MessageBus = MessageRouter()
        assert isinstance(bus, MessageBus)


class TestEvictStale:
    """Stale agents are evicted by TTL; fresh agents survive."""

    def test_no_eviction_when_all_fresh(self, sample_descriptor):
        reg = LocalRegistry()
        reg.register(_descriptor(sample_descriptor, "a1"))
        evicted = reg.evict_stale(ttl_seconds=3600)
        assert evicted == []
        assert reg.count == 1

    def test_evicts_stale_agent(self, sample_descriptor):
        reg = LocalRegistry()
        reg.register(_descriptor(sample_descriptor, "a1"))
        entry = reg.get("a1")
        assert entry is not None
        entry.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=120)
        evicted = reg.evict_stale(ttl_seconds=60)
        assert evicted == ["a1"]
        assert reg.count == 0
        assert reg.get("a1") is None

    def test_partial_eviction_keeps_fresh(self, sample_descriptor):
        reg = LocalRegistry()
        reg.register(_descriptor(sample_descriptor, "fresh"))
        reg.register(_descriptor(sample_descriptor, "stale"))
        stale = reg.get("stale")
        assert stale is not None
        stale.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=999)
        evicted = reg.evict_stale(ttl_seconds=60)
        assert evicted == ["stale"]
        assert reg.count == 1
        assert reg.get("fresh") is not None

    def test_zero_ttl_evicts_nothing(self, sample_descriptor):
        reg = LocalRegistry()
        reg.register(_descriptor(sample_descriptor, "a1"))
        assert reg.evict_stale(ttl_seconds=0) == []
        assert reg.count == 1
