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
    assert len(actions) == 108
    assert {"idle", "walk", "run", "jump", "dodge", "guard", "damage_light", "death", "victory", "heavy_sword_attack_1", "heavy_sword_attack_2", "heavy_sword_attack_3", "heavy_sword_charge"}.issubset({action.name for action in actions})
    assert {"slide", "dodge_roll", "double_jump", "air_attack_light", "air_attack_heavy", "air_attack_spin", "air_attack_plunge", "dash", "ladder_climb", "wall_hang", "wall_jump", "wall_climb", "swim_forward", "rope_swing", "grapple_fire", "grapple_pull", "ledge_climb"}.issubset({action.name for action in actions})
    assert {"walk_backward", "sprint", "turn_left_180", "crouch_walk", "jump_start", "land_hard", "ladder_mount", "swim_dive", "weapon_draw", "pickup", "carry_walk", "door_open", "hit_front", "parry", "stun_idle", "air_hit", "recover_quick"}.issubset({action.name for action in actions})
    assert all(animation_checks.values()), animation_checks
    qa_checks, diagnostics = validate_character(objects, armature, actions, load_export_profile(ROOT, job["export_profile"]))
    assert not diagnostics, diagnostics
    assert all(value for key, value in qa_checks.items() if key.startswith("qa_") and isinstance(value, bool)), qa_checks
    print("Phase 4 animation and QA verification passed.")

if __name__ == "__main__":
    try: main()
    except Exception:
        import traceback; traceback.print_exc(); raise SystemExit(1)
