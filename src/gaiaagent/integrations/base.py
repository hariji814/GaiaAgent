"""LoopBackend protocol — the formal contract for CLI agentic-loop backends.
LoopBackend 协议 —— CLI agentic-loop 后端的正式契约

Both ``claude_cli`` and ``codex_cli`` already implement the same adapter shape
(``run_agentic_loop``, ``cli_available``, ``prompt_too_long``,
``stop_reason_to_recovery_action``). This module formalizes that contract as a
:class:`LoopBackend` :class:`typing.Protocol` so that:

1. New backends can be validated against the contract at import time.
2. The ``backend="auto"`` selector in ``ClaudeLLM`` has a documented
   interface to check, rather than duck-typing by convention.
3. Static type checkers (mypy / pyright) can verify backend wiring.

This module does **not** refactor existing code — it only adds the contract
and a lightweight registry/validator on top.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class LoopBackend(Protocol):
    """Structural contract for a CLI agentic-loop backend.
    CLI agentic-loop 后端的结构化契约

    A backend module must expose these four callables (module-level
    functions). The Protocol is ``@runtime_checkable`` so
    ``isinstance(module, LoopBackend)`` works via structural typing.
    """

    def cli_available(self, cli_path: str | None = ...) -> bool: ...

    def prompt_too_long(self, prompt: str) -> bool: ...

    def stop_reason_to_recovery_action(self, stop_reason: str) -> Any: ...

    async def run_agentic_loop(self, **kwargs: Any) -> Any: ...


