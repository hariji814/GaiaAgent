"""Regression test for the REAL ACP <-> MCP cross-process interop demo.

The ACP counterpart of ``test_e2e_mcp_a2a_interop``. Locks in the
no-fabrication sellability proof on the ACP side: a spec-compliant ACP
client sends a real `invoke` envelope over HTTP to an AURC node; AURC
translates it to an AURC skill call; that skill invokes a REAL MCP server
(official FastMCP + official MCP ClientSession over stdio) and returns the
result as an ACP completed envelope -- with the envelope id (correlation)
carried end-to-end. If this breaks, the "AURC bridges real ACP and real
MCP" claim breaks.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "e2e_acp_interop.py"


def test_acp_mcp_interop_runs_clean() -> None:
    """Run examples/e2e_acp_interop.py and assert it exits 0 + real-chain markers."""
    completed = subprocess.run(
        [sys.executable, str(EXAMPLE)],
        capture_output=True,
        text=True,
        timeout=90,
        env=dict(os.environ),
    )

    combined = completed.stdout + completed.stderr
    assert completed.returncode == 0, (
        f"interop demo exited {completed.returncode}\n--- stdout ---\n{completed.stdout}"
        f"\n--- stderr ---\n{completed.stderr}"
    )
    # Both protocol ends are real: ACP client + real MCP server, bridged by AURC.
    assert "real ACP client -> AURC -> real MCP, correlation e2e" in combined, combined
    assert "a real ACP client reached a real MCP server through AURC" in combined, combined
    # The arithmetic was computed inside the real MCP server, not by AURC.
    assert "real-mcp" in combined, combined
    assert "mcp_content" in combined, combined
    assert "42" in combined, combined


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
