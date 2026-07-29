"""Build the governed full cast concurrently and record report-backed release evidence."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from vcf_core.advanced import load_cast_plan
from vcf_core.jobs import load_job
from vcf_core.operator import atomic_write_json
from vcf_core.builds import implementation_hash

def find_blender()->Path:
    value=os.environ.get("VCF_BLENDER")
    if value and Path(value).is_file():return Path(value)
    choices=sorted(Path(r"C:\Program Files\Blender Foundation").glob("**/blender.exe"),reverse=True)
    if choices:return choices[0]
    discovered=shutil.which("blender")
    if discovered:return Path(discovered)
    raise RuntimeError("Blender 4.5 or newer was not found")

def report_path(entry:dict)->Path:
    job=load_job(ROOT/entry["job_path"],ROOT); suffix=job["id"].split("_",1)[1] if "_" in job["id"] else job["id"]
    return ROOT/"exports"/job["game"]/suffix/f"{job['id']}_report.json"

def valid_report(entry:dict)->bool:
    path=report_path(entry)
    try:value=json.loads(path.read_text())
    except Exception:return False
    log=ROOT/"logs"/"full_cast"/f"{entry['id']}.log"
    unsafe=log.is_file() and any(pattern in log.read_text(encoding="utf-8",errors="replace") for pattern in ("not valid, and may be exported wrongly","result may not be as expected"))
    return not unsafe and value.get("job")==entry["id"] and value.get("status")=="complete" and value.get("input_hashes",{}).get("implementation")==implementation_hash(ROOT) and value.get("checks",{}).get("godot_import_passed") is True and len(value.get("artifacts",[]))>=20

def build(entry:dict,blender:Path,force:bool)->tuple[str,bool,str]:
    if not force and valid_report(entry):return entry["id"],True,"resumed"
    log=ROOT/"logs"/"full_cast"/f"{entry['id']}.log"; log.parent.mkdir(parents=True,exist_ok=True)
    command=[str(blender),"--background","--python",str(ROOT/"blender_worker"/"process_character.py"),"--","--job",str(ROOT/entry["job_path"]),"--project-root",str(ROOT)]
    if force:command.append("--no-cache")
    result=subprocess.run(command,capture_output=True,text=True,cwd=ROOT,env=os.environ.copy()); output=(result.stdout or "")+(result.stderr or "")
    log.write_text(output,encoding="utf-8")
    unsafe_warning=any(pattern in output for pattern in ("not valid, and may be exported wrongly","result may not be as expected"))
    return entry["id"],result.returncode==0 and not unsafe_warning and valid_report(entry),f"exit {result.returncode}"+("; unsafe mesh warning" if unsafe_warning else "")

def record_release(plan:dict)->Path:
    records=[]
    for entry in plan["characters"]:
        path=report_path(entry); report=json.loads(path.read_text()); checks=report["checks"]
        records.append({"id":entry["id"],"job_path":entry["job_path"],"implementation_hash":report["input_hashes"]["implementation"],"content_hash":report["content_hash"],"report_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"artifact_count":len(report["artifacts"]),"checks":{"parts":"passed" if checks.get("part_resolution_complete") else "failed","rig":"passed" if checks.get("rigid_binding_complete") else "failed","animation":"passed" if checks.get("qa_animation_presence") else "failed","export":"passed" if checks.get("artifact_completeness") else "failed","godot":"passed" if checks.get("godot_import_passed") else "failed"},"tool_versions":{"blender":report["tool_versions"].get("blender"),"godot":checks.get("godot_version")}})
    target=ROOT/"config"/"production"/"full_cast_release.v1.json"; atomic_write_json(target,{"schema_version":1,"characters":records}); return target

def main()->int:
    parser=argparse.ArgumentParser(); parser.add_argument("--workers",type=int,default=4); parser.add_argument("--force",action="store_true"); args=parser.parse_args()
    if not 1<=args.workers<=4:parser.error("--workers must be from 1 to 4")
    plan=load_cast_plan(ROOT/"config"/"production"/"large_cast.v1.json"); blender=find_blender(); failures=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(build,entry,blender,args.force):entry for entry in plan["characters"]}
        for completed,future in enumerate(as_completed(futures),1):
            identifier,passed,detail=future.result(); print(f"[{completed:03d}/{len(futures)}] {identifier}: {'passed' if passed else 'FAILED'} ({detail})",flush=True)
            if not passed:failures.append(identifier)
    if failures:print("Full-cast failures: "+", ".join(failures));return 1
    path=record_release(plan); print(f"Recorded {len(plan['characters'])} report-backed models in {path.relative_to(ROOT)}");return 0
if __name__=="__main__":raise SystemExit(main())
