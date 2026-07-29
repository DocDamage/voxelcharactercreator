from __future__ import annotations

import unittest
from pathlib import Path

from vcf_core.builds import (
    BLOCKING_QA_CHECKS,
    BuildStatus,
    determine_status,
    require_matching_input_provenance,
    safe_output_directory,
    successful_build_status,
    summarize_blocking_checks,
)


class BuildStatusTests(unittest.TestCase):
    def test_proxy_is_never_complete(self) -> None:
        self.assertEqual(
            BuildStatus.PROTOTYPE,
            determine_status(uses_proxy=True, has_unbound_geometry=False, blocking_checks_passed=True),
        )

    def test_unbound_geometry_is_never_complete(self) -> None:
        self.assertEqual(
            BuildStatus.INCOMPLETE,
            determine_status(uses_proxy=False, has_unbound_geometry=True, blocking_checks_passed=True),
        )

    def test_failed_blocking_check_is_never_complete(self) -> None:
        self.assertEqual(
            BuildStatus.INCOMPLETE,
            determine_status(uses_proxy=False, has_unbound_geometry=False, blocking_checks_passed=False),
        )

    def test_fully_bound_passing_build_can_complete(self) -> None:
        self.assertEqual(
            BuildStatus.COMPLETE,
            determine_status(uses_proxy=False, has_unbound_geometry=False, blocking_checks_passed=True),
        )

    def test_blocking_summary_fails_closed_for_false_or_missing_checks(self) -> None:
        checks = {name: True for name in BLOCKING_QA_CHECKS}
        self.assertTrue(summarize_blocking_checks(checks, BLOCKING_QA_CHECKS)["passed"])
        checks["qa_color_budget"] = False
        failed = summarize_blocking_checks(checks, BLOCKING_QA_CHECKS)
        self.assertFalse(failed["passed"])
        self.assertEqual(["qa_color_budget"], failed["failed"])
        del checks["qa_animation_presence"]
        missing = summarize_blocking_checks(checks, BLOCKING_QA_CHECKS)
        self.assertFalse(missing["passed"])
        self.assertEqual(["qa_animation_presence"], missing["missing"])

    def test_blocking_summary_requires_literal_true(self) -> None:
        summary = summarize_blocking_checks({"exported": 1}, {"exported"})
        self.assertFalse(summary["passed"])
        self.assertEqual(["exported"], summary["failed"])

    def test_only_promotable_statuses_allow_a_successful_worker_exit(self) -> None:
        self.assertTrue(successful_build_status(BuildStatus.PROTOTYPE))
        self.assertTrue(successful_build_status("complete"))
        self.assertFalse(successful_build_status("incomplete"))
        self.assertFalse(successful_build_status("failed"))

    def test_character_output_is_contained_under_exports(self) -> None:
        root = Path("project").resolve()
        self.assertEqual(
            root / "exports" / "ff7" / "cloud",
            safe_output_directory(root, "ff7", "cloud"),
        )
        with self.assertRaises(ValueError):
            safe_output_directory(root, "../../outside", "cloud")
        for alias in ("other/../ff7", ".cache", "C:/exports/ff7"):
            with self.subTest(alias=alias), self.assertRaises(ValueError):
                safe_output_directory(root, alias, "cloud")
        with self.assertRaises(ValueError):
            safe_output_directory(root, "ff7", "cloud/../tifa")

    def test_execution_root_must_match_hashed_input_root(self) -> None:
        root = Path("project").resolve()
        require_matching_input_provenance(root, root)
        with self.assertRaises(ValueError):
            require_matching_input_provenance(root / "live", root / "snapshot")


if __name__ == "__main__":
    unittest.main()
