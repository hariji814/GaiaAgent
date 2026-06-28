"""Regenerate the frozen AURC wire-format JSON Schema.
重新生成冻结的 AURC 线缆格式 JSON Schema

Run after any change to gaiaagent.core.message.AURCMessage that affects the
wire format. The real logic lives in gaiaagent.conformance.schema so the CLI
(``aurc conformance --schema``) and this script share one implementation.

Usage:
    python scripts/generate_schema.py            # rewrite the snapshot
    python scripts/generate_schema.py --check    # CI: exit 1 if stale
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from a source checkout without an editable install.
# 允许在源码检出目录直接运行,无需可编辑安装。
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gaiaagent.conformance.schema import (  # noqa: E402
    published_schema_matches_model,
    write_schema,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the published schema is stale (CI mode).",
    )
    args = parser.parse_args()

    if args.check:
        if published_schema_matches_model():
            print("schema: up to date")
            return 0
        print(
            "schema: STALE - regenerate with `python scripts/generate_schema.py`",
            file=sys.stderr,
        )
        return 1

    write_schema()
    if not published_schema_matches_model():
        print("schema: write succeeded but drift check still fails", file=sys.stderr)
        return 1
    print("schema: published")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
