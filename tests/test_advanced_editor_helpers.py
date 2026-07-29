from __future__ import annotations

import json
import math
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from app.advanced_editor import positive_finite_number, resolve_editor_context


class AdvancedEditorHelperTests(unittest.TestCase):
    def test_positive_finite_number_rejects_invalid_steps(self) -> None:
        self.assertEqual(0.25, positive_finite_number(0.25, "Step"))
        for value in (0, -1, math.inf, -math.inf, math.nan, True, "0.5"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    positive_finite_number(value, "Step")

    def test_editor_resolves_inherited_parts_without_expanding_raw_job(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            parent_path = root / "characters" / "original" / "parent.json"
            child_path = root / "characters" / "game" / "child.json"
            parent_path.parent.mkdir(parents=True)
            child_path.parent.mkdir(parents=True)

            parent = {
                "schema_version": 2,
                "id": "parent",
                "name": "Parent",
                "source": {"mode": "assembly", "asset_ids": ["head", "body"]},
                "settings_overrides": {
                    "part_transforms": {
                        "cape": {
                            "location": [0, 0, 0],
                            "rotation_degrees": [0, 0, 0],
                            "scale": [1, 1, 1],
                        }
                    }
                },
            }
            raw_child = {
                "schema_version": 2,
                "id": "child",
                "name": "Child",
                "variant_of": "parent",
            }
            parent_path.write_text(json.dumps(parent), encoding="utf-8")
            child_path.write_text(json.dumps(raw_child), encoding="utf-8")
            original = deepcopy(raw_child)

            resolved, parts = resolve_editor_context(raw_child, root)

            self.assertEqual(["head", "body", "cape"], parts)
            self.assertEqual(parent["source"], resolved["source"])
            self.assertEqual(original, raw_child)
            self.assertNotIn("source", raw_child)


if __name__ == "__main__":
    unittest.main()
