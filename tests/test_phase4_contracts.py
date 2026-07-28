from __future__ import annotations

import json
import unittest
from pathlib import Path

from vcf_core.animation import AnimationPackError, load_animation_pack, validate_animation_pack
from vcf_core.export_profiles import load_export_profile


ROOT = Path(__file__).resolve().parents[1]


class Phase4ContractTests(unittest.TestCase):
    def test_production_animation_pack_has_required_actions_and_events(self):
        pack = load_animation_pack(ROOT / "config/animation_packs/heavy_sword_core.v1.json")
        self.assertEqual({"idle", "walk", "run", "heavy_sword_attack_1"}, {action.name for action in pack.actions})
        attack = next(action for action in pack.actions if action.name == "heavy_sword_attack_1")
        self.assertEqual(["trail_start", "hit_start", "hit_end", "trail_end"], [event["name"] for event in attack.events])
        self.assertTrue(all(action.poses for action in pack.actions))

    def test_loop_without_seam_frames_is_rejected(self):
        value = json.loads((ROOT / "config/animation_packs/heavy_sword_core.v1.json").read_text())
        value["actions"][0]["poses"][-1]["frame"] = 59
        self.assertTrue(any("seam" in error for error in validate_animation_pack(value)))

    def test_all_engine_profiles_are_versioned_and_bounded(self):
        for profile_id in ("godot_character", "unity_character", "unreal_character"):
            profile = load_export_profile(ROOT, profile_id)
            self.assertGreater(profile.scale, 0)
            self.assertLessEqual(profile.budgets["max_objects"], 32)


if __name__ == "__main__": unittest.main()
