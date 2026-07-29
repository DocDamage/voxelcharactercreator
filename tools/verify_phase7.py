"""Verify promoted reports against the tracked Phase 7 completion matrix."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vcf_core.jobs import load_job
from vcf_core.production import load_pilot_matrix


def main() -> int:
    matrix = load_pilot_matrix(ROOT / "config" / "production" / "pilot_ten.v1.json")
    failures: list[str] = []
    for entry in matrix["characters"]:
        if any(state != "passed" for state in entry["checks"].values()):
            failures.append(f"{entry['job_id']}: tracked completion matrix is not fully passed")
        matches = [path for path in (ROOT / "characters").glob("*/*.json") if json.loads(path.read_text(encoding="utf-8")).get("id") == entry["job_id"]]
        if len(matches) != 1:
            failures.append(f"{entry['job_id']}: expected one job, found {len(matches)}")
            continue
        job = load_job(matches[0], ROOT)
        slug = job["id"].split("_", 1)[1] if "_" in job["id"] else job["id"]
        report_path = ROOT / "exports" / job["game"] / slug / f"{job['id']}_report.json"
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"{job['id']}: missing or invalid promoted report: {exc}")
            continue
        if report.get("status") != "complete":
            failures.append(f"{job['id']}: status is {report.get('status')!r}, expected complete")
        if not report.get("content_hash"):
            failures.append(f"{job['id']}: report has no semantic content hash")
        if any(item.get("severity") == "error" for item in report.get("diagnostics", [])):
            failures.append(f"{job['id']}: report contains blocking diagnostics")
        failed_stages = [item.get("name") for item in report.get("stages", []) if item.get("status") not in {"passed", "cached"}]
        if failed_stages:
            failures.append(f"{job['id']}: failed stages: {', '.join(failed_stages)}")
    if failures:
        print("Phase 7 verification failed:", *failures, sep="\n- ")
        return 1
    print("Verified ten promoted Phase 7 reports: every converted profile is complete and has a semantic content hash.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
