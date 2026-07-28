"""Collection-scoped engine export."""

from __future__ import annotations

from pathlib import Path
import bpy


def export_character(output: Path, slug: str, formats: list[str], objects: list[bpy.types.Object], armature: bpy.types.Object, profile) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in [*objects, armature]: obj.hide_set(False); obj.select_set(True)
    bpy.context.view_layer.objects.active = armature
    if "glb" in formats:
        bpy.ops.export_scene.gltf(filepath=str(output / f"{slug}.glb"), export_format="GLB", use_selection=True, export_animations=True, export_animation_mode="ACTIONS", export_nla_strips=False, export_materials="EXPORT", export_image_format="AUTO")
    if "fbx" in formats:
        bpy.ops.export_scene.fbx(filepath=str(output / f"{slug}.fbx"), use_selection=True, global_scale=profile.scale, axis_forward=profile.forward_axis, axis_up=profile.up_axis, add_leaf_bones=False, bake_anim=True, bake_anim_use_all_actions=True)
