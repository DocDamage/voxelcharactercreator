from __future__ import annotations

import unittest

from vcf_core.builds import BuildStatus, determine_status


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


if __name__ == "__main__":
    unittest.main()
