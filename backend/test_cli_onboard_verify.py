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
from unittest import mock

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
            for name in ("contract_legacy_v2.json", "robot_package.json", "contract.json"):
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
            self.assertIn("真值 present", proc.stdout)

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
            (package / "contract.json").unlink()
            proc = run_cli("--json", "verify", "package", str(package))
            # 缺 v3 是 warning（训练侧可退回 v2），不是 fail：如实分级
            self.assertEqual(0, proc.returncode, proc.stdout)
            payload = json.loads(proc.stdout)
            self.assertEqual("missing", payload["contract"])
            self.assertTrue(any("contract" in item for item in payload["warnings"]))

            (package / "contract_legacy_v2.json").unlink()
            broken = run_cli("--json", "verify", "package", str(package))
            self.assertEqual(1, broken.returncode, broken.stdout)
            self.assertIn("缺 contract_legacy_v2.json", json.loads(broken.stdout)["problems"][0])


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


class ImportPreviewConsistencyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="legged-studio-import-preview-")
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Path(self.tmp.name) / "ws"
        patcher = mock.patch.dict(os.environ, {"LEGGED_STUDIO_WORKSPACE": str(self.workspace)})
        patcher.start()
        self.addCleanup(patcher.stop)
        from backend.robot_packages import invalidate_package_cache

        self.addCleanup(invalidate_package_cache)

    def test_preview_matches_persisted_contracts_without_writing_a_package(self):
        from backend.model_api import import_package_directory, preview_package_import

        source = make_robot_dir(Path(self.tmp.name))
        preview = preview_package_import(source)
        self.assertTrue(preview["valid"], preview)
        self.assertEqual([], list((self.workspace / "packages").iterdir()))
        self.assertFalse((self.workspace / "package_index.json").exists())

        imported = import_package_directory(source)
        self.assertTrue(imported["imported"], imported)
        self.assertEqual(imported["package_id"], preview["package_id"])
        self.assertEqual(imported["package_root"], preview["package_root"])
        package = Path(imported["package_root"])
        persisted_v2 = json.loads((package / "contract_legacy_v2.json").read_text(encoding="utf-8"))
        persisted_truth = json.loads((package / "contract.json").read_text(encoding="utf-8"))
        self.assertEqual(persisted_v2, preview["contract_draft"])
        self.assertEqual(persisted_truth, preview["contract_preview"])
        self.assertEqual(persisted_v2, imported["contract_draft"])
        self.assertEqual("demo_quad", persisted_v2["family"])
        self.assertEqual(["fl_hip", "fl_knee"], persisted_v2["action"]["joint_order"])

    def test_reimport_preserves_existing_contracts_and_manifest(self):
        from backend.model_api import import_package_directory

        source = make_robot_dir(Path(self.tmp.name))
        imported = import_package_directory(source)
        self.assertTrue(imported["contract"]["generated"], imported)
        package = Path(imported["package_root"])
        truth_path = package / "contract.json"
        truth = json.loads(truth_path.read_text(encoding="utf-8"))
        truth["description"] = "user calibration"
        truth_path.write_text(json.dumps(truth), encoding="utf-8")
        before = {name: (package / name).read_bytes() for name in (
            "contract.json", "contract_legacy_v2.json", "robot_package.json",
        )}

        repeated = import_package_directory(source)
        self.assertTrue(repeated["imported"], repeated)
        self.assertEqual(imported["package_id"], repeated["package_id"])
        self.assertEqual({"generated": False, "note": None}, repeated["contract"])
        self.assertEqual(before, {name: (package / name).read_bytes() for name in before})
        index = json.loads((self.workspace / "package_index.json").read_text(encoding="utf-8"))
        self.assertEqual([imported["package_id"]], [item["robot_id"] for item in index])

    def test_invalid_preview_leaves_no_package_or_index(self):
        from backend.model_api import preview_package_import

        source = make_robot_dir(Path(self.tmp.name), urdf=INVALID_URDF)
        preview = preview_package_import(source)
        self.assertFalse(preview["valid"])
        self.assertTrue(preview["errors"])
        self.assertNotIn("package_id", preview)
        self.assertEqual([], list((self.workspace / "packages").iterdir()))
        self.assertFalse((self.workspace / "package_index.json").exists())


class VerifyRunTest(unittest.TestCase):
    """``verify run``：Run 档案对账（判据取 backend.training.runs.verify_run，不重算）。"""

    def setUp(self):
        self.previous_venv = os.environ.get("LEGGED_STUDIO_MJLAB_VENV")
        self.tmp = tempfile.TemporaryDirectory(prefix="legged-studio-verify-run-")

    def tearDown(self):
        if self.previous_venv is None:
            os.environ.pop("LEGGED_STUDIO_MJLAB_VENV", None)
        else:
            os.environ["LEGGED_STUDIO_MJLAB_VENV"] = self.previous_venv
        self.tmp.cleanup()

    def _make_run(self, *, name: str = "unitree_go2_task_000000000001") -> tuple[Path, Path]:
        """造一个四件套齐全的合成 Run（用真实落盘函数，环境锁指向假 venv 以保证可复现）。"""

        from types import SimpleNamespace

        from backend.training.runs import create_run_for_task

        fake_venv = Path(self.tmp.name) / "venv"
        site = fake_venv / "lib" / "python3.12" / "site-packages"
        for dist in ("torch-2.0.0.dist-info", "mjlab-1.6.0.dist-info"):
            (site / dist).mkdir(parents=True)
        os.environ["LEGGED_STUDIO_MJLAB_VENV"] = str(fake_venv)

        workspace = Path(self.tmp.name) / "ws"
        workspace.mkdir(exist_ok=True)
        run_dir = workspace / name
        contract = SimpleNamespace(robot_id="unitree_go2", compute_hash=lambda: "cafe1234")
        create_run_for_task(
            run_dir, contract=contract,
            config={"robot_id": "unitree_go2", "seed": 7, "num_envs": 16, "max_iterations": 5},
            task="training",
        )
        return workspace, run_dir

    def test_healthy_run_passes(self):
        workspace, run_dir = self._make_run()
        proc = run_cli("verify", "run", run_dir.name, "--workspace", str(workspace))
        self.assertEqual(0, proc.returncode, proc.stdout)
        self.assertIn("✓", proc.stdout)
        self.assertIn("1 通过", proc.stdout)

    def test_tampered_run_is_rejected(self):
        """档案被改过（resolved-config 与登记指纹不符）→ 必红。"""

        workspace, run_dir = self._make_run()
        payload = json.loads((run_dir / "resolved-config.json").read_text(encoding="utf-8"))
        payload["inputs"]["seed"] = 999               # 篡改一处输入（种子）
        (run_dir / "resolved-config.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        proc = run_cli("verify", "run", run_dir.name, "--workspace", str(workspace))
        self.assertEqual(1, proc.returncode, proc.stdout)
        self.assertIn("✗", proc.stdout)
        self.assertTrue("改动过" in proc.stdout or "不一致" in proc.stdout, proc.stdout)

    def test_all_skips_dirs_without_run_json(self):
        workspace, _run_dir = self._make_run()
        (workspace / "legacy_20260101").mkdir()       # B9 接线前的旧目录
        proc = run_cli("--json", "verify", "run", "--all", "--workspace", str(workspace))
        self.assertEqual(0, proc.returncode, proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertEqual(1, payload["count"])
        self.assertEqual(1, payload["ok_count"])

    def test_non_run_directory_fails_closed(self):
        workspace = Path(self.tmp.name) / "ws"
        workspace.mkdir(exist_ok=True)
        (workspace / "not_a_run").mkdir()
        proc = run_cli("verify", "run", "not_a_run", "--workspace", str(workspace))
        self.assertEqual(1, proc.returncode, proc.stdout)
        self.assertIn("run.json", proc.stderr)


class VerifyArtifactsTest(unittest.TestCase):
    """``verify artifacts``：出库索引对账（判据取 backend.policy_artifacts.verify_artifacts）。"""

    def _indexed(self, tmp: str) -> Path:
        from backend import policy_artifacts as pa

        root = Path(tmp) / "robots"
        out = Path(tmp) / "policies"
        package = root / "go2"
        (package / "simulation" / "policies").mkdir(parents=True)
        (package / "simulation" / "policies" / "walk.onnx").write_bytes(b"onnx-bytes-0123456789")
        (package / "simulation" / "config.json").write_text(json.dumps({"policies": [{
            "id": "walk-100", "path": "simulation/policies/walk.onnx", "label": "Walk",
            "obs_dim": 48, "action_dim": 12, "history_len": 1, "task_type": "velocity",
            "source": "builtin-package",
            "contract": {"observation_kind": "go2_velocity", "action_scale": 0.25},
        }]}, ensure_ascii=False), encoding="utf-8")
        pa.build_all(robots_dir=root, out_dir=out, write=True)
        return out

    def test_healthy_index_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._indexed(tmp)
            proc = run_cli("verify", "artifacts", "--out-dir", str(out), "--robots-dir", str(Path(tmp) / "robots"))
            self.assertEqual(0, proc.returncode, proc.stdout)
            self.assertIn("✓ 通过", proc.stdout)

    def test_changed_onnx_is_rejected(self):
        """包内 onnx 被换掉 → 索引里的 hash 立刻不符（出库最怕的"悄悄漂移"）。"""

        with tempfile.TemporaryDirectory() as tmp:
            out = self._indexed(tmp)
            (Path(tmp) / "robots" / "go2" / "simulation" / "policies" / "walk.onnx").write_bytes(b"tampered")
            proc = run_cli("--json", "verify", "artifacts", "--out-dir", str(out), "--robots-dir", str(Path(tmp) / "robots"))
            self.assertEqual(1, proc.returncode, proc.stdout)
            payload = json.loads(proc.stdout)
            self.assertFalse(payload["ok"])
            self.assertTrue(any("重新出库" in item for item in payload["problems"]), payload["problems"])


class OfflineModeTest(unittest.TestCase):
    """``--offline``：离线命令照跑；需后端的命令**如实拒绝**（不静默跳过）。"""

    def test_offline_allows_offline_commands(self):
        proc = run_cli("--offline", "pack", "list")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("汇总", proc.stdout)

    def test_offline_refuses_backend_commands(self):
        proc = run_cli("--offline", "train", "list")
        self.assertEqual(1, proc.returncode, proc.stdout)
        self.assertIn("--offline", proc.stderr)
        self.assertIn("需后端", proc.stderr)

    def test_help_documents_offline_semantics(self):
        proc = run_cli("--help")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("--offline", proc.stdout)
        for name in ("onboard", "verify"):
            self.assertIn(name, proc.stdout)


if __name__ == "__main__":
    unittest.main()
