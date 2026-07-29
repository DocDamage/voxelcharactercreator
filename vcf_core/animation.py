"""Blender-independent Animation Pack v1 contracts."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class AnimationPackError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass(frozen=True)
class AnimationAction:
    name: str
    frame_start: int
    frame_end: int
    loop: bool
    root_motion: str
    required_bones: tuple[str, ...]
    events: tuple[dict[str, Any], ...]
    poses: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class AnimationPack:
    schema_version: int
    pack_id: str
    frame_rate: int
    compatibility_tags: tuple[str, ...]
    required_bones: tuple[str, ...]
    actions: tuple[AnimationAction, ...]


def load_animation_pack(path: Path) -> AnimationPack:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnimationPackError([f"could not read animation pack {path}: {exc}"]) from exc
    errors = validate_animation_pack(value)
    if errors:
        raise AnimationPackError(errors)
    return AnimationPack(
        schema_version=1, pack_id=value["pack_id"], frame_rate=value["frame_rate"],
        compatibility_tags=tuple(value["compatibility_tags"]), required_bones=tuple(value["required_bones"]),
        actions=tuple(AnimationAction(
            name=item["name"], frame_start=item["frame_start"], frame_end=item["frame_end"], loop=item["loop"],
            root_motion=item["root_motion"], required_bones=tuple(item["required_bones"]),
            events=tuple(item["events"]), poses=tuple(item["poses"]),
        ) for item in value["actions"]),
    )


def validate_animation_pack(value: Any) -> list[str]:
    errors: list[str] = []
    required = {"schema_version", "pack_id", "frame_rate", "compatibility_tags", "required_bones", "actions"}
    if not isinstance(value, dict):
        return ["animation pack must be a JSON object"]
    if set(value) != required:
        errors.append("animation pack fields must exactly match Animation Pack v1")
    if value.get("schema_version") != 1:
        errors.append("animation pack schema_version must be 1")
    if not _safe_id(value.get("pack_id")):
        errors.append("animation pack pack_id must be a safe catalog ID")
    fps = value.get("frame_rate")
    if isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 240:
        errors.append("animation pack frame_rate must be an integer from 1 to 240")
    for key in ("compatibility_tags", "required_bones"):
        items = value.get(key)
        if not isinstance(items, list) or not items or any(not isinstance(item, str) or not item for item in items) or len(items) != len(set(items)):
            errors.append(f"animation pack {key} must be a non-empty unique string array")
    actions = value.get("actions")
    if not isinstance(actions, list) or not actions:
        errors.append("animation pack actions must be a non-empty array")
        return errors
    names: list[str] = []
    for index, action in enumerate(actions):
        prefix = f"actions[{index}]"
        fields = {"name", "frame_start", "frame_end", "loop", "root_motion", "required_bones", "events", "poses"}
        if not isinstance(action, dict) or set(action) != fields:
            errors.append(f"{prefix} fields must exactly match Animation Action v1")
            continue
        name = action.get("name")
        if not _safe_id(name): errors.append(f"{prefix}.name must be a safe catalog ID")
        else: names.append(name)
        start, end = action.get("frame_start"), action.get("frame_end")
        if any(isinstance(item, bool) or not isinstance(item, int) for item in (start, end)) or (isinstance(start, int) and isinstance(end, int) and start >= end):
            errors.append(f"{prefix} must have integer frame_start < frame_end")
        if not isinstance(action.get("loop"), bool): errors.append(f"{prefix}.loop must be boolean")
        if action.get("root_motion") not in {"none", "in_place", "root_bone"}: errors.append(f"{prefix}.root_motion is invalid")
        bones = action.get("required_bones")
        if not isinstance(bones, list) or not bones or any(not isinstance(item, str) or not item for item in bones): errors.append(f"{prefix}.required_bones must be a non-empty string array")
        events = action.get("events")
        if not isinstance(events, list) or any(not isinstance(event, dict) or set(event) != {"name", "frame"} or not _safe_id(event.get("name")) or not isinstance(event.get("frame"), int) or not isinstance(start, int) or not isinstance(end, int) or not start <= event["frame"] <= end for event in events):
            errors.append(f"{prefix}.events must contain named frames inside the action range")
        poses = action.get("poses")
        if not isinstance(poses, list) or len(poses) < 2:
            errors.append(f"{prefix}.poses must contain at least two poses")
        else:
            frames = []
            for pose in poses:
                if not isinstance(pose, dict) or set(pose) != {"frame", "bones"} or not isinstance(pose.get("frame"), int) or not isinstance(pose.get("bones"), dict):
                    errors.append(f"{prefix}.poses entries must contain frame and bones")
                    continue
                frames.append(pose["frame"])
                for bone, rotation in pose["bones"].items():
                    if not isinstance(bone, str) or not isinstance(rotation, list) or len(rotation) != 3 or any(isinstance(axis, bool) or not isinstance(axis, (int, float)) or not math.isfinite(float(axis)) for axis in rotation):
                        errors.append(f"{prefix}.poses rotations must be finite XYZ triplets")
            if isinstance(start, int) and isinstance(end, int) and frames and (min(frames) < start or max(frames) > end): errors.append(f"{prefix}.poses fall outside the action range")
            if action.get("loop") and frames and (start not in frames or end not in frames): errors.append(f"{prefix} loop must key both seam frames")
    if len(names) != len(set(names)): errors.append("animation action names must be unique")
    return errors


def _safe_id(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and all(character.islower() or character.isdigit() or character in "_.-" for character in value) and value[0].isalnum()


def find_animation_pack(root: Path, pack_id: str) -> Path:
    matches = sorted((root / "config" / "animation_packs").glob(f"{pack_id}.v*.json"))
    if len(matches) != 1:
        raise AnimationPackError([f"animation pack {pack_id} resolved to {len(matches)} files; expected exactly one"])
    return matches[0]
