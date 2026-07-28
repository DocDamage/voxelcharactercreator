from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.services.job_validator import validate_job
from vcf_core.jobs import load_job, migrate_job


ROOT = Path(__file__).resolve().parents[1]


class JobValidatorTests(unittest.TestCase):
    def valid_job(self) -> dict:
        return {
            "id": "ff7_cloud",
            "name": "Cloud Strife",
            "game": "ff7",
            "role": "hero",
            "body_template": "male_heroic",
            "rig_template": "humanoid_standard",
            "animation_profile": "heavy_sword",
            "height_voxels": 44,
            "accent_colors": ["#E7C544"],
            "export_formats": ["glb", "fbx"],
        }

    def test_all_bundled_jobs_are_valid(self) -> None:
        failures = {}
        for path in (ROOT / "characters").glob("*/*.json"):
            errors = validate_job(json.loads(path.read_text(encoding="utf-8")), project_root=ROOT)
            if errors:
                failures[path.name] = errors
        self.assertEqual({}, failures)

    def test_reports_multiple_errors_at_once(self) -> None:
        job = self.valid_job()
        job.update({"id": "Bad ID", "role": "wizard", "height_voxels": True, "accent_colors": ["red"]})
        errors = validate_job(job)
        self.assertGreaterEqual(len(errors), 4)
        self.assertTrue(any("id must" in error for error in errors))
        self.assertTrue(any("role must" in error for error in errors))
        self.assertTrue(any("height_voxels" in error for error in errors))
        self.assertTrue(any("accent_colors" in error for error in errors))

    def test_resolves_source_model_against_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "assets" / "incoming" / "model.vox"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"VOX ")
            job = self.valid_job()
            job["source_model"] = "assets/incoming/model.vox"
            self.assertEqual([], validate_job(job, project_root=root))

    def test_rejects_path_traversal_and_unknown_fields(self) -> None:
        job = self.valid_job()
        job["source_model"] = "../outside.vox"
        job["unexpected"] = True
        errors = validate_job(job, project_root=ROOT)
        self.assertTrue(any("approved import root" in error for error in errors))
        self.assertTrue(any("unknown job fields" in error for error in errors))

    def test_migrates_v1_job_losslessly_to_v2(self) -> None:
        original = self.valid_job()
        original["source_model"] = None
        migrated = migrate_job(original)
        self.assertEqual(2, migrated["schema_version"])
        self.assertEqual({"mode": "proxy"}, migrated["source"])
        self.assertNotIn("source_model", migrated)

    def test_rejects_unknown_future_schema(self) -> None:
        job = self.valid_job()
        job["schema_version"] = 99
        self.assertTrue(any("unsupported future" in error for error in validate_job(job)))

    def test_v2_rejects_unknown_vox_meshing_mode(self) -> None:
        job = migrate_job(self.valid_job())
        job["settings_overrides"] = {"vox_meshing_mode": "triangles"}
        self.assertTrue(any("vox_meshing_mode" in error for error in validate_job(job)))

    def test_rejects_unsupported_source_extension(self) -> None:
        job = self.valid_job()
        job["source_model"] = "character.stl"
        errors = validate_job(job)
        self.assertTrue(any("source_model must use" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
