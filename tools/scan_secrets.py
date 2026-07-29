"""Dependency-free, conservative committed-secret scan for CI."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])"
    r"(?:[A-Za-z][A-Za-z0-9]*[_-])*"
    r"(?:api[_-]?key|client[_-]?secret|access[_-]?token|password|secret|token)"
    r"(?![A-Za-z0-9_-])"
    r"\s*[:=]\s*(.+)$"
)
TOKEN_PATTERN = re.compile(r"\b(?:sk[-_]|ghp_)[A-Za-z0-9_-]{20,}\b")
PURE_REFERENCE_PATTERN = re.compile(
    r"(?ix)^(?:"
    r"\$\{[a-z_][a-z0-9_]*\}|"
    r"\$env:[a-z_][a-z0-9_]*|%[a-z_][a-z0-9_]*%|"
    r"\{\{?[a-z_][a-z0-9_.-]*\}?\}|<[^<>]+>|"
    r"(?:your|replace|example)[_-][a-z0-9_-]+|changeme(?:[_-][a-z0-9_-]+)?|"
    r"(?:os\.)?getenv\(\s*['\"][a-z_][a-z0-9_]*['\"]\s*\)|"
    r"os\.environ(?:\.get\(\s*['\"][a-z_][a-z0-9_]*['\"]\s*\)|"
    r"\[\s*['\"][a-z_][a-z0-9_]*['\"]\s*\])|"
    r"(?:process\.env|settings|config)(?:\.[a-z_][a-z0-9_]*|"
    r"\[\s*['\"][a-z_][a-z0-9_]*['\"]\s*\])"
    r")\s*;?$"
)
DOCUMENTED_PLACEHOLDER_PATTERN = re.compile(
    r"(?ix)^(?:your|replace|example)[_-][a-z0-9_-]+$|^changeme(?:[_-][a-z0-9_-]+)?$"
)
QUOTED_VALUE_PATTERN = re.compile(
    r"(?P<quote>['\"])(?P<value>(?:\\.|(?!(?P=quote)).)*)(?P=quote)"
)
ENVIRONMENT_LOOKUP_ARGUMENT_PATTERN = re.compile(
    r"(?ix)(?:(?:os\.)?getenv|os\.environ\.get)\(\s*(['\"])(?P<name>[a-z_][a-z0-9_]*)\1"
)


def tracked_files(root: Path = ROOT) -> list[Path]:
    """Return only files present in Git's index."""

    result = subprocess.run(
        ["git", "ls-files", "--cached", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    paths = []
    for item in result.stdout.split(b"\0"):
        if not item:
            continue
        path = root / item.decode("utf-8")
        if path.is_file():
            paths.append(path)
    return paths


def _find_secrets_in_text(text: str, display: Path | str) -> list[str]:
    return [
        f"{display}:{number}"
        for number, line in enumerate(text.splitlines(), 1)
        if line_contains_secret(line)
    ]


def find_index_secrets(root: Path = ROOT) -> list[str]:
    """Scan blob bytes from Git's index, even when the worktree differs."""

    listed = subprocess.run(
        ["git", "ls-files", "--stage", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    entries: list[tuple[bytes, str]] = []
    for record in listed.stdout.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        _mode, object_id, stage = metadata.split()
        if stage != b"0":
            continue
        entries.append((object_id, raw_path.decode("utf-8")))
    if not entries:
        return []

    result = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=root,
        input=b"".join(object_id + b"\n" for object_id, _path in entries),
        check=True,
        capture_output=True,
    )
    findings: list[str] = []
    offset = 0
    for _object_id, path in entries:
        header_end = result.stdout.find(b"\n", offset)
        if header_end < 0:
            raise RuntimeError("git cat-file returned a truncated batch header")
        header = result.stdout[offset:header_end].split()
        offset = header_end + 1
        if len(header) != 3:
            raise RuntimeError("git cat-file returned an invalid batch header")
        object_type, size = header[1], int(header[2])
        data = result.stdout[offset : offset + size]
        offset += size + 1  # Every batch object is followed by one newline.
        if object_type != b"blob":
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(_find_secrets_in_text(text, path))
    return findings


def line_contains_secret(line: str) -> bool:
    if TOKEN_PATTERN.search(line):
        return True
    for match in ASSIGNMENT_PATTERN.finditer(line):
        right_hand_side = match.group(1).strip()
        if PURE_REFERENCE_PATTERN.fullmatch(right_hand_side):
            continue
        lookup_arguments = {
            lookup.span("name")
            for lookup in ENVIRONMENT_LOOKUP_ARGUMENT_PATTERN.finditer(right_hand_side)
        }
        quoted = []
        for quoted_match in QUOTED_VALUE_PATTERN.finditer(right_hand_side):
            value_span = quoted_match.span("value")
            prefix = right_hand_side[: quoted_match.start()].rstrip()
            suffix = right_hand_side[quoted_match.end() :].lstrip()
            object_key = suffix.startswith(":") and bool(prefix) and prefix[-1] in "{,"
            if value_span in lookup_arguments or object_key:
                # Ignore only a recognized environment lookup argument or an
                # structurally positioned object key. Uppercase literals,
                # ternaries, and container values still scan.
                continue
            quoted.append(quoted_match.group("value").strip())
        candidates = [
            value
            for value in quoted
            if len(value) >= 12
        ]
        if not quoted:
            token = re.split(r"[\s#,;]", right_hand_side, maxsplit=1)[0].strip()
            if len(token) >= 12:
                candidates.append(token)
        if any(
            not PURE_REFERENCE_PATTERN.fullmatch(value)
            and not DOCUMENTED_PLACEHOLDER_PATTERN.fullmatch(value)
            for value in candidates
        ):
            return True
    return False


def find_secrets(paths, *, root: Path = ROOT) -> list[str]:
    """Return relative file/line locations containing likely credentials."""

    findings: list[str] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        try:
            display = path.relative_to(root)
        except ValueError:
            display = path
        findings.extend(_find_secrets_in_text(text, display))
    return findings


def main() -> int:
    findings = sorted(set(find_index_secrets() + find_secrets(tracked_files())))
    if findings:
        print("Possible committed secrets:", *findings, sep="\n- ")
        return 1
    print("No committed secrets detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
