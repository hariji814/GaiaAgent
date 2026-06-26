"""Phase 4.2 tests: AuditSink Protocol + FileAuditSink real-time persistence.

Verifies the sink abstraction, that AuditLog delegates correctly, and that
FileAuditSink writes entries to disk in real time with size-based rotation.
"""
from __future__ import annotations

import json

from gaiaagent.security.audit import AuditAction, AuditLog, AuditSeverity
from gaiaagent.security.audit_sink import (
    AuditSink,
    FileAuditSink,
    MemoryAuditSink,
)


def _entry(action=AuditAction.MESSAGE_SENT, agent_id="a1"):
    from gaiaagent.security.audit import AuditEntry

    return AuditEntry(action=action, agent_id=agent_id, severity=AuditSeverity.INFO)


class TestProtocolConformance:
    def test_memory_sink_is_audit_sink(self):
        assert isinstance(MemoryAuditSink(), AuditSink)

    def test_file_sink_is_audit_sink(self, tmp_path):
        assert isinstance(FileAuditSink(tmp_path / "a.jsonl"), AuditSink)


class TestFileAuditSink:
    def test_real_time_write(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        sink = FileAuditSink(path)
        e = _entry()
        sink.append(e)
        # File exists immediately with one JSON line.
        assert path.exists()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["action"] == "message_sent"
        assert rec["agent_id"] == "a1"

    def test_rotation_on_size(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        # Tiny max_bytes so a single entry triggers rotation on the next append.
        sink = FileAuditSink(path, max_bytes=1)
        sink.append(_entry())
        sink.append(_entry())  # this append should rotate then write fresh
        rotated = tmp_path / "audit.jsonl.1"
        assert rotated.exists(), "rotated file should exist"
        # The rotated file has the first entry; the active file has the second.
        assert len(rotated.read_text(encoding="utf-8").strip().splitlines()) == 1
        assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 1

    def test_entries_buffer(self, tmp_path):
        sink = FileAuditSink(tmp_path / "a.jsonl")
        sink.append(_entry(agent_id="x"))
        sink.append(_entry(agent_id="y"))
        ids = [e.agent_id for e in sink.entries()]
        assert ids == ["x", "y"]
        assert sink.count == 2

    def test_clear(self, tmp_path):
        sink = FileAuditSink(tmp_path / "a.jsonl")
        sink.append(_entry())
        assert sink.clear() == 1
        assert sink.count == 0


class TestAuditLogDelegation:
    def test_default_is_memory_sink(self):
        log = AuditLog()
        log.log(action=AuditAction.AGENT_REGISTERED, agent_id="a")
        assert log.count == 1
        assert log.get_recent(10)[0].agent_id == "a"

    def test_file_sink_backed_log_persists(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        log = AuditLog(sink=FileAuditSink(path))
        log.log(action=AuditAction.MESSAGE_BRIDGED, agent_id="b1", protocol="mcp")
        assert path.exists()
        rec = json.loads(path.read_text(encoding="utf-8").strip())
        assert rec["action"] == "message_bridged"
        assert rec["protocol"] == "mcp"

    def test_query_works_with_file_sink(self, tmp_path):
        log = AuditLog(sink=FileAuditSink(tmp_path / "a.jsonl"))
        log.log(action=AuditAction.MESSAGE_SENT, agent_id="x")
        log.log(action=AuditAction.MESSAGE_RECEIVED, agent_id="y")
        results = log.query(agent_id="x")
        assert len(results) == 1
        assert results[0].agent_id == "x"
