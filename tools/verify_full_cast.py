"""Audit every full-cast release record against promoted artifacts and reports."""
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from vcf_core.advanced import AdvancedValidationError,load_cast_plan,load_cast_release
from vcf_core.jobs import load_job
from vcf_core.builds import implementation_hash

def output_for(job:dict)->Path:
    suffix=job["id"].split("_",1)[1] if "_" in job["id"] else job["id"]
    return ROOT/"exports"/job["game"]/suffix

def main()->int:
    failures=[];plan=load_cast_plan(ROOT/"config"/"production"/"large_cast.v1.json");release_path=ROOT/"config"/"production"/"full_cast_release.v1.json"
    try:release=load_cast_release(release_path,plan)
    except (OSError,json.JSONDecodeError,AdvancedValidationError) as exc:print(f"Full-cast release invalid: {exc}");return 1
    planned={item["id"]:item for item in plan["characters"]}
    for record in release["characters"]:
        job_path=ROOT/record["job_path"];job=load_job(job_path,ROOT);output=output_for(job);report_path=output/f"{job['id']}_report.json"
        try:report=json.loads(report_path.read_text())
        except Exception as exc:failures.append(f"{job['id']}: report unavailable: {exc}");continue
        if hashlib.sha256(report_path.read_bytes()).hexdigest()!=record["report_sha256"]:failures.append(f"{job['id']}: report hash drift")
        if hashlib.sha256(job_path.read_bytes()).hexdigest()!=report.get("input_hashes",{}).get("job"):failures.append(f"{job['id']}: report does not cover current job bytes")
        if implementation_hash(ROOT)!=record["implementation_hash"] or report.get("input_hashes",{}).get("implementation")!=record["implementation_hash"]:failures.append(f"{job['id']}: report does not cover current pipeline sources")
        if report.get("status")!="complete" or report.get("content_hash")!=record["content_hash"]:failures.append(f"{job['id']}: promoted report is incomplete or semantic hash drifted")
        checks=report.get("checks",{});topology=planned[job["id"]]["topology"]
        if checks.get("deformation_fallback_available") is not True or checks.get("spring_motion_rigid_fallback") is not True:failures.append(f"{job['id']}: deterministic rigid fallback evidence is missing")
        if topology=="flying" and (checks.get("deformation_applied") is not True or checks.get("spring_motion_applied") is not True):failures.append(f"{job['id']}: flying deform/spring path was not exercised")
        if topology=="boss" and checks.get("spring_motion_applied") is not True:failures.append(f"{job['id']}: boss spring motion was not exercised")
        if any(stage.get("status") not in {"passed","cached"} for stage in report.get("stages",[])):failures.append(f"{job['id']}: a pipeline stage did not pass")
        artifacts={item["name"]:item for item in report.get("artifacts",[])}
        if len(artifacts)!=record["artifact_count"]:failures.append(f"{job['id']}: artifact count drift")
        for name,item in artifacts.items():
            path=output/name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=item["sha256"]:failures.append(f"{job['id']}: artifact missing or changed: {name}")
    if failures:
        print("Full-cast verification failed:",*failures,sep="\n- ");return 1
    print(f"Full-cast release passed: {len(release['characters'])} distinct semantic hashes with current jobs, reports, tool versions, completion matrices, and hashed artifacts.");return 0
if __name__=="__main__":raise SystemExit(main())
