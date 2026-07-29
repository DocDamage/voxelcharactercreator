"""Headless Godot import gate for the production GLB."""
from __future__ import annotations
import os
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def verify_godot_import(root: Path, glb: Path, required_actions: list[str] | None = None, expected_height: float | None = None, minimum_bones: int = 16, expected_extent: float | None = None) -> dict[str, str | bool]:
    executable = _find_godot()
    if not executable: raise ValueError("GODOT_NOT_FOUND: install Godot 4.6.2 or set VCF_GODOT")
    version = _run([str(executable), "--version"], "GODOT_VERSION_FAILED").strip()
    (root / "logs").mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vcf-godot-gate-",dir=root/"logs") as folder:
        project=Path(folder); imported=project/"imported"/"character.glb"; imported.parent.mkdir(parents=True)
        shutil.copy2(root/"tests"/"godot"/"project.godot",project/"project.godot"); shutil.copy2(root/"tests"/"godot"/"verify_import.gd",project/"verify_import.gd"); shutil.copy2(glb,imported)
        (imported.parent / "gate_config.json").write_text(json.dumps({
            "required_actions": required_actions or ["idle", "walk", "run"],
            "min_extent": max(0.25, float(expected_extent) * 0.8) if expected_extent else max(0.25, float(expected_height or 4.56) * 0.5),
            "max_extent": float(expected_extent) * 1.2 if expected_extent else float(expected_height or 4.56) * 3.0,
            "min_bones": minimum_bones,
        }) + "\n", encoding="utf-8")
        _run([str(executable), "--headless", "--editor", "--path", str(project), "--import"], "GODOT_IMPORT_FAILED")
        output = _run([str(executable), "--headless", "--path", str(project), "--script", str(project / "verify_import.gd")], "GODOT_SCENE_INVALID")
    if '"status":"passed"' not in output: raise ValueError("GODOT_REPORT_MISSING: verifier did not produce a passing machine-readable result")
    return {"godot_import_passed": True, "godot_version": version.splitlines()[0]}


def _run(command: list[str], code: str) -> str:
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode: raise ValueError(f"{code}: {output[-3000:]}")
    return output


def _find_godot() -> Path | None:
    value = os.environ.get("VCF_GODOT") or shutil.which("godot.exe") or shutil.which("godot4") or shutil.which("godot")
    if not value: return None
    path = Path(value).resolve()
    candidates = sorted(path.parent.glob("*console.exe")) if os.name == "nt" else []
    return candidates[0] if candidates else path
