"""Atomically persist reviewed Phase 3 semantic mappings to a Job v2 file."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vcf_core.jobs import load_job, validate_job
from vcf_core.rigging import PartResolution, persist_part_overrides


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path, help="JSON object mapping semantic roles to existing source object names.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args()
    root = arguments.project_root.resolve()
    job_path = arguments.job.resolve()
    mapping_path = arguments.mapping.resolve()
    job = load_job(job_path, root)
    try:
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"could not read mapping {mapping_path}: {exc}")
    if not isinstance(mapping, dict) or any(not isinstance(role, str) or not isinstance(source, str) for role, source in mapping.items()):
        raise SystemExit("mapping must be a JSON object mapping semantic roles to source object names")
    resolved = {
        role: PartResolution(role, source, 1.0, "manual_mapping", "", ())
        for role, source in mapping.items()
    }
    updated = persist_part_overrides(job, resolved)
    errors = validate_job(updated, root)
    if errors:
        raise SystemExit("mapping was rejected:\n" + "\n".join(errors))
    descriptor, temporary = tempfile.mkstemp(prefix=f".{job_path.stem}.", suffix=".tmp", dir=job_path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(updated, stream, indent=2)
            stream.write("\n")
        Path(temporary).replace(job_path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print(f"Saved {len(mapping)} part override(s) to {job_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
