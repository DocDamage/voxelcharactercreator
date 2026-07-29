import json
import tempfile
import unittest
from pathlib import Path

from tools.validate import validate_schema_documents, validate_schema_instances


ROOT = Path(__file__).resolve().parents[1]


class PublishedSchemaTests(unittest.TestCase):
    def test_every_published_schema_parses_and_passes_meta_checks(self) -> None:
        self.assertEqual([], validate_schema_documents(ROOT))

    def test_every_published_schema_accepts_its_repository_instances(self) -> None:
        self.assertEqual([], validate_schema_instances(ROOT))

    def test_malformed_published_schema_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            schema_dir = root / "schemas"
            schema_dir.mkdir()
            (schema_dir / "broken.schema.json").write_text("{", encoding="utf-8")
            errors = validate_schema_documents(root)
        self.assertEqual(1, len(errors))
        self.assertIn("invalid published schema JSON", errors[0])

    def test_invalid_json_schema_keyword_value_fails_meta_validation(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            schema_dir = root / "schemas"
            schema_dir.mkdir()
            (schema_dir / "invalid-type.schema.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "title": "Invalid type fixture",
                        "type": "definitely-not-a-json-schema-type",
                        "properties": {},
                    }
                ),
                encoding="utf-8",
            )
            errors = validate_schema_documents(root)
        self.assertEqual(1, len(errors))
        self.assertIn("invalid Draft 2020-12 schema", errors[0])

    def test_external_schema_reference_fails_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "schemas").mkdir()
            (root / "documents").mkdir()
            (root / "schemas" / "external.schema.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "title": "External reference fixture",
                        "type": "object",
                        "properties": {
                            "value": {"$ref": "shared.schema.json"},
                            "dynamic": {"$dynamicRef": "https://example.invalid/schema"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / "documents" / "fixture.json").write_text(
                '{"value": 1}', encoding="utf-8"
            )
            document_errors = validate_schema_documents(root)
            instance_errors = validate_schema_instances(
                root, {"external.schema.json": ("documents/*.json",)}
            )
        self.assertTrue(any("schema reference" in error for error in document_errors))
        self.assertTrue(any("unresolved or nonlocal" in error for error in instance_errors))

    def test_local_anchor_reference_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "schemas").mkdir()
            (root / "documents").mkdir()
            (root / "schemas" / "anchor.schema.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "title": "Local anchor fixture",
                        "type": "object",
                        "$defs": {
                            "positive": {
                                "$anchor": "positive",
                                "type": "integer",
                                "minimum": 1,
                            }
                        },
                        "properties": {"value": {"$ref": "#positive"}},
                        "required": ["value"],
                    }
                ),
                encoding="utf-8",
            )
            (root / "documents" / "fixture.json").write_text(
                '{"value": 2}', encoding="utf-8"
            )
            self.assertEqual([], validate_schema_documents(root))
            self.assertEqual(
                [],
                validate_schema_instances(
                    root, {"anchor.schema.json": ("documents/*.json",)}
                ),
            )

    def test_array_pointer_and_literal_reference_data_are_supported(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "schemas").mkdir()
            (root / "documents").mkdir()
            (root / "schemas" / "pointer.schema.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "title": "Array pointer fixture",
                        "type": "object",
                        "allOf": [
                            {"$defs": {"value": {"type": "integer", "minimum": 1}}}
                        ],
                        "properties": {
                            "value": {"$ref": "#/allOf/0/$defs/value"},
                            "literal": {"const": {"$ref": "literal instance data"}},
                        },
                        "required": ["value", "literal"],
                    }
                ),
                encoding="utf-8",
            )
            (root / "documents" / "fixture.json").write_text(
                '{"value": 2, "literal": {"$ref": "literal instance data"}}',
                encoding="utf-8",
            )
            self.assertEqual([], validate_schema_documents(root))
            self.assertEqual(
                [],
                validate_schema_instances(
                    root, {"pointer.schema.json": ("documents/*.json",)}
                ),
            )

    def test_schema_instance_drift_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "schemas").mkdir()
            (root / "documents").mkdir()
            (root / "schemas" / "fixture.schema.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "title": "Fixture",
                        "type": "object",
                        "properties": {"version": {"const": 1}},
                        "required": ["version"],
                    }
                ),
                encoding="utf-8",
            )
            (root / "documents" / "fixture.json").write_text(
                '{"version": 2}\n', encoding="utf-8"
            )
            errors = validate_schema_instances(
                root, {"fixture.schema.json": ("documents/*.json",)}
            )
        self.assertEqual(1, len(errors))
        self.assertIn("1 was expected", errors[0])

    def test_published_schema_requires_an_instance_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "schemas").mkdir()
            (root / "schemas" / "unmapped.schema.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "title": "Unmapped fixture",
                        "type": "object",
                        "properties": {},
                    }
                ),
                encoding="utf-8",
            )
            errors = validate_schema_instances(root, {})
        self.assertEqual(1, len(errors))
        self.assertIn("has no governed instance mapping", errors[0])

    def test_legacy_job_is_migrated_before_v2_schema_validation(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "schemas").mkdir()
            (root / "characters").mkdir()
            (root / "schemas" / "job.v2.schema.json").write_bytes(
                (ROOT / "schemas" / "job.v2.schema.json").read_bytes()
            )
            legacy = {
                "id": "ff7_cloud",
                "name": "Cloud",
                "game": "ff7",
                "role": "hero",
                "body_template": "humanoid",
                "rig_template": "humanoid",
                "animation_profile": "core",
                "source_model": None,
            }
            (root / "characters" / "legacy.json").write_text(
                json.dumps(legacy), encoding="utf-8"
            )
            errors = validate_schema_instances(
                root, {"job.v2.schema.json": ("characters/*.json",)}
            )
        self.assertEqual([], errors)

    def test_asset_manifest_schema_matches_tracked_catalog_wrappers(self) -> None:
        schema = json.loads((ROOT / "schemas" / "asset_manifest.v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual({"catalog_schema_version", "assets"}, set(schema["required"]))
        self.assertEqual(1, schema["properties"]["catalog_schema_version"]["const"])
        self.assertEqual("#/$defs/asset", schema["properties"]["assets"]["items"]["$ref"])
        asset_schema = schema["$defs"]["asset"]
        required_asset_fields = set(asset_schema["required"])
        allowed_asset_fields = set(asset_schema["properties"])

        paths = sorted((ROOT / "assets" / "manifests").glob("*.json"))
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(path=path.name):
                catalog = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual({"catalog_schema_version", "assets"}, set(catalog))
                self.assertEqual(1, catalog["catalog_schema_version"])
                self.assertIsInstance(catalog["assets"], list)
                self.assertTrue(catalog["assets"])
                for asset in catalog["assets"]:
                    self.assertTrue(required_asset_fields.issubset(asset))
                    self.assertFalse(set(asset) - allowed_asset_fields)

    def test_advanced_rig_schema_tracks_runtime_document_shape(self) -> None:
        schema = json.loads((ROOT / "schemas" / "advanced_rig.v1.schema.json").read_text(encoding="utf-8"))
        required = set(schema["required"])
        self.assertEqual(required, set(schema["properties"]))
        checks = schema["properties"]["engine_checks"]
        self.assertEqual(5, checks["minItems"])
        self.assertEqual(5, checks["maxItems"])

        paths = sorted((ROOT / "config" / "advanced_rigs").glob("*.v1.json"))
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(path=path.name):
                document = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(required, set(document))
                self.assertEqual(set(checks["items"]["enum"]), set(document["engine_checks"]))


if __name__ == "__main__":
    unittest.main()
