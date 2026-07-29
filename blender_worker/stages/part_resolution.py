"""Blender adapter for the deterministic Phase 3 part resolver."""

from __future__ import annotations

from pathlib import Path
import hashlib

import bpy
from mathutils import Vector

from vcf_core.rigging import PartCandidate, PartResolution, ResolutionTrace, get_rig_template, resolve_parts
from vcf_core.advanced import load_topology_rig


PART_COLORS = {
    "head": "#E6AA7C", "hair": "#E1BE3C", "torso": "#3E73AA", "pelvis": "#6D4B75",
    "upper_arm_l": "#4FB1A7", "upper_arm_r": "#4FB1A7", "lower_arm_l": "#77D2C8", "lower_arm_r": "#77D2C8",
    "hand_l": "#F0C39D", "hand_r": "#F0C39D", "upper_leg_l": "#596FC6", "upper_leg_r": "#596FC6",
    "lower_leg_l": "#8597E6", "lower_leg_r": "#8597E6", "foot_l": "#343A4E", "foot_r": "#343A4E",
    "coat": "#A05373", "glove_l": "#2F3442", "glove_r": "#485064",
    "boot_l": "#2F3442", "boot_r": "#485064", "pauldron_l": "#B6C4D2",
    "pauldron_r": "#8392A3", "weapon": "#D4E3EF",
}

def _part_color(role: str) -> str:
    if role in PART_COLORS:return PART_COLORS[role]
    digest=hashlib.sha256(role.encode()).digest()
    return "#"+"".join(f"{64+(channel%160):02X}" for channel in digest[:3])


def _bounds(obj: bpy.types.Object) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return (
        tuple(min(corner[index] for corner in corners) for index in range(3)),
        tuple(max(corner[index] for corner in corners) for index in range(3)),
    )


def _candidate(obj: bpy.types.Object) -> PartCandidate:
    tags = tuple(str(item) for item in obj.get("vcf.semantic_tags", []))
    marker_colors = tuple(str(item) for item in obj.get("vcf.marker_colors", []))
    layer = obj.get("vcf.vox_layer_name")
    component_count = _connected_components(obj)
    obj["vcf.connected_components"] = component_count
    return PartCandidate(
        name=obj.name, asset_id=obj.get("vcf.asset_id"), semantic_tags=tags,
        layer_name=str(layer) if layer else None, marker_colors=marker_colors,
        bounds=_bounds(obj), component_count=component_count,
    )


def _connected_components(obj: bpy.types.Object) -> int:
    """Count mesh islands for diagnostics without changing editable geometry."""
    if obj.type != "MESH" or not obj.data.vertices:
        return 0
    neighbors: dict[int, set[int]] = {vertex.index: set() for vertex in obj.data.vertices}
    for edge in obj.data.edges:
        neighbors[edge.vertices[0]].add(edge.vertices[1])
        neighbors[edge.vertices[1]].add(edge.vertices[0])
    remaining = set(neighbors)
    components = 0
    while remaining:
        components += 1
        frontier = [remaining.pop()]
        while frontier:
            current = frontier.pop()
            linked = neighbors[current] & remaining
            remaining.difference_update(linked)
            frontier.extend(linked)
    return components


def resolve_scene_parts(objects: list[bpy.types.Object], job: dict) -> tuple[dict, list[dict]]:
    """Persist one semantic role, explanation trace, and intended bone per part."""
    advanced_path=Path(__file__).resolve().parents[2]/"config"/"advanced_rigs"/f"{job['rig_template']}.v1.json"
    if advanced_path.is_file():
        template=load_topology_rig(advanced_path); candidates=[_candidate(obj) for obj in objects]; resolutions={}; traces=[]
        used=set()
        for role in template.required_roles:
            matches=[item for item in candidates if role in item.semantic_tags]
            if len(matches)!=1: raise ValueError(f"PART_{'MISSING' if not matches else 'CONFLICT'}: advanced role {role} matched {len(matches)} objects")
            item=matches[0]; used.add(item.name); trace=ResolutionTrace(role,"asset_manifest",item.name,1.0,f"resolved {item.name} via advanced topology manifest")
            traces.append(trace); resolutions[role]=PartResolution(role,item.name,1.0,"asset_manifest",template.role_bones[role],(trace,))
        extras=sorted(obj.name for obj in objects if obj.name not in used)
        if extras: raise ValueError("PART_UNRESOLVED: advanced topology objects lack required semantic roles: "+", ".join(extras))
    else:
        template = get_rig_template(job["rig_template"])
        resolutions, traces = resolve_parts([_candidate(obj) for obj in objects], part_overrides=job.get("part_overrides", {}), template=template)
    by_name = {obj.name: obj for obj in objects}
    for role, resolution in resolutions.items():
        obj = by_name[resolution.candidate]
        obj["vcf.semantic_role"] = role
        obj["vcf.part_resolution"] = {
            "source": resolution.source, "confidence": resolution.confidence, "parent_bone": resolution.parent_bone,
        }
    trace_payload = [
        {"role": item.role, "source": item.source, "candidate": item.candidate, "confidence": item.confidence, "detail": item.detail}
        for item in traces
    ]
    return resolutions, trace_payload


def render_part_map_preview(objects: list[bpy.types.Object], path: Path) -> None:
    """Render an explicit color-coded mapping preview and restore source materials."""
    saved = [(obj, list(obj.data.materials)) for obj in objects if obj.type == "MESH"]
    materials: dict[str, bpy.types.Material] = {}
    try:
        for obj, _original in saved:
            role = obj.get("vcf.semantic_role", "accessory")
            color = _part_color(role)
            if color not in materials:
                material = bpy.data.materials.new(f"VCF_PartMap_{role}")
                value = color.lstrip("#")
                material.diffuse_color = tuple(int(value[index:index + 2], 16) / 255 for index in (0, 2, 4)) + (1,)
                material.use_nodes = True
                material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = material.diffuse_color
                materials[color] = material
            obj.data.materials.clear()
            obj.data.materials.append(materials[color])
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
    finally:
        for obj, original in saved:
            obj.data.materials.clear()
            for material in original:
                obj.data.materials.append(material)
