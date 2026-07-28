from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from vcf_core.rigging import (
    MARKER_ROLE_BY_RGB,
    SEMANTIC_ROLES,
    PartCandidate,
    PartResolutionError,
    get_rig_template,
    load_rig_template,
    persist_part_overrides,
    resolve_parts,
    standard_male_template,
)


ROOT = Path(__file__).resolve().parents[1]


def pilot_candidates() -> list[PartCandidate]:
    return [
        PartCandidate(name=role, asset_id=role, semantic_tags=(role,))
        for role in standard_male_template().required_roles
    ]


class RiggingContractTests(unittest.TestCase):
    def test_v1_marker_palette_covers_each_semantic_role_once(self) -> None:
        self.assertEqual(SEMANTIC_ROLES, frozenset(MARKER_ROLE_BY_RGB.values()))
        self.assertEqual(len(SEMANTIC_ROLES), len(MARKER_ROLE_BY_RGB))

    def test_versioned_standard_template_loads_and_is_valid(self) -> None:
        template = load_rig_template(ROOT / "config" / "rig_templates" / "humanoid_standard.v1.json")
        self.assertEqual("humanoid_standard", template.template_id)
        self.assertEqual([], template.validate())
        self.assertEqual(template.required_roles, get_rig_template("humanoid_standard").required_roles)
        self.assertIn("weapon_socket.R", template.sockets)
        self.assertEqual("hand.R", template.sockets["weapon_socket.R"][0])

    def test_template_rejects_non_numeric_socket_offsets(self) -> None:
        payload = json.loads((ROOT / "config" / "rig_templates" / "humanoid_standard.v1.json").read_text(encoding="utf-8"))
        payload["sockets"]["weapon_socket.R"]["offset"] = [0, "bad", 0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.v1.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(PartResolutionError) as context:
                load_rig_template(path)
        self.assertIn("sockets must declare", str(context.exception))

    def test_manifest_mapping_has_complete_explanation_trace(self) -> None:
        candidates = pilot_candidates() + [PartCandidate("sword_mesh", semantic_tags=("heavy_sword",))]
        mappings, trace = resolve_parts(candidates)
        self.assertEqual(len(candidates), len(mappings))
        self.assertEqual("weapon_socket.R", mappings["weapon"].parent_bone)
        self.assertTrue(all(item.source == "asset_manifest" for item in trace))
        self.assertTrue(all("mesh_components=" in item.detail for item in trace))

    def test_color_marker_precedes_spatial_fallback(self) -> None:
        candidates = pilot_candidates()[1:]
        candidates.append(PartCandidate("mystery_top", marker_colors=("HEAD",), bounds=((-1, -1, 3), (1, 1, 4))))
        mappings, _trace = resolve_parts(candidates)
        self.assertEqual("color_marker", mappings["head"].source)

    def test_job_override_wins_over_manifest_tag(self) -> None:
        candidates = pilot_candidates()
        candidates[0] = PartCandidate("custom_head", semantic_tags=("torso",))
        candidates[1] = PartCandidate("custom_torso", semantic_tags=("head",))
        mappings, _ = resolve_parts(candidates, part_overrides={"head": "custom_head", "torso": "custom_torso"})
        self.assertEqual("custom_head", mappings["head"].candidate)
        self.assertEqual("job_override", mappings["head"].source)

    def test_conflicts_and_missing_required_roles_fail_closed(self) -> None:
        candidates = pilot_candidates()
        candidates.append(PartCandidate("other_head", semantic_tags=("head",)))
        with self.assertRaises(PartResolutionError) as duplicate:
            resolve_parts(candidates)
        self.assertIn("PART_CONFLICT", str(duplicate.exception))
        with self.assertRaises(PartResolutionError) as missing:
            resolve_parts(pilot_candidates()[1:])
        self.assertIn("PART_MISSING", str(missing.exception))

    def test_low_confidence_spatial_guess_requires_mapping(self) -> None:
        candidates = [
            PartCandidate("unknown_a", bounds=((-1, -1, 0), (1, 1, 1))),
            PartCandidate("unknown_b", bounds=((-1, -1, 3), (1, 1, 4))),
        ]
        with self.assertRaises(PartResolutionError) as context:
            resolve_parts(candidates)
        self.assertIn("PART_NEEDS_MAPPING", str(context.exception))

    def test_persisted_overrides_replay_deterministically(self) -> None:
        candidates = pilot_candidates()
        mappings, _ = resolve_parts(candidates)
        job = json.loads((ROOT / "characters" / "original" / "heavy_sword_hero.json").read_text(encoding="utf-8"))
        persisted = persist_part_overrides(job, mappings)
        self.assertEqual("head", persisted["part_overrides"]["head"])
        self.assertNotIn("part_overrides", job)

    def test_unknown_manual_override_role_is_rejected_by_job_contract(self) -> None:
        from vcf_core.jobs import validate_job
        job = json.loads((ROOT / "characters" / "original" / "heavy_sword_hero.json").read_text(encoding="utf-8"))
        job["part_overrides"] = {"mystery_limb": "hsh_head"}
        self.assertTrue(any("unknown semantic roles" in error for error in validate_job(job, ROOT)))

    def test_limb_length_overrides_are_bounded(self) -> None:
        from vcf_core.jobs import validate_job
        job = json.loads((ROOT / "characters" / "original" / "heavy_sword_hero.json").read_text(encoding="utf-8"))
        job["settings_overrides"] = {"limb_length_overrides": {"upper_arm.L": 1.1}}
        self.assertEqual([], validate_job(job, ROOT))
        job["settings_overrides"]["limb_length_overrides"]["upper_arm.L"] = 1.6
        self.assertTrue(any("limb_length_overrides" in error for error in validate_job(job, ROOT)))
        job["settings_overrides"]["limb_length_overrides"] = {"made_up_bone": 1.1}
        self.assertTrue(any("supported limb bone" in error for error in validate_job(job, ROOT)))

    def test_phase3_job_fields_fail_early(self) -> None:
        from vcf_core.jobs import validate_job
        job = json.loads((ROOT / "characters" / "original" / "heavy_sword_hero.json").read_text(encoding="utf-8"))
        job["target_height_meters"] = False
        self.assertTrue(any("target_height_meters" in error for error in validate_job(job, ROOT)))
        job["target_height_meters"] = 4.56
        job["source"] = {"mode": "model"}
        self.assertTrue(any("must declare path" in error for error in validate_job(job, ROOT)))


if __name__ == "__main__":
    unittest.main()
