"""Tests for the AURC conformance suite.
AURC 一致性套件测试

Two roles:
1. Self-test the suite — valid corpus passes, each invariant has a negative
   case that fails it, drift detection catches a stale schema.
2. Document, via the valid corpus, what a conformant AURC message looks like
   on the wire (the corpus doubles as a polyglot reference).
"""

from __future__ import annotations

import copy
import json

import pytest

from gaiaagent.bus.codec import JSONCodec, NDJSONCodec
from gaiaagent.conformance import (
    ConformanceReport,
    generate_message_schema,
    published_schema_matches_model,
    run_conformance,
    validate_message,
    validate_structure,
)
from gaiaagent.conformance.invariants import (
    check_cross_message_response_symmetry,
    inv_correlation_on_response,
    inv_delegation_narrows,
    inv_error_result_exclusive,
    inv_message_id_nonempty,
    inv_source_target_nonempty,
    inv_stream_chunk_index,
    inv_ttl_positive,
)
from gaiaagent.core.message import AURCMessage, MessageBody, MessageSecurity
from gaiaagent.core.types import MessageDirection

# ---------------------------------------------------------------------------
# Corpus builders / 语料构建器
# ---------------------------------------------------------------------------


def _wire(msg: AURCMessage) -> dict:
    """The canonical wire form: model_dump(mode="json"). 规范线缆形态"""
    return msg.model_dump(mode="json")


def request_msg() -> AURCMessage:
    return AURCMessage(
        source="aurc:demo/a:v1.0",
        target="aurc:demo/b:v1.0",
        type=MessageDirection.REQUEST,
        correlation_id="corr-1",
        body=MessageBody(method="invoke", skill="calc.add", params={"a": 2, "b": 2}),
    )


def response_msg() -> AURCMessage:
    return AURCMessage(
        source="aurc:demo/b:v1.0",
        target="aurc:demo/a:v1.0",
        type=MessageDirection.RESPONSE,
        correlation_id="corr-1",
        body=MessageBody(result=4, metadata={"in_response_to": "msg-x"}),
    )


def error_response_msg() -> AURCMessage:
    from gaiaagent.core.message import ErrorInfo

    return AURCMessage(
        source="aurc:demo/b:v1.0",
        target="aurc:demo/a:v1.0",
        type=MessageDirection.RESPONSE,
        correlation_id="corr-1",
        body=MessageBody(error=ErrorInfo(code="tool_not_found", message="nope")),
    )


def notification_msg() -> AURCMessage:
    return AURCMessage(
        source="aurc:demo/a:v1.0",
        target="aurc:demo/b:v1.0",
        type=MessageDirection.NOTIFICATION,
        body=MessageBody(event="agent.ready", data={"state": "ready"}),
    )


def stream_chunk_msg(is_final: bool = False, index: int = 0) -> AURCMessage:
    return AURCMessage(
        source="aurc:demo/b:v1.0",
        target="aurc:demo/a:v1.0",
        type=MessageDirection.STREAM,
        correlation_id="corr-1",
        body=MessageBody(chunk_index=index, total_chunks=3, data="chunk", is_final=is_final),
    )


def delegation_msg() -> AURCMessage:
    from datetime import datetime, timezone

    from gaiaagent.core.message import DelegationHop

    return AURCMessage(
        source="aurc:demo/a:v1.0",
        target="aurc:demo/c:v1.0",
        type=MessageDirection.DELEGATION,
        correlation_id="corr-d",
        security=MessageSecurity(
            scopes=["read", "write"],
            delegation_chain=[
                DelegationHop(
                    from_agent="aurc:demo/a:v1.0",
                    to_agent="aurc:demo/b:v1.0",
                    scopes=["read", "write"],
                    timestamp=datetime.now(timezone.utc),
                ),
                DelegationHop(
                    from_agent="aurc:demo/b:v1.0",
                    to_agent="aurc:demo/c:v1.0",
                    scopes=["read"],
                    timestamp=datetime.now(timezone.utc),
                ),
            ],
        ),
    )


def valid_corpus() -> list[dict]:
    """One conformant message per type — the polyglot reference.
    每种类型一条合规消息 — 多语言参考"""
    return [
        _wire(request_msg()),
        _wire(response_msg()),
        _wire(error_response_msg()),
        _wire(notification_msg()),
        _wire(stream_chunk_msg()),
        _wire(stream_chunk_msg(is_final=True, index=2)),
        _wire(delegation_msg()),
    ]


# ---------------------------------------------------------------------------
# Structural + full-suite on the valid corpus / 合规语料的结构与全量套件
# ---------------------------------------------------------------------------


class TestValidCorpus:
    def test_each_message_is_structurally_valid(self) -> None:
        for msg in valid_corpus():
            assert validate_structure(msg) == [], validate_structure(msg)

    def test_full_suite_passes(self) -> None:
        report = run_conformance(valid_corpus())
        assert report.ok, report.summary()
        assert report.failed == 0
        assert report.passed == len(valid_corpus())

    def test_single_message_validator(self) -> None:
        assert validate_message(_wire(request_msg())).passed

    def test_response_symmetry_holds_for_paired_corpus(self) -> None:
        corpus = [_wire(request_msg()), _wire(response_msg())]
        assert check_cross_message_response_symmetry(corpus) == []


# ---------------------------------------------------------------------------
# Structural negatives / 结构性反例
# ---------------------------------------------------------------------------


class TestStructureNegatives:
    def test_missing_required_target_is_rejected(self) -> None:
        msg = _wire(request_msg())
        del msg["target"]
        assert validate_structure(msg), "expected structural errors"

    def test_bad_enum_is_rejected(self) -> None:
        msg = _wire(request_msg())
        msg["type"] = "not-a-direction"
        assert validate_structure(msg), "expected structural errors"

    def test_wrong_type_for_ttl_is_rejected(self) -> None:
        msg = _wire(request_msg())
        msg["routing"]["ttl_hops"] = "five"
        assert validate_structure(msg), "expected structural errors"


# ---------------------------------------------------------------------------
# Per-message invariant negatives / 单消息不变式反例
# ---------------------------------------------------------------------------


def _set(msg: dict, path: list, value: object) -> dict:
    """Mutate a nested field on a copy and return it. 在副本上改嵌套字段"""
    out = copy.deepcopy(msg)
    node = out
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return out


def _del(msg: dict, path: list) -> dict:
    out = copy.deepcopy(msg)
    node = out
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    return out


class TestInvariants:
    def test_message_id_nonempty(self) -> None:
        msg = _wire(request_msg())
        assert inv_message_id_nonempty(msg) == []
        msg["message_id"] = ""
        assert inv_message_id_nonempty(msg)

    def test_source_target_nonempty(self) -> None:
        msg = _wire(request_msg())
        assert inv_source_target_nonempty(msg) == []
        msg["source"] = ""
        assert inv_source_target_nonempty(msg)

    def test_ttl_positive(self) -> None:
        msg = _wire(request_msg())
        assert inv_ttl_positive(msg) == []
        msg["routing"]["ttl_hops"] = 0
        assert inv_ttl_positive(msg)
        msg["routing"]["ttl_hops"] = -1
        assert inv_ttl_positive(msg)
        msg["routing"]["ttl_hops"] = True  # bool must not count as int here
        assert inv_ttl_positive(msg)

    def test_correlation_required_on_response(self) -> None:
        resp = _wire(response_msg())
        assert inv_correlation_on_response(resp) == []
        resp["correlation_id"] = None
        assert inv_correlation_on_response(resp)
        # A request without correlation is fine.
        req = _wire(request_msg())
        req["correlation_id"] = None
        assert inv_correlation_on_response(req) == []

    def test_error_result_exclusive(self) -> None:
        resp = _wire(response_msg())
        assert inv_error_result_exclusive(resp) == []
        bad = _set(resp, ["body", "error"], {"code": "x", "message": "y"})
        assert inv_error_result_exclusive(bad), "both error and result set"

    def test_delegation_narrows(self) -> None:
        msg = _wire(delegation_msg())
        assert inv_delegation_narrows(msg) == []
        # Widen the second hop's scopes -> violation.
        msg["security"]["delegation_chain"][1]["scopes"] = ["read", "write", "admin"]
        assert inv_delegation_narrows(msg)

    def test_stream_chunk_index(self) -> None:
        msg = _wire(stream_chunk_msg())
        assert inv_stream_chunk_index(msg) == []
        msg["body"]["chunk_index"] = 5  # >= total_chunks (3)
        assert inv_stream_chunk_index(msg)
        msg["body"]["chunk_index"] = -1
        assert inv_stream_chunk_index(msg)

    def test_invariant_failure_fails_the_report(self) -> None:
        msg = _wire(request_msg())
        msg["routing"]["ttl_hops"] = 0
        report = run_conformance([msg])
        assert not report.ok
        names = {c.name for c in report.messages[0].checks if not c.passed}
        assert "ttl_positive" in names


# ---------------------------------------------------------------------------
# Cross-message invariant negatives / 跨消息不变式反例
# ---------------------------------------------------------------------------


class TestCrossMessage:
    def test_response_source_must_equal_request_target(self) -> None:
        req = _wire(request_msg())  # target = aurc:demo/b:v1.0
        resp = _wire(response_msg())  # source = aurc:demo/b:v1.0 (matches)
        assert check_cross_message_response_symmetry([req, resp]) == []
        # Invert the response source -> mismatch.
        resp["source"] = "aurc:demo/other:v1.0"
        assert check_cross_message_response_symmetry([req, resp])

    def test_unpaired_response_is_not_a_symmetry_violation(self) -> None:
        resp = _wire(response_msg())
        # No matching request in the corpus; must not falsely flag symmetry.
        assert check_cross_message_response_symmetry([resp]) == []


# ---------------------------------------------------------------------------
# Schema drift detection / schema 漂移检测
# ---------------------------------------------------------------------------


class TestSchemaDrift:
    def test_published_matches_model(self) -> None:
        assert published_schema_matches_model(), (
            "spec/aurc-message.schema.json is stale — regenerate via "
            "`python scripts/generate_schema.py`"
        )

    def test_schema_has_canonical_markers(self) -> None:
        schema = generate_message_schema()
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"] == "https://gaiaagent.dev/spec/aurc-message.schema.json"
        assert schema["title"] == "AURCMessage"

    def test_stale_published_file_is_detected(self, tmp_path, monkeypatch) -> None:
        # Point the published-path resolver at a tampered file and confirm
        # the drift check flips to False.
        # 将 published 路径解析器指向被篡改的文件，确认漂移检测翻为 False。
        tampered = tmp_path / "aurc-message.schema.json"
        tampered.write_text(json.dumps({"title": "tampered"}), encoding="utf-8")
        monkeypatch.setattr(
            "gaiaagent.conformance.schema.PUBLISHED_SCHEMA_PATH", tampered
        )
        assert not published_schema_matches_model()


# ---------------------------------------------------------------------------
# Codec round-trip fidelity / 编解码往返保真
# ---------------------------------------------------------------------------


class TestCodecRoundTrip:
    @pytest.mark.parametrize(
        "builder",
        [
            request_msg, response_msg, error_response_msg,
            notification_msg, stream_chunk_msg, delegation_msg,
        ],
    )
    def test_json_roundtrip_preserves_wire_form(self, builder) -> None:
        msg = builder()
        wire = _wire(msg)
        decoded = JSONCodec.decode(JSONCodec.encode(msg)).model_dump(mode="json")
        assert decoded == wire

    def test_ndjson_roundtrip(self) -> None:
        # Build once so message_id/timestamp are identical on both sides.
        # 只构建一次，确保两侧 message_id/timestamp 一致。
        msgs = [request_msg(), response_msg()]
        encoded = NDJSONCodec.encode_stream(msgs)
        decoded = NDJSONCodec.decode_stream(encoded)
        assert [m.model_dump(mode="json") for m in decoded] == [_wire(msgs[0]), _wire(msgs[1])]

    def test_roundtrip_message_is_conformant(self) -> None:
        # A message that survives a JSON codec round-trip must still conform.
        # 经 JSON 编解码往返后仍存活的消息必须仍合规。
        msg = request_msg()
        decoded = JSONCodec.decode(JSONCodec.encode(msg))
        report = run_conformance([decoded.model_dump(mode="json")])
        assert report.ok, report.summary()


# ---------------------------------------------------------------------------
# Report structure / 报告结构
# ---------------------------------------------------------------------------


class TestReportShape:
    def test_empty_corpus_is_ok(self) -> None:
        report: ConformanceReport = run_conformance([])
        assert report.ok
        assert report.total == 0
        assert report.summary().startswith("PASS")

    def test_report_exposes_check_names(self) -> None:
        report = run_conformance([_wire(request_msg())])
        names = [c.name for c in report.messages[0].checks]
        assert "structure" in names
        assert "ttl_positive" in names
        assert "delegation_narrows" in names
        # Cross-message check is present even for a single message.
        assert [c.name for c in report.cross_message_checks] == ["response_symmetry"]
