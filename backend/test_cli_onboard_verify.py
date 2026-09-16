"""I 组：``onboard`` / ``verify package`` 两条离线命令（DoD #2 的 CLI 半边）。

## 这组测试守的是什么

DoD #2：「新机器人 = 1 目录 + 3 JSON + 模型文件；``onboard → verify → train → export``
全绿且**不改一行 Python**」。这里守前半段（onboard → verify），并且钉住三条不变量：

1. **两条入口 = 同一件事**：CLI ``onboard <dir>``（目录拷贝）与 Web
   ``POST /api/models/import``（base64 上传）必须给出**同一个 ``package_id``** ——
   两边的内容摘要由同一 :func:`backend.model_api._content_hash` 从同样的字节算出。
   这条一旦破了，"同一台机器人"会变成两个包，且没有任何东西会报错。
2. **默认预演、写才落盘、校验不过一字节不写**（与 ``tools/skill_pack.py import`` 同惯例）：
   坏模型必须 exit 1 且包目录不存在；好模型预演后同样不存在。
3. **verify 是门禁**：篡改模型（内容与契约登记的哈希不符）必须 exit 1 并指出原因；
   健康包 exit 0。

命令一律用 subprocess 真调 ``scripts/legged_studio_cli.py``（与用户用法完全一致），
``--workspace`` 指向临时工作区，绝不碰真实 ``workspace/``。
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CLI = ROOT / "scripts" / "legged_studio_cli.py"
#: 控制面 venv 的 python（测试正是跑在里面）；不存在则退回当前解释器。
_VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.is_file() else sys.executable

VALID_URDF = """<robot name='demo_quad'>
  <link name='base'><inertial><mass value='5.0'/></inertial></link>
  <link name='fl_thigh'><inertial><mass value='0.5'/></inertial></link>
  <link name='fl_foot'><inertial><mass value='0.2'/></inertial></link>
  <joint name='fl_hip' type='revolute'>
    <parent link='base'/><child link='fl_thigh'/><limit lower='-1' upper='1'/>
  </joint>
  <joint name='fl_knee' type='revolute'>
    <parent link='fl_thigh'/><child link='fl_foot'/><limit lower='-2' upper='0'/>
  </joint>
</robot>
"""

INVALID_URDF = """<robot name='broken'>
  <link name='b'/>
  <joint name='j' type='revolute'><parent link='b'/><child link='missing'/></joint>
</robot>
"""


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """以仓库根为 cwd 真调 CLI；强制 UTF-8，保证中文/JSON 在 Windows 管道下不乱码。"""

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [PYTHON, str(CLI), *args],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(ROOT), env=env, timeout=180,
    )


def make_robot_dir(base: Path, *, urdf: str = VALID_URDF, mesh: bool = True) -> Path:
    """造一个"1 目录 + 模型文件（+ 随附 mesh）"的机器人目录。"""

    directory = base / "robot"
    (directory / "meshes").mkdir(parents=True)
    (directory / "model.urdf").write_text(urdf, encoding="utf-8")
    if mesh:
        (directory / "meshes" / "leg.stl").write_text("mesh-bytes", encoding="utf-8")
    return directory


class OnboardTest(unittest.TestCase):
    """``onboard``：预演 / 落盘 / fail-closed / 多候选模型。"""

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            proc = run_cli("onboard", str(make_robot_dir(Path(tmp))), "--workspace", str(workspace))
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("预演", proc.stdout)
            self.assertIn("三件 JSON", proc.stdout)
            # 未落盘：packages/ 下没有任何包目录（staging 用完即删）
            packages = workspace / "packages"
            self.assertEqual([], [p for p in packages.iterdir()] if packages.is_dir() else [])
            self.assertFalse((workspace / "package_index.json").exists())

    def test_write_creates_three_json_and_registers(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            directory = make_robot_dir(Path(tmp))
            proc = run_cli("onboard", str(directory), "--workspace", str(workspace), "--write")
            self.assertEqual(0, proc.returncode, proc.stderr)
            packages = sorted(p for p in (workspace / "packages").iterdir() if p.is_dir())
            self.assertEqual(1, len(packages), f"应恰好落下一个包：{packages}")
            package = packages[0]
            for name in ("contract.json", "robot_package.json", "contract_v3.json"):
                self.assertTrue((package / name).is_file(), f"缺 {name}")
            # 模型与随附 mesh 都照搬（不做"猜哪些是资产"的筛选）
            self.assertTrue((package / "model.urdf").is_file())
            self.assertTrue((package / "meshes" / "leg.stl").is_file())
            # 登记：工作区内出现包索引，且索引里能看到这个包
            index_file = workspace / "package_index.json"
            self.assertTrue(index_file.is_file(), "onboard --write 之后应在工作区登记索引")
            self.assertIn(package.name, index_file.read_text(encoding="utf-8"))

    def test_json_report_has_machine_readable_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            proc = run_cli("--json", "onboard", str(make_robot_dir(Path(tmp))), "--workspace", str(workspace))
            self.assertEqual(0, proc.returncode, proc.stderr)
            payload = json.loads(proc.stdout)
            for key in ("preview", "valid", "model_file", "file_count", "package_id",
                        "package_root", "contract_draft", "skipped_dirs", "staged_bytes"):
                self.assertIn(key, payload, f"缺字段 {key}")
            self.assertTrue(payload["preview"] and payload["valid"])
            self.assertEqual("model.urdf", payload["model_file"])
            self.assertEqual(2, payload["file_count"])                     # model.urdf + meshes/leg.stl
            self.assertEqual("demo_quad", payload["contract_draft"]["family"])

    def test_invalid_model_fails_closed_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            proc = run_cli("onboard", str(make_robot_dir(Path(tmp), urdf=INVALID_URDF)),
                           "--workspace", str(workspace), "--write")
            self.assertEqual(1, proc.returncode, proc.stdout)
            self.assertIn("未通过", proc.stdout)
            self.assertIn("未写任何文件", proc.stdout)
            packages = workspace / "packages"
            self.assertEqual([], [p for p in packages.iterdir()] if packages.is_dir() else [])
            self.assertFalse((workspace / "package_index.json").exists())

    def test_multiple_models_require_explicit_choice(self):
        """多个候选模型不许"挑一个最像的"：报错并列出候选，指定 --model 后才放行。"""

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            directory = make_robot_dir(Path(tmp))
            (directory / "other.xml").write_text(VALID_URDF, encoding="utf-8")
            refused = run_cli("onboard", str(directory), "--workspace", str(workspace))
            self.assertEqual(1, refused.returncode, refused.stdout)
            # 用法错误走 stderr（Unix 惯例），正文里必须点出 --model 与候选清单
            self.assertIn("--model", refused.stderr, refused.stdout)
            self.assertIn("model.urdf", refused.stderr, refused.stdout)
            chosen = run_cli("onboard", str(directory), "--model", "model.urdf",
                             "--workspace", str(workspace))
            self.assertEqual(0, chosen.returncode, chosen.stderr)
            self.assertIn("model.urdf", chosen.stdout)


class VerifyPackageTest(unittest.TestCase):
    """``verify package``：健康包通过、被改动的包必红。"""

    def _onboarded(self, tmp: str) -> tuple[Path, Path]:
        workspace = Path(tmp) / "ws"
        proc = run_cli("onboard", str(make_robot_dir(Path(tmp))), "--workspace", str(workspace), "--write")
        self.assertEqual(0, proc.returncode, proc.stderr)
        package = next(p for p in (workspace / "packages").iterdir() if p.is_dir())
        return workspace, package

    def test_healthy_package_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            _workspace, package = self._onboarded(tmp)
            proc = run_cli("verify", "package", str(package))
            self.assertEqual(0, proc.returncode, proc.stdout)
            self.assertIn("✓ 通过", proc.stdout)
            self.assertIn("v3 present", proc.stdout)

    def test_tampered_model_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _workspace, package = self._onboarded(tmp)
            with (package / "model.urdf").open("a", encoding="utf-8") as handle:
                handle.write("\n<!-- tampered -->\n")
            proc = run_cli("verify", "package", str(package))
            self.assertEqual(1, proc.returncode, proc.stdout)
            self.assertIn("hash mismatch", proc.stdout)

    def test_missing_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _workspace, package = self._onboarded(tmp)
            (package / "contract_v3.json").unlink()
            proc = run_cli("--json", "verify", "package", str(package))
            # 缺 v3 是 warning（训练侧可退回 v2），不是 fail：如实分级
            self.assertEqual(0, proc.returncode, proc.stdout)
            payload = json.loads(proc.stdout)
            self.assertEqual("missing", payload["contract_v3"])
            self.assertTrue(any("contract_v3" in item for item in payload["warnings"]))

            (package / "contract.json").unlink()
            broken = run_cli("--json", "verify", "package", str(package))
            self.assertEqual(1, broken.returncode, broken.stdout)
            self.assertIn("缺 contract.json", json.loads(broken.stdout)["problems"][0])


class BothEntriesShareOnePackageIdTest(unittest.TestCase):
    """跨入口不变量：目录导入与 base64 上传必须得到同一个 ``package_id``。

    两条入口描述的是同一份资产；digest 不同就会产出两个包，而且**不会报错** ——
    所以这条必须由测试钉住，而不是靠人记得。
    """

    def test_directory_import_and_upload_agree(self):
        from fastapi.testclient import TestClient

        from backend.api_complete import app
        from backend.model_api import import_package_directory

        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("LEGGED_STUDIO_WORKSPACE")
            os.environ["LEGGED_STUDIO_WORKSPACE"] = str(Path(tmp) / "ws")
            try:
                directory = make_robot_dir(Path(tmp))
                files = [
                    {"path": relative, "content": (directory / relative).read_text(encoding="utf-8"), "encoding": "utf-8"}
                    for relative in ("model.urdf", "meshes/leg.stl")
                ]
                upload = TestClient(app).post(
                    "/api/models/import",
                    json={"files": files, "model_filename": "model.urdf", "format": "auto"},
                )
                self.assertEqual(200, upload.status_code, upload.text)
                uploaded = upload.json()
                self.assertTrue(uploaded["imported"], uploaded)

                # 目录入口：同一个目录、同一份内容 → 必须是同一个包（幂等复用，而不是新建）
                by_directory = import_package_directory(directory, model_filename="model.urdf")
                self.assertTrue(by_directory["imported"], by_directory)
                self.assertEqual(uploaded["package_id"], by_directory["package_id"])
                self.assertEqual(uploaded["package_root"], by_directory["package_root"])
            finally:
                if previous is None:
                    os.environ.pop("LEGGED_STUDIO_WORKSPACE", None)
                else:
                    os.environ["LEGGED_STUDIO_WORKSPACE"] = previous
                from backend.robot_packages import invalidate_package_cache

                invalidate_package_cache()

    def test_base64_and_directory_bytes_hash_identically(self):
        """更直接的一条：同一份字节，两条入口的摘要函数必须给出同一个数。"""

        from backend.model_api import _content_hash, _package_content_hash, ModelImportRequest

        with tempfile.TemporaryDirectory() as tmp:
            directory = make_robot_dir(Path(tmp))
            raw = (directory / "model.urdf").read_bytes()
            from_directory = _content_hash({Path("model.urdf"): raw}.items())
            request = ModelImportRequest(**{
                "files": [{"path": "model.urdf", "content": base64.b64encode(raw).decode("ascii"), "encoding": "base64"}],
                "model_filename": "model.urdf",
                "format": "auto",
            })
            self.assertEqual(from_directory, _package_content_hash(request))


if __name__ == "__main__":
    unittest.main()
