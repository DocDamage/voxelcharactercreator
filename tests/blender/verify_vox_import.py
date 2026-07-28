"""Headless Blender Phase 1 acceptance test; run through tools/verify.ps1 -Blender."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blender_worker.stages.vox_ingest import VoxImportOptions, import_vox_scene
from tests.vox_fixture import scene_graph_fixture


def material(name: str, color: str):
    result = bpy.data.materials.new(name)
    value = color.lstrip("#")
    result.diffuse_color = tuple(int(value[index : index + 2], 16) / 255 for index in (0, 2, 4)) + (1,)
    return result


def main() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    temporary = tempfile.TemporaryDirectory()
    path = Path(temporary.name) / "scene.vox"
    path.write_bytes(scene_graph_fixture())
    objects = import_vox_scene(path, material, VoxImportOptions(meshing_mode="greedy", target_extent_meters=3.0))
    export_path = Path(temporary.name) / "scene.glb"
    bpy.ops.export_scene.gltf(filepath=str(export_path), export_format="GLB", use_selection=False)
    assert {obj.name for obj in objects} == {"torso", "hair"}, [obj.name for obj in objects]
    assert {obj["vcf.vox_model_id"] for obj in objects} == {0, 1}
    assert all(obj["vcf.vox_layer_id"] == 0 for obj in objects)
    assert {tuple(obj["vcf.vox_world_translation"]) for obj in objects} == {(0, 0, 0), (2, 0, 1)}
    assert all(len(obj.data.materials) == 1 for obj in objects)
    assert objects[0].data.materials[0].diffuse_color[:3] in {(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)}
    minimum_z = min(vertex.co.z for obj in objects for vertex in obj.data.vertices)
    maximum_x = max(vertex.co.x for obj in objects for vertex in obj.data.vertices)
    assert abs(minimum_z) < 1e-6, minimum_z
    assert maximum_x > 2.0, maximum_x
    expected_bounds = (minimum_z, maximum_x)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(export_path))
    imported = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    actual_bounds = (min(vertex.co.z for obj in imported for vertex in obj.data.vertices), max(vertex.co.x for obj in imported for vertex in obj.data.vertices))
    assert {obj.name for obj in imported} == {"torso", "hair"}
    assert all(abs(before - after) < 1e-5 for before, after in zip(expected_bounds, actual_bounds)), (expected_bounds, actual_bounds)
    print("Phase 1 VOX Blender import verification passed.")


if __name__ == "__main__":
    main()
