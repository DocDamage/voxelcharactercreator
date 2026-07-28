from __future__ import annotations

import unittest

from app.services.llm_client import apply_patch


class ApplyPatchTests(unittest.TestCase):
    def test_applies_allowed_keys_without_mutating_original(self) -> None:
        original = {"id": "ff7_cloud", "notes": "before", "source_model": None}
        updated = apply_patch(original, {"notes": "after", "id": "unsafe_change", "source_model": "unsafe.vox"})
        self.assertEqual("before", original["notes"])
        self.assertEqual("after", updated["notes"])
        self.assertEqual("ff7_cloud", updated["id"])
        self.assertIsNone(updated["source_model"])

    def test_requires_object_patch(self) -> None:
        with self.assertRaises(TypeError):
            apply_patch({}, ["not", "an", "object"])


if __name__ == "__main__":
    unittest.main()
