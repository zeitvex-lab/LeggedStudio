import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from .preflight import build_report, source_metadata


class MjlabPreflightTests(unittest.TestCase):
    def test_workspace_source_metadata(self):
        report = build_report()
        self.assertEqual(report["schema_version"], "mjlab-preflight-1.0")
        self.assertEqual(report["python"]["target"], "3.12.x")
        self.assertEqual(report["mjlab_source"]["name"], "mjlab")
        self.assertEqual(report["mjlab_source"]["version"], "1.6.0")
        self.assertEqual(report["mjlab_source"]["upstream_python_default"], "3.13")
        self.assertTrue(report["baseline_ready"])
        self.assertEqual(report["ready"], all(report["runtime_checks"].values()))

    def test_missing_source_is_reported(self):
        with TemporaryDirectory() as directory:
            metadata = source_metadata(Path(directory) / "missing")
        self.assertFalse(metadata["exists"])
        self.assertNotIn("version", metadata)


if __name__ == "__main__":
    unittest.main()
