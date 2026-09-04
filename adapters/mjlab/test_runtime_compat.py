import unittest

from adapters.mjlab.runtime_compat import evaluate_package_runtime, satisfies_version


class RuntimeCompatibilityTests(unittest.TestCase):
    def test_version_constraints(self):
        self.assertTrue(satisfies_version("1.6.0", ">=1.6,<2.0"))
        self.assertFalse(satisfies_version("1.3.0", ">=1.6,<2.0"))
        self.assertIsNone(satisfies_version(None, ">=1.6"))

    def test_package_report_is_explicit(self):
        package = {"runtime_requirements": {"mjlab": ">=1.6,<2.0", "torch": ">=2.7"}}
        report = evaluate_package_runtime(package, {"mjlab_version": "1.6.0", "torch_version": "2.11.0+cu128"})
        self.assertEqual(report["status"], "compatible")
        failed = evaluate_package_runtime(package, {"mjlab_version": "1.3.0", "torch_version": "2.11.0+cu128"})
        self.assertEqual(failed["status"], "incompatible")


if __name__ == "__main__":
    unittest.main()
