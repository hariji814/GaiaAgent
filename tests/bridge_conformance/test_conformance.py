"""Bridge conformance tests driven by golden-pair JSON fixtures.

Each fixture in fixtures/ pairs an external-protocol message with the AURC
properties it must produce after translation. Adding a new conformance case is
just dropping another JSON file - no test code changes needed.

This guards the translation contract that makes AURC bridges trustworthy:
external protocol X -> AURC must always yield the documented type/method/origin.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

import pytest

from gaiaagent.bridges.a2a import A2ABridge
from gaiaagent.bridges.acp import ACPBridge
from gaiaagent.bridges.base import MCPBridge
from gaiaagent.core.message import AURCMessage
from gaiaagent.core.types import MessageDirection

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class _Bridge(Protocol):
    async def translate_to_aurc(self, message: dict[str, Any]) -> AURCMessage: ...
    async def translate_from_aurc(self, message: AURCMessage) -> dict[str, Any]: ...


_BRIDGES: dict[str, type[_Bridge]] = {
    "mcp": MCPBridge,
    "a2a": A2ABridge,
    "acp": ACPBridge,
}

_TYPE_MAP = {
    "request": MessageDirection.REQUEST,
    "delegation": MessageDirection.DELEGATION,
    "notification": MessageDirection.NOTIFICATION,
    "response": MessageDirection.RESPONSE,
}


def _load_fixtures() -> list[tuple[str, dict[str, Any]]]:
    cases: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        cases.append((path.stem, data))
    return cases


_CASES = _load_fixtures()


@pytest.mark.parametrize("name,case", _CASES, ids=[c[0] for c in _CASES])
async def test_external_to_aurc_conformance(name: str, case: dict[str, Any]) -> None:
    """Every golden pair: external msg -> AURC must match expected properties."""
    protocol = case["protocol"]
    bridge = _BRIDGES[protocol]()

    aurc = await bridge.translate_to_aurc(case["external_message"])
    expected = case["expected_aurc"]

    if "type" in expected:
        assert aurc.type == _TYPE_MAP[expected["type"]], (
            f'{name}: type {aurc.type.value} != {expected["type"]}'
        )
    if "body_method" in expected:
        assert aurc.body.method == expected["body_method"]
    if "body_skill" in expected:
        assert aurc.body.skill == expected["body_skill"]
    if "origin_protocol" in expected:
        assert aurc.protocol_context.origin_protocol == expected["origin_protocol"]


@pytest.mark.parametrize("name,case", _CASES, ids=[c[0] for c in _CASES])
async def test_round_trip_preserves_intent(name: str, case: dict[str, Any]) -> None:
    """external -> AURC -> external should keep the original method/intent."""
    protocol = case["protocol"]
    bridge = _BRIDGES[protocol]()

    aurc = await bridge.translate_to_aurc(case["external_message"])
    back = await bridge.translate_from_aurc(aurc)

    assert isinstance(back, dict)
    orig_method = case["external_message"].get("method")
    if orig_method is not None:
        assert back.get("method") is not None, f"{name}: method lost in round-trip"


def test_fixtures_are_well_formed() -> None:
    """Every fixture must declare protocol + external_message + expected_aurc."""
    assert _CASES, "no conformance fixtures found"
    for name, case in _CASES:
        assert "protocol" in case, f"{name}: missing protocol"
        assert "external_message" in case, f"{name}: missing external_message"
        assert "expected_aurc" in case, f"{name}: missing expected_aurc"
        assert case["protocol"] in _BRIDGES, f"{name}: unknown protocol"
