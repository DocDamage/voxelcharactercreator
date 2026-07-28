"""Blender adapter for typed VOX scenes and pure meshing."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import bpy

from blender_worker.adapters.vox_reader import VoxDocument, read_vox
from blender_worker.adapters.vox_scene import ResolvedVoxel, resolve_scene_voxels, voxel_bounds
from blender_worker.geometry.vox_mesher import MeshingVoxel, mesh_voxels


@dataclass(frozen=True)
class VoxImportOptions:
    meshing_mode: str = "greedy"
    target_extent_meters: float = 5.5


def import_vox_scene(path: Path, make_material, options: VoxImportOptions | None = None) -> list[bpy.types.Object]:
    """Create one normalized editable mesh per model/layer/semantic identity."""
    options = options or VoxImportOptions()
    document = read_vox(path)
    voxels = resolve_scene_voxels(document)
    minimum, maximum = voxel_bounds(voxels)
    extent = max(maximum[index] - minimum[index] for index in range(3))
    unit = options.target_extent_meters / extent
    root_collection = bpy.data.collections.new(f"VOX::{path.stem}")
    bpy.context.scene.collection.children.link(root_collection)
    root_collection["vcf.vox_source"] = str(path)
    root_collection["vcf.vox_meshing_mode"] = options.meshing_mode
    root_collection["vcf.vox_unit_meters"] = unit
    root_collection["vcf.vox_normalization_origin"] = list(minimum)
    grouped: dict[tuple[int, int | None, str, object], list[ResolvedVoxel]] = defaultdict(list)
    for voxel in voxels:
        grouped[(voxel.model_id, voxel.layer_id, voxel.semantic_part, voxel.transform)].append(voxel)
    created: list[bpy.types.Object] = []
    used_names: set[str] = set()
    for (model_id, layer_id, semantic, transform), cells in sorted(grouped.items(), key=lambda item: (item[0][0], str(item[0][1]), item[0][2], item[0][3].translation)):
        mesh_data = mesh_voxels(
            [MeshingVoxel(cell.x, cell.y, cell.z, cell.color_index, cell.semantic_part) for cell in cells],
            options.meshing_mode,  # type: ignore[arg-type]
        )
        vertices = [
            ((vertex[0] - minimum[0]) * unit, (vertex[1] - minimum[1]) * unit, (vertex[2] - minimum[2]) * unit)
            for vertex in mesh_data.vertices
        ]
        mesh = bpy.data.meshes.new(f"VOX_Mesh_{model_id}")
        mesh.from_pydata(vertices, [], mesh_data.faces)
        mesh.update()
        base_name = _safe_name(semantic, f"model_{model_id}")
        object_name = base_name
        index = 2
        while object_name in used_names:
            object_name = f"{base_name}.{index:03d}"
            index += 1
        used_names.add(object_name)
        obj = bpy.data.objects.new(object_name, mesh)
        root_collection.objects.link(obj)
        obj["vcf.vox_model_id"] = model_id
        obj["vcf.vox_layer_id"] = -1 if layer_id is None else layer_id
        obj["vcf.semantic_part"] = semantic
        obj["vcf.vox_origin"] = list(minimum)
        obj["vcf.vox_world_translation"] = list(transform.translation)
        obj["vcf.vox_world_rotation"] = [value for row in transform.rotation for value in row]
        material_slots = {}
        for color_index in sorted(set(mesh_data.material_indices)):
            red, green, blue, alpha = document.palette[(color_index - 1) % 256]
            voxel_material = make_material(f"VOX_{color_index:03d}", f"#{red:02X}{green:02X}{blue:02X}")
            voxel_material.diffuse_color = (red / 255, green / 255, blue / 255, alpha / 255)
            obj.data.materials.append(voxel_material)
            material_slots[color_index] = len(obj.data.materials) - 1
        for polygon, color_index in zip(mesh.polygons, mesh_data.material_indices):
            polygon.material_index = material_slots[color_index]
        created.append(obj)
    return created


def _safe_name(value: str, fallback: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in "_.-" else "_" for character in value).strip("_")
    return cleaned or fallback
