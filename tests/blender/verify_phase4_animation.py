"""Headless Phase 4 animation and QA acceptance test."""
from __future__ import annotations
import sys
from pathlib import Path
import bpy

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from blender_worker.process_character import material
from blender_worker.stages.animation import apply_animation_packs
from blender_worker.stages.asset_assembly import assemble_assets
from blender_worker.stages.part_resolution import resolve_scene_parts
from blender_worker.stages.quality import validate_character
from blender_worker.stages.rigging import align_weapon_to_primary_grip, create_fitted_rig, rigid_bind
from vcf_core.assets import load_registry
from vcf_core.export_profiles import load_export_profile
from vcf_core.jobs import load_job

def main():
    bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False)
    job = load_job(ROOT / "characters/original/heavy_sword_hero.json", ROOT)
    objects = assemble_assets(job, load_registry(ROOT), ROOT, material)
    resolutions, _ = resolve_scene_parts(objects, job)
    armature, _ = create_fitted_rig(objects, resolutions, job)
    align_weapon_to_primary_grip(objects, armature, resolutions); rigid_bind(objects, armature, resolutions)
    actions, animation_checks = apply_animation_packs(armature, job, ROOT)
    assert {action.name for action in actions} == {"idle", "walk", "run", "heavy_sword_attack_1"}
    assert all(animation_checks.values()), animation_checks
    qa_checks, diagnostics = validate_character(objects, armature, actions, load_export_profile(ROOT, job["export_profile"]))
    assert not diagnostics, diagnostics
    assert all(value for key, value in qa_checks.items() if key.startswith("qa_") and isinstance(value, bool)), qa_checks
    print("Phase 4 animation and QA verification passed.")

if __name__ == "__main__":
    try: main()
    except Exception:
        import traceback; traceback.print_exc(); raise SystemExit(1)
