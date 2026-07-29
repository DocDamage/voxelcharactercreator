from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vcf_core.jobs import JobValidationError, load_job, resolve_job
from vcf_core.production import (
    PILOT_CHECKS, capacity_estimate, load_cast_database, load_pilot_matrix,
    package_source_distribution, plan_reference_analysis, similarity_false_positive_rate,
    validate_packaging_strategy, visual_similarity,
)


ROOT = Path(__file__).resolve().parents[1]


class Phase7ProductionTests(unittest.TestCase):
    def test_pilot_ten_are_compact_resolved_production_variants(self) -> None:
        matrix = load_pilot_matrix(ROOT / "config" / "production" / "pilot_ten.v1.json")
        self.assertEqual(10, len(matrix["characters"]))
        for entry in matrix["characters"]:
            paths = list((ROOT / "characters").glob(f"*/{entry['job_id'].split('_', 1)[1]}.json"))
            self.assertEqual(1, len(paths), entry["job_id"])
            raw = json.loads(paths[0].read_text(encoding="utf-8"))
            self.assertNotIn("source", raw)
            job = load_job(paths[0], ROOT)
            self.assertEqual("assembly", job["source"]["mode"])
            self.assertEqual(entry["base_job_id"], job["variant_of"])
            self.assertEqual(set(PILOT_CHECKS), set(entry["checks"]))
            self.assertTrue(all(value == "passed" for value in entry["checks"].values()))

    def test_variant_inheritance_is_deterministic_and_cycle_safe(self) -> None:
        raw = json.loads((ROOT / "characters" / "ff7" / "cloud.json").read_text())
        first = resolve_job(raw, ROOT)
        second = resolve_job(raw, ROOT)
        self.assertEqual(first, second)
        self.assertEqual("original_heavy_sword_hero", first["variant_of"])
        self.assertEqual("assembly", first["source"]["mode"])
        broken = {"schema_version": 2, "id": "broken", "name": "Broken", "variant_of": "missing"}
        with self.assertRaises(JobValidationError): resolve_job(broken, ROOT)

    def test_reference_planner_emits_reviewable_data_only(self) -> None:
        plan = plan_reference_analysis({"accent_colors":["#112233"], "views":[
            {"view":"front", "parts":[{"semantic":"cape", "note":"long"}]},
            {"view":"back", "parts":[{"semantic":"cape", "note":"split hem"},{"semantic":"hair"}]},
        ]}, "phase6_mage_robe")
        self.assertEqual("review_required", plan["status"])
        self.assertEqual(["blender_code", "source_paths"], plan["prohibited_output"])
        self.assertEqual(["cape", "hair"], [item["semantic"] for item in plan["part_requests"]])

    def test_visual_similarity_is_advisory_and_tracks_false_positives(self) -> None:
        features = {"silhouette":[0.1,0.9], "palette":[0.2,0.8], "landmarks":[0.4,0.6]}
        result = visual_similarity(features, features)
        self.assertEqual(1.0, result["score"])
        self.assertTrue(result["advisory"])
        self.assertFalse(result["blocking"])
        rates = similarity_false_positive_rate([{"score":.9,"review":"reject"},{"score":.95,"review":"accept"},{"score":.2,"review":"reject"}])
        self.assertEqual(.5, rates["false_positive_rate"])

    def test_capacity_and_ff4_through_ff10_database_follow_measurements(self) -> None:
        matrix = load_pilot_matrix(ROOT / "config" / "production" / "pilot_ten.v1.json")
        estimate = capacity_estimate(matrix)
        self.assertEqual(10, estimate.sample_size)
        self.assertGreater(estimate.characters_per_person_month, 0)
        database = load_cast_database(ROOT / "config" / "production" / "cast_ff4_ff10.v1.json")
        self.assertEqual({f"ff{i}" for i in range(4, 11)}, {item["game"] for item in database["characters"]})

    def test_windows_source_package_is_deterministic_and_release_signing_is_required(self) -> None:
        strategy = json.loads((ROOT / "config" / "production" / "windows_packaging.v1.json").read_text())
        validate_packaging_strategy(strategy)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            first = package_source_distribution(ROOT, target / "a.zip", [ROOT / "VERSION.txt", ROOT / "README.md"])
            second = package_source_distribution(ROOT, target / "b.zip", [ROOT / "README.md", ROOT / "VERSION.txt"])
            self.assertEqual(first["sha256"], second["sha256"])
            self.assertTrue(strategy["rollback"]["preserve_previous"])
            self.assertTrue(strategy["signing"]["release_requires_authenticode"])


if __name__ == "__main__": unittest.main()
