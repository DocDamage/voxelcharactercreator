"""Verify promoted Phase 8 topology and production gates."""
from __future__ import annotations
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from vcf_core.advanced import cast_quality_summary, load_cast_plan

JOBS=("quadruped_standard","flying_standard","multi_arm_standard","final_boss_composite")

def main()->int:
    failures=[]
    for name in JOBS:
        path=ROOT/"exports"/"original"/name/f"phase8_{name}_report.json"
        if not path.is_file():failures.append(f"missing promoted report for {name}");continue
        report=json.loads(path.read_text())
        if report.get("status")!="complete":failures.append(f"{name}: status is not complete")
        if report.get("checks",{}).get("godot_import_passed") is not True:failures.append(f"{name}: Godot gate did not pass")
        if report.get("checks",{}).get("deformation_fallback_available") is not True:failures.append(f"{name}: rigid fallback is unavailable")
        if len(report.get("artifacts",[]))<20:failures.append(f"{name}: expected at least 20 hashed artifacts")
    flyer=ROOT/"exports"/"original"/"flying_standard"/"phase8_flying_standard_report.json"
    if flyer.is_file() and json.loads(flyer.read_text()).get("checks",{}).get("deformation_applied") is not True:failures.append("flying fixture did not exercise deform binding")
    summary=cast_quality_summary(load_cast_plan(ROOT/"config"/"production"/"large_cast.v1.json"))
    if summary["model_count"]<100 or not summary["resumable"]:failures.append("large-cast planning/recovery gate failed")
    if failures:
        print("Phase 8 verification failed:",*failures,sep="\n- ");return 1
    print(f"Phase 8 vertical slice passed: {len(JOBS)} advanced Blender/Godot builds, deform fallback, and {summary['model_count']} buildable cast jobs across {summary['batch_count']} resumable batches.")
    return 0
if __name__=="__main__":raise SystemExit(main())
