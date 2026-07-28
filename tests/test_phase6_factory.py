from __future__ import annotations

import json
import tempfile
import unittest
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

    def test_all_seven_weapon_animation_families_are_versioned(self) -> None:
        families = {"sword_shield", "spear", "staff", "katana", "gunblade", "firearm", "caster"}
        for family in families:
            pack = load_animation_pack(ROOT / "config" / "animation_packs" / f"{family}_core.v1.json")
            self.assertIn(family, pack.compatibility_tags)
            self.assertTrue({"idle", "walk", "run"}.issubset({action.name for action in pack.actions}))
            self.assertIn(f"{family}_attack_1", {action.name for action in pack.actions})

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
        first = {"source":{"mode":"proxy"},"render_resolution":128,"animation_packs":["a"]}
        second = {**first, "animation_packs":["b"]}
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


if __name__ == "__main__": unittest.main()
