"""序 10：Capability 导出物的 Web 入口（`/api/exports`）测试。

守四条：

1. **委托而非重写**：打包/校验的结果必须与 `bundle_export` 一致（页面导出的与 CLI 导出的
   得是同一个东西）——所以每个用例都同时用库函数对照；
2. **只按名字认目录**：名字里的分隔符 / `..` / 空串一律拒（页面输入不能当路径用）；
3. **不覆盖**：同名导出物已存在 ⇒ 409，除非显式 `overwrite=true`；
4. **收包只校验不落盘**：导入返回**验过的载荷**（调用方拿去跑/预填），不往磁盘写新位置。

工作区用 `LEGGED_STUDIO_WORKSPACE` 指到临时目录（`backend.paths.workspace_root` 每次读环境变量，
无缓存），因此**绝不碰真实 `workspace/`**。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.paths import WORKSPACE_ENV  # noqa: E402

SCENARIO = {
    "scenario_id": "web_export_demo",
    "map_id": "warehouse",
    "mode": "navigation",
    "waypoints": [{"x": 0, "y": 0}, {"x": 2, "y": 1}],
}


class ExportsApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name)
        self._env = mock.patch.dict(os.environ, {WORKSPACE_ENV: str(self.workspace)})
        self._env.start()
        from fastapi.testclient import TestClient

        from backend.api_complete import app

        self.client = TestClient(app)

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    # ── 1. 列表 ──────────────────────────────────────────────────────────
    def test_list_is_well_formed_when_empty(self):
        response = self.client.get("/api/exports")
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(0, payload["count"])
        self.assertEqual([], payload["exports"])
        self.assertIn("exports", payload["root"])

    # ── 2. 打包场景（内联载荷）────────────────────────────────────────────
    def test_create_scenario_export_from_inline_payload(self):
        from backend.bundle_export import verify_export

        response = self.client.post("/api/exports/scenario", json={"scenario": SCENARIO})
        self.assertEqual(200, response.status_code, response.text)
        payload = response.json()
        self.assertTrue(payload["success"], payload)
        self.assertTrue(payload["verify"]["ok"], payload["verify"]["problems"])
        out_dir = self.workspace / "exports" / "scenario-web_export_demo"
        self.assertTrue((out_dir / "scenario.json").is_file())
        # **委托而非重写**：库函数对同一目录给出同一结论
        self.assertTrue(verify_export(out_dir)["ok"])

        listed = self.client.get("/api/exports").json()
        self.assertEqual(1, listed["count"])
        self.assertEqual(0, listed["broken"])
        self.assertEqual("scenario", listed["exports"][0]["kind"])

    def test_created_export_can_be_read_back_through_detail(self):
        self.client.post("/api/exports/scenario", json={"scenario": SCENARIO})
        detail = self.client.get("/api/exports/scenario-web_export_demo").json()
        self.assertTrue(detail["success"], detail)
        self.assertEqual("scenario", detail["kind"])
        self.assertIn("entries", detail)

    # ── 3. 输入的拒绝路径 ────────────────────────────────────────────────
    def test_invalid_scenario_is_rejected(self):
        bad = dict(SCENARIO, scenario_id="Bad Id!")
        response = self.client.post("/api/exports/scenario", json={"scenario": bad})
        self.assertEqual(400, response.status_code)
        self.assertIn("场景不合法", response.json()["detail"])

    def test_missing_input_is_rejected(self):
        response = self.client.post("/api/exports/scenario", json={})
        self.assertEqual(400, response.status_code)

    def test_unshippable_map_is_rejected_with_reason(self):
        """地图不可随包走（库外且找不到文件）⇒ **400 带原话**，不是 500（C4）。

        "接口说谎"的反面：拒绝要让人看得懂怎么修；而如果这里返回 500，用户只会知道
        "打包失败了"，不知道要先把地形放进 `assets/maps/`。
        """

        payload = dict(SCENARIO, scenario_id="unshippable-map", map_id="my_secret_terrain")
        response = self.client.post("/api/exports/scenario",
                                    json={"scenario": payload, "out_name": "unshippable-map"})
        self.assertEqual(400, response.status_code)
        self.assertIn("公共地图库", response.json()["detail"])

    def test_absolute_scenario_path_is_rejected(self):
        for value in ("C:/tmp/x.json", "/tmp/x.json", "../outside.json"):
            response = self.client.post("/api/exports/scenario", json={"scenario_path": value})
            self.assertEqual(400, response.status_code, f"{value} 应被拒（只接受仓库相对路径）")

    def test_export_name_traversal_is_rejected(self):
        for name in ("..", "a/b", "a\\b", "", "../../etc"):
            response = self.client.post("/api/exports/import-scenario", json={"name": name})
            self.assertEqual(400, response.status_code, f"名字 {name!r} 应被拒")

    def test_unknown_export_is_404(self):
        self.assertEqual(404, self.client.get("/api/exports/no_such_export").status_code)
        self.assertEqual(404, self.client.post("/api/exports/import-scenario", json={"name": "no_such_export"}).status_code)

    # ── 4. 不覆盖 + 收包 ─────────────────────────────────────────────────
    def test_same_name_is_not_overwritten_by_default(self):
        first = self.client.post("/api/exports/scenario", json={"scenario": SCENARIO})
        self.assertEqual(200, first.status_code)
        second = self.client.post("/api/exports/scenario", json={"scenario": SCENARIO})
        self.assertEqual(409, second.status_code, second.text)
        forced = self.client.post("/api/exports/scenario", json={"scenario": SCENARIO, "overwrite": True})
        self.assertEqual(200, forced.status_code, forced.text)

    def test_import_returns_validated_payload_without_writing(self):
        from contracts.scenario_contract import ScenarioContract

        self.client.post("/api/exports/scenario", json={"scenario": SCENARIO})
        response = self.client.post("/api/exports/import-scenario", json={"name": "scenario-web_export_demo"})
        self.assertEqual(200, response.status_code, response.text)
        payload = response.json()
        self.assertTrue(payload["success"], payload)
        self.assertEqual("export_dir", payload["form"])
        self.assertEqual(ScenarioContract(**SCENARIO).to_payload(), payload["scenario"])
        # **不落盘**：导出目录之外没有任何新东西
        self.assertEqual({"exports"}, {path.name for path in self.workspace.iterdir()})

    def test_tampered_pack_is_refused_on_import_and_reported_in_detail(self):
        self.client.post("/api/exports/scenario", json={"scenario": SCENARIO})
        target = self.workspace / "exports" / "scenario-web_export_demo" / "scenario.json"
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["map_id"] = "flat"
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        imported = self.client.post("/api/exports/import-scenario", json={"name": "scenario-web_export_demo"})
        self.assertEqual(400, imported.status_code)
        self.assertIn("完整性", imported.json()["detail"])

        detail = self.client.get("/api/exports/scenario-web_export_demo").json()
        self.assertFalse(detail["success"])
        self.assertTrue(any("sha256" in problem for problem in detail["problems"]), detail["problems"])

        listed = self.client.get("/api/exports").json()
        self.assertEqual(1, listed["broken"], "坏包必须在列表里被标出来，而不是混在好包里")


if __name__ == "__main__":
    unittest.main()
