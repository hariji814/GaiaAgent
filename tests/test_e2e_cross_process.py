"""Regression test for the cross-process AURC end-to-end demo.

Locks in the headline sellability claim: a real HTTP round-trip that routes a
native AURC request to a real @skill, then bridges an A2A delegation back to an
AURC response, with correlation_id carried end-to-end. If this breaks, the
"AURC is a real interop runtime, not just a translation library" promise breaks.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "e2e_cross_process.py"


def test_e2e_cross_process_demo_runs_clean() -> None:
    """Run examples/e2e_cross_process.py as a subprocess and assert exit 0 + markers."""
    env = dict(os.environ)
    completed = subprocess.run(
        [sys.executable, str(EXAMPLE)],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )

    combined = completed.stdout + completed.stderr
    assert completed.returncode == 0, (
        f"e2e demo exited {completed.returncode}\n--- stdout ---\n{completed.stdout}"
        f"\n--- stderr ---\n{completed.stderr}"
    )
    assert "routed to real @skill, correlation preserved" in combined, combined
    assert "real network round-trip, correlation carried end-to-end" in combined, combined
    assert "Demo complete: AURC routes real skills over HTTP and bridges A2A" in combined


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
