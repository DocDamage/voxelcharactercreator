"""Prepare and launch the out-of-process Godot animation player."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from vcf_core.operator import atomic_write_json


class AnimationPlayerError(RuntimeError):
    pass


def _godot_pair(configured: str = "") -> tuple[Path | None,Path | None]:
    value = configured or os.environ.get("VCF_GODOT", "") or shutil.which("godot.exe") or shutil.which("godot4") or shutil.which("godot") or ""
    if not value:
        return None,None
    path = Path(value).resolve()
    if not path.is_file():
        return None,None
    if path.name.lower().endswith("_console.exe"):
        gui = path.with_name(path.name[:-12] + ".exe")
        return (gui if gui.is_file() else path),path
    consoles=sorted(path.parent.glob("*console.exe")) if os.name=="nt" else []
    return path,(consoles[0] if consoles else path)

def find_godot(configured: str = "") -> Path | None:return _godot_pair(configured)[0]
def find_godot_console(configured: str = "") -> Path | None:return _godot_pair(configured)[1]


def player_config(report: dict[str, Any]) -> dict[str, Any]:
    animation = report.get("animation", {}) if isinstance(report, dict) else {}
    actions = animation.get("actions", []) if isinstance(animation, dict) else []
    return {
        "schema_version": 1,
        "character": str(report.get("job", "character")),
        "frame_rate": 30,
        "actions": [{
            "name": str(action.get("name", "")),
            "loop": bool(action.get("loop", False)),
            "frame_start": int(action.get("frame_start", 1)),
            "frame_end": int(action.get("frame_end", 2)),
            "events": list(action.get("events", [])),
        } for action in actions if isinstance(action, dict) and action.get("name")],
    }


def prepare_player(root: Path, glb: Path, report: dict[str, Any]) -> Path:
    if not glb.is_file():
        raise AnimationPlayerError(f"Build the character before opening the animation player: {glb}")
    project = root / "tools" / "animation_player"
    imported = project / "imported"
    imported.mkdir(parents=True, exist_ok=True)
    shutil.copy2(glb, imported / "character.glb")
    atomic_write_json(imported / "player_config.json", player_config(report))
    return project


def launch_player(root: Path, glb: Path, report: dict[str, Any], configured_godot: str = "") -> subprocess.Popen[str]:
    executable = find_godot(configured_godot);console=find_godot_console(configured_godot)
    if executable is None or console is None:
        raise AnimationPlayerError("Godot was not found. Set it in Settings or VCF_GODOT.")
    project = prepare_player(root, glb, report)
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    imported = subprocess.run(
        [str(console), "--headless", "--editor", "--path", str(project), "--import", "--quit"],
        capture_output=True, text=True, timeout=120, creationflags=flags, check=False,
    )
    if imported.returncode:
        output = (imported.stdout or "") + (imported.stderr or "")
        raise AnimationPlayerError("Godot could not import the character:\n" + output[-2000:])
    return subprocess.Popen([str(executable), "--path", str(project)], cwd=project, text=True)
