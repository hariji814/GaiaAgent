#!/usr/bin/env python
"""Pre-commit encoding guard for GaiaAgent.

Rejects files that are not valid UTF-8 or that contain CRLF line endings.
This prevents the historical Chinese-comment mojibake (UTF-8 double-encoded
as GBK) from re-entering the tree — see TODO.md P1 and CLAUDE.md "Encoding Guard".

Exit code 1 fails the commit if any staged file violates the rule.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _check(path: Path) -> str | None:
    """Return an error message if `path` is not UTF-8 or contains CRLF, else None."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return f"not valid UTF-8 ({exc.reason} at byte {exc.start})"
    if "\r\n" in text or "\r" in text:
        return "contains CRLF/CR line endings (expected LF)"
    return None


def main() -> int:
    offenders = []
    for arg in sys.argv[1:]:
        path = Path(arg)
        if not path.is_file():
            continue
        if msg := _check(path):
            offenders.append((str(path), msg))
    if offenders:
        for p, msg in offenders:
            sys.stderr.write(f"  {p}: {msg}\n")
        sys.stderr.write(
            "\nEncoding guard: files must be UTF-8 with LF line endings.\n"
            "Re-encode the file(s) above — do not bypass this hook.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
