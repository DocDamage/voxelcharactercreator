"""Deterministic Animation Pack v1 loading and Blender action validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import bpy

from vcf_core.animation import AnimationPack, find_animation_pack, load_animation_pack


def apply_animation_packs(armature: bpy.types.Object, job: dict, root: Path) -> tuple[list[bpy.types.Action], dict[str, Any]]:
    pack_ids = job.get("animation_packs") or []
    if not pack_ids:
        raise ValueError("ANIM_PACK_MISSING: production builds must declare animation_packs")
    packs = [load_animation_pack(find_animation_pack(root, pack_id)) for pack_id in pack_ids]
    actions: list[bpy.types.Action] = []
    checks: dict[str, Any] = {}
    existing_bones = set(armature.pose.bones.keys())
    profile_tags = {str(job.get("animation_profile", "")), "humanoid"}
    for pack in packs:
        missing_pack_bones = sorted(set(pack.required_bones) - existing_bones)
        if missing_pack_bones:
            raise ValueError(f"ANIM_INCOMPATIBLE_RIG: {pack.pack_id} is missing bones: {', '.join(missing_pack_bones)}")
        if not profile_tags.intersection(pack.compatibility_tags):
            raise ValueError(f"ANIM_INCOMPATIBLE_PROFILE: {pack.pack_id} does not support {job.get('animation_profile')}")
        bpy.context.scene.render.fps = pack.frame_rate
        for contract in pack.actions:
            action = _create_action(armature, pack, contract)
            actions.append(action)
            action_checks = validate_action(action, armature, contract)
            checks.update({f"animation_{contract.name}_{name}": passed for name, passed in action_checks.items()})
            failed = [name for name, passed in action_checks.items() if not passed]
            if failed:
                raise ValueError(f"ANIM_VALIDATION_FAILED: {contract.name}: {', '.join(failed)}")
    armature.animation_data_create()
    armature.animation_data.action = actions[0]
    armature["vcf.animation_packs"] = [pack.pack_id for pack in packs]
    armature["vcf.actions"] = [action.name for action in actions]
    return actions, checks


def _create_action(armature: bpy.types.Object, pack: AnimationPack, contract) -> bpy.types.Action:
    action = bpy.data.actions.get(contract.name)
    if action: bpy.data.actions.remove(action)
    action = bpy.data.actions.new(contract.name)
    action.use_fake_user = True
    action["vcf.schema_version"] = pack.schema_version
    action["vcf.pack_id"] = pack.pack_id
    action["vcf.frame_rate"] = pack.frame_rate
    action["vcf.loop"] = contract.loop
    action["vcf.root_motion"] = contract.root_motion
    action["vcf.events"] = json.dumps(list(contract.events), separators=(",", ":"))
    action["vcf.frame_start"] = contract.frame_start
    action["vcf.frame_end"] = contract.frame_end
    armature.animation_data_create()
    armature.animation_data.action = action
    for bone in armature.pose.bones:
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = (0.0, 0.0, 0.0)
        bone.location = (0.0, 0.0, 0.0)
    for pose in contract.poses:
        keyed = {name: pose["bones"].get(name, (0.0, 0.0, 0.0)) for name in contract.required_bones}
        keyed.update(pose["bones"])
        for bone_name, rotation in keyed.items():
            if bone_name not in armature.pose.bones:
                raise ValueError(f"ANIM_UNKNOWN_BONE: {contract.name} keys missing bone {bone_name}")
            bone = armature.pose.bones[bone_name]
            bone.rotation_euler = tuple(float(axis) for axis in rotation)
            bone.keyframe_insert("rotation_euler", frame=pose["frame"], group=bone_name)
        # Explicit root keys prove in-place/root-motion policy and avoid empty
        # root curves being fabricated by exporters.
        root = armature.pose.bones["root"]
        root.location = (0.0, 0.0, 0.0)
        root.keyframe_insert("location", frame=pose["frame"], group="root")
    for curve in action.fcurves:
        for point in curve.keyframe_points:
            point.interpolation = "BEZIER" if contract.name == "idle" else "LINEAR"
    return action


def validate_action(action: bpy.types.Action, armature: bpy.types.Object, contract) -> dict[str, bool]:
    curves = list(action.fcurves)
    keyed_bones = {curve.data_path.split('"')[1] for curve in curves if 'pose.bones["' in curve.data_path}
    root_curves = [curve for curve in curves if 'pose.bones["root"]' in curve.data_path and curve.data_path.endswith("location")]
    root_static = all(len({round(point.co.y, 6) for point in curve.keyframe_points}) == 1 for curve in root_curves)
    seam_ok = True
    if contract.loop:
        for curve in curves:
            start = next((point.co.y for point in curve.keyframe_points if round(point.co.x) == contract.frame_start), None)
            end = next((point.co.y for point in curve.keyframe_points if round(point.co.x) == contract.frame_end), None)
            if start is not None and end is not None and abs(start - end) > 0.00001: seam_ok = False
    return {
        "non_empty": bool(curves) and all(curve.keyframe_points for curve in curves),
        "required_bones_covered": set(contract.required_bones).issubset(keyed_bones),
        "loop_seam": seam_ok,
        "foot_sliding": contract.root_motion != "in_place" or root_static,
        "events_valid": all(contract.frame_start <= event["frame"] <= contract.frame_end for event in contract.events),
        "root_motion_valid": contract.root_motion == "root_bone" or root_static,
    }
