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
        names = {action.name for action in pack.actions}
        self.assertEqual(24, len(names))
        self.assertTrue({"idle", "walk", "run", "jump", "dodge", "guard", "guard_hit", "damage_light", "damage_heavy", "knockdown", "death", "victory", "crouch_idle", "backstep", "fall", "get_up", "heavy_sword_attack_1", "heavy_sword_attack_2", "heavy_sword_attack_3", "heavy_sword_charge", "heavy_sword_overhead_smash", "heavy_sword_wide_sweep", "heavy_sword_launcher", "heavy_sword_limit_break"}.issubset(names))
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
