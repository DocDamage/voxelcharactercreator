"""Prepare, launch, validate, and atomically apply Godot 3D editor sessions."""
from __future__ import annotations
import json,os,shutil,subprocess,tempfile
from pathlib import Path
from typing import Any
from vcf_core.jobs import load_job,validate_job
from vcf_core.operator import atomic_write_json
from vcf_core.viewer import find_godot,find_godot_console

class CharacterEditorError(RuntimeError):pass

def apply_editor_result(root:Path,job_path:Path,changes:dict[str,Any])->dict[str,Any]:
    if not isinstance(changes,dict) or set(changes)!={"schema_version","part_transforms","socket_overrides"} or changes.get("schema_version")!=1:raise CharacterEditorError("3D editor result does not match schema v1")
    raw=json.loads(job_path.read_text());overrides=raw.setdefault("settings_overrides",{});overrides["part_transforms"]=changes["part_transforms"];overrides["socket_overrides"]=changes["socket_overrides"]
    errors=validate_job(raw,root)
    if errors:raise CharacterEditorError("3D editor output failed canonical Job v2 validation:\n"+"\n".join(errors))
    atomic_write_json(job_path,raw);return raw

def run_editor(root:Path,job_path:Path,glb:Path,configured_godot:str="")->dict[str,Any]:
    executable=find_godot(configured_godot);console=find_godot_console(configured_godot)
    if executable is None or console is None:raise CharacterEditorError("Godot was not found. Set it in Settings or VCF_GODOT.")
    if not glb.is_file():raise CharacterEditorError(f"Build the character before opening the 3D editor: {glb}")
    job=load_job(job_path,root);sessions=root/"exports"/".editor";sessions.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="session-",dir=sessions) as folder:
        project=Path(folder);source=root/"tools"/"character_editor"
        for name in ("project.godot","main.tscn","main.gd"):shutil.copy2(source/name,project/name)
        imported=project/"imported";imported.mkdir();shutil.copy2(glb,imported/"character.glb")
        settings=job.get("settings_overrides",{});atomic_write_json(project/"editor_config.json",{"schema_version":1,"job_id":job["id"],"part_transforms":settings.get("part_transforms",{}),"socket_overrides":settings.get("socket_overrides",{})})
        flags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0
        imported_result=subprocess.run([str(console),"--headless","--editor","--path",str(project),"--import","--quit"],capture_output=True,text=True,timeout=120,creationflags=flags)
        if imported_result.returncode:raise CharacterEditorError("Godot could not prepare the 3D editor:\n"+((imported_result.stdout or "")+(imported_result.stderr or ""))[-2000:])
        result=subprocess.run([str(executable),"--path",str(project)],cwd=project,text=True)
        result_path=project/"editor_result.json"
        if result.returncode or not result_path.is_file():return {"saved":False}
        changes=json.loads(result_path.read_text());apply_editor_result(root,job_path,changes);return {"saved":True,"part_count":len(changes["part_transforms"]),"socket_count":len(changes["socket_overrides"])}
