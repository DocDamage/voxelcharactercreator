"""Headless Godot import gate for the production GLB."""
from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path


def verify_godot_import(root: Path, glb: Path) -> dict[str, str | bool]:
    executable = _find_godot()
    if not executable: raise ValueError("GODOT_NOT_FOUND: install Godot 4.6.2 or set VCF_GODOT")
    project = root / "tests" / "godot"
    imported = project / "imported" / "character.glb"
    imported.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(glb, imported)
    version = _run([str(executable), "--version"], "GODOT_VERSION_FAILED").strip()
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
