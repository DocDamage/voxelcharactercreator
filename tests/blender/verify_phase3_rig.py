"""Headless Phase 3 acceptance test for fitted rigid binding and sockets."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blender_worker.process_character import material
from blender_worker.stages.asset_assembly import assemble_assets
from blender_worker.stages.part_resolution import resolve_scene_parts
from blender_worker.stages.rigging import align_weapon_to_primary_grip, create_fitted_rig, rigid_bind
from vcf_core.assets import load_registry
from vcf_core.jobs import load_job
from vcf_core.rigging import get_rig_template


def main() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    job = load_job(ROOT / "characters" / "original" / "heavy_sword_hero.json", ROOT)
    job["settings_overrides"] = {"limb_length_overrides": {"upper_arm.L": 1.1, "upper_arm.R": 1.1}}
    objects = assemble_assets(job, load_registry(ROOT), ROOT, material)
    resolutions, trace = resolve_scene_parts(objects, job)
    armature, rig_checks = create_fitted_rig(objects, resolutions, job)
    socket_checks = align_weapon_to_primary_grip(objects, armature, resolutions)
    template = get_rig_template(job["rig_template"])
    weapon = next(obj for obj in objects if obj.get("vcf.semantic_role") == "weapon")
    grip = weapon.get("vcf.asset_sockets")["primary_grip"]
    unit = float(weapon.get("vcf.voxel_unit_meters"))
    actual_grip = weapon.matrix_world @ Vector(tuple(float(axis) * unit for axis in grip))
    grip_target = armature.matrix_world @ armature.pose.bones["weapon_socket.R"].head
    weapon_corners = [weapon.matrix_world @ Vector(corner) for corner in weapon.bound_box]
    weapon_extent = max(max(point[axis] for point in weapon_corners) - min(point[axis] for point in weapon_corners) for axis in range(3))
    rigid_bind(objects, armature, resolutions)

    required_bones = {"root", "pelvis", "spine", "head", "upper_arm.L", "forearm.L", "hand.L", "thigh.L", "shin.L", "foot.L", "weapon_socket.R", "off_hand_socket.L", "back_socket", "waist_socket", "effect_socket", "projectile_socket"}
    assert required_bones.issubset(set(armature.data.bones.keys()))
    assert len(trace) == len(objects) == len(resolutions)
    assert all(rig_checks.values()), rig_checks
    assert armature["vcf.fit_scale"] != 1.0
    assert abs(float(armature["vcf.body_height_meters"]) - job["target_height_meters"]) < 0.0001, (
        armature["vcf.body_height_meters"], job["target_height_meters"]
    )
    assert set(armature["vcf.template_joints_applied"]) == set(template.normalized_joints)
    assert set(armature["vcf.template_sockets_applied"]) == set(template.sockets)
    assert armature["vcf.limb_length_overrides"]["upper_arm.L"] == 1.1
    assert (armature.data.bones["upper_arm.L"].tail_local - armature.data.bones["forearm.L"].head_local).length < 0.0001
    assert socket_checks["primary_grip_aligned"], socket_checks
    assert (actual_grip - grip_target).length <= template.tolerances["socket_alignment_meters"]
    assert weapon_extent > 1.5
    assert socket_checks["weapon_socket_metadata_complete"], socket_checks
    assert socket_checks["weapon_socket_bones_present"], socket_checks
    assert socket_checks["carry_alignment_declared"], socket_checks
    assert socket_checks["carry_alignment_valid"], socket_checks
    assert socket_checks["weapon_body_clear"], socket_checks
    assert all(obj.parent == armature and obj.parent_type == "BONE" and obj.get("vcf.bind_mode") == "rigid" for obj in objects)
    assert bpy.data.objects["hsh_glove_l"].parent_bone == "hand.L"
    assert bpy.data.objects["hsh_glove_r"].parent_bone == "hand.R"
    assert bpy.data.objects["hsh_boot_l"].parent_bone == "foot.L"
    assert bpy.data.objects["hsh_boot_r"].parent_bone == "foot.R"
    assert bpy.data.objects["hsh_pauldron_l"].parent_bone == "upper_arm.L"
    assert bpy.data.objects["hsh_pauldron_r"].parent_bone == "upper_arm.R"

    arm = bpy.data.objects["VCF_Rig"]
    upper_arm = bpy.data.objects["hsh_upper_arm_l"]
    left_pauldron = bpy.data.objects["hsh_pauldron_l"]
    right_pauldron = bpy.data.objects["hsh_pauldron_r"]
    before = upper_arm.matrix_world.copy()
    left_before = left_pauldron.matrix_world.copy()
    right_before = right_pauldron.matrix_world.copy()
    pose_bone = arm.pose.bones["upper_arm.L"]
    pose_bone.rotation_mode = "XYZ"
    pose_bone.rotation_euler.y = 0.35
    bpy.context.view_layer.update()
    assert (upper_arm.matrix_world.translation - before.translation).length > 0.001
    assert (left_pauldron.matrix_world.translation - left_before.translation).length > 0.001
    assert (right_pauldron.matrix_world.translation - right_before.translation).length < 0.0001
    print("Phase 3 fitted-rig, rigid-bind, and socket verification passed.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Blender otherwise reports a Python traceback while returning a zero
        # process code, which makes CI treat a failed rig assertion as green.
        import traceback
        traceback.print_exc()
        raise SystemExit(1)
