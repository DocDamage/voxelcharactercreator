"""Versioned engine export profile contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ExportProfileError(ValueError):
    pass


@dataclass(frozen=True)
class ExportProfile:
    profile_id: str
    engine: str
    scale: float
    forward_axis: str
    up_axis: str
    materials: str
    animation_mode: str
    root_motion: str
    textures: str
    compression: bool
    budgets: dict[str, int]


def load_export_profile(root: Path, profile_id: str) -> ExportProfile:
    path = root / "config" / "export_profiles" / f"{profile_id}.v1.json"
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise ExportProfileError(f"could not read export profile {profile_id}: {exc}") from exc
    errors = validate_export_profile(value)
    if errors: raise ExportProfileError("\n".join(errors))
    return ExportProfile(profile_id=value["profile_id"], engine=value["engine"], scale=float(value["scale"]), forward_axis=value["forward_axis"], up_axis=value["up_axis"], materials=value["materials"], animation_mode=value["animation_mode"], root_motion=value["root_motion"], textures=value["textures"], compression=value["compression"], budgets=dict(value["budgets"]))


def validate_export_profile(value: Any) -> list[str]:
    fields = {"schema_version", "profile_id", "engine", "scale", "forward_axis", "up_axis", "materials", "animation_mode", "root_motion", "textures", "compression", "budgets"}
    if not isinstance(value, dict) or set(value) != fields: return ["export profile fields must exactly match Export Profile v1"]
    errors = []
    if value["schema_version"] != 1: errors.append("export profile schema_version must be 1")
    if value["engine"] not in {"godot", "unity", "unreal"}: errors.append("export profile engine is invalid")
    if isinstance(value["scale"], bool) or not isinstance(value["scale"], (int, float)) or value["scale"] <= 0: errors.append("export profile scale must be positive")
    if value["forward_axis"] not in {"X", "-X", "Y", "-Y", "Z", "-Z"} or value["up_axis"] not in {"X", "-X", "Y", "-Y", "Z", "-Z"}: errors.append("export profile axes are invalid")
    if value["materials"] not in {"embedded", "external"} or value["animation_mode"] not in {"actions", "scene"} or value["root_motion"] not in {"none", "root_bone"} or value["textures"] not in {"embedded", "copy"} or not isinstance(value["compression"], bool): errors.append("export profile policy is invalid")
    budgets = value["budgets"]
    if not isinstance(budgets, dict) or set(budgets) != {"max_objects", "max_faces", "max_materials", "max_colors"} or any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in budgets.values()): errors.append("export profile budgets are invalid")
    return errors
