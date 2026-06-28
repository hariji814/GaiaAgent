"""Frozen wire-format JSON Schema for AURCMessage.
AURC 消息冻结线缆格式 JSON Schema

The schema is the polyglot contract: TS/Go/Rust SDKs and the conformance
suite validate raw wire JSON against it. It is generated from the pydantic
``AURCMessage`` model via :func:`generate_message_schema`, so it can never
silently drift from the Python implementation. The published snapshot lives
at ``spec/aurc-message.schema.json`` and is drift-checked by
:func:`published_schema_matches_model`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..core.message import AURCMessage

# JSON Schema dialect / JSON Schema 方言
SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
# Stable canonical identifier for the published artifact / 已发布制品的稳定规范标识
SCHEMA_ID = "https://gaiaagent.dev/spec/aurc-message.schema.json"
SCHEMA_TITLE = "AURCMessage"
SCHEMA_DESCRIPTION = (
    "Frozen AURC v0.1 wire-format contract. Generated from "
    "gaiaagent.core.message.AURCMessage. Polyglot SDKs (TS/Go/Rust) and "
    "the AURC conformance suite validate messages against this artifact."
)

# Repository location of the published snapshot / 仓库内已发布快照位置
PUBLISHED_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "spec" / "aurc-message.schema.json"
)


def generate_message_schema() -> dict[str, Any]:
    """Build the canonical AURC wire-format schema from the model.
    从模型生成规范的 AURC 线缆格式 schema

    Deterministic and stable: identical input model -> identical dict, so a
    drift test can diff it against the published snapshot byte-for-byte.
    """
    schema = AURCMessage.model_json_schema()
    schema["$schema"] = SCHEMA_DIALECT
    schema["$id"] = SCHEMA_ID
    schema["title"] = SCHEMA_TITLE
    schema["description"] = SCHEMA_DESCRIPTION
    # Stable top-level key order for reproducible publication.
    # 稳定的顶层键序，保证发布物可复现。
    ordered: dict[str, Any] = {
        "$schema": schema["$schema"],
        "$id": schema["$id"],
        "title": schema["title"],
        "description": schema["description"],
    }
    for key, value in schema.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def published_schema_matches_model() -> bool:
    """Return True iff the published snapshot equals the model-generated schema.
    已发布快照与模型生成 schema 一致时返回 True

    Best-effort: when the snapshot file is absent (e.g. installed wheel
    without the repo ``spec/`` tree), returns True so installs are not
    broken. From a source checkout the file is present and drift is caught.
    """
    if not PUBLISHED_SCHEMA_PATH.is_file():
        return True
    try:
        published = json.loads(PUBLISHED_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(published == generate_message_schema())


def write_schema() -> None:
    """Regenerate and write the published schema snapshot.
    重新生成并写入已发布 schema 快照

    Idempotent: the result always round-trips through
    :func:`published_schema_matches_model`.
    """
    schema = generate_message_schema()
    text = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
    PUBLISHED_SCHEMA_PATH.write_text(text, encoding="utf-8")


def _load_validator() -> Any | None:
    """Import ``jsonschema`` lazily; return None if unavailable.
    惰性导入 ``jsonschema``，不可用则返回 None

    ``jsonschema`` is an optional dependency (the ``conformance`` extra).
    When absent, structural validation degrades to a pydantic fallback.
    """
    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:
        return None
    return jsonschema


def validate_structure(message: dict[str, Any]) -> list[str]:
    """Validate a raw wire-JSON message against the frozen schema.
    依据冻结 schema 校验原始线缆 JSON 消息

    Returns a list of human-readable error strings (empty == valid). Uses
    ``jsonschema`` against the published contract when available; otherwise
    falls back to pydantic ``model_validate`` (degraded: no strict format
    checking, pydantic coercion semantics).
    """
    schema = generate_message_schema()
    errors: list[str] = []

    jsonschema = _load_validator()
    if jsonschema is not None:
        validator_cls = jsonschema.Draft202012Validator
        try:
            format_checker = jsonschema.FormatChecker()
        except AttributeError:  # very old jsonschema / stub
            format_checker = None
        validator = validator_cls(schema, format_checker=format_checker)
        for err in sorted(validator.iter_errors(message), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
            errors.append(f"schema: {loc}: {err.message}")
        return errors

    # Degraded fallback: pydantic. 降级回退：pydantic。
    try:
        AURCMessage.model_validate(message)
    except ValidationError as exc:
        for err in exc.errors():
            loc = "/".join(str(p) for p in err["loc"]) or "<root>"
            errors.append(f"pydantic(fallback): {loc}: {err['msg']}")
    return errors
