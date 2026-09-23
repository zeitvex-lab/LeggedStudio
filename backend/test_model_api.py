import unittest
import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api_complete import app
from backend.gl_env import offscreen_render_status
from backend.robot_presets import list_robot_presets
from backend.robot_packages import package_for_contract


class ModelInspectionTests(unittest.TestCase):
    def setUp(self):
        self.workspace_temp = tempfile.TemporaryDirectory(prefix="legged-studio-test-")
        self.previous_workspace = os.environ.get("LEGGED_STUDIO_WORKSPACE")
        os.environ["LEGGED_STUDIO_WORKSPACE"] = self.workspace_temp.name
        self.client = TestClient(app)

    def tearDown(self):
        if self.previous_workspace is None:
            os.environ.pop("LEGGED_STUDIO_WORKSPACE", None)
        else:
            os.environ["LEGGED_STUDIO_WORKSPACE"] = self.previous_workspace
        self.workspace_temp.cleanup()

    def test_builtin_robot_is_described_as_a_package(self):
        package = package_for_contract(list_robot_presets()[0]["contract"])
        self.assertEqual(package["schema_version"], "robot-package-1.0")
        self.assertEqual(package["task_kind"], "generic")
        self.assertTrue(package["package_root"])


    def test_mjcf_report_contains_structure_and_actuator_mapping(self):
        preset = next(item for item in list_robot_presets() if item["robot_id"] == "unitree_go2")
        response = self.client.post(
            "/api/models/validate",
            json={"path": preset["asset_path"], "format": "mjcf", "contract": preset["contract"]},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["valid"])
        self.assertGreater(payload["stats"]["links"], 0)
        self.assertGreater(payload["stats"]["actuators"], 0)
        self.assertIn("topology", payload["inspection"])
        self.assertIn("actuators", payload["inspection"])

    def test_uploaded_urdf_returns_diagnostics(self):
        urdf = """<robot name='fixture'><link name='base'/><link name='foot'/><joint name='bad' type='revolute'><parent link='base'/><child link='foot'/></joint></robot>"""
        response = self.client.post(
            "/api/models/validate",
            json={"content": urdf, "filename": "fixture.urdf", "format": "auto"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["format"], "urdf")
        self.assertFalse(payload["valid"])
        self.assertTrue(any("missing limit" in item for item in payload["errors"]))
        self.assertIn("inertial", payload["inspection"])

    def test_validation_rejects_a_model_outside_allowed_roots(self):
        with tempfile.TemporaryDirectory(prefix="outside-model-") as outside:
            model = Path(outside) / "model.urdf"
            model.write_text("<robot name='outside'><link name='base'/></robot>", encoding="utf-8")
            response = self.client.post("/api/models/validate", json={"path": str(model)})
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertFalse(payload["valid"], payload)
        self.assertEqual(["model path must be inside the Legged Studio project or workspace"], payload["errors"])

    def test_validation_prefers_content_and_cleans_its_temporary_source(self):
        payload = self.client.post("/api/models/validate", json={
            "path": "missing.urdf", "filename": "uploaded.urdf", "format": "auto",
            "content": "<robot name='uploaded'><link name='base'/></robot>",
        }).json()
        self.assertTrue(payload["valid"], payload)
        self.assertEqual("urdf", payload["format"])
        self.assertEqual("uploaded.urdf", payload["filename"])
        self.assertFalse(Path(payload["source_path"]).exists())

    def test_missing_input_and_invalid_format_keep_distinct_error_contracts(self):
        missing = self.client.post("/api/models/validate", json={})
        self.assertEqual(200, missing.status_code)
        self.assertEqual({"valid": False, "errors": ["provide either path or content"], "warnings": []}, missing.json())
        invalid = self.client.post("/api/models/validate", json={"content": "<robot/>", "format": "unknown"})
        self.assertEqual(422, invalid.status_code)

    def test_upload_rejects_parent_paths_without_persisting_files(self):
        for path in ("../model.urdf", "nested/../../model.urdf", r"..\model.urdf"):
            with self.subTest(path=path):
                payload = self.client.post("/api/models/import", json={
                    "files": [{"path": path, "content": "<robot><link name='base'/></robot>"}],
                }).json()
                self.assertFalse(payload["imported"], payload)
                self.assertTrue(payload["errors"], payload)
        workspace = Path(self.workspace_temp.name)
        self.assertEqual([], list((workspace / "packages").iterdir()))
        self.assertFalse((workspace / "package_index.json").exists())

    def test_uploaded_urdf_has_real_topology_preview(self):
        urdf = """<robot name='fixture'><link name='base'/><link name='foot'/><joint name='hip' type='revolute'><parent link='base'/><child link='foot'/></joint></robot>"""
        response = self.client.post("/api/models/preview", json={"content": urdf, "filename": "fixture.urdf", "format": "urdf"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertIn("<svg", payload["svg"])
        self.assertIn("hip", payload["svg"])

    def test_mjcf_has_real_render_preview(self):
        # 显式前置：离屏渲染需要可用的 GL 后端（无显示环境依赖 libEGL/libOSMesa）。
        # 环境显式关闭渲染（MUJOCO_GL=disabled）或缺少后端时，这是环境约束而非
        # 代码缺陷，按 skip 处理并带上原因，避免把环境问题误报成失败。
        available, reason = offscreen_render_status()
        if not available:
            self.skipTest(f"离屏渲染不可用：{reason}")
        preset = next(item for item in list_robot_presets() if item["robot_id"] == "unitree_go2")
        response = self.client.post("/api/models/preview", json={"path": preset["asset_path"], "format": "mjcf", "width": 960, "height": 640})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"], payload)
        self.assertTrue(payload["image_base64"])

    def test_import_persists_model_and_generates_contract_draft(self):
        urdf = """<robot name='imported'><link name='base'><inertial><mass value='2'/></inertial></link></robot>"""
        response = self.client.post(
            "/api/models/import",
            json={"files": [{"path": "demo/model.urdf", "content": urdf, "encoding": "utf-8"}], "model_filename": "demo/model.urdf", "format": "auto"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["imported"])
        package_root = Path(payload["package_root"])
        self.assertEqual(package_root.parent, Path(self.workspace_temp.name) / "packages")
        self.assertTrue(Path(payload["model_path"]).is_file())
        self.assertEqual(payload["contract_draft"]["source"], "legged_studio_asset_import")

        # Importing identical content reuses the immutable package rather than
        # creating another random workspace entry.
        again = self.client.post(
            "/api/models/import",
            json={"files": [{"path": "demo/model.urdf", "content": urdf, "encoding": "utf-8"}], "model_filename": "demo/model.urdf", "format": "auto"},
        ).json()
        self.assertEqual(again["package_id"], payload["package_id"])
        packages = self.client.get("/api/project/packages").json()
        self.assertEqual(packages["count"], 1)
        self.assertEqual(packages["packages"][0]["source"], "workspace")

    def test_project_package_round_trip_contains_training_and_scenario(self):
        import base64
        response = self.client.post("/api/project/export", json={"training_config": {"algorithm": "PPO", "reward_scales": {"track_linear_velocity": 2.0}}, "scenario": {"map_id": "warehouse", "mode": "navigation"}})
        self.assertEqual(response.status_code, 200)
        encoded = base64.b64encode(response.content).decode("ascii")
        imported = self.client.post("/api/project/import", json={"archive_base64": encoded})
        self.assertEqual(imported.status_code, 200)
        payload = imported.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["training_config"]["algorithm"], "PPO")
        self.assertEqual(payload["scenario"]["map_id"], "warehouse")
        self.assertFalse((Path(self.workspace_temp.name) / "imports").exists())

    def test_project_router_imports_raw_models_without_model_router(self):
        import subprocess
        import sys

        script = """
import base64, io, json, sys, zipfile
sys.modules['backend.model_api'] = None
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.project_api import router
app = FastAPI()
app.include_router(router)
stream = io.BytesIO()
with zipfile.ZipFile(stream, 'w') as archive:
    archive.writestr('robots/demo.urdf', "<robot name='demo'><link name='base'/></robot>")
response = TestClient(app).post('/api/project/import', json={'archive_base64': base64.b64encode(stream.getvalue()).decode('ascii')})
print(json.dumps(response.json()))
"""
        proc = subprocess.run(
            [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        import json

        report = json.loads(proc.stdout)
        self.assertTrue(report["success"], report)
        self.assertEqual(["imported_demo"], report["package_ids"])
        self.assertTrue(Path(report["robots"][0]["asset_path"]).is_file())

    def test_raw_project_archive_import_list_and_export(self):
        import base64
        import io
        import json
        import zipfile

        stream = io.BytesIO()
        urdf = "<robot name='demo'><link name='base'><inertial><mass value='2'/></inertial></link></robot>"
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("manifest.json", json.dumps({"model_path": "robots/demo.urdf"}))
            archive.writestr("robots/demo.urdf", urdf)
        response = self.client.post(
            "/api/project/import",
            json={"archive_base64": base64.b64encode(stream.getvalue()).decode("ascii")},
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(payload["success"], payload)
        self.assertEqual(["imported_demo"], payload["package_ids"])
        robot = payload["robots"][0]
        self.assertEqual("legged_studio_project_import", robot["contract"]["source"])
        self.assertEqual(["imported", "project_package"], robot["contract"]["tags"])
        self.assertEqual(urdf, Path(robot["asset_path"]).read_text(encoding="utf-8"))
        listed = self.client.get("/api/project/packages").json()
        self.assertEqual(1, listed["count"])
        self.assertEqual("imported_demo", listed["packages"][0]["package_id"])
        exported = self.client.post("/api/project/export", json={"import_ids": ["imported_demo"]})
        self.assertEqual(200, exported.status_code)
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            self.assertEqual(urdf.encode("utf-8"), archive.read("robots/imported_demo/robots/demo.urdf"))


if __name__ == "__main__":
    unittest.main()
