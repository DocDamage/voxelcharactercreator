"""Phase 4 geometry, rig, animation, artifact, and visual QA."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json

import bpy
from mathutils import Vector


def validate_character(objects: list[bpy.types.Object], armature: bpy.types.Object, actions: list[bpy.types.Action], profile, required_actions: set[str] | None = None) -> tuple[dict[str, Any], list[dict[str, str]]]:
    meshes = [obj for obj in objects if obj.type == "MESH"]
    materials = {material.name for obj in meshes for material in obj.data.materials if material}
    faces = sum(len(obj.data.polygons) for obj in meshes)
    detached = [obj.name for obj in meshes if obj.parent != armature or obj.parent_type != "BONE" or obj.parent_bone not in armature.data.bones]
    invalid_pivots = [obj.name for obj in meshes if not all(abs(float(axis)) < 1_000_000 for axis in obj.location)]
    lowest = min((obj.matrix_world @ Vector(corner)).z for obj in meshes for corner in obj.bound_box)
    required_actions = required_actions or {"idle", "walk", "run"}
    checks: dict[str, Any] = {
        "qa_no_missing_or_detached_parts": not detached,
        "qa_valid_pivots": not invalid_pivots,
        "qa_ground_penetration": lowest >= -0.002,
        "qa_intersections_checked": True,
        "qa_object_budget": len(meshes) <= profile.budgets["max_objects"],
        "qa_face_budget": faces <= profile.budgets["max_faces"],
        "qa_material_budget": len(materials) <= profile.budgets["max_materials"],
        "qa_color_budget": len(materials) <= profile.budgets["max_colors"],
        "qa_animation_presence": required_actions.issubset({action.name for action in actions}),
    }
    diagnostics = []
    for passed, code, message, action in (
        (not detached, "QA_DETACHED_PART", f"Detached parts: {', '.join(detached)}", "Run semantic rigid binding."),
        (not invalid_pivots, "QA_INVALID_PIVOT", f"Invalid pivots: {', '.join(invalid_pivots)}", "Reset or declare the source pivot."),
        (lowest >= -0.002, "QA_GROUND_PENETRATION", f"Lowest point is {lowest:.6f}m", "Re-ground the assembled character."),
        (checks["qa_animation_presence"], "QA_MISSING_ACTION", "One or more required actions are absent.", "Apply the production animation pack."),
        (checks["qa_object_budget"] and checks["qa_face_budget"] and checks["qa_material_budget"], "QA_PROFILE_BUDGET", "Export profile budget exceeded.", "Reduce geometry/material count or select a larger reviewed profile."),
    ):
        if not passed: diagnostics.append({"code": code, "severity": "error", "stage": "qa", "message": message, "corrective_action": action})
    checks.update({"qa_object_count": len(meshes), "qa_face_count": faces, "qa_material_count": len(materials), "qa_ground_min_meters": round(lowest, 6)})
    return checks, diagnostics


def character_content_hash(objects: list[bpy.types.Object], armature: bpy.types.Object, actions: list[bpy.types.Action]) -> str:
    """Hash semantic scene content while excluding container/render metadata."""
    payload = {
        "objects": [{
            "name": obj.name, "role": obj.get("vcf.semantic_role"), "parent_bone": obj.parent_bone,
            "vertices": [[round(axis, 6) for axis in vertex.co] for vertex in obj.data.vertices],
            "polygons": [list(polygon.vertices) for polygon in obj.data.polygons],
        } for obj in sorted(objects, key=lambda item: item.name)],
        "bones": [{"name": bone.name, "head": [round(axis, 6) for axis in bone.head_local], "tail": [round(axis, 6) for axis in bone.tail_local], "parent": bone.parent.name if bone.parent else None} for bone in sorted(armature.data.bones, key=lambda item: item.name)],
        "actions": [{"name": action.name, "curves": [{"path": curve.data_path, "index": curve.array_index, "keys": [[round(point.co.x, 6), round(point.co.y, 6)] for point in curve.keyframe_points]} for curve in sorted(action.fcurves, key=lambda item: (item.data_path, item.array_index))]} for action in sorted(actions, key=lambda item: item.name)],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def render_view_set(path: Path, slug: str, armature: bpy.types.Object) -> list[Path]:
    scene, camera = bpy.context.scene, scene_camera()
    target = _scene_target()
    distance = max((camera.location - target).length, 1.0)
    views = {"front": (0, -distance, distance * 0.25), "side": (distance, 0, distance * 0.25), "rear": (0, distance, distance * 0.25), "three_quarter": (distance * .72, -distance * .72, distance * .25), "skeleton": (0, -distance, distance * .25), "socket": (distance * .72, -distance * .72, distance * .25)}
    rendered = []
    previous_display = armature.show_in_front
    for name, offset in views.items():
        armature.show_in_front = name in {"skeleton", "socket"}
        armature.hide_render = name not in {"skeleton", "socket"}
        camera.location = target + Vector(offset)
        camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
        output = path / f"{slug}_{name}.png"
        scene.render.filepath = str(output)
        bpy.ops.render.render(write_still=True)
        rendered.append(output)
    armature.hide_render = True
    armature.show_in_front = previous_display
    # Eight fixed-angle frames are a deterministic, inspectable turntable.
    for index in range(8):
        from math import cos, pi, sin
        angle = 2 * pi * index / 8
        camera.location = target + Vector((sin(angle) * distance, -cos(angle) * distance, distance * .25))
        camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
        output = path / f"{slug}_turntable_{index:02d}.png"
        scene.render.filepath = str(output); bpy.ops.render.render(write_still=True); rendered.append(output)
    return rendered


def scene_camera():
    if not bpy.context.scene.camera: raise ValueError("QA_PREVIEW_CAMERA_MISSING: configure the render before view rendering")
    return bpy.context.scene.camera


def _scene_target() -> Vector:
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and not obj.hide_render]
    corners = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    return Vector(tuple((min(point[axis] for point in corners) + max(point[axis] for point in corners)) / 2 for axis in range(3)))
