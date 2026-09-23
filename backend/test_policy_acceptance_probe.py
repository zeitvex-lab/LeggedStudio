"""开环探针（preflight acceptance probe）的**策略条目解析与动作空间守卫**。

背景（B25，2026-09-16）：GPU 冒烟（microduck-standup-flat，**该机型已于 2026-09-23 族架构
收敛时删除，本条背景留作历史叙述**）的
native_preflight.json 出现 ``acceptance_probe_error: IndexError: index 0 is
out of bounds for axis 0 with size 0``。取证结论：

* worker 训练链从不携带策略条目（``config["policy"]`` 恒缺位，training_config.json
  无此键）；而包级 ``policy_contract`` 只在 g1/go2w/zex-w/tron1 声明了
  obs_dim/action_dim，microduck/go1/go2 等包的维度只在 ``policies[]`` 各条目顶层；
* 条目缺位 → ``PackageContract.action_dim`` 落 0 → ``run_probe`` 拿空动作数组按
  14 项关节序取 ``raw[0]`` → 裸 IndexError（探针报错不阻断训练，但监控页每次
  冒烟都带脏字段）。

修复语义（这里守五件事）：

1. ``resolve_probe_policy_entry``：条目缺位时从包内声明解析——优先
   ``training_ref.profile`` 对上训练 profile 的条目，否则第一条（与 CLI
   ``--probe`` 同口径）；
2. ``PackageContract``：action_dim 未声明时按动作关节序派生（动作槽与关节序
   语义同源）；已声明的值仍是唯一真值，不静默改写；
3. ``run_probe`` fail-closed：动作空间缺失/自相矛盾给**中文明确原因**（V4：
   报错而不是猜），守卫在 mujoco import 之前——控制面 venv 可直接测；
4. 全仓不变量：任意包 + 空条目，``action_dim == len(action_joint_order)``；
5. 端到端（mjlab 适配器 venv 子进程）：``--probe`` 出 JSON 结果，不再抛 IndexError
   （原用例跑 microduck，2026-09-23 该机型删除后改用 deeprobotics_m20 —— 被判据
   覆盖的机制没变：真实包 + 空条目下动作空间不得落 0）。
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: mjlab 适配器 venv（有 mujoco/onnxruntime）；不存在（如精简 CI）则跳过端到端用例。
_MJLAB_PYTHON = ROOT / "adapters" / "mjlab" / ".venv" / "Scripts" / "python.exe"


def load_engine():
    """按文件位置加载 ``policy_acceptance``（它不是包成员；顶层只依赖 numpy）。"""
    spec = importlib.util.spec_from_file_location(
        "policy_acceptance_for_probe_test",
        ROOT / "adapters" / "mjlab" / "policy_acceptance.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_worker():
    """控制面 venv 直接导入 native_worker（顶层仅 stdlib，见 test_training_episode_override）。"""
    from adapters.mjlab.native_worker import _probe_policy_entry

    return _probe_policy_entry


class _StubContract:
    """只带 run_probe 守卫所需字段的契约替身（守卫在 mujoco import 前，无需物理引擎）。"""

    def __init__(self, action_dim, order, name="ghost"):
        self.action_dim = action_dim
        self.action_joint_order = list(order)
        self.root = Path(name)


class ResolveProbePolicyEntryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        cls.engine = load_engine()

    def _sim_cfg(self, pkg: str) -> dict:
        return json.loads(
            (ROOT / "assets" / "robots" / pkg / "simulation" / "config.json").read_text(encoding="utf-8-sig")
        )

    # ---------- 真实包数据 ----------

    def test_m20_profile_match(self):
        """m20：训练 profile 精确对上自己的声明条目（B25 的两条声明共用 profile 的对条口径）。"""
        entry = self.engine.resolve_probe_policy_entry(
            self._sim_cfg("deeprobotics_m20"), "m20-velocity"
        )
        self.assertEqual("m20-velocity-57", entry.get("id"))
        self.assertEqual(57, entry.get("obs_dim"))
        self.assertEqual(16, entry.get("action_dim"))

    def test_go2_profile_match(self):
        """go2：声明多条时按 training_ref.profile 对条（此前同族裸 IndexError 包）。"""
        entry = self.engine.resolve_probe_policy_entry(
            self._sim_cfg("unitree_go2"), "go2-velocity-flat"
        )
        self.assertIsNotNone(entry.get("id"))
        ref = (entry.get("training_ref") or {}).get("profile")
        self.assertEqual("go2-velocity-flat", ref)

    def test_unknown_profile_falls_back_to_first(self):
        """profile 对不上任何声明 → 第一条（与 CLI --probe「只提供物理口径」同语义）。"""
        sim = self._sim_cfg("unitree_go2")
        first = next(p for p in sim["policies"] if isinstance(p, dict))
        entry = self.engine.resolve_probe_policy_entry(sim, "no-such-profile")
        self.assertEqual(first.get("id"), entry.get("id"))

    def test_no_profile_falls_back_to_first(self):
        """generic 任务（无 profile_id）→ 第一条声明。"""
        sim = self._sim_cfg("unitree_go2")
        first = next(p for p in sim["policies"] if isinstance(p, dict))
        self.assertEqual(first.get("id"), self.engine.resolve_probe_policy_entry(sim).get("id"))

    def test_no_policies_returns_empty_dict(self):
        """包内没有任何声明 → 空 dict，由 run_probe 守卫 fail-closed（不猜）。"""
        self.assertEqual({}, self.engine.resolve_probe_policy_entry({"policies": ["junk", None]}))
        self.assertEqual({}, self.engine.resolve_probe_policy_entry({}))


class PackageContractActionDimTest(unittest.TestCase):
    """B25 不变量：条目缺位时 action_dim 不得落 0（按关节序派生）；声明值仍是真值。"""

    @classmethod
    def setUpClass(cls):
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        cls.engine = load_engine()

    def _contract(self, pkg: str, entry: dict):
        return self.engine.PackageContract(ROOT / "assets" / "robots" / pkg, entry)

    def test_empty_entry_never_yields_zero_action_dim_any_package(self):
        """全仓扫描：空条目（= 训练链现状）下 action_dim == 动作关节序长度 > 0。

        这是 B25 崩溃形态的直接反例（microduck 曾是 0 vs 14 → raw[0] IndexError；
        该机型已删除，判据本身与机型无关，照旧全仓扫）。
        """
        robots = ROOT / "assets" / "robots"
        checked = 0
        for pkg in sorted(robots.iterdir()):
            if not (pkg / "simulation" / "config.json").is_file():
                continue
            contract = self._contract(pkg.name, {})
            self.assertEqual(
                len(contract.action_joint_order), contract.action_dim,
                f"{pkg.name}: 空条目下 action_dim({contract.action_dim}) ≠ 关节序({len(contract.action_joint_order)})",
            )
            self.assertGreater(contract.action_dim, 0, f"{pkg.name}: 动作空间为空，探针应 fail-closed")
            checked += 1
        self.assertGreaterEqual(checked, 8, "前置失效：8 个内置包都应被扫到")

    def test_declared_action_dim_wins_over_derivation(self):
        """已声明的值不被派生改写：go2w 包级声明 16/53，空条目下原样保留。"""
        contract = self._contract("unitree_go2w", {})
        self.assertEqual(16, contract.action_dim)
        self.assertEqual(53, contract.obs_dim)

    def test_entry_declared_dims_fill_obs_dim(self):
        """m20 + 训练同款条目：obs_dim/action_dim 与声明一致（57/16）。"""
        sim = json.loads(
            (ROOT / "assets" / "robots" / "deeprobotics_m20" / "simulation" / "config.json").read_text(encoding="utf-8-sig")
        )
        entry = self.engine.resolve_probe_policy_entry(sim, "m20-velocity")
        contract = self.engine.PackageContract(ROOT / "assets" / "robots" / "deeprobotics_m20", entry)
        self.assertEqual((57, 16), (contract.obs_dim, contract.action_dim))


class RunProbeGuardTest(unittest.TestCase):
    """fail-closed 守卫：声明缺失/自相矛盾 → 中文明确原因，不再是裸 IndexError。"""

    @classmethod
    def setUpClass(cls):
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        cls.engine = load_engine()

    def test_missing_action_space_raises_with_reason(self):
        stub = _StubContract(0, [])
        with self.assertRaises(ValueError) as ctx:
            self.engine.run_probe(stub, None, None, None)
        msg = str(ctx.exception)
        self.assertIn("无法开环探测", msg)
        self.assertIn("action_dim=0", msg)
        self.assertIn("ghost", msg)  # 报出包名，方便定位是哪台机器人的契约

    def test_order_larger_than_action_dim_raises(self):
        """关节序 5 项 > 声明 3：B25 的 IndexError 形态，现在给明确原因。"""
        stub = _StubContract(3, ["a", "b", "c", "d", "e"])
        with self.assertRaises(ValueError) as ctx:
            self.engine.run_probe(stub, None, None, None)
        self.assertIn("自相矛盾", str(ctx.exception))
        self.assertIn("action_dim=3", str(ctx.exception))


class WorkerProbePolicyEntryTest(unittest.TestCase):
    """worker 侧条目解析：显式条目透传，缺位时走包内声明解析。"""

    @classmethod
    def setUpClass(cls):
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        # staticmethod：普通函数挂在类上会被实例访问绑定成方法，多出一个 self。
        cls.resolve = staticmethod(load_worker())

    def test_profile_id_resolves_declared_entry(self):
        pkg = ROOT / "assets" / "robots" / "deeprobotics_m20"
        entry = self.resolve(pkg, {"profile_id": "m20-velocity"})
        self.assertEqual("m20-velocity-57", entry.get("id"))

    def test_explicit_config_policy_passthrough(self):
        """上游显式给了条目（config["policy"]）→ 原样使用，不覆盖。"""
        pkg = ROOT / "assets" / "robots" / "deeprobotics_m20"
        entry = self.resolve(pkg, {"policy": {"id": "custom", "action_dim": 7}})
        self.assertEqual(("custom", 7), (entry.get("id"), entry.get("action_dim")))


@unittest.skipUnless(_MJLAB_PYTHON.is_file(), "mjlab 适配器 venv 不存在，跳过 mujoco 端到端")
class M20ProbeEndToEndTest(unittest.TestCase):
    """端到端（mjlab venv 子进程）：deeprobotics_m20 --probe 出 JSON 结果，不再裸 IndexError。

    跑真实物理（编译包内 robot.xml + 开环扫包络），守住 B25 的验收口径：
    "run_probe 对真实包必须能出结果，不允许再抛 IndexError"（原用例跑 microduck，
    2026-09-23 族架构收敛删除该机型后改用 m20）。
    """

    def test_cli_probe_produces_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "probe.json"
            proc = subprocess.run(
                [str(_MJLAB_PYTHON), str(ROOT / "adapters" / "mjlab" / "policy_acceptance.py"),
                 "--package", str(ROOT / "assets" / "robots" / "deeprobotics_m20"),
                 "--probe", "--seconds", "1", "--output", str(out)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                cwd=str(ROOT), timeout=240,
            )
            combined = (proc.stdout or "") + (proc.stderr or "")
            self.assertEqual(0, proc.returncode, f"探针进程失败:\n{combined[-2000:]}")
            self.assertNotIn("IndexError", combined)
            report = json.loads(out.read_text(encoding="utf-8-sig"))
            self.assertEqual("policy-probe-1.0", report.get("schema"))
            self.assertIn(report.get("verdict"), ("pass", "warn"))
            self.assertEqual(9, len(report.get("results") or []), "9 个幅值档位都应有结果")


if __name__ == "__main__":
    unittest.main()
