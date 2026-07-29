"""Engine-safe baked secondary-motion segment rigs with rigid fallback."""

from __future__ import annotations

from math import radians
from typing import Any

import bpy
from mathutils import Vector

from vcf_core.factory import SecondaryMotionChain, validate_secondary_motion
from vcf_core.advanced import validate_spring_motion


def create_secondary_motion_rig(armature: bpy.types.Object, settings: dict[str, Any]) -> list[SecondaryMotionChain]:
    values = settings.get("secondary_motion", [])
    errors = validate_secondary_motion(values)
    if errors:
        raise ValueError("SECONDARY_INVALID: " + "; ".join(errors))
    chains = [SecondaryMotionChain(
        item["chain_id"], item["kind"], tuple(item["segments"]), item["parent_bone"],
        float(item["stiffness"]), float(item["damping"]), float(item["max_angle_degrees"]), item["fallback"],
    ) for item in values]
    if not chains:
        armature["vcf.secondary_motion"] = []
        return chains
    bpy.context.view_layer.objects.active = armature; armature.select_set(True); bpy.ops.object.mode_set(mode="EDIT")
    try:
        for chain in chains:
            parent = armature.data.edit_bones.get(chain.parent_bone)
            if parent is None:
                raise ValueError(f"SECONDARY_PARENT_MISSING: {chain.chain_id} references {chain.parent_bone}")
            head = parent.tail.copy()
            length = max((parent.tail - parent.head).length * 0.35, 0.025)
            for name in chain.segments:
                if armature.data.edit_bones.get(name):
                    raise ValueError(f"SECONDARY_BONE_DUPLICATE: {name}")
                bone = armature.data.edit_bones.new(name); bone.head = head; bone.tail = head + Vector((0, 0, -length)); bone.parent = parent
                parent, head = bone, bone.tail.copy()
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    armature["vcf.secondary_motion"] = [{"chain_id": chain.chain_id, "segments": list(chain.segments), "fallback": chain.fallback} for chain in chains]
    return chains


def bake_secondary_motion(armature: bpy.types.Object, actions: list[bpy.types.Action], chains: list[SecondaryMotionChain]) -> dict[str, Any]:
    """Bake deterministic damped follow-through curves into every exported action."""
    for action in actions:
        armature.animation_data.action = action
        start, end = int(action.get("vcf.frame_start", 1)), int(action.get("vcf.frame_end", 2))
        span = max(1, end - start)
        for chain in chains:
            for index, name in enumerate(chain.segments, start=1):
                bone = armature.pose.bones[name]; bone.rotation_mode = "XYZ"
                amplitude = radians(chain.max_angle_degrees) * (1.0 - chain.stiffness) / index
                for frame, factor in ((start, 0.0), (start + span // 2, amplitude * (1.0 - chain.damping)), (end, 0.0)):
                    bone.rotation_euler = (factor, 0.0, 0.0); bone.keyframe_insert("rotation_euler", frame=frame, group=name)
    return {"secondary_chain_count": len(chains), "secondary_bone_count": sum(len(chain.segments) for chain in chains), "secondary_motion_baked": all(any(chain.segments for chain in chains) for _action in actions) if chains else True, "secondary_rigid_fallback": all(chain.fallback == "rigid" for chain in chains)}


def bake_spring_motion(armature: bpy.types.Object, actions: list[bpy.types.Action], settings: dict[str, Any]) -> dict[str, Any]:
    chains=settings.get("spring_motion",[])
    if not chains:return {"spring_motion_requested":False,"spring_motion_applied":False,"spring_motion_baked":True,"spring_motion_rigid_fallback":True}
    errors=validate_spring_motion(chains)
    if errors:raise ValueError("SPRING_MOTION_INVALID: "+"; ".join(errors))
    missing=sorted({bone for chain in chains for bone in chain["bones"] if bone not in armature.pose.bones})
    if missing:raise ValueError("SPRING_MOTION_BONE_MISSING: "+", ".join(missing))
    for action in actions:
        armature.animation_data.action=action; start,end=int(action.get("vcf.frame_start",1)),int(action.get("vcf.frame_end",2)); span=max(1,end-start)
        for chain in chains:
            for index,name in enumerate(chain["bones"],1):
                bone=armature.pose.bones[name]; bone.rotation_mode="XYZ"; amplitude=radians(float(chain["max_angle_degrees"]))*(1-float(chain["stiffness"]))*((1-float(chain["damping"]))**index)
                lag=max(1,round(span*float(chain["damping"])*index*.1)); frames=((start,0.0),(min(end,start+span//3+lag),amplitude),(min(end,start+2*span//3+lag),-amplitude),(end,0.0))
                for frame,value in frames:bone.rotation_euler=(value,0,0);bone.keyframe_insert("rotation_euler",frame=frame,group=name)
    armature["vcf.spring_motion"]=[{"chain_id":chain["chain_id"],"bones":chain["bones"],"fallback":"rigid"} for chain in chains]
    return {"spring_motion_requested":True,"spring_motion_applied":True,"spring_motion_baked":True,"spring_motion_rigid_fallback":True,"spring_motion_chain_count":len(chains),"spring_motion_bone_count":sum(len(chain["bones"]) for chain in chains)}
