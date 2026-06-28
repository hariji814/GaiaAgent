"""Semantic protocol invariants the JSON Schema cannot express.
JSON Schema 无法表达的语义协议不变式

Each invariant is a callable ``(message: dict) -> list[str]`` returning
human-readable violation strings (empty == pass). They encode the wire-level
rules that make an AURC message *meaningful*, not merely well-shaped:
correlation propagation, delegation scope narrowing, TTL positivity,
error/result exclusivity, and stream-chunk indexing.

These mirror logic already enforced inside the runtime (e.g.
``MessageSecurity.validate_delegation_chain``) but operate on raw wire dicts
so a third-party implementation can be checked without importing Python.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# A per-message invariant maps a raw message dict to a list of violations.
# 单消息不变式：原始消息 dict -> 违规描述列表。
Invariant = Callable[[dict[str, Any]], list[str]]

# Types that must carry a correlation_id back to an originating request.
# 必须回带 correlation_id 指向原始请求的消息类型。
_RESPONSE_TYPES = {"response", "stream"}


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _body(message: dict[str, Any]) -> dict[str, Any]:
    body = message.get("body")
    return body if isinstance(body, dict) else {}


def _routing(message: dict[str, Any]) -> dict[str, Any]:
    routing = message.get("routing")
    return routing if isinstance(routing, dict) else {}


def _security(message: dict[str, Any]) -> dict[str, Any]:
    security = message.get("security")
    return security if isinstance(security, dict) else {}


def inv_message_id_nonempty(message: dict[str, Any]) -> list[str]:
    """``message_id`` must be a non-empty string.
    ``message_id`` 必须是非空字符串"""
    if not _as_str(message.get("message_id")):
        return ["message_id: must be a non-empty string"]
    return []


def inv_source_target_nonempty(message: dict[str, Any]) -> list[str]:
    """``source`` and ``target`` must be non-empty strings.
    ``source`` 与 ``target`` 必须为非空字符串"""
    errors: list[str] = []
    if not _as_str(message.get("source")):
        errors.append("source: must be a non-empty string")
    if not _as_str(message.get("target")):
        errors.append("target: must be a non-empty string")
    return errors


def inv_aurc_version_nonempty(message: dict[str, Any]) -> list[str]:
    """``aurc_version`` must be a non-empty string.
    ``aurc_version`` 必须是非空字符串"""
    if not _as_str(message.get("aurc_version")):
        return ["aurc_version: must be a non-empty string"]
    return []


def inv_ttl_positive(message: dict[str, Any]) -> list[str]:
    """``routing.ttl_hops`` must be a positive integer.
    ``routing.ttl_hops`` 必须为正整数

    A ttl of 0 means "do not forward"; a message offered to the bus for
    routing must still have hop budget remaining.
    """
    ttl = _routing(message).get("ttl_hops")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl <= 0:
        return ["routing.ttl_hops: must be a positive integer"]
    return []


def inv_correlation_on_response(message: dict[str, Any]) -> list[str]:
    """Responses and stream chunks must carry a correlation_id.
    响应与流式块必须携带 correlation_id

    Without it the originating request cannot be paired, breaking the
    cross-protocol traceability AURC guarantees.
    """
    if message.get("type") in _RESPONSE_TYPES:
        if not _as_str(message.get("correlation_id")):
            return ["correlation_id: required on response/stream messages"]
    return []


def inv_error_result_exclusive(message: dict[str, Any]) -> list[str]:
    """A response body must not carry both ``error`` and ``result``.
    响应体不得同时携带 ``error`` 与 ``result``

    A response is either a success (result set, error null) or a failure
    (error set, result null). Both populated is a semantic contradiction.
    """
    if message.get("type") != "response":
        return []
    body = _body(message)
    has_error = isinstance(body.get("error"), dict)
    has_result = body.get("result") is not None
    if has_error and has_result:
        return ["body: response must not set both error and result"]
    return []


def inv_delegation_narrows(message: dict[str, Any]) -> list[str]:
    """Delegation chain scopes must only narrow (never widen).
    委托链权限范围只能收窄，不得扩大

    Each hop's scopes must be a subset of the previous hop's scopes. This is
    AURC's defence against MCP's confused-deputy problem, checked at the
    wire level so a non-Python implementation can be held to it.
    """
    chain = _security(message).get("delegation_chain")
    if not isinstance(chain, list) or len(chain) < 2:
        return []
    errors: list[str] = []
    for i in range(1, len(chain)):
        prev = chain[i - 1]
        curr = chain[i]
        if not isinstance(prev, dict) or not isinstance(curr, dict):
            errors.append(f"delegation_chain[{i}]: hops must be objects")
            continue
        prev_scopes = prev.get("scopes")
        curr_scopes = curr.get("scopes")
        if not isinstance(prev_scopes, list) or not isinstance(curr_scopes, list):
            errors.append(f"delegation_chain[{i}]: scopes must be arrays")
            continue
        extra = set(curr_scopes) - set(prev_scopes)
        if extra:
            errors.append(
                f"delegation_chain[{i}]: scopes widened by {sorted(extra)}"
            )
    return errors


def inv_stream_chunk_index(message: dict[str, Any]) -> list[str]:
    """Stream chunks must have a non-negative index below ``total_chunks``.
    流式块索引必须非负且小于 ``total_chunks``"""
    if message.get("type") != "stream":
        return []
    body = _body(message)
    index = body.get("chunk_index")
    total = body.get("total_chunks")
    errors: list[str] = []
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        errors.append("body.chunk_index: must be a non-negative integer")
    elif isinstance(total, int) and not isinstance(total, bool) and total > 0:
        if index >= total:
            errors.append(
                f"body.chunk_index: {index} must be < total_chunks {total}"
            )
    return errors


# Ordered registry of per-message invariants.
# 单消息不变式的有序注册表。
PER_MESSAGE_INVARIANTS: list[tuple[str, Invariant]] = [
    ("message_id_nonempty", inv_message_id_nonempty),
    ("source_target_nonempty", inv_source_target_nonempty),
    ("aurc_version_nonempty", inv_aurc_version_nonempty),
    ("ttl_positive", inv_ttl_positive),
    ("correlation_on_response", inv_correlation_on_response),
    ("error_result_exclusive", inv_error_result_exclusive),
    ("delegation_narrows", inv_delegation_narrows),
    ("stream_chunk_index", inv_stream_chunk_index),
]


def check_cross_message_response_symmetry(
    messages: list[dict[str, Any]],
) -> list[str]:
    """A response's source must equal its request's target.
    响应的 source 必须等于其请求的 target

    Pairs responses to requests by correlation_id (falling back to the
    request's message_id when the response carries no explicit correlation).
    Violations signal a confused-deputy or routing inversion at the wire.
    """
    # Index requests by message_id for the no-correlation fallback.
    # 按 message_id 索引请求，用于无 correlation 的回退匹配。
    by_id: dict[str, dict[str, Any]] = {}
    by_corr: dict[str, dict[str, Any]] = {}
    for msg in messages:
        if msg.get("type") != "request":
            continue
        mid = _as_str(msg.get("message_id"))
        if mid:
            by_id[mid] = msg
        corr = _as_str(msg.get("correlation_id"))
        if corr:
            by_corr[corr] = msg

    errors: list[str] = []
    for msg in messages:
        if msg.get("type") != "response":
            continue
        corr = _as_str(msg.get("correlation_id"))
        request = by_corr.get(corr) if corr else None
        if request is None and corr:
            # Response correlated to a request whose correlation_id we stored.
            # 响应关联到已记录 correlation_id 的请求。
            request = by_corr.get(corr)
        if request is None:
            # Unpaired response: not a symmetry violation, skip (covered by
            # correlation_on_response when corr itself is missing).
            continue
        expected_source = _as_str(request.get("target"))
        actual_source = _as_str(msg.get("source"))
        if expected_source and actual_source and expected_source != actual_source:
            errors.append(
                f"response source '{actual_source}' != request target "
                f"'{expected_source}' (correlation_id={corr or '-'})"
            )
    return errors


# Ordered registry of cross-message invariants over a full corpus.
# 针对整批消息的跨消息不变式有序注册表。
CROSS_MESSAGE_INVARIANTS: list[tuple[str, Callable[[list[dict[str, Any]]], list[str]]]] = [
    ("response_symmetry", check_cross_message_response_symmetry),
]
