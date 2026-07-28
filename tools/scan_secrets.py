"""Dependency-free, conservative committed-secret scan for CI."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", ".venv", "venv", "__pycache__", "exports", "assets/incoming", "assets/generated"}
PATTERNS = (
    re.compile(r"(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*[\"'](?!\$\{|YOUR_|REPLACE_|EXAMPLE_)[^\"']{12,}[\"']"),
    re.compile(r"\b(?:sk|ghp)_[A-Za-z0-9_-]{20,}\b"),
)


def main() -> int:
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if any(pattern.search(line) for pattern in PATTERNS):
                findings.append(f"{path.relative_to(ROOT)}:{number}")
    if findings:
        print("Possible committed secrets:", *findings, sep="\n- ")
        return 1
    print("No committed secrets detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
