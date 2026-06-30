"""Regression test for the messaging-channel interop demo.

Locks in the claim that a real Slack mention and a real Telegram /command
reach a real @aurc_agent skill and are answered back in-channel -- with
correlation carried end-to-end and the reply POSTed to the real platform
endpoint shape (no network; a fake client stands in for the wire). If this
breaks, the "AURC bridges messaging channels" claim breaks.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "e2e_channel_interop.py"


def test_channel_interop_runs_clean() -> None:
    """Run examples/e2e_channel_interop.py and assert it exits 0 + real-chain markers."""
    completed = subprocess.run(
        [sys.executable, str(EXAMPLE)],
        capture_output=True,
        text=True,
        timeout=60,
        env=dict(os.environ),
    )

    combined = completed.stdout + completed.stderr
    assert completed.returncode == 0, (
        f"channel interop demo exited {completed.returncode}\n--- stdout ---\n{completed.stdout}"
        f"\n--- stderr ---\n{completed.stderr}"
    )
    # Both channel ends are bridged by AURC through a real agent skill.
    assert "Slack, Telegram & Discord round-trip" in combined, combined
    assert "a real AURC agent skill and were answered back in-channel" in combined, combined
    assert "correlation carried end-to-end across three channel boundaries" in combined, combined
    # The reply was actually POSTed to each platform's real endpoint shape.
    assert "chat.postMessage to slack.com" in combined, combined
    assert "sendMessage to api.telegram.org" in combined, combined
    assert "createMessage to discord.com" in combined, combined


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
