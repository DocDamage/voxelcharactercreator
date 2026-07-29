"""Headless smoke test for the interactive Godot 3D editor scene contract."""
from __future__ import annotations
import json,os,shutil,subprocess,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from vcf_core.operator import atomic_write_json
from vcf_core.viewer import find_godot_console
def main()->int:
    godot=find_godot_console("");glb=ROOT/"exports"/"original"/"quadruped_standard"/"phase8_quadruped_standard.glb"
    if godot is None or not glb.is_file():print("Build the quadruped and install Godot before verifying the 3D editor.");return 1
    with tempfile.TemporaryDirectory(prefix="vcf-editor-test-",dir=ROOT/"logs") as folder:
        project=Path(folder);source=ROOT/"tools"/"character_editor"
        for name in ("project.godot","main.tscn","main.gd"):shutil.copy2(source/name,project/name)
        (project/"imported").mkdir();shutil.copy2(glb,project/"imported"/"character.glb");atomic_write_json(project/"editor_config.json",{"schema_version":1,"job_id":"phase8_quadruped_standard","part_transforms":{},"socket_overrides":{}})
        flags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0
        imported=subprocess.run([str(godot),"--headless","--editor","--path",str(project),"--import","--quit"],capture_output=True,text=True,timeout=120,creationflags=flags)
        if imported.returncode:print((imported.stdout or "")+(imported.stderr or ""));return 1
        result=subprocess.run([str(godot),"--headless","--path",str(project),"--","--validate"],capture_output=True,text=True,timeout=120,creationflags=flags);output=(result.stdout or "")+(result.stderr or "")
        if result.returncode or '"status":"passed"' not in output:print(output);return 1
        print("Interactive Godot 3D editor scene passed headless mesh, rig, and animation inspection.");return 0
if __name__=="__main__":raise SystemExit(main())
