"""Build and verify the Phase 7 Windows source distribution."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vcf_core.production import package_source_distribution, validate_packaging_strategy
from tools.scan_secrets import find_secrets


def package_files(
    root: Path = ROOT, *, include_untracked_development_files: bool = False
) -> list[Path]:
    command = ["git", "ls-files", "--cached"]
    if include_untracked_development_files:
        command.extend(["--others", "--exclude-standard"])
    command.append("-z")
    result = subprocess.run(
        command,
        cwd=root,
        check=True,
        capture_output=True,
    )
    files: list[Path] = []
    for item in result.stdout.split(b"\0"):
        if not item:
            continue
        path = root / item.decode("utf-8")
        if path.is_file():
            files.append(path)
    return files


def tracked_files() -> list[Path]:
    """Return the safe default package input set retained for API compatibility."""
    return package_files()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "exports" / "packages" / "VoxelCharacterFactory-source.zip")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--include-untracked-development-files",
        action="store_true",
        help="DEVELOPMENT ONLY: include untracked, nonignored worktree files in the source package.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    strategy = json.loads((ROOT / "config" / "production" / "windows_packaging.v1.json").read_text(encoding="utf-8"))
    validate_packaging_strategy(strategy)
    files = package_files(
        include_untracked_development_files=args.include_untracked_development_files
    )
    findings = find_secrets(files, root=ROOT)
    if findings:
        print("Package blocked by possible secrets:", *findings, sep="\n- ", file=sys.stderr)
        return 1
    manifest = package_source_distribution(ROOT, args.output.resolve(), files)
    manifest["channel"] = (
        "development-source-with-untracked-files"
        if args.include_untracked_development_files
        else "development-source-only"
    )
    manifest["signed"] = False
    manifest["includes_untracked_files"] = args.include_untracked_development_files
    target = args.manifest.resolve() if args.manifest else args.output.with_suffix(".manifest.json").resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    selection = "tracked and untracked nonignored development" if args.include_untracked_development_files else "Git-tracked"
    print(f"Created {args.output} with {len(manifest['files'])} {selection} files; release publication remains gated on Authenticode signing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
