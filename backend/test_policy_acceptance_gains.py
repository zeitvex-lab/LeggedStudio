"""PD 增益的**单一真值回落链**与"零增益即报错"（2026-09-22）。

## 背景（要记住的那次事故）

go2 包一度有 **8 条策略"零力矩"**：契约链一条都取不到 `stiffness/damping`，而
`gain_for()` 查不到就兜底 **0.0** —— 在 `actuator_interface="torque"` 下
``torque = (target − q)·0 − dq·0 = 0`` ⇒ **腿完全不支撑**：机器人笔直下坠、
且对观测/历史的任何改动毫无反应（与"翻倒"的区别是倾角几乎为零）。
后果不只是"看着不对"：这 8 条里有 7 条是 LainLab 技能族，它们在行为级验收上
长期 `fail`，被误读成"策略/观测有问题"，实际根因只是"没把增益再写一遍"。

## 这里守三件事

1. **回落链**（策略 `contract.control` > 策略 `contract.stiffness` > 包级
   `simulation.control` > **机器人 `contract.json` 的 `actuator_profile.by_role`**）：
   部署所需的一切本来就在机器人契约里（`joints.actuated` 的 `role` +
   `joints.default_pose` + `actuator_profile.by_role`），新增策略只该声明
   "真正与机器人不同的东西"——否则每来一族就要人肉对齐一次，且漏写静默变 0。
2. **`default_for` 同链**：策略不声明 `default_joint_angles` 时继承机器人契约的
   `joints.default_pose`（消掉逐条重写 12 个角的重复）。
3. **fail-closed**：torque 接口下，任一**位置控制**关节的 kp 解析为 0 ⇒ 构造即抛
   （`ValueError`，中文指名关节与补齐处）。**参数缺失不许静默降级成物理错误**。

不依赖 mujoco：`PackageContract.__init__` 只读 JSON（物理引擎在函数内才 import）。
"""

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GO2 = ROOT / "assets" / "robots" / "unitree_go2"


def load_engine():
    spec = importlib.util.spec_from_file_location(
        "policy_acceptance_for_gains_test", ROOT / "adapters" / "mjlab" / "policy_acceptance.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _policy_entry(pid="t-runner", contract=None, **extra):
    entry = {"id": pid, "contract": dict(contract or {})}
    entry.update(extra)
    return entry


class GainResolutionChainTest(unittest.TestCase):
    """回落链：三级来源 + 优先级 + 姿态继承 + fail-closed。"""

    @classmethod
    def setUpClass(cls):
        cls.engine = load_engine()

    def setUp(self):
        # 真包目录会被 ``PackageContract`` 整个读（config.json + contract.json），故用临时包：
        # 拷一份**真实** unitree_go2 contract.json（含 actuator_profile.by_role 单真值），
        # config.json 按用例现场写。
        self._tmp = tempfile.TemporaryDirectory()
        self.pkg = Path(self._tmp.name) / "unitree_go2"
        (self.pkg / "simulation").mkdir(parents=True)
        shutil.copyfile(GO2 / "contract.json", self.pkg / "contract.json")

    def tearDown(self):
        self._tmp.cleanup()

    def _write_sim(self, policies, **top):
        cfg = {"schema_version": "robot-simulation-1.0", "policies": policies}
        cfg.update(top)
        (self.pkg / "simulation" / "config.json").write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8-sig"
        )

    def _strip_robot_actuator_profile(self):
        """把机器人契约里的 `actuator_profile` 抽掉（模拟"哪儿都没声明增益"）。"""
        rc = json.loads((self.pkg / "contract.json").read_text(encoding="utf-8-sig"))
        rc.pop("actuator_profile", None)
        (self.pkg / "contract.json").write_text(
            json.dumps(rc, ensure_ascii=False, indent=2), encoding="utf-8-sig"
        )

    def _contract(self, entry):
        return self.engine.PackageContract(self.pkg, entry)

    # ---------- ① 机器人契约兜底（本次事故的正主：不写增益也不该变 0） ----------

    def test_robot_contract_gains_apply_when_policy_silent(self):
        self._write_sim([_policy_entry()])
        c = self._contract(_policy_entry())
        for joint in ("FL_hip_joint", "RL_thigh_joint", "FR_calf_joint"):
            self.assertEqual(20.0, c.gain_for(c.stiffness, joint), joint)
            self.assertEqual(0.5, c.gain_for(c.damping, joint), joint)

    def test_robot_contract_default_pose_inherited(self):
        """不声明 `default_joint_angles` ⇒ 继承 `joints.default_pose`（go2 = 前 0.8 后 1.0, 小腿 −1.5）。"""
        self._write_sim([_policy_entry()])
        c = self._contract(_policy_entry())
        self.assertAlmostEqual(0.1, c.default_for("FL_hip_joint"), places=6)
        self.assertAlmostEqual(0.8, c.default_for("FL_thigh_joint"), places=6)
        self.assertAlmostEqual(1.0, c.default_for("RL_thigh_joint"), places=6)
        self.assertAlmostEqual(-1.5, c.default_for("RR_calf_joint"), places=6)

    # ---------- ② 优先级：策略 > 包级 > 机器人契约 ----------

    def test_package_control_overrides_robot_contract(self):
        self._write_sim(
            [_policy_entry()],
            control={"stiffness": {"calf": 40.0}, "damping": {"calf": 2.0}},
        )
        c = self._contract(_policy_entry())
        self.assertEqual(40.0, c.gain_for(c.stiffness, "FL_calf_joint"))
        self.assertEqual(2.0, c.gain_for(c.damping, "FL_calf_joint"))
        # 未在包级声明的角色仍回落机器人契约
        self.assertEqual(20.0, c.gain_for(c.stiffness, "FL_hip_joint"))

    def test_policy_control_overrides_package_control(self):
        self._write_sim(
            [_policy_entry(contract={"control": {"stiffness": {"thigh": 25.0}}})],
            control={"stiffness": {"thigh": 40.0}},
        )
        c = self._contract(_policy_entry(contract={"control": {"stiffness": {"thigh": 25.0}}}))
        self.assertEqual(25.0, c.gain_for(c.stiffness, "FL_thigh_joint"))

    # ---------- ③ fail-closed：哪儿都查不到 ⇒ 当场炸，不静默跑成零力矩 ----------

    def test_zero_gains_raise_instead_of_silent_limp(self):
        # 抽掉机器人契约的 actuator_profile（保留 joints.actuated ⇒ 动作关节序仍可解析）
        # ⇒ 三级来源全空
        self._strip_robot_actuator_profile()
        self._write_sim([_policy_entry()], actuator_interface="torque")
        with self.assertRaises(ValueError) as ctx:
            self._contract(_policy_entry())
        msg = str(ctx.exception)
        self.assertIn("PD 增益解析为 0", msg)
        self.assertIn("零力矩", msg)

    def test_position_target_interface_not_gated(self):
        """非 torque 接口（PD 由 MJCF 的 kp/kv 决定）不该被这条守卫拦下。"""
        self._strip_robot_actuator_profile()
        self._write_sim([_policy_entry()], actuator_interface="position_target")
        c = self._contract(_policy_entry())  # 不抛即通过
        self.assertEqual("position_target", c.actuator_interface)


class RepoWideGainInvariantTest(unittest.TestCase):
    """全仓不变量：**任何包的任何策略**构造时都不该因零增益抛错（已全部接上真值）。"""

    @classmethod
    def setUpClass(cls):
        cls.engine = load_engine()

    def test_audit_matches_engine_gain_chain(self):
        """审计（`tools/audit_policy_gains.py`）与运行时（引擎）**逐关节同值**。

        审计刻意保留独立实现（不共享 bug），代价是"链的形状"必须逐字同步——本测试就是那份
        契约：任何一侧加/减一级、或改动优先级，这里立刻红。真实包全量对账，不构造假数据。
        """
        spec = importlib.util.spec_from_file_location(
            "audit_policy_gains_for_test", ROOT / "tools" / "audit_policy_gains.py"
        )
        audit_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit_mod)

        checked = 0
        for pkg_dir in sorted((ROOT / "assets" / "robots").iterdir()):
            sim_path = pkg_dir / "simulation" / "config.json"
            if not sim_path.is_file():
                continue
            sim = json.loads(sim_path.read_text(encoding="utf-8-sig"))
            profile = audit_mod._contract_profile(pkg_dir)
            robot_s = {j: p["stiffness"] for j, p in profile.items() if p.get("stiffness") is not None}
            robot_d = {j: p["damping"] for j, p in profile.items() if p.get("damping") is not None}
            for section in ("policies", "demo_policies"):
                for entry in sim.get(section) or []:
                    if not isinstance(entry, dict) or not entry.get("id"):
                        continue
                    contract = entry.get("contract") or {}
                    order = (contract.get("action_joint_order")
                             or sim.get("action_joint_order") or [])
                    tool_s, tool_d = audit_mod.resolve_gains(contract, sim, robot_s, robot_d)
                    try:
                        c = self.engine.PackageContract(pkg_dir, entry)
                    except ValueError:
                        continue      # 零增益包由上面的不变量测试负责
                    order = order or c.action_joint_order
                    for joint in order:
                        self.assertAlmostEqual(
                            c.gain_for(c.stiffness, joint),
                            audit_mod.gain_for(tool_s, joint), places=6,
                            msg=f"{pkg_dir.name}/{entry['id']} stiffness {joint}",
                        )
                        self.assertAlmostEqual(
                            c.gain_for(c.damping, joint),
                            audit_mod.gain_for(tool_d, joint), places=6,
                            msg=f"{pkg_dir.name}/{entry['id']} damping {joint}",
                        )
                    checked += 1
        # family-arch 收敛（14 → 8 机型）后真实对账样本为 43 条策略；下限随实际收敛
        # 重标定，仍保留"样本太少 ⇒ 循环没跑全"的守卫意图。
        self.assertGreater(checked, 40, "对账样本太少（8 机型实际 43 条），覆盖面不足")

    def test_all_declared_policies_resolve_gains(self):
        bad = []
        for pkg_dir in sorted((ROOT / "assets" / "robots").iterdir()):
            sim_path = pkg_dir / "simulation" / "config.json"
            if not sim_path.is_file():
                continue
            sim = json.loads(sim_path.read_text(encoding="utf-8-sig"))
            for section in ("policies", "demo_policies"):
                for entry in sim.get(section) or []:
                    if not isinstance(entry, dict) or not entry.get("id"):
                        continue
                    try:
                        self.engine.PackageContract(pkg_dir, entry)
                    except ValueError as exc:  # 只关心"零增益"这一类
                        if "PD 增益解析为 0" in str(exc):
                            bad.append(f"{pkg_dir.name}/{entry['id']}")
                    except Exception:  # noqa: BLE001 —— 其它异常不属本测试范围
                        pass
        self.assertEqual([], bad, f"以下策略仍未接上 PD 增益真值：{bad}")


if __name__ == "__main__":
    unittest.main()
