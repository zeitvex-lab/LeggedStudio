"""I3 的 Web 向导半边：训练配置页能导入新机器人（与 CLI `onboard` 同一份编排）。

## 这组测试守的是什么

I3 的验收是"**新机器人 = 1 目录 + 3 JSON + 模型，不改一行 Python**"。CLI `onboard` 与
`POST /api/models/import` 早已共用一份编排（`import_staged_package`），但**训练配置页没有入口** ——
用户想训新导入的机器人，得先跑去别的页面传模型。这里补的正是那个入口，于是要钉住三件事：

1. **页面真有入口**（按钮 + 目录选择 + 结果行），且调用的是**同一个端点**——
   不在前端另写落位规则（包 id 由内容哈希决定，前端猜不得）；
2. **导入后能接着配训练**：新包必须出现在 `/api/robots/presets` 里（页面刷新列表的前提）；
3. **脚本语法过**（`node --check`）：单文件内联脚本，语法错就是整页白屏。

端到端那条用 `TestClient` + 临时工作区（**不碰仓库的 workspace/packages**）。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.test_cli_onboard_verify import make_robot_dir  # noqa: E402  复用同一份最小机器人目录夹具

PAGE = ROOT / "web" / "training_create.html"


class TrainingPageImportEntryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = PAGE.read_text(encoding="utf-8")

    def test_import_entry_exists(self):
        for element in ("robotImportBtn", "robotImportInput", "robotImportResult"):
            self.assertIn(f'id="{element}"', self.html, f"训练页缺 {element}")
        self.assertIn("webkitdirectory", self.html, "没有目录选择：模型与 mesh 要一起选")

    def test_page_uses_the_shared_import_endpoint(self):
        """**同一个端点**：与 CLI `onboard`、工作台/校验页的上传共用编排。"""

        self.assertIn("/api/models/import", self.html)
        self.assertIn("model_filename", self.html)
        self.assertIn("encoding: 'base64'", self.html)

    def test_import_refreshes_and_selects_the_new_package(self):
        self.assertIn("await loadPresets(payload.package_id)", self.html)
        self.assertIn("loadPresets(preferredRobotId)", self.html)

    def test_failure_path_does_not_claim_success(self):
        """校验不过时不许写"导入失败"这种查不出原因的话 —— 要把后端校验报告摆出来。"""

        self.assertIn("未写入任何文件", self.html)
        self.assertIn("errors", self.html)

    def test_inline_scripts_pass_node_syntax_check(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("没有 node，跳过脚本语法门禁")
        blocks = re.findall(r"<script>(.*?)</script>", self.html, re.S)
        self.assertTrue(blocks)
        with tempfile.TemporaryDirectory() as tmp:
            for index, block in enumerate(blocks):
                path = Path(tmp) / f"block-{index}.js"
                path.write_text(block, encoding="utf-8")
                completed = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
                self.assertEqual(0, completed.returncode, f"块{index} 语法错误：{completed.stderr[:300]}")


class OnboardFromTrainingPageTest(unittest.TestCase):
    """页面上传的载荷形状（base64 整目录）→ 真导入 → 能在机器人列表里被选上。"""

    def test_upload_payload_imports_and_appears_in_presets(self):
        from fastapi.testclient import TestClient

        from backend.api_complete import app
        from backend.robot_packages import invalidate_package_cache

        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("LEGGED_STUDIO_WORKSPACE")
            os.environ["LEGGED_STUDIO_WORKSPACE"] = str(Path(tmp) / "ws")
            try:
                directory = make_robot_dir(Path(tmp))
                files = [
                    {
                        "path": relative,
                        "content": __import__("base64").b64encode((directory / relative).read_bytes()).decode(),
                        "encoding": "base64",
                    }
                    for relative in ("model.urdf", "meshes/leg.stl")
                ]
                client = TestClient(app)
                response = client.post(
                    "/api/models/import",
                    json={"files": files, "model_filename": "model.urdf", "format": "auto"},
                )
                self.assertEqual(200, response.status_code, response.text)
                payload = response.json()
                self.assertTrue(payload["imported"], payload)
                self.assertTrue(payload["package_id"])

                # 页面的下一步是 `loadPresets(package_id)`：新包必须出现在机器人列表里
                invalidate_package_cache()
                presets = client.get("/api/robots/presets").json().get("presets") or []
                ids = {str(item.get("robot_id")) for item in presets}
                self.assertIn(payload["package_id"], ids, f"新包没进机器人列表：{sorted(ids)}")
            finally:
                if previous is None:
                    os.environ.pop("LEGGED_STUDIO_WORKSPACE", None)
                else:
                    os.environ["LEGGED_STUDIO_WORKSPACE"] = previous
                invalidate_package_cache()

    def test_failed_validation_writes_nothing(self):
        """校验不过 ⇒ `imported=false` 且**一个字节都不写**（页面据此如实报"未写入任何文件"）。"""

        from fastapi.testclient import TestClient

        from backend.api_complete import app

        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("LEGGED_STUDIO_WORKSPACE")
            workspace = Path(tmp) / "ws"
            os.environ["LEGGED_STUDIO_WORKSPACE"] = str(workspace)
            try:
                response = TestClient(app).post(
                    "/api/models/import",
                    json={"files": [{"path": "broken.xml", "content": "<mujoco><broken>", "encoding": "utf-8"}],
                          "model_filename": "broken.xml", "format": "auto"},
                )
                self.assertEqual(200, response.status_code, response.text)
                payload = response.json()
                self.assertFalse(payload["imported"], payload)
                self.assertTrue(payload.get("errors"), payload)
                packages = workspace / "packages"
                self.assertEqual([], [item for item in packages.iterdir()] if packages.is_dir() else [])
            finally:
                if previous is None:
                    os.environ.pop("LEGGED_STUDIO_WORKSPACE", None)
                else:
                    os.environ["LEGGED_STUDIO_WORKSPACE"] = previous


if __name__ == "__main__":
    unittest.main()
