"""I1 收尾：``deploy gate`` / ``deploy package`` 两条离线命令测试。

## 这组测试守的是什么

部署 = 部署契约校验 + 部署包打包。CLI 两条命令都**不连后端**，判据/打包全部委托
backend 既有实现（``backend.export_gate.compare_contracts`` /
``backend.deploy_pack.generate_deploy_package``，与 Web 的 ``/api/deploy/*`` 同一实现）。
这里用 subprocess 真调 ``scripts/legged_studio_cli.py``（与用户用法完全一致），钉住：

1. **离线路径**：``--offline`` 下照常运行（deploy 属于离线命令家族）；
2. **成功路径**：真实机器人包（unitree_go2）打包出四件套 + 平台适配层，产物落
   ``--out`` 指定的临时目录（绝不污染真实 ``workspace/``）；契约一致的包 gate 通过；
3. **失败路径 fail-closed**：包内契约漂移（如 control_hz 被改）→ blocker + 退出码 1；
   未知机器人 / 缺 contract_truth → 如实报错、退出码非 0；
4. **当前真实数据的诚实结果**：内置包的 contract_truth 比 v2 丰富（observation.components /
   actuator_profile 是 v3 才有的声明），gate 必须**如实报 deny**（退出码 1），
   绝不为了"绿"编造通过。

fixture 说明：在**临时 workspace** 放一个名为 ``go2_gate_probe`` 的包副本（从内置
unitree_go2 拷三件 JSON）——目录名不与任何内置包同名，所以 ``backend.robot_packages``
的内容同步永远不会把它"治愈"回源树；而按 robot_id 去重时 workspace 副本优先于内置
assets 树，因此 ``deploy gate unitree_go2 --workspace <tmp>`` 解析到的就是这个可控副本。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CLI = ROOT / "scripts" / "legged_studio_cli.py"
#: 控制面 venv 的 python（测试正是跑在里面）；不存在则退回当前解释器。
_VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.is_file() else sys.executable

GO2 = "unitree_go2"
#: 部署包四件套（backend.deploy_pack 的核心产物）+ 平台适配层
DEPLOY_FOUR_PIECES = (
    "deployment-contract.yaml",
    "fsm_safety_template.py",
    "action_decoder_template.py",
    "人工确认清单.md",
)


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """以仓库根为 cwd 真调 CLI；强制 UTF-8，保证中文/JSON 在 Windows 管道下不乱码。

    与既有 CLI 测试的唯一差别：**摘掉**环境里可能残留的 ``LEGGED_STUDIO_WORKSPACE``，
    让"没传 --workspace"的用例确定性地解析仓库默认 workspace，不受外部环境污染。
    """

    env = {key: value for key, value in os.environ.items() if key != "LEGGED_STUDIO_WORKSPACE"}
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [PYTHON, str(CLI), *args],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(ROOT), env=env, timeout=180,
    )


def make_probe_workspace(base: Path, *, with_v3: bool = True) -> Path:
    """临时 workspace + 内置 go2 的包副本（robot_id 仍是 unitree_go2，目录名不同步治愈）。"""

    ws = base / "ws"
    probe = ws / "packages" / "go2_gate_probe"
    probe.mkdir(parents=True)
    source = ROOT / "assets" / "robots" / GO2
    for name in ("contract_legacy_v2.json", "robot_package.json"):
        shutil.copy2(source / name, probe / name)
    if with_v3:
        shutil.copy2(source / "contract.json", probe / "contract.json")
    return ws


class DeployHelpTest(unittest.TestCase):
    """命令契约：deploy 组与两个子命令的 --help 都写明「离线命令，无需后端」。"""

    def test_group_help_documents_offline_semantics(self):
        proc = run_cli("deploy", "--help")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("gate", proc.stdout)
        self.assertIn("package", proc.stdout)
        self.assertIn("离线命令", proc.stdout)

    def test_leaf_helps_document_offline_semantics(self):
        for leaf in ("gate", "package"):
            proc = run_cli("deploy", leaf, "--help")
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("离线命令，无需后端", proc.stdout)


class DeployGateTest(unittest.TestCase):
    """``deploy gate``：一致即过、漂移必红、格式边界如实降 warn 不误杀。"""

    def test_bundled_robot_schema_boundary_is_warn_not_deny(self):
        """内置包 v3 比 v2 丰富 ⇒ 格式边界降 warn（SCHEMA_BOUNDARY），不再误 deny。

        v2 快照（robot-contract-2.0）从未记录过 actuator_profile / dict 形 components
        ——缺这些字段是当时的 schema 装不下，不是"训练后契约被改"。v2 的 components
        段名表与 v3 段名序一致 ⇒ 按名比对放行。真正的漂移（值/名对不上、v3 侧缺
        v2 有值的字段）仍走 deny（见 test_tampered_control_hz_fails_with_blocker 等）。
        用**空临时 workspace** 让包根解析回落到内置 assets 树（确定性）。
        """

        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "empty_ws"
            ws.mkdir()
            proc = run_cli("deploy", "gate", GO2, "--workspace", str(ws))
            self.assertEqual(0, proc.returncode, proc.stdout)
            self.assertIn("✓ 通过", proc.stdout)
            # v3-only 字段缺失 → 格式边界 warn（CLI 打 reason 文本；basis=SCHEMA_BOUNDARY#* 在 API JSON 的 entries 里）
            self.assertIn("格式边界", proc.stdout)
            self.assertIn("actuator_profile", proc.stdout)
            self.assertNotIn("observation.components 不对称", proc.stdout)

    def test_v3_side_missing_field_still_denies(self):
        """v3 侧缺 v2 有值的字段（v3 本可携带）⇒ 仍 deny——格式边界豁免不外溢。

        把 probe 的 v3 contract.json 删掉 control.control_hz（imported_fsdog1 的
        真实欠账形态）：v3 schema 能记录却不记录 = 契约漂移，不是格式边界。
        """

        with tempfile.TemporaryDirectory() as tmp:
            ws = make_probe_workspace(Path(tmp))
            probe = ws / "packages" / "go2_gate_probe"
            payload = json.loads((probe / "contract.json").read_text(encoding="utf-8-sig"))
            del payload["control"]["control_hz"]
            (probe / "contract.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
            )
            proc = run_cli("deploy", "gate", GO2, "--workspace", str(ws))
            self.assertEqual(1, proc.returncode, proc.stdout)
            self.assertIn("不通过", proc.stdout)
            self.assertIn("control_hz", proc.stdout)

    def test_in_sync_package_passes(self):
        """v2 与 v3 一致的副本 ⇒ gate 通过（退出码 0）。"""

        with tempfile.TemporaryDirectory() as tmp:
            ws = make_probe_workspace(Path(tmp))
            probe = ws / "packages" / "go2_gate_probe"
            shutil.copy2(probe / "contract.json", probe / "contract_legacy_v2.json")  # legacy := truth
            proc = run_cli("deploy", "gate", GO2, "--workspace", str(ws))
            self.assertEqual(0, proc.returncode, proc.stdout)
            self.assertIn("✓ 通过", proc.stdout)

    def test_offline_flag_still_runs(self):
        """``--offline`` 下照常运行（deploy 是离线命令，不需要拒绝）。"""

        with tempfile.TemporaryDirectory() as tmp:
            ws = make_probe_workspace(Path(tmp))
            probe = ws / "packages" / "go2_gate_probe"
            shutil.copy2(probe / "contract.json", probe / "contract_legacy_v2.json")
            proc = run_cli("--offline", "deploy", "gate", GO2, "--workspace", str(ws))
            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            self.assertIn("✓ 通过", proc.stdout)

    def test_tampered_control_hz_fails_with_blocker(self):
        """副本的 v2 control_hz 被改 ⇒ 与 v3 不一致 → blocker + 退出码 1（fail-closed）。"""

        with tempfile.TemporaryDirectory() as tmp:
            ws = make_probe_workspace(Path(tmp))
            probe = ws / "packages" / "go2_gate_probe"
            payload = json.loads((probe / "contract_legacy_v2.json").read_text(encoding="utf-8-sig"))
            payload["control"]["control_hz"] = int(payload["control"].get("control_hz", 50)) + 7
            (probe / "contract_legacy_v2.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
            )
            proc = run_cli("deploy", "gate", GO2, "--workspace", str(ws))
            self.assertEqual(1, proc.returncode, proc.stdout)
            self.assertIn("不通过", proc.stdout)
            self.assertIn("control_hz", proc.stdout)

    def test_json_output_is_machine_readable(self):
        """--json：通过/不通过两种结局都可解析，robot_id / package_root / blockers 齐全。"""

        with tempfile.TemporaryDirectory() as tmp:
            ws = make_probe_workspace(Path(tmp))
            probe = ws / "packages" / "go2_gate_probe"
            shutil.copy2(probe / "contract.json", probe / "contract_legacy_v2.json")
            good = run_cli("--json", "deploy", "gate", GO2, "--workspace", str(ws))
            self.assertEqual(0, good.returncode, good.stdout)
            payload = json.loads(good.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(GO2, payload["robot_id"])
            self.assertIn("go2_gate_probe", payload["package_root"])
            self.assertEqual([], payload["blockers"])

            (probe / "contract_legacy_v2.json").write_text(
                json.dumps({"control": {"control_hz": 999}}, ensure_ascii=False), encoding="utf-8",
            )
            bad = run_cli("--json", "deploy", "gate", GO2, "--workspace", str(ws))
            self.assertEqual(1, bad.returncode, bad.stdout)
            broken = json.loads(bad.stdout)
            self.assertFalse(broken["ok"])
            self.assertTrue(broken["blockers"])
            self.assertTrue(any("control_hz" in item for item in broken["blockers"]))

    def test_unknown_robot_fails_honestly(self):
        proc = run_cli("deploy", "gate", "no_such_robot")
        self.assertEqual(1, proc.returncode, proc.stdout)
        self.assertIn("找不到机器人包", proc.stderr)
        self.assertIn("no_such_robot", proc.stderr)


class DeployPackageTest(unittest.TestCase):
    """``deploy package``：真实机器人包打包成功、产物落 --out 临时目录、失败如实非 0。"""

    def test_package_written_to_requested_out_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "deploy_out"
            proc = run_cli("deploy", "package", GO2, "--out", str(out))
            self.assertEqual(0, proc.returncode, proc.stderr)
            zips = list(out.glob("*.zip"))
            self.assertEqual(1, len(zips), f"应恰好落一个部署包：{zips}")
            names = set(zipfile.ZipFile(zips[0]).namelist())
            self.assertTrue(set(DEPLOY_FOUR_PIECES) <= names, names)
            self.assertIn("platform_adapter.py", names)
            self.assertIn(str(zips[0]), proc.stdout)
            self.assertIn("一键生成 ≠ 一键上机", proc.stdout)      # 安全边界必须随包说清

    def test_json_reports_path_and_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "deploy_out"
            proc = run_cli("--json", "deploy", "package", GO2, "--out", str(out))
            self.assertEqual(0, proc.returncode, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(GO2, payload["robot_id"])
            self.assertTrue(Path(payload["path"]).is_file())
            self.assertTrue(set(DEPLOY_FOUR_PIECES) <= set(payload["files"]))

    def test_flags_reach_the_artifact(self):
        """--platform/--bench/--degraded 真的传进 backend 打包（产物可验证，不是摆设）。"""

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "deploy_out"
            proc = run_cli("deploy", "package", GO2, "--out", str(out),
                           "--platform", "ros2", "--bench", "--degraded")
            self.assertEqual(0, proc.returncode, proc.stderr)
            with zipfile.ZipFile(next(out.glob("*.zip"))) as zf:
                names = set(zf.namelist())
                self.assertIn("d2_bench_test.py", names)                       # --bench
                adapter = zf.read("platform_adapter.py").decode("utf-8")
                contract_py = zf.read("deployment_contract.py").decode("utf-8")
            self.assertIn("ROS2Adapter", adapter)                              # --platform ros2
            # --degraded：力矩 ×0.8（go2 hip 23.7 → 18.96，与 backend 同一口径）
            self.assertIn("18.96", contract_py)

    def test_unknown_robot_fails_honestly(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_cli("deploy", "package", "no_such_robot", "--out", str(tmp))
            self.assertEqual(1, proc.returncode, proc.stdout)
            self.assertIn("deploy 失败", proc.stderr)
            self.assertIn("no_such_robot", proc.stderr)
            self.assertEqual([], list(Path(tmp).glob("*.zip")))                # 失败不落任何产物

    def test_missing_truth_contract_fails_closed(self):
        """副本缺 contract.json ⇒ backend 拒绝打包（一键生成不能建在不完整契约上）。"""

        with tempfile.TemporaryDirectory() as tmp:
            ws = make_probe_workspace(Path(tmp), with_v3=False)
            proc = run_cli("deploy", "package", GO2, "--workspace", str(ws), "--out", str(Path(tmp) / "out"))
            self.assertEqual(1, proc.returncode, proc.stdout)
            self.assertIn("contract", proc.stderr)
            self.assertFalse((Path(tmp) / "out").exists())

    def test_offline_flag_still_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "deploy_out"
            proc = run_cli("--offline", "deploy", "package", GO2, "--out", str(out))
            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            self.assertEqual(1, len(list(out.glob("*.zip"))))

    def test_policy_flag_is_carried_into_the_package(self):
        """``--policy <onnx>``：策略真进包（与 API 的 policy_onnx_path 同一实现）。"""

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "deploy_out"
            onnx = Path(tmp) / "policy.onnx"
            onnx.write_bytes(b"fake-onnx-bytes")
            proc = run_cli("deploy", "package", GO2, "--out", str(out), "--policy", str(onnx))
            self.assertEqual(0, proc.returncode, proc.stderr)
            with zipfile.ZipFile(next(out.glob("*.zip"))) as zf:
                self.assertIn("policy.onnx", zf.namelist())
                self.assertEqual(b"fake-onnx-bytes", zf.read("policy.onnx"))

    def test_missing_policy_fails_closed(self):
        """给了 --policy 而文件不存在 ⇒ 退出码 1、不落任何产物（不静默忽略）。"""

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "deploy_out"
            proc = run_cli("deploy", "package", GO2, "--out", str(out),
                           "--policy", str(Path(tmp) / "no_such.onnx"))
            self.assertEqual(1, proc.returncode, proc.stdout)
            self.assertIn("deploy 失败", proc.stderr)
            self.assertIn("no_such.onnx", proc.stderr)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
