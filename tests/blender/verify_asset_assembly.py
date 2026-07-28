"""Headless Blender acceptance test for Phase 2 registry assembly."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blender_worker.stages.asset_assembly import assemble_assets
from vcf_core.assets import load_registry
from vcf_core.jobs import load_job


def material(name: str, color: str):
    result = bpy.data.materials.new(name)
    value = color.lstrip("#")
    result.diffuse_color = tuple(int(value[index : index + 2], 16) / 255 for index in (0, 2, 4)) + (1,)
    return result


def main() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    job = load_job(ROOT / "characters" / "original" / "heavy_sword_hero.json", ROOT)
    objects = assemble_assets(job, load_registry(ROOT), ROOT, material)
    declared = set(job["source"]["asset_ids"])
    assert len(objects) == len(declared), (len(objects), len(declared))
    assert {obj.name for obj in objects} == declared
    assert all(obj["vcf.asset_id"] == obj.name for obj in objects)
    assert all(obj["vcf.semantic_tags"] and obj["vcf.asset_pivots"] for obj in objects)
    assert all(obj.data.vertices and obj.data.polygons for obj in objects)
    lowest = min((obj.matrix_world @ Vector(corner)).z for obj in objects for corner in obj.bound_box)
    assert abs(lowest) < 1e-6, lowest
    sword = bpy.data.objects["hsh_heavy_sword"]
    assert {"primary_grip", "secondary_grip", "back_carry", "waist_carry", "trail_base", "trail_tip"}.issubset(sword["vcf.asset_sockets"])
    print("Phase 2 asset-registry Blender assembly verification passed.")


if __name__ == "__main__":
    main()
