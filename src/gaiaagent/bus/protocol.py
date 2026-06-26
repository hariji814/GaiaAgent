"""MessageBus Protocol - the dispatch contract any message bus backend implements.

LocalRegistry/MessageRouter satisfy this today; an out-of-process bus
(Redis pub/sub, Kafka, etc.) can drop in by implementing these members.
Phase 4.1 of the adoption plan.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..core.message import AURCMessage


@runtime_checkable
class MessageBus(Protocol):
    """Dispatch contract for message buses.

    MessageRouter satisfies this today; a distributed backend needs only to
    implement these members to be a drop-in replacement.
    """

    def register_handler(self, agent_id: str, handler: Any) -> None: ...

    def unregister_handler(self, agent_id: str) -> None: ...

    def has_handler(self, agent_id: str) -> bool: ...

    @property
    def handler_count(self) -> int: ...

    def subscribe(self, topic: str, subscriber: Any) -> None: ...

    def unsubscribe(self, topic: str, subscriber: Any) -> None: ...

    async def route(self, message: AURCMessage) -> AURCMessage: ...

    def dead_letter_queue(self) -> list[AURCMessage]: ...

    def clear_dead_letters(self) -> None: ...
