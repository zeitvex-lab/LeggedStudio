"""L3：域随机化（E1–E8）—— 口径、边界，以及**验收判据本身**。

## 这组测试守的是什么

L3 最容易做成"我开了 DR"这种口号。三条可自动化的判据：

1. **term 表是声明**（名字/字段/算子/范围/模式写死在表里，不散落代码）；声明里给未知算子/
   分布/模式/目标 ⇒ **报错**，不静默忽略（静默忽略会让"我开了 DR"变成"我以为开了"）；
2. **开了要真的影响结果，且仍要可复现**：同 seed 两次**逐帧一致**（确定性不能因 DR 丢掉），
   换 seed **结果不同** —— 这正是 `tools/replay_gate.py --seed-probe` 的验收线，测试直接跑它；
3. **字段映射只有一处**（`field_array`）：`body/mass` 与 `body/ipos` 必须映射到不同数组
   —— 早先按 target 分派，`ipos` 拿到 1 维 mass、写 2 维时 IndexError（实测踩到）。
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "adapters" / "mjlab"
for path in (str(ROOT), str(ADAPTER)):
    if path not in sys.path:
        sys.path.insert(0, path)

import domain_randomization as dr  # noqa: E402


class TermTableTest(unittest.TestCase):
    def test_eight_terms_use_the_declared_vocabulary(self):
        self.assertEqual(8, len(dr.DEFAULT_TERMS), "E1–E8")
        for term in dr.DEFAULT_TERMS:
            self.assertIn(term.op, dr.OPS, term.name)
            self.assertIn(term.distribution, dr.DISTRIBUTIONS, term.name)
            self.assertIn(term.mode, dr.MODES, term.name)
            self.assertLessEqual(term.low, term.high, term.name)

    def test_sampling_respects_range_and_seed(self):
        rng = np.random.default_rng(0)
        for term in dr.DEFAULT_TERMS:
            if term.distribution == "gaussian":
                continue
            values = np.asarray([term.sample(rng) for _ in range(32)])
            self.assertGreaterEqual(values.min(), min(term.low, term.high) - 1e-9, term.name)
            self.assertLessEqual(values.max(), max(term.low, term.high) + 1e-9, term.name)
        first = [t.sample(np.random.default_rng(7)) for t in dr.DEFAULT_TERMS]
        self.assertEqual(first, [t.sample(np.random.default_rng(7)) for t in dr.DEFAULT_TERMS])
        self.assertNotEqual(first, [t.sample(np.random.default_rng(99)) for t in dr.DEFAULT_TERMS])

    def test_unknown_declaration_is_rejected_not_ignored(self):
        for bad in ({"target": "geom", "field": "friction", "op": "twist"},
                    {"target": "geom", "field": "friction", "distribution": "cauchy"},
                    {"target": "geom", "field": "friction", "mode": "whenever"},
                    {"target": "sky", "field": "friction"}):
            with self.assertRaises(ValueError, msg=str(bad)):
                dr.terms_from_config({"terms": [bad]})


class FieldMappingTest(unittest.TestCase):
    def test_each_field_maps_to_its_own_array(self):
        class Fake:
            geom_friction = "geom_friction"
            dof_armature = "dof_armature"
            dof_frictionloss = "dof_frictionloss"
            dof_damping = "dof_damping"
            body_mass = "body_mass"
            body_ipos = "body_ipos"

        fake = Fake()
        self.assertEqual("body_ipos", dr.field_array(fake, "body", "ipos"), "ipos 不能映射到 mass")
        self.assertEqual("body_mass", dr.field_array(fake, "body", "mass"))
        self.assertIsNone(dr.field_array(fake, "body", "inertia"), "未实现的字段返回 None，调用方记 skipped")


class ApplyOnRealModelTest(unittest.TestCase):
    """真模型：同 seed 同值（确定性）、换 seed 不同值（DR 生效）、scale 不连乘漂走。"""

    @classmethod
    def setUpClass(cls):
        try:
            import mujoco  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("没有 mujoco")
        cls.model_path = ROOT / "assets" / "robots" / "zex-w" / "model" / "robot.xml"
        if not cls.model_path.is_file():
            raise unittest.SkipTest("没有 zex-w 模型")

    def _run(self, seed: int, terms=None, repeats: int = 1) -> dict:
        import mujoco

        model = mujoco.MjModel.from_xml_path(str(self.model_path))
        data = mujoco.MjData(model)
        baseline = {
            "friction": np.array(model.geom_friction, copy=True),
            "armature": np.array(model.dof_armature, copy=True),
        }
        rng = np.random.default_rng(seed)
        # 备份要**跨调用复用**（生产路径 `frame_log` 就是这么传的）：scale 类算子基于
        # 出厂值采样；不传备份时每次调用都把"已改过的值"当基线 ⇒ 连乘漂走（这正是本测试要抓的）。
        backup: dict = {}
        report = None
        for _ in range(repeats):
            report = dr.apply(model, data, rng, terms=terms or dr.DEFAULT_TERMS, backup=backup)
        return {
            "report": report,
            "friction": np.array(model.geom_friction, copy=True),
            "armature": np.array(model.dof_armature, copy=True),
            "mass": np.array(model.body_mass, copy=True),
            "ipos": np.array(model.body_ipos, copy=True),
            "baseline": baseline,
        }

    def test_applies_the_declared_terms(self):
        result = self._run(7)
        names = {item["term"] for item in result["report"]["applied"] if not item.get("skipped")}
        for expected in ("E1-geom-friction", "E2-dof-armature", "E5-body-mass", "E6-body-ipos"):
            self.assertIn(expected, names, result["report"])

    def test_same_seed_identical_other_seed_differs(self):
        first, second, other = self._run(7), self._run(7), self._run(99)
        for field in ("friction", "armature", "mass", "ipos"):
            np.testing.assert_allclose(first[field], second[field], atol=0, err_msg=f"{field} 同 seed 不一致")
            self.assertFalse(np.allclose(first[field], other[field]),
                             f"{field} 换 seed 完全一样 ⇒ DR 没生效")

    def test_scale_operator_does_not_drift_across_resets(self):
        """scale 必须基于**出厂值**反复采样；基于上次结果会连乘漂走。"""

        armor_term = tuple(t for t in dr.DEFAULT_TERMS if t.name == "E2-dof-armature")
        result = self._run(11, terms=armor_term, repeats=5)
        baseline = result["baseline"]["armature"]
        # 只在**非零**关节上量比值：zex-w 有 6/22 个关节的 XML armature 是 0
        # （armature 由契约的关节常量表给定），0 基线做除法只会得到 0/0=nan，
        # 那时"漂没漂"根本量不出来 —— 这是测量口径问题，不是 DR 的问题。
        mask = baseline > 0
        self.assertGreater(int(mask.sum()), 0)
        ratio = result["armature"][mask] / baseline[mask]
        self.assertTrue(np.all(ratio > 0.7) and np.all(ratio < 1.3), f"连乘漂走：{ratio.min()}~{ratio.max()}")


class SeedProbeAcceptanceTest(unittest.TestCase):
    """**验收判据本身**：DR 关 ⇒ 换 seed 结果相同；DR 开 ⇒ 换 seed 结果不同（且仍确定性）。"""

    @classmethod
    def setUpClass(cls):
        cls.gate = ROOT / "tools" / "replay_gate.py"
        if not Path("/opt/legged-studio/mjlab-cpu/.venv/bin/python").is_file():
            raise unittest.SkipTest("适配器 venv 不在")
        if not (ROOT / "assets" / "robots" / "zex-w").is_dir():
            raise unittest.SkipTest("没有 zex-w 包")

    def _produce(self, *extra: str) -> dict:
        command = [sys.executable, str(self.gate), "--produce", "--json",
                   "--package", str(ROOT / "assets" / "robots" / "zex-w"),
                   "--policy-id", "zex-w-rough-9600", "--steps", "8", "--min-frames", "5",
                   "--seed-probe", "99", *extra]
        completed = subprocess.run(command, capture_output=True, text=True, cwd=str(ROOT))
        self.assertIn(completed.returncode, (0, 1), completed.stderr[-400:])
        return json.loads(completed.stdout)

    def test_domain_rand_off_means_seed_is_inert(self):
        summary = self._produce()
        self.assertEqual("pass", summary["determinism"]["verdict"])
        self.assertFalse(summary["seed_sensitivity"]["changed"])
        self.assertFalse(summary["seed_sensitivity"]["randomization_declared"])

    def test_domain_rand_on_flips_the_probe_but_keeps_determinism(self):
        summary = self._produce("--domain-rand")
        self.assertEqual("pass", summary["determinism"]["verdict"], "同 seed 两进程必须仍逐帧一致")
        self.assertTrue(summary["seed_sensitivity"]["changed"], "开了 DR 换 seed 必须影响结果")
        self.assertTrue(summary["seed_sensitivity"]["randomization_declared"])
        self.assertFalse(summary["seed_sensitivity"]["is_problem"])
        self.assertEqual("pass", summary["verdict"])


if __name__ == "__main__":
    unittest.main()
