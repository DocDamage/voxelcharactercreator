"""Fitted humanoid rig, rigid binding, and socket construction for Phase 3."""

from __future__ import annotations

from math import pi
from pathlib import Path
from typing import Any

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from vcf_core.rigging import REQUIRED_SOCKET_BONES, PartResolution, get_rig_template, standard_male_template
from vcf_core.advanced import load_topology_rig


def _bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return Vector(tuple(min(corner[index] for corner in corners) for index in range(3))), Vector(tuple(max(corner[index] for corner in corners) for index in range(3)))


def _center(obj: bpy.types.Object) -> Vector:
    low, high = _bounds(obj)
    return (low + high) / 2


def _combined_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    lows, highs = zip(*(_bounds(obj) for obj in objects))
    return (
        Vector(tuple(min(point[axis] for point in lows) for axis in range(3))),
        Vector(tuple(max(point[axis] for point in highs) for axis in range(3))),
    )


def _template_guides(template, low: Vector, high: Vector) -> dict[str, Vector]:
    """Map normalized template joints into the fitted character's body space."""
    height = high.z - low.z
    center = (low + high) / 2
    return {
        name: Vector((center.x + point[0] * height, center.y + point[1] * height, low.z + point[2] * height))
        for name, point in template.normalized_joints.items()
    }


def _point_in_bounds(obj: bpy.types.Object, guide: Vector) -> Vector:
    low, high = _bounds(obj)
    return Vector(tuple(max(low[axis], min(high[axis], guide[axis])) for axis in range(3)))


def _joint_between(first: bpy.types.Object, second: bpy.types.Object, guide: Vector) -> Vector:
    """Fit a guide to the shared boundary or midpoint gap of two semantic parts."""
    first_low, first_high = _bounds(first)
    second_low, second_high = _bounds(second)
    coordinates = []
    for axis in range(3):
        overlap_low = max(first_low[axis], second_low[axis])
        overlap_high = min(first_high[axis], second_high[axis])
        if overlap_low <= overlap_high:
            coordinates.append(max(overlap_low, min(overlap_high, guide[axis])))
        elif first_high[axis] < second_low[axis]:
            coordinates.append((first_high[axis] + second_low[axis]) / 2)
        else:
            coordinates.append((second_high[axis] + first_low[axis]) / 2)
    return Vector(coordinates)


def _safe_tail(head: Vector, tail: Vector) -> Vector:
    return tail if (tail - head).length > 0.001 else head + Vector((0.0, 0.0, 0.05))


def _add_bone(bones, name: str, head: Vector, tail: Vector, parent=None):
    bone = bones.new(name)
    bone.head, bone.tail = head, _safe_tail(head, tail)
    if parent:
        bone.parent = parent
        bone.use_connect = (bone.head - parent.tail).length < 0.001
    return bone


def _scale_to_target(
    objects: list[bpy.types.Object],
    target_height: float | None,
    measurement_objects: list[bpy.types.Object],
) -> float:
    if not target_height:
        return 1.0
    low = min(_bounds(obj)[0].z for obj in measurement_objects)
    high = max(_bounds(obj)[1].z for obj in measurement_objects)
    current = high - low
    if current <= 0:
        raise ValueError("RIG_INVALID_HEIGHT: assembled geometry has no positive height")
    scale = target_height / current
    for obj in objects:
        obj.location *= scale
        obj.scale *= scale
    bpy.context.view_layer.update()
    # Object origins need not sit at the mesh floor.  Re-ground after scaling
    # the evaluated bounds rather than assuming an origin-based transform keeps
    # the existing ground contact invariant intact.
    lowest = min(_bounds(obj)[0].z for obj in objects)
    for obj in objects:
        obj.location.z -= lowest
    bpy.context.view_layer.update()
    return scale


def _apply_limb_overrides(bones, settings: dict[str, Any], *, minimum: float, maximum: float) -> dict[str, float]:
    overrides = settings.get("limb_length_overrides", {})
    if not overrides:
        return {}
    if not isinstance(overrides, dict):
        raise ValueError("RIG_INVALID_LIMB_OVERRIDE: limb_length_overrides must be an object")
    applied: dict[str, float] = {}

    def translate_branch(bone, delta: Vector) -> None:
        bone.head += delta
        bone.tail += delta
        for child in bone.children:
            translate_branch(child, delta)

    for name, factor in overrides.items():
        if name not in bones or isinstance(factor, bool) or not isinstance(factor, (int, float)) or not minimum <= factor <= maximum:
            raise ValueError(f"RIG_INVALID_LIMB_OVERRIDE: {name} must name an existing bone with a scale from {minimum} to {maximum}")
        bone = bones[name]
        previous_tail = bone.tail.copy()
        bone.tail = bone.head + (bone.tail - bone.head) * float(factor)
        delta = bone.tail - previous_tail
        for child in bone.children:
            translate_branch(child, delta)
        applied[name] = float(factor)
    return applied


def create_fitted_rig(objects: list[bpy.types.Object], resolutions: dict[str, PartResolution], job: dict) -> tuple[bpy.types.Object, dict[str, Any]]:
    """Fit an edit-bone skeleton to semantic bounds, then validate symmetry/ground."""
    if not objects:
        raise ValueError("RIG_MISSING_GEOMETRY: no resolved objects were supplied")
    advanced_path=Path(__file__).resolve().parents[2]/"config"/"advanced_rigs"/f"{job['rig_template']}.v1.json"
    if advanced_path.is_file():
        return create_topology_rig(objects,resolutions,job,load_topology_rig(advanced_path))
    by_role = {role: next(obj for obj in objects if obj.name == resolution.candidate) for role, resolution in resolutions.items()}
    template = get_rig_template(job["rig_template"])
    measurement_objects = [by_role[role] for role in template.required_roles]
    scale = _scale_to_target(objects, job.get("target_height_meters"), measurement_objects)
    body_low, body_high = _combined_bounds(measurement_objects)
    body_height = body_high.z - body_low.z
    guides = _template_guides(template, body_low, body_high)
    data = bpy.data.armatures.new("VCF_Rig")
    armature = bpy.data.objects.new("VCF_Rig", data)
    bpy.context.collection.objects.link(armature)
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        pelvis_point = _point_in_bounds(by_role["pelvis"], guides["pelvis"])
        spine_point = _joint_between(by_role["pelvis"], by_role["torso"], guides["spine"])
        neck_point = _joint_between(by_role["torso"], by_role["head"], guides["neck"])
        head_point = _point_in_bounds(by_role["head"], guides["head"])
        root_point = guides["root"]
        root_point.z = body_low.z
        root = _add_bone(data.edit_bones, "root", root_point, pelvis_point)
        pelvis = _add_bone(data.edit_bones, template.bone_by_role["pelvis"], pelvis_point, spine_point, root)
        spine = _add_bone(data.edit_bones, template.bone_by_role["torso"], spine_point, neck_point, pelvis)
        _add_bone(data.edit_bones, template.bone_by_role["head"], neck_point, head_point, spine)
        for side in ("L", "R"):
            suffix = side.lower()
            upper = by_role[f"upper_arm_{side.lower()}"]
            lower = by_role[f"lower_arm_{side.lower()}"]
            hand_obj = by_role[f"hand_{side.lower()}"]
            shoulder = _joint_between(by_role["torso"], upper, guides[f"shoulder.{side}"])
            elbow = _joint_between(upper, lower, guides[f"elbow.{side}"])
            wrist = _joint_between(lower, hand_obj, guides[f"wrist.{side}"])
            hand_tail = _center(hand_obj)
            upper_bone = _add_bone(data.edit_bones, template.bone_by_role[f"upper_arm_{suffix}"], shoulder, elbow, spine)
            lower_bone = _add_bone(data.edit_bones, template.bone_by_role[f"lower_arm_{suffix}"], elbow, wrist, upper_bone)
            _add_bone(data.edit_bones, template.bone_by_role[f"hand_{suffix}"], wrist, hand_tail, lower_bone)
            thigh = by_role[f"upper_leg_{suffix}"]
            shin = by_role[f"lower_leg_{suffix}"]
            foot = by_role[f"foot_{suffix}"]
            hip = _joint_between(by_role["pelvis"], thigh, guides[f"hip.{side}"])
            knee = _joint_between(thigh, shin, guides[f"knee.{side}"])
            ankle = _joint_between(shin, foot, guides[f"ankle.{side}"])
            foot_tail = _center(foot)
            thigh_bone = _add_bone(data.edit_bones, template.bone_by_role[f"upper_leg_{suffix}"], hip, knee, pelvis)
            shin_bone = _add_bone(data.edit_bones, template.bone_by_role[f"lower_leg_{suffix}"], knee, ankle, thigh_bone)
            _add_bone(data.edit_bones, template.bone_by_role[f"foot_{suffix}"], ankle, foot_tail, shin_bone)
        # Socket bones are explicit and exported with the armature rather than
        # being empty helper objects which many formats discard.
        socket_length = max(body_height * 0.02, 0.02)
        for name, (parent_name, normalized_offset) in template.sockets.items():
            parent = data.edit_bones.get(parent_name)
            if parent is None:
                raise ValueError(f"RIG_SOCKET_UNKNOWN_PARENT: {name} references missing bone {parent_name}")
            socket_head = parent.tail + Vector(normalized_offset) * body_height
            _add_bone(data.edit_bones, name, socket_head, socket_head + Vector((0.0, -socket_length, 0.0)), parent)
        settings = job.get("settings_overrides", {})
        if not isinstance(settings, dict):
            raise ValueError("RIG_INVALID_SETTINGS: settings_overrides must be an object")
        applied_overrides = _apply_limb_overrides(data.edit_bones, settings, minimum=template.tolerances["min_limb_scale"], maximum=template.tolerances["max_limb_scale"])
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    armature["vcf.rig_template"] = template.template_id
    armature["vcf.rig_template_version"] = template.schema_version
    armature["vcf.fit_scale"] = scale
    armature["vcf.body_height_meters"] = body_height
    armature["vcf.bone_by_role"] = template.bone_by_role
    armature["vcf.template_joints_applied"] = sorted(template.normalized_joints)
    armature["vcf.template_sockets_applied"] = sorted(template.sockets)
    armature["vcf.limb_length_overrides"] = applied_overrides
    armature["vcf.rig_tolerances"] = template.tolerances
    checks = validate_fitted_rig(armature, objects, template=template)
    if not all(checks.values()):
        raise ValueError("RIG_FIT_INVALID: " + ", ".join(name for name, passed in checks.items() if not passed))
    return armature, checks


def create_topology_rig(objects: list[bpy.types.Object], resolutions: dict[str, PartResolution], job: dict, template) -> tuple[bpy.types.Object, dict[str, Any]]:
    """Fit an arbitrary acyclic topology to manifest-resolved part centers."""
    by_role={role:next(obj for obj in objects if obj.name==resolution.candidate) for role,resolution in resolutions.items()}
    scale=_scale_to_target(objects,job.get("target_height_meters"),list(by_role.values()))
    low,high=_combined_bounds(list(by_role.values())); center=(low+high)/2; role_by_bone={bone:role for role,bone in template.role_bones.items()}
    data=bpy.data.armatures.new("VCF_Rig"); armature=bpy.data.objects.new("VCF_Rig",data); bpy.context.collection.objects.link(armature); bpy.context.view_layer.objects.active=armature; armature.select_set(True); bpy.ops.object.mode_set(mode="EDIT")
    try:
        pending=dict(template.bones)
        while pending:
            progressed=False
            for name,parent_name in list(pending.items()):
                if parent_name is not None and data.edit_bones.get(parent_name) is None:continue
                role=role_by_bone.get(name); point=_center(by_role[role]) if role else center.copy(); parent=data.edit_bones.get(parent_name) if parent_name else None
                if parent and role is None:point=parent.tail.copy()
                tail=point+Vector((0,0,max((high.z-low.z)*.04,.02))); _add_bone(data.edit_bones,name,point,tail,parent); pending.pop(name); progressed=True
            if not progressed:raise ValueError("RIG_TOPOLOGY_CYCLE: advanced template hierarchy cannot be constructed")
        for name,(parent_name,offset) in template.sockets.items():
            parent=data.edit_bones.get(parent_name); head=parent.tail+Vector(offset); _add_bone(data.edit_bones,name,head,head+Vector((0,-.02,0)),parent)
    finally:bpy.ops.object.mode_set(mode="OBJECT")
    armature["vcf.rig_template"]=template.template_id; armature["vcf.topology"]=template.topology; armature["vcf.fit_scale"]=scale; armature["vcf.bone_by_role"]=template.role_bones; armature["vcf.template_sockets_applied"]=sorted(template.sockets)
    existing=set(armature.data.bones.keys()); checks={"rig_required_bones_present":set(template.bones).issubset(existing),"rig_template_sockets_applied":set(template.sockets).issubset(existing),"rig_required_role_count":len(resolutions)==len(template.required_roles),"rig_grounded":abs(min(_bounds(obj)[0].z for obj in objects))<=.002,"rig_topology_valid":not template.validate()}
    if not all(checks.values()):raise ValueError("RIG_TOPOLOGY_INVALID: "+", ".join(name for name,passed in checks.items() if not passed))
    return armature,checks


def rigid_bind(objects: list[bpy.types.Object], armature: bpy.types.Object, resolutions: dict[str, PartResolution]) -> None:
    for role, resolution in resolutions.items():
        obj = next(item for item in objects if item.name == resolution.candidate)
        bone = resolution.parent_bone
        if bone not in armature.pose.bones:
            raise ValueError(f"RIG_BIND_UNKNOWN_BONE: {role} resolved to missing bone {bone}")
        world = obj.matrix_world.copy()
        obj.parent = armature
        obj.parent_type = "BONE"
        obj.parent_bone = bone
        obj.matrix_world = world
        obj["vcf.bind_mode"] = "rigid"
        obj["vcf.parent_bone"] = bone


def align_weapon_to_primary_grip(objects: list[bpy.types.Object], armature: bpy.types.Object, resolutions: dict[str, PartResolution]) -> dict[str, float | bool]:
    """Align a declared primary grip to the right-hand socket before rigid bind."""
    weapon_resolution = resolutions.get("weapon")
    if not weapon_resolution:
        return {"weapon_present": False, "primary_grip_aligned": True, "primary_grip_distance_meters": 0.0}
    weapon = next(item for item in objects if item.name == weapon_resolution.candidate)
    socket = weapon.get("vcf.asset_sockets", {})
    grip = socket.get("primary_grip") if hasattr(socket, "get") else None
    if not grip:
        raise ValueError("SOCKET_MISSING_PRIMARY_GRIP: weapon manifest does not declare primary_grip")
    # Mesh vertices are already authored in meters, and matrix_world carries the
    # fitted object scale. Multiplying by the fit scale here would apply it twice.
    unit = float(weapon.get("vcf.voxel_unit_meters", 1.0))
    # Authoring VOX is Z-up.  Put the long blade outboard of the right hand so
    # it remains visible in the standard front preview and clear of the torso.
    weapon.rotation_euler = (0.0, -pi / 4, 0.0)
    bpy.context.view_layer.update()
    grip_world = weapon.matrix_world @ Vector(tuple(float(value) * unit for value in grip))
    target = armature.matrix_world @ armature.pose.bones["weapon_socket.R"].head
    weapon.location += target - grip_world
    bpy.context.view_layer.update()
    aligned = weapon.matrix_world @ Vector(tuple(float(value) * unit for value in grip))
    distance = (aligned - target).length
    weapon["vcf.socket_alignment"] = {"primary_grip_distance_meters": distance}
    required_metadata = {"primary_grip", "secondary_grip", "back_carry", "waist_carry", "trail_base", "trail_tip"}
    declared = set(socket.keys()) if hasattr(socket, "keys") else set()
    missing = sorted(required_metadata - declared)
    socket_bones = set(REQUIRED_SOCKET_BONES)
    existing_bones = set(armature.pose.bones.keys())
    # Carry points are source-space attachment alternatives.  Record their
    # post-fit locations so equipment can be deterministically switched to
    # back/waist sockets by the later animation stage.
    carry_points = {}
    for source_name, target_name in (("back_carry", "back_socket"), ("waist_carry", "waist_socket")):
        if source_name not in declared or target_name not in armature.pose.bones:
            continue
        source_point = weapon.matrix_world @ Vector(tuple(float(axis) * unit for axis in socket[source_name]))
        target_point = armature.matrix_world @ armature.pose.bones[target_name].head
        translation = target_point - source_point
        carry_points[source_name] = {
            "target_bone": target_name,
            "translation": [round(value, 6) for value in translation],
            "alignment_distance_meters": round((source_point + translation - target_point).length, 6),
        }
    weapon["vcf.carry_alignment"] = carry_points
    grip_allowance = max(unit * float(armature.get("vcf.fit_scale", 1.0)) * 4.0, 0.05)
    intersections = _weapon_body_intersections(weapon, objects, grip_world=aligned, grip_allowance=grip_allowance)
    tolerances = armature.get("vcf.rig_tolerances", {})
    socket_tolerance = float(tolerances.get("socket_alignment_meters", 0.001))
    return {
        "weapon_present": True,
        "weapon_socket_metadata_complete": not missing,
        "weapon_socket_bones_present": socket_bones.issubset(existing_bones),
        "primary_grip_aligned": distance <= socket_tolerance,
        "primary_grip_distance_meters": round(distance, 6),
        "carry_alignment_declared": {"back_carry", "waist_carry"}.issubset(declared),
        "carry_alignment_valid": set(carry_points) == {"back_carry", "waist_carry"} and all(
            point["alignment_distance_meters"] <= socket_tolerance for point in carry_points.values()
        ),
        "weapon_body_clear": not intersections,
        "weapon_body_intersection_count": len(intersections),
        "weapon_body_intersections": intersections,
    }


def _weapon_body_intersections(
    weapon: bpy.types.Object,
    objects: list[bpy.types.Object],
    *,
    grip_world: Vector,
    grip_allowance: float,
) -> list[str]:
    """Use an AABB broad phase and world-space BVH outside the grip allowance."""
    weapon_low, weapon_high = _bounds(weapon)
    weapon_tree = _world_bvh(weapon)
    intersecting: list[str] = []
    for obj in objects:
        if obj == weapon or obj.get("vcf.semantic_role") in {"hand_r", "glove_r"}:
            continue
        low, high = _bounds(obj)
        overlap_low = Vector(tuple(max(weapon_low[index], low[index]) for index in range(3)))
        overlap_high = Vector(tuple(min(weapon_high[index], high[index]) for index in range(3)))
        if all(overlap_low[index] < overlap_high[index] for index in range(3)):
            if not weapon_tree.overlap(_world_bvh(obj)):
                continue
            closest = Vector(tuple(max(overlap_low[index], min(overlap_high[index], grip_world[index])) for index in range(3)))
            if (closest - grip_world).length <= grip_allowance:
                continue
            intersecting.append(obj.name)
    return intersecting


def _world_bvh(obj: bpy.types.Object) -> BVHTree:
    vertices = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    polygons = [tuple(polygon.vertices) for polygon in obj.data.polygons]
    return BVHTree.FromPolygons(vertices, polygons, all_triangles=False, epsilon=0.00001)


def render_joint_pose_preview(armature: bpy.types.Object, path: Path) -> None:
    """Render a non-destructive diagnostic pose covering each major joint pair."""
    pose = armature.pose
    bone_by_role = armature.get("vcf.bone_by_role", {})
    role_angles = {
        "upper_arm_l": (0.0, 0.0, -0.45), "lower_arm_l": (0.0, 0.0, -0.55), "hand_l": (0.2, 0.0, 0.0),
        "upper_arm_r": (0.0, 0.0, 0.35), "lower_arm_r": (0.0, 0.0, 0.45), "hand_r": (-0.2, 0.0, 0.0),
        "upper_leg_l": (0.35, 0.0, 0.0), "lower_leg_l": (-0.55, 0.0, 0.0), "foot_l": (0.2, 0.0, 0.0),
        "upper_leg_r": (-0.3, 0.0, 0.0), "lower_leg_r": (0.5, 0.0, 0.0), "foot_r": (-0.2, 0.0, 0.0),
    }
    angles = {str(bone_by_role[role]): angle for role, angle in role_angles.items() if role in bone_by_role and str(bone_by_role[role]) in pose.bones}
    if not angles:
        # Advanced topologies pose their first non-root semantic bone so the
        # diagnostic remains meaningful without assuming humanoid limbs.
        for role in bone_by_role.keys():
            name = str(bone_by_role[role])
            if name in pose.bones and name != "root":
                angles[name] = (0.0, 0.12, 0.0)
                break
    saved = {name: (pose.bones[name].rotation_mode, pose.bones[name].rotation_euler.copy()) for name in angles}
    try:
        for name, angle in angles.items():
            bone = pose.bones[name]
            bone.rotation_mode = "XYZ"
            bone.rotation_euler = angle
        bpy.context.view_layer.update()
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
    finally:
        for name, (mode, rotation) in saved.items():
            bone = pose.bones[name]
            bone.rotation_mode = mode
            bone.rotation_euler = rotation
        bpy.context.view_layer.update()


def validate_fitted_rig(armature: bpy.types.Object, objects: list[bpy.types.Object], *, template=None) -> dict[str, bool]:
    template = template or standard_male_template()
    required = template.required_roles
    required_bones = {"root", *(template.bone_by_role[role] for role in required)}
    lowest = min(_bounds(obj)[0].z for obj in objects)
    left = armature.data.bones.get(template.bone_by_role["upper_arm_l"])
    right = armature.data.bones.get(template.bone_by_role["upper_arm_r"])
    return {
        "rig_required_bones_present": required_bones.issubset(set(armature.data.bones.keys())),
        "rig_template_joints_applied": set(armature.get("vcf.template_joints_applied", ())) == set(template.normalized_joints),
        "rig_template_sockets_applied": set(armature.get("vcf.template_sockets_applied", ())) == set(template.sockets),
        "rig_grounded": abs(lowest) <= template.tolerances["ground_meters"],
        "rig_left_right_symmetric": bool(left and right and abs(left.head.x + right.head.x) <= template.tolerances["symmetry_meters"] and abs(left.tail.x + right.tail.x) <= template.tolerances["symmetry_meters"]),
        "rig_required_role_count": sum(1 for obj in objects if obj.get("vcf.semantic_role") in required) == len(required),
    }
