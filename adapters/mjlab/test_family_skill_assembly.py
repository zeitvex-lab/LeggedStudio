"""族级技能**通用装配**的回归锁：装配表是数据、新包零代码可用、能力缺口给精确原因。

守四件事：
1. 装配表（`skill_catalog`）读得出来且必备字段齐（缺项立即报，不静默给空）；
2. 成员机型的**通用装配 == 包内逐档档案**（解析等价：执行器目标集合相同）；
3. **一台全新包**（契约 + 标准位置 MJCF，零机型 Python）能装配出族级技能；
4. 不适用时 `try_build_family_skill_from_package` 返回 None（**不干预**既有流程），
   能力不足则报**具名**错（足端 site / IMU 传感器 / `_collision` 具名几何）。
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

try:
    import mjlab  # noqa: F401
    import mujoco  # noqa: F401
except ImportError as _exc:  # pragma: no cover
    raise unittest.SkipTest(f"训练栈不可用: {_exc}")

from adapters.mjlab import family_skill_builder as builder  # noqa: E402

B2 = ROOT / "assets" / "robots" / "unitree_b2"
GO2 = ROOT / "assets" / "robots" / "unitree_go2"
for _path in (str(B2), str(B2 / "training" / "source")):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def _b2_contract() -> dict:
    return json.loads((B2 / "contract.json").read_text(encoding="utf-8-sig"))


class CatalogTest(unittest.TestCase):
    def test_catalog_is_complete_data(self):
        catalog = builder.family_skill_catalog("quadruped")
        for task in ("velocity", "trot", "jump", "spring_jump", "backflip", "handstand", "leggedstand", "wtw"):
            self.assertIn(task, catalog)
            recipe = catalog[task]
            self.assertTrue(recipe.env.endswith("make_env_cfg") or ":make_env_cfg" in recipe.env)
            self.assertIn(":make_runner_cfg", recipe.runner)
            self.assertIn(":", recipe.profile)

    def test_unknown_family_is_loud(self):
        with self.assertRaises((ValueError, FileNotFoundError)):
            builder.family_skill_catalog("no_such_family")


class AssemblyEquivalenceTest(unittest.TestCase):
    """成员机型：通用装配与包内逐档档案**解析等价**。"""

    @classmethod
    def setUpClass(cls):
        cls.contract = _b2_contract()
        cls.model = B2 / "model" / "robot.xml"

    def test_generic_matches_profile_for_jump(self):
        from mjlab.entity import Entity

        # 出生高是**逐档档案唯一钉死的那个数**（源配方参数）：对拍时显式给同值，
        # 好让差异只剩"通用装配 vs 手写装配"本身。
        assembly = builder.build_family_skill(
            self.contract, self.model, "jump", family_id="quadruped", init_base_height=0.54
        )
        from b2_jump.config import make_b2_jump_env_cfg  # noqa: E402  (包内逐档档案)

        profile_cfg = make_b2_jump_env_cfg(play=False)

        def targets(cfg):
            entity = Entity(cfg.scene.entities["robot"])
            return sorted(name for actuator in entity.actuators for name in actuator.target_names)

        self.assertEqual(targets(profile_cfg), targets(assembly.env_cfg))
        self.assertEqual(profile_cfg.scene.num_envs, assembly.env_cfg.scene.num_envs)
        self.assertEqual(len(profile_cfg.rewards), len(assembly.env_cfg.rewards))

    def test_identity_and_height_are_derived(self):
        assembly = builder.build_family_skill(self.contract, self.model, "jump", family_id="quadruped")
        diagnostics = assembly.diagnostics
        self.assertEqual("unitree_b2", diagnostics["robot_id"])
        # 出生高按**默认姿 FK**推（站立高）；显式给值时以显式为准
        self.assertIn("默认姿 FK", diagnostics["init_height_source"])
        self.assertAlmostEqual(0.5115, diagnostics["init_base_height"], places=3)
        pinned = builder.build_family_skill(
            self.contract, self.model, "jump", family_id="quadruped", init_base_height=0.54
        )
        self.assertEqual("调用方显式给定", pinned.diagnostics["init_height_source"])
        self.assertEqual("base_link", diagnostics["binding_root_body"])
        self.assertEqual([0, 2], diagnostics["right_leg_indices"])


class SimSizingTest(unittest.TestCase):
    """sim 规模（接触/约束缓冲）是**装配表数据**，不是机型胶水。

    源配方里的 `nconmax=35` 是按 go2w 那台资产手调的缓冲值；换一台资产（b2w）就溢出
    （`nconmax overflow`）。族级装配声明 `sim_sizing`（None = 交给 mjwarp 按资产启发式定），
    于是新机型不需要为"缓冲区多大"写任何机型侧代码。
    """

    def test_wheel_leg_catalog_declares_heuristic_sizing(self):
        recipe = builder.family_skill_catalog("wheel_leg")["velocity"]
        self.assertEqual({"nconmax": None, "njmax": None}, recipe.sim_sizing)

    def test_quadruped_catalog_keeps_profile_sizing(self):
        # 四足族没有声明 ⇒ 沿用族 profile 自己的 sim 档（不被装配器改）
        for recipe in builder.family_skill_catalog("quadruped").values():
            self.assertEqual({}, recipe.sim_sizing)

    def test_declared_sizing_reaches_env_and_play_cfg(self):
        b2w = ROOT / "assets" / "robots" / "unitree_b2w"
        if not (b2w / "contract.json").is_file():
            self.skipTest("本机没有 b2w 资产")
        contract = json.loads((b2w / "contract.json").read_text(encoding="utf-8-sig"))
        assembly = builder.build_family_skill(
            contract, b2w / "model" / "robot.xml", "velocity", family_id="wheel_leg"
        )
        for cfg in (assembly.env_cfg, assembly.play_cfg):
            self.assertIsNone(cfg.sim.nconmax)
            self.assertIsNone(cfg.sim.njmax)
        self.assertEqual(
            {"nconmax": None, "njmax": None}, assembly.diagnostics["sim_sizing"]
        )


class CcdMarginTest(unittest.TestCase):
    """带非零 geom margin 的资产：族级装配也要按已登记口径条件关 MULTICCD/NATIVECCD。

    族注册表把这类资产登记为 `warp_ccd_off`（margin 是物理量，不抹）；此前只有
    `generic_task_builder` 那条路实现了这个口径，族级装配漏了 ⇒ go2w 真跑直接
    `NotImplementedError: geom pair (terrain_0, 559) has non-zero margin ... MULTICCD`。
    """

    def _assembly(self, robot: str, task: str, family: str):
        package = ROOT / "assets" / "robots" / robot
        if not (package / "contract.json").is_file():
            self.skipTest(f"本机没有 {robot} 资产")
        contract = json.loads((package / "contract.json").read_text(encoding="utf-8-sig"))
        return builder.build_family_skill(
            contract, package / "model" / "robot.xml", task, family_id=family
        )

    def test_margin_asset_disables_ccd_flags(self):
        assembly = self._assembly("unitree_go2w", "velocity", "wheel_leg")
        for cfg in (assembly.env_cfg, assembly.play_cfg):
            flags = tuple(cfg.sim.mujoco.disableflags)
            self.assertIn("multiccd", flags)
            self.assertIn("nativeccd", flags)
        self.assertEqual(
            ["multiccd", "nativeccd"], assembly.diagnostics["mujoco_disableflags"]
        )

    def test_zero_margin_asset_is_untouched(self):
        assembly = self._assembly("unitree_b2w", "velocity", "wheel_leg")
        self.assertEqual([], assembly.diagnostics["mujoco_disableflags"])
        self.assertEqual((), tuple(assembly.env_cfg.sim.mujoco.disableflags))


class TrainingAssetTest(unittest.TestCase):
    """训练资产由**包声明**（`model.training_path`），缺省就是 `model.path`。

    go2 包里有两份 MJCF：`model/robot.xml`（上游字节，几何名 `FL_thigh_geom`、无足端 site、
    default class 带 margin）与 `model/training.xml`（合族约定：`*_collision` 几何 +
    `FL_foot_collision` + 足端 site）。go2 所有既有训练路径用的都是后者
    （`local_tasks/mjlab_extension.py: GO2_XML = model/training.xml`），而装配器此前只看
    `model.path` ⇒ 拿上游那份去撞族约定（足端几何判红）。上游字节不改（那是忠实搬运的证据），
    改的是"哪份是训练资产"这条**包级声明**。
    """

    def test_declared_training_asset_wins(self):
        _contract, model, _used = builder.resolve_package_assets(GO2)
        self.assertEqual((GO2 / "model" / "training.xml").resolve(), model)

    def test_default_is_the_declared_model(self):
        _contract, model, _used = builder.resolve_package_assets(B2)
        self.assertEqual((B2 / "model" / "robot.xml").resolve(), model)

    def test_go2_family_skill_assembles_from_its_training_asset(self):
        contract, model, _used = builder.resolve_package_assets(GO2)
        assembly = builder.build_family_skill(contract, model, "velocity", family_id="quadruped")
        self.assertEqual(
            ["FL_foot_collision", "FR_foot_collision", "RL_foot_collision", "RR_foot_collision"],
            assembly.diagnostics["binding_foot_geoms"],
        )

    def test_go2_capabilities_are_measured_on_the_training_asset(self):
        contract, model, _used = builder.resolve_package_assets(GO2)
        items = builder.robot_capabilities(contract, model)["items"]
        self.assertTrue(items["foot_sites"]["ok"], items["foot_sites"]["detail"])
        self.assertTrue(items["named_collision_geoms"]["ok"])


class NewPackageTest(unittest.TestCase):
    """一台全新包（契约 + 标准位置 MJCF，零机型 Python）：装配得出来、缺能力报得清楚。"""

    @classmethod
    def setUpClass(cls):
        source = ROOT / "workspace" / "packages" / "imported_fsdog1_2f7de81ba2"
        if not source.is_dir():
            raise unittest.SkipTest("本机没有导入包夹具（workspace/packages/imported_fsdog1_*）")
        cls.tmp = Path(tempfile.mkdtemp(prefix="legged_newpkg_"))
        (cls.tmp / "model").mkdir(parents=True, exist_ok=True)
        shutil.copy(source / "contract.json", cls.tmp / "contract.json")
        xml = (source / "fsdog1.xml").read_text(encoding="utf-8")
        import re

        xml = re.sub(
            r'<motor name="([^"]+)" joint="([^"]+)"\s*/>',
            r'<position name="\1" joint="\2" kp="40" kv="1"/>',
            xml,
        )
        (cls.tmp / "model" / "robot.xml").write_text(xml, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_assets_are_resolved_from_the_standard_layout(self):
        contract, model, used = builder.resolve_package_assets(self.tmp)
        self.assertEqual("contract.json", used)
        self.assertEqual(self.tmp / "model" / "robot.xml", model)
        self.assertEqual(("quadruped",), builder.candidate_families(contract))

    def test_family_skill_assembles_without_robot_code(self):
        assembly = builder.try_build_family_skill_from_package(self.tmp, "jump")
        self.assertIsNotNone(assembly)
        self.assertEqual("jump", assembly.task_name)
        self.assertEqual("asset", assembly.diagnostics["binding_actuator_source"])

    def test_not_applicable_returns_none(self):
        # 任务不在任何族的装配表里 ⇒ 返回 None，让既有流程（generic / 报错）接管
        self.assertIsNone(builder.try_build_family_skill_from_package(self.tmp, "no_such_task"))

    def test_capability_gaps_are_named(self):
        capabilities = builder.robot_capabilities(
            json.loads((self.tmp / "contract.json").read_text(encoding="utf-8-sig")),
            self.tmp / "model" / "robot.xml",
        )
        items = capabilities["items"]
        self.assertFalse(items["foot_sites"]["ok"])       # 该夹具没有足端 site
        self.assertFalse(items["imu_sensors"]["ok"])      # 也没有 IMU 传感器
        # 执行器模式：契约声明 vs MJCF 实际的**对账**（该夹具已按标准写成 position ⇒ 一致）
        self.assertTrue(items["actuator_modes"]["ok"])
        # 依赖缺失能力的任务要报**具名**错（含缺哪条）
        with self.assertRaises(ValueError) as ctx:
            builder.build_family_skill(
                json.loads((self.tmp / "contract.json").read_text(encoding="utf-8-sig")),
                self.tmp / "model" / "robot.xml",
                "handstand",
                family_id="quadruped",
            )
        self.assertIn("foot_sites", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
