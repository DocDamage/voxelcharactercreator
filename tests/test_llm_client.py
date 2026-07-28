from __future__ import annotations

import unittest

from app.services.llm_client import apply_patch, proposal_diff


class ApplyPatchTests(unittest.TestCase):
    def test_applies_allowed_keys_without_mutating_original(self) -> None:
        original = {"id": "ff7_cloud", "notes": "before", "source_model": None}
        updated = apply_patch(original, {"changes": {"notes": "after"}, "diagnostics": []})
        self.assertEqual("before", original["notes"])
        self.assertEqual("after", updated["notes"])
        self.assertEqual("ff7_cloud", updated["id"])
        self.assertIsNone(updated["source_model"])

    def test_rejects_unreviewable_or_path_based_proposals(self) -> None:
        with self.assertRaises(ValueError):
            apply_patch({}, {"changes": {"id": "unsafe_change"}})
        with self.assertRaises(ValueError):
            apply_patch({}, {"changes": {"source": {"mode": "model", "path": "private.vox"}}})

    def test_asset_palette_mapping_proposal_has_previewable_diff(self) -> None:
        original = {"source": {"mode": "assembly", "asset_ids": ["old"]}, "accent_colors": ["#000000"]}
        proposal = {"changes": {"source": {"mode": "assembly", "asset_ids": ["new"]}, "accent_colors": ["#FFFFFF"], "part_overrides": {"head": "new"}}}
        updated = apply_patch(original, proposal)
        self.assertEqual(["new"], updated["source"]["asset_ids"])
        self.assertEqual(3, len(proposal_diff(original, proposal)))

    def test_requires_object_patch(self) -> None:
        with self.assertRaises(TypeError):
            apply_patch({}, ["not", "an", "object"])


if __name__ == "__main__":
    unittest.main()
