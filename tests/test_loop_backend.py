"""Tests for the LoopBackend protocol (integrations/base.py).

Verifies that claude_cli and codex_cli satisfy the LoopBackend contract,
and that is_loop_backend validation works.
"""

from __future__ import annotations

import pytest

from gaiaagent.integrations.base import LoopBackend


def test_claude_cli_satisfies_protocol():
    """claude_cli module exposes all four LoopBackend callables."""
    from gaiaagent.integrations import claude_cli
    assert hasattr(claude_cli, "cli_available")
    assert hasattr(claude_cli, "prompt_too_long")
    assert hasattr(claude_cli, "stop_reason_to_recovery_action")
    assert hasattr(claude_cli, "run_agentic_loop")
    assert callable(claude_cli.cli_available)
    assert callable(claude_cli.prompt_too_long)
    assert callable(claude_cli.stop_reason_to_recovery_action)


def test_codex_cli_satisfies_protocol():
    """codex_cli module exposes all four LoopBackend callables."""
    from gaiaagent.integrations import codex_cli
    assert hasattr(codex_cli, "cli_available")
    assert hasattr(codex_cli, "prompt_too_long")
    assert hasattr(codex_cli, "stop_reason_to_recovery_action")
    assert hasattr(codex_cli, "run_agentic_loop")
    assert callable(codex_cli.cli_available)
    assert callable(codex_cli.prompt_too_long)
    assert callable(codex_cli.stop_reason_to_recovery_action)


def test_claude_cli_cli_available_is_bool():
    from gaiaagent.integrations import claude_cli
    result = claude_cli.cli_available()
    assert isinstance(result, bool)


def test_codex_cli_cli_available_is_bool():
    from gaiaagent.integrations import codex_cli
    result = codex_cli.cli_available()
    assert isinstance(result, bool)


def test_prompt_too_long_returns_bool():
    from gaiaagent.integrations import claude_cli
    assert claude_cli.prompt_too_long("short") is False
    assert claude_cli.prompt_too_long("x" * 10000) is True


def test_stop_reason_to_recovery_action_returns_none_for_end_turn():
    from gaiaagent.integrations import claude_cli
    from gaiaagent.core.types import RecoveryAction
    assert claude_cli.stop_reason_to_recovery_action("end_turn") is None
    result = claude_cli.stop_reason_to_recovery_action("max_turns")
    assert result == RecoveryAction.COMPACT_AND_RETRY


def test_codex_stop_reason_to_recovery_action_returns_none_for_end_turn():
    from gaiaagent.integrations import codex_cli
    from gaiaagent.core.types import RecoveryAction
    assert codex_cli.stop_reason_to_recovery_action("end_turn") is None
    result = codex_cli.stop_reason_to_recovery_action("error")
    assert result == RecoveryAction.RETRY_WITH_BACKOFF


def test_protocol_is_runtime_checkable():
    """The LoopBackend protocol supports isinstance() checks at runtime."""
    from gaiaagent.integrations import claude_cli
    # runtime_checkable Protocol checks for attribute presence
    assert isinstance(claude_cli, LoopBackend)


def test_invalid_backend_fails_protocol_check():
    """A module missing required attributes does not satisfy LoopBackend."""
    class _Incomplete:
        def cli_available(self):
            return True
        # Missing prompt_too_long, stop_reason_to_recovery_action, run_agentic_loop

    assert not isinstance(_Incomplete(), LoopBackend)