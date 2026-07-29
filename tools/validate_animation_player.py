"""Headless smoke test for the Godot animation player project."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vcf_core.viewer import AnimationPlayerError, find_godot, prepare_player


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glb", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--godot", default="")
    args = parser.parse_args()
    root = ROOT
    report = json.loads(args.report.read_text(encoding="utf-8"))
    project = prepare_player(root, args.glb, report)
    executable = find_godot(args.godot)
    if executable is None:
        raise AnimationPlayerError("Godot was not found")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    for command in (
        [str(executable), "--headless", "--editor", "--path", str(project), "--import", "--quit"],
        [str(executable), "--headless", "--path", str(project), "--", "--validate"],
    ):
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, creationflags=flags, check=False)
        if result.returncode:
            raise AnimationPlayerError(((result.stdout or "") + (result.stderr or ""))[-3000:])
    print(f"Animation player loaded {len(report.get('animation', {}).get('actions', []))} actions.")
    return 0


if __name__ == "__main__": raise SystemExit(main())
