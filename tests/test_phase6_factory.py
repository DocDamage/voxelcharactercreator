from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from vcf_core.animation import load_animation_pack
from vcf_core.assets import load_registry
from vcf_core.factory import (
    BODY_ARCHETYPES, FactoryValidationError, measured_parallelism, parse_optimization,
    preview_fingerprint, validate_secondary_motion,
)
from vcf_core.jobs import load_job
from vcf_core.operator import BuildQueue
from vcf_core.rigging import get_rig_template
from vcf_core.viewer import player_config, prepare_player


ROOT = Path(__file__).resolve().parents[1]


class Phase6FactoryTests(unittest.TestCase):
    def test_five_archetypes_share_the_registry_pipeline(self) -> None:
        registry = load_registry(ROOT)
        jobs = [load_job(ROOT / "characters" / "original" / f"phase6_{name}.json", ROOT) for name in sorted(BODY_ARCHETYPES)]
        self.assertEqual(5, len(jobs))
        for job in jobs:
            self.assertEqual("assembly", job["source"]["mode"])
            self.assertGreaterEqual(len(registry.resolve(job["source"]["asset_ids"], body_template=job["body_template"])), 16)
            self.assertEqual(15, len(get_rig_template(job["rig_template"]).required_roles))

    def test_all_weapon_animation_families_are_versioned(self) -> None:
        families = {"sword_shield", "spear", "staff", "katana", "gunblade", "firearm", "caster"}
        for family in families:
            pack = load_animation_pack(ROOT / "config" / "animation_packs" / f"{family}_core.v1.json")
            self.assertIn(family, pack.compatibility_tags)
            self.assertEqual(24, len(pack.actions))
            self.assertTrue({"idle", "walk", "run"}.issubset({action.name for action in pack.actions}))
            self.assertTrue(any(action.name.startswith(family + "_") for action in pack.actions))

    def test_shared_animation_packs_have_stable_unique_catalogs(self) -> None:
        expected = {
            "directional_locomotion": {"walk_backward", "strafe_left", "strafe_right", "run_backward", "run_strafe_left", "run_strafe_right", "sprint", "sprint_start", "sprint_stop", "turn_left_90", "turn_right_90", "turn_left_180", "turn_right_180", "crouch_enter", "crouch_walk", "crouch_exit"},
            "traversal_transitions": {"jump_start", "fall_sustain", "land_soft", "land_hard", "ladder_mount", "ladder_dismount", "wall_hang_enter", "wall_corner_left", "wall_corner_right", "wall_climb_exit", "swim_dive", "swim_surface", "swim_turn_left", "swim_turn_right", "swim_exit", "grapple_land"},
            "interaction_core": {"weapon_draw", "weapon_sheath", "weapon_swap", "pickup", "item_use", "interact", "push", "pull", "carry_idle", "carry_walk", "lever_use", "door_open"},
            "combat_reactions": {"hit_front", "hit_back", "hit_left", "hit_right", "block_break", "parry", "stagger", "stun_enter", "stun_idle", "stun_recover", "knockback", "launch_react", "air_hit", "ground_hit", "recover_quick", "recover_slow"},
        }
        for pack_id, expected_names in expected.items():
            pack = load_animation_pack(ROOT / "config" / "animation_packs" / f"{pack_id}.v1.json")
            self.assertEqual(expected_names, {action.name for action in pack.actions})

        required_packs = {"humanoid_traversal", *expected}
        for path in [ROOT / "characters" / "original" / "heavy_sword_hero.json", *sorted((ROOT / "characters" / "original").glob("phase6_*.json"))]:
            job = load_job(path, ROOT)
            self.assertTrue(required_packs.issubset(job["animation_packs"]))
            actions = [
                action.name
                for pack_id in job["animation_packs"]
                for action in load_animation_pack(ROOT / "config" / "animation_packs" / f"{pack_id}.v1.json").actions
            ]
            self.assertEqual(108, len(actions))
            self.assertEqual(len(actions), len(set(actions)))

    def test_universal_traversal_pack_has_exactly_24_mechanics_clips(self) -> None:
        pack = load_animation_pack(ROOT / "config" / "animation_packs" / "humanoid_traversal.v1.json")
        names = {action.name for action in pack.actions}
        self.assertEqual(24, len(names))
        self.assertEqual({"slide","dodge_roll","double_jump","airborne_idle","air_attack_light","air_attack_heavy","air_attack_spin","air_attack_plunge","dash","ladder_idle","ladder_climb","wall_hang","wall_jump","wall_climb","swim_idle","swim_forward","rope_swing","rope_release","grapple_fire","grapple_pull","grapple_swing","grapple_release","ledge_grab","ledge_climb"}, names)
        for name in BODY_ARCHETYPES:
            job = load_job(ROOT / "characters" / "original" / f"phase6_{name}.json", ROOT)
            self.assertIn("humanoid_traversal", job["animation_packs"])

    def test_secondary_motion_requires_rigid_fallback(self) -> None:
        valid = [{"chain_id":"cape","kind":"cape","segments":["cape.01"],"parent_bone":"spine","stiffness":.5,"damping":.4,"max_angle_degrees":30,"fallback":"rigid"}]
        self.assertEqual([], validate_secondary_motion(valid))
        invalid = [{**valid[0], "fallback":"dynamic"}]
        self.assertIn("fallback must be rigid", "\n".join(validate_secondary_motion(invalid)))

    def test_optimization_policy_has_lods_atlas_and_incremental_previews(self) -> None:
        policy = parse_optimization({"optimization":{"lod_ratios":[1,.5,.25],"material_batching":"palette_atlas","compression":"engine","incremental_previews":True}})
        self.assertEqual((1.0, .5, .25), policy.lod_ratios)
        self.assertTrue(policy.incremental_previews)
        with self.assertRaises(FactoryValidationError):
            parse_optimization({"optimization":{"lod_ratios":[.5,1]}})

    def test_preview_fingerprint_ignores_animation_only_changes(self) -> None:
        first = {"source":{"mode":"proxy"},"render_resolution":128,"animation_profile":"sword","animation_packs":["a"]}
        second = {**first, "animation_profile":"staff", "animation_packs":["b"]}
        self.assertEqual(preview_fingerprint(first, []), preview_fingerprint(second, []))

    def test_preview_fingerprint_invalidates_resolved_geometry_and_rig_settings(self) -> None:
        first = {
            "source": {"mode": "assembly", "asset_ids": ["body"]},
            "body_template": "male_heavy",
            "rig_template": "humanoid_heavy",
            "target_height_meters": 2.0,
            "settings_overrides": {
                "part_transforms": {"head": {"location": [0, 0, 0], "rotation_degrees": [0, 0, 0], "scale": [1, 1, 1]}},
                "socket_overrides": {"effect_socket": {"bone": "head", "offset": [0, 0, 0.1]}},
                "limb_length_overrides": {"upper_arm.L": 1.0},
                "deformation": {"mode": "deform", "max_influences": 4, "normalize_weights": True, "secondary_solver": "none", "bake": True, "fallback": "rigid"},
                "secondary_motion": [{"chain_id": "cape", "kind": "cape", "segments": ["cape.01"], "parent_bone": "spine", "stiffness": 0.5, "damping": 0.4, "max_angle_degrees": 30, "fallback": "rigid"}],
            },
        }
        changes = {
            "target height": lambda job: job.update(target_height_meters=2.1),
            "editor transform": lambda job: job["settings_overrides"]["part_transforms"]["head"]["location"].__setitem__(2, 0.25),
            "socket offset": lambda job: job["settings_overrides"]["socket_overrides"]["effect_socket"]["offset"].__setitem__(2, 0.2),
            "limb length": lambda job: job["settings_overrides"]["limb_length_overrides"].update({"upper_arm.L": 1.2}),
            "deformation": lambda job: job["settings_overrides"]["deformation"].update({"mode": "rigid"}),
            "secondary motion": lambda job: job["settings_overrides"]["secondary_motion"][0].update({"stiffness": 0.7}),
        }
        original = preview_fingerprint(first, [])
        for name, change in changes.items():
            with self.subTest(name=name):
                second = deepcopy(first)
                change(second)
                self.assertNotEqual(original, preview_fingerprint(second, []))

    def test_preview_fingerprint_ignores_post_render_optimization_changes(self) -> None:
        first = {"source": {"mode": "assembly", "asset_ids": ["body"]}, "settings_overrides": {"optimization": {"lod_ratios": [1, .5]}}}
        second = deepcopy(first)
        second["settings_overrides"]["optimization"]["lod_ratios"] = [1, .25]
        self.assertEqual(preview_fingerprint(first, []), preview_fingerprint(second, []))

    def test_parallelism_is_conservative_without_measurements_and_bounded_with_them(self) -> None:
        self.assertEqual(1, measured_parallelism([], cpu_count=16, memory_gb=32))
        self.assertEqual(4, measured_parallelism([{"peak_memory_gb":2}], cpu_count=16, memory_gb=32))
        self.assertEqual(1, measured_parallelism([{"peak_memory_gb":6}], cpu_count=8, memory_gb=8))

    def test_queue_claim_is_atomic_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            queue = BuildQueue(Path(folder) / "queue.json")
            for index in range(5): queue.add(Path(f"job-{index}.json"))
            self.assertEqual(2, len(queue.claim_pending(2)))
            self.assertEqual(3, len([item for item in queue.items if item.status == "pending"]))
            with self.assertRaises(ValueError): queue.claim_pending(5)

    def test_animation_player_receives_actions_and_events(self) -> None:
        report = {"job":"hero", "animation":{"actions":[{"name":"attack","loop":False,"frame_start":1,"frame_end":20,"events":[{"name":"hit_start","frame":10}]}]}}
        value = player_config(report)
        self.assertEqual("attack", value["actions"][0]["name"])
        self.assertEqual("hit_start", value["actions"][0]["events"][0]["name"])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / "hero.glb"; source.write_bytes(b"glTF")
            project = prepare_player(root, source, report)
            self.assertTrue((project / "imported" / "character.glb").is_file())
            self.assertEqual("hero", json.loads((project / "imported" / "player_config.json").read_text())["character"])


if __name__ == "__main__": unittest.main()
