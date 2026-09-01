import unittest

from .training_adapter import resolve_torch_device, runtime_device_info


class TrainingRuntimeTests(unittest.TestCase):
    def test_auto_resolves_to_available_runtime(self):
        resolved = resolve_torch_device("auto")
        self.assertIn(resolved, {"cpu", "cuda"})
        info = runtime_device_info(resolved)
        self.assertEqual(info["resolved"], resolved)
        self.assertIn("torch_version", info)

    def test_invalid_device_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_torch_device("metal")

    def test_cpu_is_always_supported(self):
        self.assertEqual(resolve_torch_device("cpu"), "cpu")


if __name__ == "__main__":
    unittest.main()
