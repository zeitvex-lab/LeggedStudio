import unittest

from tools.audit_observation_parity import audit


class ObservationParityTests(unittest.TestCase):
    def test_current_tree_has_no_parity_errors(self):
        report = audit()
        self.assertEqual(report["errors"], [])
        self.assertGreater(report["robots"], 0)
        self.assertGreater(report["policies"], 0)

    def test_legacy_manifest_is_used_only_for_nonstandard_widths(self):
        report = audit()
        self.assertGreater(report["legacy_policies"], 0)


if __name__ == "__main__":
    unittest.main()
