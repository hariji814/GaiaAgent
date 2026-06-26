"""AgentRegistry Protocol - the discovery contract any registry backend implements.

This decouples the in-memory LocalRegistry from the rest of the system, so a
SQLite or Redis-backed registry can drop in later without touching callers.
Phase 4.1 of the adoption plan: abstract the memory-state wall away.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..core.capability import CapabilityMatch
from ..core.identity import AgentDescriptor
from .local import RegistryEntry


@runtime_checkable
class AgentRegistry(Protocol):
    """Discovery contract for agent registries.

    LocalRegistry satisfies this today; a persistent backend (SQLite/Redis)
    needs only to implement these members to be a drop-in replacement.
    """

    def register(self, descriptor: AgentDescriptor) -> RegistryEntry: ...

    def unregister(self, agent_id: str) -> None: ...

    def update_descriptor(self, descriptor: AgentDescriptor) -> None: ...

    def get(self, agent_id: str) -> RegistryEntry | None: ...

    def list_all(self) -> list[RegistryEntry]: ...

    def list_descriptors(self) -> list[AgentDescriptor]: ...

    @property
    def count(self) -> int: ...

    def find_by_skills(
        self,
        required_skills: list[str],
        required_protocol: str | None = ...,
        tags: list[str] | None = ...,
    ) -> list[CapabilityMatch]: ...

    def find_by_tag(self, tag: str) -> list[RegistryEntry]: ...

    def find_by_protocol(self, protocol: str) -> list[RegistryEntry]: ...

    def find_best(
        self,
        required_skills: list[str],
        required_protocol: str | None = ...,
    ) -> CapabilityMatch | None: ...

    def heartbeat(self, agent_id: str) -> None: ...

    def evict_stale(self, ttl_seconds: float) -> list[str]: ...

    def export_to_dict(self) -> list[dict[str, object]]: ...
