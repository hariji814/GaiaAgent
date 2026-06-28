"""AURC conformance suite — defines what "AURC-compatible" means.
AURC 一致性套件 — 定义「AURC-compatible」的含义

A third-party implementation is conformant if its messages pass
:func:`run_conformance`. The suite has two layers:

1. **Structural** — the raw JSON message validates against the frozen
   wire-format JSON Schema (the polyglot contract in
   ``spec/aurc-message.schema.json``).
2. **Semantic** — protocol invariants the schema cannot express
   (correlation propagation, scope narrowing, TTL, error/result
   exclusivity, stream indexing).

The schema is generated from the pydantic model so it never drifts
silently; a drift-detection test forces re-publication on any
wire-format change.

Example:
    >>> from gaiaagent.conformance import run_conformance
    >>> report = run_conformance([msg_dict])
    >>> report.ok
    True
"""

from __future__ import annotations

from .runner import (
    ConformanceCheck,
    ConformanceReport,
    MessageReport,
    run_conformance,
    validate_message,
)
from .schema import (
    SCHEMA_DIALECT,
    SCHEMA_ID,
    SCHEMA_TITLE,
    generate_message_schema,
    published_schema_matches_model,
    validate_structure,
)

__all__ = [
    "ConformanceCheck",
    "ConformanceReport",
    "MessageReport",
    "SCHEMA_DIALECT",
    "SCHEMA_ID",
    "SCHEMA_TITLE",
    "generate_message_schema",
    "published_schema_matches_model",
    "run_conformance",
    "validate_message",
    "validate_structure",
]
