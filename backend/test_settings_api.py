"""Tests for the settings API (Feature 2)."""

from __future__ import annotations

import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.api_complete import app
from backend.settings_api import MIRRORS, read_settings


class SettingsApiTests(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.TemporaryDirectory(prefix="legged-studio-settings-")
        self.previous_data = os.environ.get("LEGGED_STUDIO_DATA_DIR")
        os.environ["LEGGED_STUDIO_DATA_DIR"] = self.data_dir.name
        self.client = TestClient(app)

    def tearDown(self):
        if self.previous_data is None:
            os.environ.pop("LEGGED_STUDIO_DATA_DIR", None)
        else:
            os.environ["LEGGED_STUDIO_DATA_DIR"] = self.previous_data
        self.data_dir.cleanup()

    def test_default_settings_exposed(self):
        payload = self.client.get("/api/settings").json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["settings"]["backend_port"], 8765)
        self.assertEqual(payload["settings"]["torch_device"], "gpu")
        self.assertEqual(payload["settings"]["mirror"], "tsinghua")
        self.assertIn("tsinghua", payload["catalog"]["mirrors"])
        self.assertIn("sjtu", payload["catalog"]["mirrors"])
        self.assertIn("official", payload["catalog"]["mirrors"])

    def test_update_settings_persists(self):
        response = self.client.put("/api/settings", json={
            "backend_port": 9999,
            "torch_device": "cpu",
            "mirror": "sjtu",
            "python_path": "C:/python.exe",
        })
        self.assertEqual(response.status_code, 200)
        saved = response.json()["settings"]
        self.assertEqual(saved["backend_port"], 9999)
        self.assertEqual(saved["torch_device"], "cpu")
        self.assertEqual(saved["mirror"], "sjtu")
        self.assertTrue(saved["schema_version"].startswith("legged-studio-settings"))
        # Re-read from disk to confirm persistence.
        self.assertEqual(read_settings()["mirror"], "sjtu")

    def test_mirror_catalog(self):
        payload = self.client.get("/api/settings/mirrors").json()
        self.assertEqual(payload["current"], "tsinghua")
        self.assertIn("pypi_index", payload["mirrors"]["tsinghua"])
        self.assertIn("torch_index", payload["mirrors"]["tsinghua"])

    def test_gpu_profile_switch_persists(self):
        response = self.client.post("/api/settings/gpu-profile/switch", json={"torch_device": "cpu"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["requires_reinstall"])
        self.assertEqual(read_settings()["torch_device"], "cpu")

    def test_gpu_profile_reinstall_reports_command(self):
        response = self.client.post("/api/settings/gpu-profile/reinstall")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["device"], "gpu")
        self.assertEqual(payload["torch"], "torch==2.11.0+cu128")
        self.assertIn("pypi_index", payload)
        self.assertIn("uv pip install", payload["command"])

    def test_invalid_port_rejected(self):
        response = self.client.put("/api/settings", json={"backend_port": 80})
        self.assertEqual(response.status_code, 422)

    def test_invalid_torch_device_rejected(self):
        response = self.client.put("/api/settings", json={"torch_device": "tpu"})
        self.assertEqual(response.status_code, 422)
