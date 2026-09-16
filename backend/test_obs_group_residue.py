"""B37：观测组名 / mjlab API 残留门禁的契约。

守三件事：
1. **真仓 14 个机型包全绿**（残留已清）；
2. **门禁不是摆设**：注入"断链配置"必须判红、注入"已删符号"必须判红；
3. **自洽写法不许误判**：`obs_groups={"actor": ("policy",)}` + env 定义了 `"policy"` 组是**能跑的**，
   判红就是误报 —— 门禁第一版正是这么错的，所以这条要钉死。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import audit_obs_group_names as gate  # noqa: E402


def _make_package(root: Path, robot: str, env_cfg: str, runner_cfg: str = "") -> None:
    """在临时根下造一个机型的训练源码包（结构同 assets/robots/<机型>/training/source）。"""

    source = root / "assets" / "robots" / robot / "training" / "source" / "pkg"
    source.mkdir(parents=True, exist_ok=True)
    (source / "env_cfg.py").write_text(env_cfg, encoding="utf-8")
    if runner_cfg:
        (source / "runner_cfg.py").write_text(runner_cfg, encoding="utf-8")


class RealRepoIsCleanTest(unittest.TestCase):
    def test_all_robot_packages_are_clean(self):
        report = gate.audit()
        self.assertTrue(report["ok"], report["errors"])
        self.assertGreaterEqual(len(report["packages"]), 14, "机型包数量不对（门禁可能找错了目录）")
        self.assertIn("microduck", report["packages"])
        self.assertIn("zex-w", report["packages"])

    def test_gate_says_it_does_not_run_mjlab(self):
        """边界要写在报告里：静态扫描 ≠ 任务能跑。"""

        self.assertFalse(gate.audit()["runs_mjlab"])


class InjectedCounterExampleTest(unittest.TestCase):
    """反例注入：门禁必须抓得住，否则它就是摆设。"""

    def test_broken_mapping_is_caught(self):
        """env 只有 "policy" 组 + runner 无 obs_groups ⇒ 默认 actor→('actor',) 找不到 ⇒ 判红。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_package(
                root, "fake_robot",
                '    observations = {\n        "policy": ObservationGroupCfg(terms={}),\n    }\n',
                "Cfg = RslRlOnPolicyRunnerCfg(\n    seed=1,\n)\n",
            )
            report = gate.audit(root)
            self.assertFalse(report["ok"], "断链配置没被抓到")
            kinds = {error["kind"] for error in report["errors"]}
            self.assertIn("broken-group-mapping", kinds)

    def test_removed_symbol_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_package(
                root, "fake_robot",
                '    observations = {\n        "actor": ObservationGroupCfg(terms={}),\n    }\n',
                "Cfg = RslRlOnPolicyRunnerCfg(\n    policy=RslRlPpoActorCriticCfg(init_noise_std=1.0),\n)\n",
            )
            report = gate.audit(root)
            self.assertFalse(report["ok"])
            self.assertIn("removed-symbol", {error["kind"] for error in report["errors"]})

    def test_self_consistent_policy_mapping_is_not_flagged(self):
        """**第一版规则踩的坑**：env 定义 "policy" 组 + 显式映射 actor→('policy',) 是自洽的，不许判红。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_package(
                root, "wuji_like",
                '    observations = {\n        "policy": ObservationGroupCfg(terms={}),\n'
                '        "critic": ObservationGroupCfg(terms={}),\n    }\n',
                'Cfg = RslRlOnPolicyRunnerCfg(\n    obs_groups={"actor": ("policy",), "critic": ("critic",)},\n)\n',
            )
            report = gate.audit(root)
            self.assertTrue(report["ok"], f"自洽写法被误判为残留：{report['errors']}")


class LandedFixesTest(unittest.TestCase):
    """三处 B37 修复必须真在文件里（防回退）。"""

    def test_microduck_uses_actor_group_and_new_api(self):
        path = ROOT / "assets/robots/microduck/training/source/mjlab_microduck/tasks/testbench_env_cfg.py"
        text = path.read_text(encoding="utf-8")
        # 只查**代码行**：注释里提到"某类已不存在"是正常的（门禁也是这个口径）
        code_lines = [line for line in text.splitlines() if not line.strip().startswith("#")]
        offenders = [line for line in code_lines if "RslRlPpoActorCriticCfg" in line]
        self.assertEqual(offenders, [], f"mjlab 1.6 已无此类，代码里不许再引用：{offenders}")
        self.assertIn('"actor": ObservationGroupCfg(', text)
        self.assertIn("actor=RslRlModelCfg(", text)
        self.assertIn("critic=RslRlModelCfg(", text)

    def test_him_wrapper_is_dual_compatible(self):
        path = ROOT / "assets/robots/zex-w/training/source/robot/rsl_rl/wrappers/him_mjlab_vec_env_wrapper.py"
        text = path.read_text(encoding="utf-8")
        self.assertIn('if "actor" in _groups:', text)
        self.assertIn('elif "policy" in _groups:', text)
        # 两者都没有时不许静默取空
        self.assertIn("raise RuntimeError", text)

    def test_microduck_symmetry_docstring_says_actor(self):
        path = ROOT / "assets/robots/microduck/training/source/mjlab_microduck/tasks/symmetry.py"
        text = path.read_text(encoding="utf-8")
        self.assertIn('keys ``"actor"`` and ``"critic"``', text)
        self.assertNotIn('keys ``"policy"`` and ``"critic"``', text)


if __name__ == "__main__":
    unittest.main()
