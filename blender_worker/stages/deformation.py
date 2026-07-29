"""Optional deterministic deform binding with mandatory rigid fallback."""
from __future__ import annotations
from typing import Any, Callable
from math import radians
import bpy
from mathutils import Vector
from vcf_core.advanced import validate_deformation

def bind_with_fallback(objects: list[bpy.types.Object], armature: bpy.types.Object, resolutions: dict, settings: dict[str, Any], rigid_binder: Callable) -> dict[str, Any]:
    policy=settings.get("deformation")
    errors=validate_deformation(policy)
    if errors: raise ValueError("DEFORMATION_INVALID: "+"; ".join(errors))
    if not policy or policy["mode"]=="rigid":
        rigid_binder(objects,armature,resolutions)
        return {"deformation_requested":False,"deformation_applied":False,"deformation_fallback":"rigid","deformation_fallback_available":True}
    try:
        for role,resolution in resolutions.items():
            obj=next(item for item in objects if item.name==resolution.candidate)
            bone=resolution.parent_bone
            group=obj.vertex_groups.get(bone) or obj.vertex_groups.new(name=bone)
            group.add(list(range(len(obj.data.vertices))),1.0,"REPLACE")
            modifier=obj.modifiers.new(name="VCF_Deform",type="ARMATURE"); modifier.object=armature
            obj.parent=armature; obj["vcf.bind_mode"]="deform"; obj["vcf.parent_bone"]=bone; obj["vcf.max_influences"]=policy["max_influences"]
        return {"deformation_requested":True,"deformation_applied":True,"deformation_fallback":"rigid","deformation_fallback_available":True}
    except Exception:
        for obj in objects:
            for modifier in list(obj.modifiers):
                if modifier.name=="VCF_Deform": obj.modifiers.remove(modifier)
            obj.vertex_groups.clear()
        rigid_binder(objects,armature,resolutions)
        return {"deformation_requested":True,"deformation_applied":False,"deformation_fallback":"rigid","deformation_fallback_available":True}

def apply_part_transforms(objects: list[bpy.types.Object], settings: dict[str, Any]) -> list[bpy.types.Object]:
    """Apply reviewed editor transforms by asset ID or object name."""
    transforms=settings.get("part_transforms",{})
    for key,value in transforms.items():
        matches=[obj for obj in objects if obj.name==key or obj.get("vcf.asset_id")==key]
        if len(matches)!=1: raise ValueError(f"EDITOR_PART_AMBIGUOUS: {key} matched {len(matches)} objects")
        obj=matches[0]; obj.location+=Vector(value["location"]); obj.rotation_euler=tuple(radians(axis) for axis in value["rotation_degrees"]); obj.scale=tuple(value["scale"]); obj["vcf.editor_transform"]=value
    bpy.context.view_layer.update()
    return objects

def apply_socket_overrides(armature: bpy.types.Object, settings: dict[str, Any]) -> dict[str, bool]:
    overrides=settings.get("socket_overrides",{})
    if not overrides:return {"editor_socket_overrides_applied":True}
    bpy.context.view_layer.objects.active=armature; armature.select_set(True); bpy.ops.object.mode_set(mode="EDIT")
    try:
        for name,value in overrides.items():
            socket=armature.data.edit_bones.get(name); parent=armature.data.edit_bones.get(value["bone"])
            if socket is None or parent is None: raise ValueError(f"EDITOR_SOCKET_UNKNOWN: {name} or parent {value['bone']} is missing")
            length=max((socket.tail-socket.head).length,.01); socket.parent=parent; socket.head=parent.tail+Vector(value["offset"]); socket.tail=socket.head+Vector((0,-length,0))
    finally:bpy.ops.object.mode_set(mode="OBJECT")
    armature["vcf.editor_socket_overrides"]=overrides
    return {"editor_socket_overrides_applied":True}
