"""Validate all repository contracts without requiring Blender."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vcf_core.jobs import migrate_job, validate_job
from vcf_core.assets import AssetValidationError, load_registry
from vcf_core.rigging import PartResolutionError, load_rig_template


def main() -> int:
    failures: list[str] = []
    try:
        registry = load_registry(ROOT)
    except AssetValidationError as exc:
        failures.extend(exc.errors)
        registry = None
    jobs = sorted((ROOT / "characters").glob("*/*.json"))
    if not jobs:
        failures.append("no character jobs found")
    for path in jobs:
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            failures.append(f"{path.relative_to(ROOT)}: invalid JSON: {exc}")
            continue
        errors = validate_job(job, ROOT)
        if errors:
            failures.extend(f"{path.relative_to(ROOT)}: {error}" for error in errors)
        else:
            migrate_job(job)
    for path in (ROOT / "config").glob("*.json"):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            failures.append(f"{path.relative_to(ROOT)}: invalid JSON: {exc}")
    rig_templates = sorted((ROOT / "config" / "rig_templates").glob("*.v1.json"))
    if not rig_templates:
        failures.append("no rig templates found")
    for path in rig_templates:
        try:
            load_rig_template(path)
        except PartResolutionError as exc:
            failures.extend(f"{path.relative_to(ROOT)}: {error}" for error in exc.errors)
    if failures:
        print("Validation failed:", *failures, sep="\n- ")
        return 1
    asset_count = len(registry.manifests) if registry else 0
    print(f"Validated {len(jobs)} jobs, {asset_count} registry assets, and {len(rig_templates)} rig templates; v1 jobs are readable and migrate to Job v2.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
