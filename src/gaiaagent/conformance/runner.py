"""Conformance runner — the entry point a third party calls.
一致性运行器 — 第三方调用的入口

``run_conformance`` takes a list of raw wire-JSON message dicts and returns a
structured :class:`ConformanceReport` combining structural (schema) and
semantic (invariant) results. An implementation is AURC-conformant for a
given corpus iff ``report.ok`` is True. The runner is pure and dependency
-light: structural validation degrades gracefully when ``jsonschema`` is
absent, but the semantic invariants always run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .invariants import CROSS_MESSAGE_INVARIANTS, PER_MESSAGE_INVARIANTS
from .schema import validate_structure


@dataclass
class ConformanceCheck:
    """Outcome of a single named check. 单项检查结果"""

    name: str
    passed: bool
    detail: str = ""


@dataclass
class MessageReport:
    """Per-message conformance result. 单条消息的一致性结果"""

    index: int
    message_id: str | None
    passed: bool
    checks: list[ConformanceCheck] = field(default_factory=list)


@dataclass
class ConformanceReport:
    """Aggregate conformance result for a corpus. 整批消息的聚合结果"""

    total: int
    passed: int
    failed: int
    messages: list[MessageReport] = field(default_factory=list)
    cross_message_checks: list[ConformanceCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True iff every message and cross-message check passed.
        当且仅当所有消息与跨消息检查均通过时为 True"""
        return self.failed == 0 and all(c.passed for c in self.cross_message_checks)

    def summary(self) -> str:
        """One-line human summary. 单行人类可读摘要"""
        status = "PASS" if self.ok else "FAIL"
        return f"{status}: {self.passed}/{self.total} messages conformant"


def _run_one(message: dict[str, Any], index: int) -> MessageReport:
    """Run all structural + per-message invariants on one message.
    对单条消息运行全部结构校验与单消息不变式"""
    mid = message.get("message_id") if isinstance(message.get("message_id"), str) else None
    checks: list[ConformanceCheck] = []

    structural = validate_structure(message)
    checks.append(
        ConformanceCheck(
            name="structure",
            passed=not structural,
            detail="; ".join(structural) if structural else "",
        )
    )

    for name, invariant in PER_MESSAGE_INVARIANTS:
        violations = invariant(message)
        checks.append(
            ConformanceCheck(
                name=name,
                passed=not violations,
                detail="; ".join(violations) if violations else "",
            )
        )

    return MessageReport(
        index=index,
        message_id=mid,
        passed=all(c.passed for c in checks),
        checks=checks,
    )


def run_conformance(messages: list[dict[str, Any]]) -> ConformanceReport:
    """Run the full conformance suite over a corpus.
    对整批消息运行完整一致性套件

    Args:
        messages: raw wire-JSON message dicts (as produced by
            ``AURCMessage.model_dump(mode="json")`` or a third-party encoder).

    Returns:
        A :class:`ConformanceReport` with per-message and cross-message
        results. ``report.ok`` is the conformant/not-conformant verdict.
    """
    message_reports = [_run_one(msg, i) for i, msg in enumerate(messages)]
    passed = sum(1 for r in message_reports if r.passed)
    failed = len(message_reports) - passed

    cross: list[ConformanceCheck] = []
    for name, invariant in CROSS_MESSAGE_INVARIANTS:
        violations = invariant(messages)
        cross.append(
            ConformanceCheck(
                name=name,
                passed=not violations,
                detail="; ".join(violations) if violations else "",
            )
        )

    return ConformanceReport(
        total=len(message_reports),
        passed=passed,
        failed=failed,
        messages=message_reports,
        cross_message_checks=cross,
    )


def validate_message(message: dict[str, Any]) -> MessageReport:
    """Convenience wrapper: run the suite on a single message.
    便捷封装：对单条消息运行套件"""
    return _run_one(message, 0)
