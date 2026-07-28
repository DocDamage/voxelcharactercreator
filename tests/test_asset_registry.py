from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from vcf_core.assets import AssetValidationError, load_registry
from vcf_core.jobs import load_job, validate_job


ROOT = Path(__file__).resolve().parents[1]


class AssetRegistryTests(unittest.TestCase):
    def test_heavy_sword_hero_registry_is_complete_and_resolvable(self) -> None:
        registry = load_registry(ROOT)
        self.assertEqual(24, len(registry.manifests))
        sword = registry.get("hsh_heavy_sword", "1.0.0")
        self.assertEqual("weapon", sword.kind)
        self.assertIn("primary_grip", sword.sockets)
        self.assertEqual(["hsh_head"], [item.asset_id for item in registry.find_by_tags({"head"}, body_template="male_heroic")])
        self.assertEqual(["hsh_boot_l"], [item.asset_id for item in registry.find_by_tags({"boot_l"}, body_template="male_heroic")])
        assembly = registry.resolve(["hsh_head", "hsh_torso", "hsh_heavy_sword"], body_template="male_heroic")
        self.assertEqual(["hsh_head", "hsh_torso", "hsh_heavy_sword"], [item.asset_id for item in assembly])

    def test_pilot_job_resolves_without_a_source_model(self) -> None:
        path = ROOT / "characters" / "original" / "heavy_sword_hero.json"
        job = load_job(path, ROOT)
        self.assertEqual("assembly", job["source"]["mode"])
        self.assertNotIn("source_model", job)
        self.assertEqual([], validate_job(job, ROOT))

    def test_unknown_or_incompatible_catalog_assets_are_rejected(self) -> None:
        path = ROOT / "characters" / "original" / "heavy_sword_hero.json"
        job = json.loads(path.read_text(encoding="utf-8"))
        job["source"]["asset_ids"] = ["does_not_exist"]
        self.assertTrue(any("unknown catalog asset" in error for error in validate_job(job, ROOT)))
        job["source"]["asset_ids"] = ["hsh_head"]
        job["body_template"] = "mage_robe"
        self.assertTrue(any("incompatible" in error for error in validate_job(job, ROOT)))

    def test_duplicate_asset_manifest_id_and_version_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_dir = root / "assets" / "manifests"
            original = root / "assets" / "original"
            manifest_dir.mkdir(parents=True)
            shutil.copytree(ROOT / "assets" / "original", original)
            (manifest_dir / "one.json").write_text(json.dumps({"assets": []}), encoding="utf-8")
            # Empty catalog is valid, while this test verifies registry-level duplicate handling
            # using the actual registry document copied twice under a different filename.
            source = ROOT / "assets" / "manifests" / "heavy_sword_hero.assets.v1.json"
            (manifest_dir / "first.json").write_bytes(source.read_bytes())
            (manifest_dir / "second.json").write_bytes(source.read_bytes())
            with self.assertRaises(AssetValidationError) as context:
                load_registry(root)
            self.assertTrue(any("duplicate asset ID/version" in error for error in context.exception.errors))


if __name__ == "__main__":
    unittest.main()
