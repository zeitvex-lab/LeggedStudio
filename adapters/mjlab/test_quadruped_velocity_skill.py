"""族级 velocity 技能（四足 Kit）的回归锁：真行为，不是"名字统一"。

覆盖四条判据（每条都对应一次真实的静默失效）：

1. **动作接口**：`joint_pos` 目标名序 == 契约 `action.joint_order`（字面名 + preserve_order），
   缩放 == 机型包自己的逐关节动作缩放（go2 = 0.25×effort/stiffness）——不是 `.*` 正则序；
2. **派生几何**：足端/大腿/小腿/躯干 传感器模式与足端 site 必须能在**真实编译 MJCF / 真实环境**
   上解析（模式空匹配 = 经典静默失效）；脚高度帧序与 site 索引序必须一致（两侧同序才配对）；
3. **profile 驱动**：换一份 profile（角色 std / 平地倾角阈值 / 摩擦档 / play 命令档）后，数值
   必须跟着变 —— 证明任务数值来自 profile 而不是 Kit 里的字面量；
4. **族可移植**：第二个（合成）绑定换腿名/腿序/腿前缀序后，**不改 Kit 代码**即可建出合法 cfg
   （动作序跟契约走，不是 MJCF 序），并能在真实环境里 reset + 非零动作 step。

真跑（建环境/step）与建 cfg 分开：前者慢但覆盖"模式解析在运行期成立"，后者快且覆盖纯配置。
"""

from __future__ import annotations

import json
import re
import sys
import textwrap
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GO2_PACKAGE = ROOT / "assets" / "robots" / "unitree_go2"
GO2_SOURCE = GO2_PACKAGE / "training" / "source"
for _path in (str(ROOT), str(GO2_PACKAGE), str(GO2_SOURCE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:  # 训练栈不可用时整文件跳过（与 adapters/mjlab 其它测试同口径）
    import mjlab  # noqa: F401
    import mujoco
except ImportError as _exc:  # pragma: no cover
    raise unittest.SkipTest(f"训练栈不可用: {_exc}")

from local_tasks import mjlab_extension  # noqa: E402

mjlab_extension.register()

from local_tasks.robots.unitree.go2.tasks.go2_skills.binding import GO2  # noqa: E402
from local_tasks.robots.unitree.go2.tasks.locomotion import velocity as go2_velocity  # noqa: E402
from local_tasks.robots.unitree.go2.tasks.locomotion.binding import (  # noqa: E402
    GO2_VELOCITY,
)


def contract() -> dict:
    return json.loads((GO2_PACKAGE / "contract.json").read_text(encoding="utf-8-sig"))


def _resolve_scale(scale, joint: str) -> float:
    """按 mjlab 口径解析动作缩放（字面名优先，再 fullmatch 正则）。"""
    if not isinstance(scale, dict):
        return float(scale)
    hits = [value for key, value in scale.items() if key == joint or re.fullmatch(key, joint)]
    if len(hits) != 1:
        raise AssertionError(f"缩放表对 {joint} 命中 {len(hits)} 条：{scale}")
    return float(hits[0])


def _resolve_std(std: dict, joint: str) -> float:
    """按 mjlab `variable_posture` 口径解析 std 表（fullmatch，恰好一条命中）。"""
    hits = [value for key, value in std.items() if key == joint or re.fullmatch(key, joint)]
    if len(hits) != 1:
        raise AssertionError(f"std 表对 {joint} 命中 {len(hits)} 条：{sorted(std)}")
    return float(hits[0])


class VelocityCfgContractTests(unittest.TestCase):
    """纯配置判据（不建环境）：动作序 / 缩放 / 派生几何 / profile 驱动。"""

    @classmethod
    def setUpClass(cls):
        cls.kit_velocity = __import__(
            "adapters.mjlab.kits.quadruped_kit.skills.velocity", fromlist=["config", "profile"]
        )
        cls.kit_config = cls.kit_velocity.config
        cls.VelocityProfile = cls.kit_velocity.profile.VelocityProfile
        cls.rough = go2_velocity.unitree_go2_rough_env_cfg()
        cls.flat = go2_velocity.unitree_go2_flat_env_cfg()

    def test_action_term_keeps_contract_order_and_package_scale(self):
        order = tuple(contract()["action"]["joint_order"])
        term = self.rough.actions["joint_pos"]
        self.assertEqual(order, tuple(term.actuator_names))
        self.assertTrue(term.preserve_order)
        # 期望缩放不是照抄 Kit：用机型包自己声明的执行器谱独立算一遍。
        expected = {
            joint: _resolve_scale(mjlab_extension.GO2_ACTION_SCALE, joint) for joint in order
        }
        self.assertEqual(
            expected, {joint: _resolve_scale(term.scale, joint) for joint in order}
        )

    def test_derived_geometry_matches_the_compiled_mjcf_inventory(self):
        model = mjlab_extension.get_spec().compile()
        geoms = [model.geom(i).name for i in range(model.ngeom)]
        sites = [model.site(i).name for i in range(model.nsite)]
        binding = GO2_VELOCITY
        # 足端几何：按契约腿序，与真实 MJCF 元素一一对应
        self.assertEqual(binding.leg_ids, ("FL", "FR", "RL", "RR"))
        for leg in binding.leg_ids:
            self.assertIn(
                binding.foot_geoms[binding.leg_ids.index(leg)], geoms, f"腿 {leg} 的足端几何不在 MJCF 里"
            )
        # 大腿/小腿几何：每腿都要有（个数不预设：go2 小腿是 calf1+calf2）
        for role, minimum in (("thigh", 1), ("calf", 2)):
            per_leg = binding.collision_geoms_for_role(role)
            self.assertEqual(4 * minimum, len(per_leg), f"{role} 几何数与 MJCF 不符")
            for name in per_leg:
                self.assertIn(name, geoms)
                self.assertRegex(name, rf"^({'|'.join(binding.leg_ids)})_")
        # 躯干模式：必须命中真实躯干几何、且不吞腿杆几何
        trunk_pattern = binding.trunk_collision_pattern()
        trunk_hits = [name for name in geoms if re.fullmatch(trunk_pattern, name)]
        self.assertEqual(["base1_collision", "base2_collision", "base3_collision"], trunk_hits)
        # 足端 site：按契约腿序，且在 MJCF site 清单里真实存在
        foot_sites = binding.foot_sites()
        self.assertEqual(tuple(binding.leg_ids), foot_sites)
        for name in foot_sites:
            self.assertIn(name, sites)
        # 两个 go2 上游副本（特技用的 go2_skills/upstream 与 velocity 用的 training.xml）
        # 派生出的几何必须一致 —— 副本漂移会让"同族同构"在这里先炸（比等训练跑歪早）。
        self.assertEqual(GO2.foot_geoms, binding.foot_geoms)
        self.assertEqual(GO2.foot_sites(), binding.foot_sites())
        self.assertEqual(GO2.trunk_collision_pattern(), trunk_pattern)
        for role in ("hip", "thigh", "calf"):
            self.assertEqual(
                GO2.collision_geoms_for_role(role), binding.collision_geoms_for_role(role)
            )
        # 配置里真的用了这些派生值（否则派生正确也没接线）
        sensors = {sensor.name: sensor for sensor in self.rough.scene.sensors}
        self.assertEqual(
            tuple(binding.foot_geoms), tuple(sensors["feet_ground_contact"].primary.pattern)
        )
        self.assertEqual(
            tuple(binding.collision_geoms_for_role("thigh")),
            tuple(sensors["thigh_ground_touch"].primary.pattern),
        )
        self.assertEqual(
            tuple(binding.collision_geoms_for_role("calf")),
            tuple(sensors["shank_ground_touch"].primary.pattern),
        )
        self.assertEqual(
            trunk_pattern, sensors["trunk_ground_touch"].primary.pattern
        )
        self.assertEqual(binding.root_body, sensors["self_collision"].primary.pattern)
        scan = sensors["foot_height_scan"]
        self.assertEqual(
            foot_sites, tuple(frame.name for frame in scan.frame)
        )
        self.assertEqual(binding.root_body, sensors["terrain_scan"].frame.name)

    def test_profile_numbers_drive_the_family_config(self):
        custom = replace(
            self.VelocityProfile(),
            pose_std_standing={"hip_abduction": 0.11, "hip_pitch": 0.22, "knee": 0.33},
            pose_std_moving={"hip_abduction": 1.1, "hip_pitch": 2.2, "knee": 3.3},
            flat_tilt_limit_degrees=45.0,
            foot_friction_slide=(0.5, 0.9),
            play_flat_lin_vel_x=(-2.0, 3.0),
            play_flat_ang_vel_z=(-0.4, 0.4),
        )
        cfg = self.kit_config.make_env_cfg(GO2_VELOCITY, custom, terrain_profile="flat")
        order = tuple(contract()["action"]["joint_order"])
        for term in ("std_standing", "std_walking"):
            table = cfg.rewards["pose"].params[term]
            for joint in order:
                self.assertIn(_resolve_std(table, joint), {0.11, 0.22, 0.33, 1.1, 2.2, 3.3})
        self.assertEqual(
            {"hip_abduction": 0.11, "hip_pitch": 0.22, "knee": 0.33},
            {role: _resolve_std(cfg.rewards["pose"].params["std_standing"], f"FL_{suffix}")
             for role, suffix in (("hip_abduction", "hip_joint"), ("hip_pitch", "thigh_joint"), ("knee", "calf_joint"))},
        )
        import math

        limit = cfg.terminations["fell_over"].params["limit_angle"]
        self.assertAlmostEqual(math.radians(45.0), limit, places=9)
        slide = cfg.events["foot_friction_slide"].params["ranges"]
        self.assertEqual((0.5, 0.9), slide)
        play_cfg = self.kit_config.make_env_cfg(
            GO2, custom, terrain_profile="flat", play=True
        )
        self.assertEqual((-2.0, 3.0), play_cfg.commands["twist"].ranges.lin_vel_x)
        self.assertEqual((-0.4, 0.4), play_cfg.commands["twist"].ranges.ang_vel_z)

    def test_flat_and_rough_keep_the_source_sensor_and_termination_shape(self):
        rough_sensors = [sensor.name for sensor in self.rough.scene.sensors]
        flat_sensors = [sensor.name for sensor in self.flat.scene.sensors]
        self.assertEqual(
            ["terrain_scan", "foot_height_scan", "feet_ground_contact", "self_collision",
             "thigh_ground_touch", "shank_ground_touch", "trunk_ground_touch"],
            rough_sensors,
        )
        self.assertEqual(["foot_height_scan", "feet_ground_contact"], flat_sensors)
        self.assertEqual(["time_out", "out_of_terrain_bounds", "illegal_contact"], list(self.rough.terminations))
        self.assertEqual(["time_out", "fell_over"], list(self.flat.terminations))
        self.assertNotIn("terrain_scan", [s.name for s in (self.flat.scene.sensors or ())])
        # 平地档的倾角阈值：70°（源配方）→ 弧度
        self.assertAlmostEqual(1.2217304763960306, self.flat.terminations["fell_over"].params["limit_angle"])


class VelocityRuntimeTests(unittest.TestCase):
    """真实环境判据：模式解析 + reset/step（族工厂建出的 cfg 直接跑）。"""

    @classmethod
    def setUpClass(cls):
        cls.cfg = go2_velocity.unitree_go2_rough_env_cfg()
        cls.cfg.scene.num_envs = 2
        from mjlab.envs import ManagerBasedRlEnv

        cls.env = ManagerBasedRlEnv(cls.cfg, device="cpu")

    @classmethod
    def tearDownClass(cls):
        cls.env.close()

    def test_sensor_patterns_resolve_on_the_real_entity(self):
        names = {
            sensor: tuple(self.env.scene[sensor].primary_names)
            for sensor in ("feet_ground_contact", "thigh_ground_touch", "shank_ground_touch",
                           "trunk_ground_touch")
        }
        for sensor, resolved in names.items():
            self.assertGreaterEqual(len(resolved), 1, f"{sensor} 模式空匹配")
        self.assertEqual(set(GO2.foot_geoms), set(names["feet_ground_contact"]))
        self.assertEqual(set(GO2.collision_geoms_for_role("thigh")), set(names["thigh_ground_touch"]))
        self.assertEqual(set(GO2.collision_geoms_for_role("calf")), set(names["shank_ground_touch"]))
        self.assertEqual(
            {"base1_collision", "base2_collision", "base3_collision"},
            set(names["trunk_ground_touch"]),
        )
        # 高度帧序 == site 索引序（mjlab 按 `preserve_order=False` 解析到模型序；两个消费者
        # 必须同序才配对，见族级 config 的足端顺序说明）
        frames = [frame.name for frame in self.cfg.scene.sensors[1].frame]
        asset_cfg = self.cfg.rewards["foot_clearance"].params["asset_cfg"]
        _, resolved_sites = self.env.scene["robot"].find_sites(
            asset_cfg.site_names, preserve_order=asset_cfg.preserve_order
        )
        self.assertEqual(frames, list(resolved_sites))
        _, slip_sites = self.env.scene["robot"].find_sites(
            self.cfg.rewards["foot_slip"].params["asset_cfg"].site_names
        )
        self.assertEqual(frames, list(slip_sites))

    def test_reset_and_nonzero_action_step(self):
        import torch

        env = self.env
        env.reset()
        action = torch.full(
            (env.num_envs, env.action_manager.total_action_dim), 0.1, device=env.device
        )
        obs, reward, terminated, truncated, _ = env.step(action)
        self.assertTrue(torch.isfinite(obs["actor"]).all())
        self.assertTrue(torch.isfinite(obs["critic"]).all())
        self.assertTrue(torch.isfinite(reward).all())
        self.assertTrue(torch.isfinite(env.scene["robot"].data.joint_pos).all())
        term = env.action_manager.get_term("joint_pos")
        self.assertEqual(tuple(contract()["action"]["joint_order"]), tuple(term.target_names))
        # 动作真的落到关节上（非零动作 → 目标 ≠ 默认姿）
        targets = env.scene["robot"].data.joint_pos_target[:, term.target_ids]
        default = env.scene["robot"].data.default_joint_pos[:, term.target_ids]
        self.assertGreater(float((targets - default).abs().max()), 0.0)


# --- 已接到族工厂的机型：绑定派生 + 动作序 + 真跑（一机型一条） ---------------------

#: 每台已接机型：包目录 + 源码根 + profile 声明（entrypoint 从 profile JSON 读 ——
#: 顺带锁住"公开入口名不动"）。新接一台 = 加一条。
_ROBOT_CASES = {
    "unitree_go1": {
        "package": ROOT / "assets" / "robots" / "unitree_go1",
        "source_dir": "training/source",
        "profiles": {
            "flat": "go1-velocity",
            "rough": "go1-velocity-rough",
        },
    },
    "unitree_b2": {
        "package": ROOT / "assets" / "robots" / "unitree_b2",
        "root_package": None,
        "source_dir": "training/source",
        "profiles": {
            "flat": "b2-velocity",
        },
    },
    "deeprobotics_lite3": {
        "package": ROOT / "assets" / "robots" / "deeprobotics_lite3",
        "root_package": None,
        "source_dir": "training/source",
        "profiles": {
            "flat": "lite3-velocity",
        },
    },
}


def _profile_entrypoint(package: Path, profile_id: str) -> str:
    """profile JSON 的 `entrypoints.env`（`module:factory`）——入口名由档案锁住。"""
    path = package / "training" / "profiles" / f"{profile_id}.json"
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return str(data["entrypoints"]["env"])


class _RobotVelocityMixin:
    """机型公共判据：绑定派生能在真实 MJCF 上解析 / 动作序 = 契约序 / 真 reset+step。"""

    ROBOT_ID: str = ""
    SPEC_FACTORY: tuple[str, str] = ("", "")

    @classmethod
    def setUpClass(cls):
        case = _ROBOT_CASES[cls.ROBOT_ID]
        cls.package: Path = case["package"]
        cls.source_root: Path = cls.package / case["source_dir"]
        for entry in (str(cls.source_root), str(cls.package), str(ROOT)):
            if entry not in sys.path:
                sys.path.insert(0, entry)
        import importlib

        binding_module, binding_attr = cls.SPEC_FACTORY
        cls.binding = getattr(importlib.import_module(binding_module), binding_attr)
        cls.contract = json.loads(
            (cls.package / "contract.json").read_text(encoding="utf-8-sig")
        )
        cls.env_factories = {}
        for variant, profile_id in case["profiles"].items():
            module_name, _, factory_name = _profile_entrypoint(
                cls.package, profile_id
            ).partition(":")
            cls.env_factories[variant] = getattr(
                importlib.import_module(module_name), factory_name
            )

    def _model(self):
        return self.binding.base_entity_cfg().spec_fn().compile()

    def test_binding_patterns_resolve_on_the_compiled_mjcf(self):
        model = self._model()
        geoms = {model.geom(i).name for i in range(model.ngeom) if model.geom(i).name}
        sites = {model.site(i).name for i in range(model.nsite) if model.site(i).name}
        binding = self.binding
        # 足端几何：按契约腿序一一对上（能力缺口机型没有足端 site，几何本身仍在）
        self.assertEqual(len(binding.leg_ids), len(binding.foot_geoms))
        for name in binding.foot_geoms:
            self.assertIn(name, geoms, f"足端几何 {name} 不在 MJCF 里")
        if binding.has_foot_sites():
            foot_sites = binding.foot_sites()
            self.assertEqual(len(binding.leg_ids), len(foot_sites))
            for name in foot_sites:
                self.assertIn(name, sites, f"足端 site {name} 不在 MJCF 里")
        else:  # 能力缺口：取即报错（不是静默给空表）
            with self.assertRaises(RuntimeError):
                binding.foot_sites()
        # 逐族角色：关节模式必须命中真实关节（同角色各腿同尾段 ⇒ 紧凑写法）
        for role in binding.leg_pattern:
            family_role = binding.family_role(role)
            patterns = binding.role_joint_pattern(family_role)
            for pattern in patterns:
                hits = [j for j in binding.joint_order if re.fullmatch(pattern, j)]
                self.assertGreaterEqual(len(hits), 1, f"关节模式 {pattern} 空匹配")
        # 腿杆碰撞几何：按契约腿序枚举 MJCF 清单（个数不预设）；
        # 躯干几何按"根 body 自己的 `_collision` 几何"派生 —— 没有即能力缺口（报错，不空匹配）。
        for role in binding.leg_pattern:
            family_role = binding.family_role(role)
            if family_role == "hip_abduction":
                continue  # 髋不参与触地惩罚（源配方口径）
            try:
                per_leg = binding.collision_geoms_for_role(role)
            except RuntimeError:
                # 能力缺口：本机型 MJCF 的碰撞几何**无名**（碰撞方案由 CollisionCfg 按正则
                # 在实体层重建，go2/lite3 的具名几何只是资产的偶然）⇒ 族级按名枚举取不到。
                # 断言这确实是"无名"（找不到含角色词的具名几何），不是挑错了名字。
                self.assertEqual(
                    [name for name in geoms if role.lower() in name.lower()], []
                )
                continue
            self.assertGreaterEqual(len(per_leg), len(binding.leg_ids))
            for name in per_leg:
                self.assertIn(name, geoms)
        if binding.root_collision_geoms:
            pattern = binding.trunk_collision_pattern()
            hits = [name for name in geoms if re.fullmatch(pattern, name)]
            self.assertGreaterEqual(len(hits), 1, f"躯干模式 {pattern} 空匹配")
        else:
            with self.assertRaises(RuntimeError):
                binding.trunk_collision_pattern()

    def test_cfg_action_order_is_the_contract_order(self):
        order = tuple(self.contract["action"]["joint_order"])
        for variant, factory in self.env_factories.items():
            with self.subTest(variant=variant):
                cfg = factory()
                term = cfg.actions["joint_pos"]
                self.assertEqual(order, tuple(term.actuator_names))
                self.assertTrue(term.preserve_order)
                for joint in order:
                    self.assertIsInstance(_resolve_scale(term.scale, joint), float)

    def test_every_derived_pattern_resolves_against_the_compiled_mjcf(self):
        """建出的 cfg 里每一个派生模式都必须命中真实编译 MJCF 的 ≥1 个名字。

        模式空匹配是经典静默失效（传感器/帧全空也不报错，训练照跑、奖励恒零）；
        这条对**每台已接机型逐档**核，`lite3` 的 body 帧口径也走同一判据。
        """
        model = self._model()
        geoms = {model.geom(i).name for i in range(model.ngeom) if model.geom(i).name}
        sites = {model.site(i).name for i in range(model.nsite) if model.site(i).name}
        bodies = {model.body(i).name for i in range(model.nbody) if model.body(i).name}
        for variant, factory in self.env_factories.items():
            cfg = factory()
            for sensor in cfg.scene.sensors or ():
                with self.subTest(variant=variant, sensor=sensor.name):
                    self._assert_sensor_targets_resolve(sensor, geoms, sites, bodies)

    def _assert_sensor_targets_resolve(self, sensor, geoms, sites, bodies) -> None:
        from mjlab.sensor import (
            ContactSensorCfg,
            RayCastSensorCfg,
            TerrainHeightSensorCfg,
        )

        if isinstance(sensor, ContactSensorCfg):
            match = sensor.primary
            pool = {"geom": geoms, "body": bodies, "subtree": bodies}[match.mode]
            patterns = (
                (match.pattern,) if isinstance(match.pattern, str) else tuple(match.pattern)
            )
            if not patterns:
                return  # 空模式 = 基座"按名不配"的占位（`foot_friction` 那类），跳过
            excluded = set(match.exclude or ())
            hits = [
                name
                for name in pool
                if name not in excluded
                and any(re.fullmatch(pattern, name) for pattern in patterns)
            ]
            self.assertGreaterEqual(
                len(hits), 1, f"传感器 {sensor.name} 的主模式 {patterns} 空匹配"
            )
        elif isinstance(sensor, TerrainHeightSensorCfg):
            frames = sensor.frame if isinstance(sensor.frame, tuple) else (sensor.frame,)
            self.assertTrue(frames, f"{sensor.name} 没有足端帧")
            for frame in frames:
                pool = sites if frame.type == "site" else bodies
                self.assertIn(
                    frame.name, pool, f"{sensor.name} 的 {frame.type} 帧 {frame.name!r} 不在 MJCF 里"
                )
        elif isinstance(sensor, RayCastSensorCfg):
            self.assertIn(sensor.frame.name, bodies, f"{sensor.name} 的帧不在 MJCF 里")

    def test_runtime_action_order_and_reset_step(self):
        import torch
        from mjlab.envs import ManagerBasedRlEnv

        order = tuple(self.contract["action"]["joint_order"])
        cfg = next(iter(self.env_factories.values()))()
        cfg.scene.num_envs = 1
        env = ManagerBasedRlEnv(cfg, device="cpu")
        try:
            env.reset()
            action = torch.full(
                (env.num_envs, env.action_manager.total_action_dim),
                0.1,
                device=env.device,
            )
            obs, reward, terminated, truncated, _ = env.step(action)
            self.assertTrue(torch.isfinite(obs["actor"]).all())
            self.assertTrue(torch.isfinite(reward).all())
            term = env.action_manager.get_term("joint_pos")
            self.assertEqual(order, tuple(term.target_names))
            targets = env.scene["robot"].data.joint_pos_target[:, term.target_ids]
            default = env.scene["robot"].data.default_joint_pos[:, term.target_ids]
            self.assertGreater(float((targets - default).abs().max()), 0.0)
        finally:
            env.close()


class B2VelocityRobotTests(_RobotVelocityMixin, unittest.TestCase):
    ROBOT_ID = "unitree_b2"
    SPEC_FACTORY = ("b2_velocity.binding", "B2_VELOCITY")


class Go1VelocityRobotTests(_RobotVelocityMixin, unittest.TestCase):
    ROBOT_ID = "unitree_go1"
    SPEC_FACTORY = ("go1_velocity.binding", "GO1_VELOCITY")

    def test_site_less_capability_drops_the_foot_terms(self):
        """无足端 site 的机型：足端高度扫描与四项依赖 site 的奖励/三项观测整项撤掉。

        （go1 的 MJCF 只有 imu 一个 site；源配方对这四项也是整项撤销 —— 能力判据是
        `binding.has_foot_sites()`，不是机型名。）
        """
        self.assertFalse(self.binding.has_foot_sites())
        cfg = self.env_factories["rough"]()
        self.assertNotIn("foot_height_scan", [s.name for s in cfg.scene.sensors])
        for name in ("foot_clearance", "foot_swing_height", "soft_landing", "foot_slip"):
            self.assertNotIn(name, cfg.rewards)
        for group in ("actor", "critic"):
            terms = cfg.observations[group].terms
            for name in ("foot_height", "foot_air_time", "foot_contact"):
                self.assertNotIn(name, terms)


class Lite3VelocityRobotTests(_RobotVelocityMixin, unittest.TestCase):
    """lite3：无足端 **site**、足端是 `<LR>_FOOT` **body**（body 帧口径的回归锁）。"""

    ROBOT_ID = "deeprobotics_lite3"
    SPEC_FACTORY = ("lite3_velocity.binding", "LITE3_VELOCITY")

    def test_foot_scan_uses_body_frames_and_flat_keeps_the_terrain_scan(self):
        """能力判据：无足端 site（取即报错）但足端 body 齐 ⇒ 扫描帧回退 body。

        另锁 flat 档口径：源配方**保留** `terrain_scan` 传感器、45 维 rl_sdk 观测里
        没有 `height_scan` 项（族级默认撤 sensor/obs，本档案靠 profile 两项开关关掉）。
        """
        self.assertFalse(self.binding.has_foot_sites())
        with self.assertRaises(RuntimeError):
            self.binding.foot_sites()
        model = self._model()
        bodies = {model.body(i).name for i in range(model.nbody) if model.body(i).name}
        scan_bodies = [f"{leg}_FOOT" for leg in self.binding.leg_ids]
        self.assertEqual(
            tuple(("body", name) for name in scan_bodies), self.binding.foot_scan_frames()
        )
        for name in scan_bodies:
            self.assertIn(name, bodies, f"足端 body {name} 不在 MJCF 里")

        cfg = self.env_factories["flat"]()
        sensors = {sensor.name: sensor for sensor in cfg.scene.sensors}
        self.assertEqual(
            ["terrain_scan", "foot_height_scan", "foot_contact", "full_contact"],
            [sensor.name for sensor in cfg.scene.sensors],
        )
        scan = sensors["foot_height_scan"]
        self.assertEqual(
            tuple(scan_bodies), tuple(frame.name for frame in scan.frame)
        )
        self.assertEqual("body", scan.frame[0].type)
        self.assertIn("terrain_scan", sensors)  # flat 档不撤（源配方）
        for group in ("actor", "critic"):
            self.assertNotIn("height_scan", cfg.observations[group].terms)
        # 接触表：足端接触面是 shank body（不是足端几何），全身接触带全部 body
        self.assertEqual(".*_SHANK", sensors["foot_contact"].primary.pattern)
        self.assertEqual("body", sensors["foot_contact"].primary.mode)
        self.assertEqual(".*", sensors["full_contact"].primary.pattern)

    def test_runtime_foot_bodies_and_reward_ids_resolve(self):
        """真环境里：足端 body 帧/接触面/奖励 body ids 全部解析到真实实体上。"""
        import torch
        from mjlab.envs import ManagerBasedRlEnv

        cfg = self.env_factories["flat"]()
        cfg.scene.num_envs = 1
        env = ManagerBasedRlEnv(cfg, device="cpu")
        try:
            env.reset()
            robot = env.scene["robot"]
            for name in (f"{leg}_FOOT" for leg in self.binding.leg_ids):
                self.assertIn(name, robot.body_names)
            resolved = env.reward_manager.get_term_cfg("phase_foot_trajectory_exp")
            foot_ids = resolved.params["asset_cfg"].body_ids
            self.assertEqual(len(self.binding.leg_ids), len(foot_ids))
            for body_id in foot_ids:
                self.assertIn("_SHANK", robot.body_names[int(body_id)])
            action = torch.full(
                (env.num_envs, env.action_manager.total_action_dim), 0.1, device=env.device
            )
            obs, reward, terminated, truncated, _ = env.step(action)
            self.assertTrue(torch.isfinite(reward).all())
            self.assertTrue(torch.isfinite(obs["actor"]).all())
        finally:
            env.close()


# --- 第二个绑定：合成机型（换腿名/腿序/根 body 名），Kit 代码零改动 -----------------

_SYNTHETIC_LEGS = ("r2", "l1", "r1", "l2")  # 契约腿序：既非字典序，也非 MJCF 序
_SYNTHETIC_MODEL_ORDER = ("l1", "r1", "l2", "r2")  # MJCF 声明序（故意与契约序不同）
_SYNTHETIC_ROOT = "chassis"

_SYNTHETIC_XML = """<mujoco model="synthetic_quad">
  <default>
    <geom type="capsule" size="0.02 0.05" rgba="0.6 0.6 0.6 1"/>
    <joint axis="0 1 0" damping="0.1"/>
  </default>
  <worldbody>
    <body name="chassis" pos="0 0 0.4">
      <freejoint name="chassis_free"/>
      <!-- 躯干几何名**刻意不跟根 body 名**（真例：go1 的根 body 叫 base_link、躯干几何叫
           trunk_collision）。第一版实现按"根 body 名首段"推正则，在 go1 上直接空匹配、
           把 jumper/AMP 两个档案的绑定构造炸掉 —— 这条命名就是这个回归的锁。 -->
      <geom name="trunk_collision" type="box" size="0.2 0.08 0.05"/>
      <site name="imu" pos="0 0 0" size="0.01"/>
{legs}
    </body>
  </worldbody>
  <sensor>
    <gyro name="imu_ang_vel" site="imu"/>
    <velocimeter name="imu_lin_vel" site="imu"/>
    <subtreeangmom name="root_angmom" body="chassis"/>
  </sensor>
</mujoco>
"""

_SYNTHETIC_LEG = """      <body name="{leg}_hip" pos="0.15 {side}0.06 0">
        <joint name="{leg}_hip_joint" axis="0 0 1"/>
        <geom name="{leg}_hip_collision" fromto="0 0 0 0 0 -0.06"/>
        <body name="{leg}_thigh" pos="0 0 -0.06">
          <joint name="{leg}_thigh_joint" axis="0 1 0"/>
          <geom name="{leg}_thigh_collision" fromto="0 0 0 0 0 -0.12"/>
          <body name="{leg}_calf" pos="0 0 -0.12">
            <joint name="{leg}_calf_joint" axis="0 1 0"/>
            <geom name="{leg}_calf1_collision" fromto="0 0 0 0 0 -0.06"/>
            <geom name="{leg}_calf2_collision" fromto="0 0 -0.06 0 0 -0.12"/>
            <geom name="{leg}_foot_collision" type="sphere" size="0.02" pos="0 0 -0.12"/>
            <site name="{leg}" pos="0 0 -0.12" size="0.02"/>
          </body>
        </body>
      </body>
"""


def _synthetic_xml() -> str:
    legs = "\n".join(
        textwrap.indent(_SYNTHETIC_LEG.format(leg=leg, side="-" if leg.startswith("r") else ""), "  ")
        for leg in _SYNTHETIC_MODEL_ORDER
    )
    return _SYNTHETIC_XML.format(legs=legs)


def _synthetic_spec() -> mujoco.MjSpec:
    return mujoco.MjSpec.from_string(_synthetic_xml())


def _synthetic_contract() -> dict:
    leg_pattern = ["hip", "thigh", "calf"]
    joint_order = [f"{leg}_{role}_joint" for leg in _SYNTHETIC_LEGS for role in leg_pattern]
    return {
        "schema_version": "robot-contract-3.0",
        "robot_id": "synthetic_quad",
        "morphology": {
            "id": "quadruped_12dof",
            "legs": 4,
            "leg_pattern": leg_pattern,
            "leg_naming": "{LR}_{role}_joint",
            "actuator_type": "position",
            "leg_ids": list(_SYNTHETIC_LEGS),
        },
        "joints": {"default_pose": [0.0] * 12},
        "action": {"joint_order": joint_order, "action_scale": 0.25},
        "actuator_profile": {
            "by_role": {
                role: {"stiffness": 40.0, "damping": 1.0, "effort": 60.0, "action_scale": 0.25}
                for role in leg_pattern
            }
        },
    }


def _synthetic_entity_cfg():
    from mjlab.actuator import BuiltinPositionActuatorCfg
    from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
    from mjlab.utils.spec_config import CollisionCfg

    def group(expr: str, stiffness: float, effort: float) -> BuiltinPositionActuatorCfg:
        return BuiltinPositionActuatorCfg(
            target_names_expr=(expr,), stiffness=stiffness, damping=1.0, effort_limit=effort
        )

    return EntityCfg(
        init_state=EntityCfg.InitialStateCfg(
            pos=(0.0, 0.0, 0.4),
            joint_pos={f".*{role}_joint": value for role, value in
                       (("hip", 0.0), ("thigh", 0.4), ("calf", -0.8))},
        ),
        collisions=(
            CollisionCfg(
                geom_names_expr=(".*",),
                contype=1,
                conaffinity=0,
                condim={".*foot.*": 3, ".*": 1},
                priority={".*foot.*": 1, ".*": 0},
            ),
        ),
        spec_fn=_synthetic_spec,
        articulation=EntityArticulationInfoCfg(
            actuators=(
                group(".*hip_joint", 40.0, 80.0),
                group(".*thigh_joint", 40.0, 60.0),
                group(".*calf_joint", 20.0, 40.0),
            ),
            soft_joint_pos_limit_factor=0.9,
        ),
    )


class SyntheticSecondRobotTests(unittest.TestCase):
    """换一台"机型"：只给契约/MJCF/实体数据，族工厂直接建出可跑的 cfg。"""

    @classmethod
    def setUpClass(cls):
        from adapters.mjlab.kits.quadruped_kit.skills import from_contract

        cls.kit_velocity = __import__(
            "adapters.mjlab.kits.quadruped_kit.skills.velocity", fromlist=["config", "profile"]
        )
        cls.binding = from_contract(
            _synthetic_contract(),
            spec_fn=_synthetic_spec,
            base_entity_cfg=_synthetic_entity_cfg,
            init_base_height=0.4,
        )
        cls.profile = cls.kit_velocity.profile.VelocityProfile()
        cls.cfg = cls.kit_velocity.config.make_env_cfg(
            cls.binding, cls.profile, terrain_profile="flat"
        )

    def test_action_order_follows_contract_not_mjcf(self):
        model = _synthetic_spec().compile()
        mjcf_order = tuple(model.joint(i).name for i in range(model.njnt) if model.jnt_type[i] != mujoco.mjtJoint.mjJNT_FREE)
        self.assertNotEqual(mjcf_order, tuple(_synthetic_contract()["action"]["joint_order"]))
        term = self.cfg.actions["joint_pos"]
        self.assertEqual(tuple(_synthetic_contract()["action"]["joint_order"]), tuple(term.actuator_names))
        # 逐关节缩放 = 契约角色 action_scale × 该实体执行器 effort/stiffness
        expected = {"hip": 0.25 * 80.0 / 40.0, "thigh": 0.25 * 60.0 / 40.0, "calf": 0.25 * 40.0 / 20.0}
        self.assertEqual(
            {joint: _resolve_scale(term.scale, joint) for joint in term.actuator_names},
            {joint: expected[joint.split("_")[1]] for joint in term.actuator_names},
        )

    def test_derived_patterns_track_this_robot_only(self):
        sensors = {sensor.name: sensor for sensor in self.cfg.scene.sensors}
        self.assertEqual(tuple(self.binding.foot_geoms), tuple(sensors["feet_ground_contact"].primary.pattern))
        self.assertEqual(
            tuple(self.binding.foot_sites()), tuple(frame.name for frame in sensors["foot_height_scan"].frame)
        )
        # 躯干模式 = 根 body **自己的**碰撞几何（本例的名字与根 body 名不同，见 XML 注释）
        self.assertEqual(("trunk_collision",), self.binding.root_collision_geoms)
        self.assertEqual(
            ["trunk_collision"],
            [name for name in self.binding.geom_names if re.fullmatch(self.binding.trunk_collision_pattern(), name)],
        )
        for role in ("thigh", "calf"):
            per_leg = self.binding.collision_geoms_for_role(role)
            self.assertEqual(4, len({name.split("_")[0] for name in per_leg}))

    def test_pose_std_tables_cover_every_joint_once(self):
        order = tuple(_synthetic_contract()["action"]["joint_order"])
        for key in ("std_standing", "std_walking", "std_running"):
            table = self.cfg.rewards["pose"].params[key]
            for joint in order:
                self.assertIsInstance(_resolve_std(table, joint), float)

    def test_synthetic_env_resets_and_steps(self):
        import torch
        from mjlab.envs import ManagerBasedRlEnv

        cfg = self.kit_velocity.config.make_env_cfg(
            self.binding, self.profile, terrain_profile="flat"
        )
        cfg.scene.num_envs = 1
        env = ManagerBasedRlEnv(cfg, device="cpu")
        try:
            env.reset()
            action = torch.full(
                (env.num_envs, env.action_manager.total_action_dim), 0.2, device=env.device
            )
            obs, reward, terminated, truncated, _ = env.step(action)
            self.assertTrue(torch.isfinite(obs["actor"]).all())
            self.assertTrue(torch.isfinite(reward).all())
            term = env.action_manager.get_term("joint_pos")
            self.assertEqual(tuple(_synthetic_contract()["action"]["joint_order"]), tuple(term.target_names))
        finally:
            env.close()


# --- 第三份资产：**同名不同写法**（腿杆/躯干碰撞几何未具名 + 执行器写在 MJCF） ------------
#
# 真例：b2 的 `model/robot.xml` 只给足端几何具名，腿杆与躯干的碰撞几何在实体构建期由
# `CollisionCfg` 重建；执行器（12 个 `<position>`）也写在 MJCF 里，cfg 只能包装不能重建
# （重建 = 往同一批关节再注入同名执行器，实体构建即崩）。
#
# 这两条都是**资产事实**，族级技能层必须按事实选路而不是按机型名判断：
#   * 匹配面：几何具名 → 按几何名；未具名 → 按 body 名（语义同为"这根腿杆与地形的接触"）；
#   * 执行器：MJCF 为执行真值 → 沿用自带执行器；cfg 自带 PD → 按契约重建。

_SYNTHETIC_BODY_ASSET_LEG = """      <body name="{leg}_hip" pos="0.15 {side}0.06 0">
        <joint name="{leg}_hip_joint" axis="0 0 1"/>
        <geom fromto="0 0 0 0 0 -0.06"/>
        <body name="{leg}_thigh" pos="0 0 -0.06">
          <joint name="{leg}_thigh_joint" axis="0 1 0"/>
          <geom fromto="0 0 0 0 0 -0.12"/>
          <body name="{leg}_calf" pos="0 0 -0.12">
            <joint name="{leg}_calf_joint" axis="0 1 0"/>
            <geom fromto="0 0 0 0 0 -0.06"/>
            <geom fromto="0 0 -0.06 0 0 -0.12"/>
            <geom name="{leg}_foot_collision" type="sphere" size="0.02" pos="0 0 -0.12"/>
            <site name="{leg}" pos="0 0 -0.12" size="0.02"/>
          </body>
        </body>
      </body>
"""


_SYNTHETIC_BODY_ASSET_XML = """<mujoco model="synthetic_quad_body_asset">
  <default>
    <geom type="capsule" size="0.02 0.05" rgba="0.6 0.6 0.6 1"/>
    <joint axis="0 1 0" damping="0.1"/>
  </default>
  <worldbody>
{body}
  </worldbody>
  <actuator>
{actuators}
  </actuator>
  <sensor>
    <gyro name="imu_ang_vel" site="imu"/>
    <velocimeter name="imu_lin_vel" site="imu"/>
    <subtreeangmom name="root_angmom" body="chassis"/>
  </sensor>
</mujoco>
"""


def _synthetic_body_asset_xml() -> str:
    legs = "\n".join(
        textwrap.indent(
            _SYNTHETIC_BODY_ASSET_LEG.format(leg=leg, side="-" if leg.startswith("r") else ""),
            "  ",
        )
        for leg in _SYNTHETIC_MODEL_ORDER
    )
    actuators = "\n".join(
        f'    <position name="{leg}_{role}_joint" joint="{leg}_{role}_joint" kp="40" kv="1"/>'
        for leg in _SYNTHETIC_LEGS
        for role in ("hip", "thigh", "calf")
    )
    # 躯干几何**未具名**（同 b2）：碰撞属性仍由 CollisionCfg 交给全体几何，但没有名字可匹配。
    body = textwrap.dedent(
        """\
        <body name="chassis" pos="0 0 0.4">
          <freejoint name="chassis_free"/>
          <geom type="box" size="0.2 0.08 0.05"/>
          <site name="imu" pos="0 0 0" size="0.01"/>
{legs}
        </body>"""
    ).format(legs=textwrap.indent(legs, "  ").strip())
    return _SYNTHETIC_BODY_ASSET_XML.format(body=body, actuators=actuators)


def _synthetic_body_asset_spec() -> mujoco.MjSpec:
    return mujoco.MjSpec.from_string(_synthetic_body_asset_xml())


def _synthetic_body_asset_entity_cfg():
    from mjlab.actuator import XmlActuatorCfg
    from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
    from mjlab.utils.spec_config import CollisionCfg

    return EntityCfg(
        init_state=EntityCfg.InitialStateCfg(
            pos=(0.0, 0.0, 0.4),
            joint_pos={".*thigh_joint": 0.4, ".*calf_joint": -0.8},
        ),
        collisions=(
            CollisionCfg(
                geom_names_expr=(".*",),
                contype=1,
                conaffinity=0,
                condim={".*foot.*": 3, ".*": 1},
                priority={".*foot.*": 1, ".*": 0},
            ),
        ),
        spec_fn=_synthetic_body_asset_spec,
        articulation=EntityArticulationInfoCfg(
            actuators=tuple(
                XmlActuatorCfg(target_names_expr=(expr,), command_field="position")
                for expr in (".*hip_joint", ".*thigh_joint", ".*calf_joint")
            ),
            soft_joint_pos_limit_factor=0.9,
        ),
    )


class AssetNamingFactTests(unittest.TestCase):
    """两台合成"机型"逐字段同构，只差**资产写法** —— 技能层代码零分支。"""

    @classmethod
    def setUpClass(cls):
        from adapters.mjlab.kits.quadruped_kit.skills import from_contract

        cls.named = from_contract(
            _synthetic_contract(),
            spec_fn=_synthetic_spec,
            base_entity_cfg=_synthetic_entity_cfg,
            init_base_height=0.4,
        )
        cls.body_asset = from_contract(
            _synthetic_contract(),
            spec_fn=_synthetic_body_asset_spec,
            base_entity_cfg=_synthetic_body_asset_entity_cfg,
            init_base_height=0.4,
        )

    def test_sensors_pick_the_matching_face_from_the_asset(self):
        """腿杆惩罚：几何具名 → 几何名；未具名 → body 名（同一语义、两种写法）。

        躯干与足端**不**参与这次选路：躯干按根 body 名匹配（源配方口径，两台机型同写法）、
        足端按足端几何名（两家资产都给足端几何具名）。
        """
        self.assertEqual(("geom", self.named.penalized_geom_pattern), self.named.penalized_contact_match())
        self.assertEqual(
            ("body", r"(?:r2|l1|r1|l2)_(?:thigh|calf)"),
            self.body_asset.penalized_contact_match(),
        )

        from mjlab.tasks.velocity.velocity_env_cfg import make_velocity_env_cfg

        from adapters.mjlab.kits.quadruped_kit.skills.mdp.sensors import (
            BASE_SENSOR,
            FEET_SENSOR,
            PENALIZED_SENSOR,
            replace_sensors,
        )

        cfg = make_velocity_env_cfg()
        replace_sensors(cfg, self.body_asset)
        sensors = {sensor.name: sensor for sensor in cfg.scene.sensors}
        self.assertEqual(
            ("body", r"(?:r2|l1|r1|l2)_(?:thigh|calf)"),
            (sensors[PENALIZED_SENSOR].primary.mode, sensors[PENALIZED_SENSOR].primary.pattern),
        )
        self.assertEqual(
            ("body", _SYNTHETIC_ROOT),
            (sensors[BASE_SENSOR].primary.mode, sensors[BASE_SENSOR].primary.pattern),
        )
        self.assertEqual(
            ("geom", self.body_asset.foot_geoms),
            (sensors[FEET_SENSOR].primary.mode, sensors[FEET_SENSOR].primary.pattern),
        )

    def test_actuators_come_from_the_declared_truth(self):
        """MJCF 为执行真值 → 沿用自带执行器；实体自带 PD → 按契约重建。"""
        self.assertEqual("contract", self.named.actuator_source)
        self.assertEqual("asset", self.body_asset.actuator_source)

        rebuilt = self.named.robot_cfg()
        self.assertEqual(
            ["IdealPdActuatorCfg"] * 3,
            [type(a).__name__ for a in rebuilt.articulation.actuators],
        )
        self.assertEqual(
            (40.0, 1.0, 60.0),
            (
                rebuilt.articulation.actuators[0].stiffness,
                rebuilt.articulation.actuators[0].damping,
                rebuilt.articulation.actuators[0].effort_limit,
            ),
        )

        kept = self.body_asset.robot_cfg()
        self.assertEqual(
            ["XmlActuatorCfg"] * 3, [type(a).__name__ for a in kept.articulation.actuators]
        )
        # 出生高与默认姿仍被覆盖（技能层只改技能关心的那几项）
        self.assertEqual((0.0, 0.0, 0.4), tuple(kept.init_state.pos))
        self.assertEqual(
            {".*hip_joint": 0.0, ".*thigh_joint": 0.0, ".*calf_joint": 0.0},
            dict(kept.init_state.joint_pos),
        )

        # armature_override 在执行真值在 MJCF 的机型上无处落地 ⇒ 显式判红，不静默丢
        from adapters.mjlab.kits.quadruped_kit.skills import from_contract

        with self.assertRaises(ValueError):
            from_contract(
                _synthetic_contract(),
                spec_fn=_synthetic_body_asset_spec,
                base_entity_cfg=_synthetic_body_asset_entity_cfg,
                init_base_height=0.4,
                armature_override=0.0,
            )

    def test_right_legs_derive_from_the_leg_markers(self):
        """右腿 = 腿标记含 R 且不含 L（两台腿序不同，派生值跟着各自的腿序走）。"""
        self.assertEqual((0, 2), self.body_asset.right_leg_indices())  # r2,l1,r1,l2
        self.assertEqual((1, 3), GO2.right_leg_indices())  # FL,FR,RL,RR


# --- 第四份资产：**契约角色词与 body 词表不相干**（lite3 实况） ---------------------------
#
# 真例：lite3 的契约角色是 `hipx / hipy / knee`（关节名 `*_HipX_joint` 等），
# 但 MJCF 的 body 叫 `*_HIP / *_THIGH / *_SHANK / *_FOOT` —— **两套词表没有共同 token**。
# 于是"腿杆惩罚"那套按角色词拼的写法（`(?:<腿>)_(?:knee)`）在它身上空匹配，
# 而按**结构**派生（腿身 body 去掉髋外展与足端）得到 `THIGH + SHANK` ✓。
# 这条锁住的是：派生走结构、不走词表。

_SYNTHETIC_ROLEWORD_JOINTS = ("HipX", "HipY", "Knee")
_SYNTHETIC_ROLEWORD_XML = """<mujoco model="synthetic_quad_roleword">
  <default>
    <geom type="capsule" size="0.02 0.05" rgba="0.6 0.6 0.6 1"/>
    <joint axis="0 1 0" damping="0.1"/>
  </default>
  <worldbody>
    <body name="chassis" pos="0 0 0.4">
      <freejoint name="chassis_free"/>
      <geom type="box" size="0.2 0.08 0.05"/>
      <site name="imu" pos="0 0 0" size="0.01"/>
{legs}
    </body>
  </worldbody>
  <actuator>
{actuators}
  </actuator>
  <sensor>
    <gyro name="imu_ang_vel" site="imu"/>
    <velocimeter name="imu_lin_vel" site="imu"/>
    <subtreeangmom name="root_angmom" body="chassis"/>
  </sensor>
</mujoco>
"""

#: lite3 式腿：**body 词表**（HIP/THIGH/SHANK/FOOT）与**角色词表**（HipX/HipY/Knee）无关。
_SYNTHETIC_ROLEWORD_LEG = """            <body name="{leg}_HIP" pos="0.15 {side}0.06 0">
              <joint name="{leg}_HipX_joint" axis="0 0 1"/>
              <joint name="{leg}_HipY_joint" axis="0 1 0"/>
              <geom name="{leg}_HIP_collision" fromto="0 0 0 0 0 -0.06"/>
              <body name="{leg}_THIGH" pos="0 0 -0.06">
                <joint name="{leg}_Knee_joint" axis="0 1 0"/>
                <geom name="{leg}_THIGH_collision" fromto="0 0 0 0 0 -0.12"/>
                <body name="{leg}_SHANK" pos="0 0 -0.12">
                  <geom name="{leg}_SHANK_collision" fromto="0 0 0 0 0 -0.12"/>
                  <body name="{leg}_FOOT" pos="0 0 -0.12">
                    <geom name="{leg}_foot_collision" type="sphere" size="0.02"/>
                  </body>
                </body>
              </body>
            </body>
"""


def _synthetic_roleword_xml() -> str:
    legs = "\n".join(
        _SYNTHETIC_ROLEWORD_LEG.format(leg=leg, side="-" if leg.startswith("r") else "")
        for leg in _SYNTHETIC_MODEL_ORDER
    )
    actuators = "\n".join(
        f'    <position name="{leg}_{joint}_joint" joint="{leg}_{joint}_joint" kp="40" kv="1"/>'
        for leg in _SYNTHETIC_LEGS
        for joint in _SYNTHETIC_ROLEWORD_JOINTS
    )
    return _SYNTHETIC_ROLEWORD_XML.format(legs=legs, actuators=actuators)


def _synthetic_roleword_spec() -> mujoco.MjSpec:
    return mujoco.MjSpec.from_string(_synthetic_roleword_xml())


def _synthetic_roleword_contract() -> dict:
    leg_pattern = ["hipx", "hipy", "knee"]
    contract = _synthetic_contract()
    contract["robot_id"] = "synthetic_roleword_quad"
    contract["morphology"] = {
        **contract["morphology"],
        "leg_pattern": leg_pattern,
    }
    contract["action"] = {
        **contract["action"],
        "joint_order": [
            f"{leg}_{joint}_joint" for leg in _SYNTHETIC_LEGS for joint in _SYNTHETIC_ROLEWORD_JOINTS
        ],
    }
    contract["actuator_profile"] = {
        "by_role": {
            role: {"stiffness": 40.0, "damping": 1.0, "effort": 60.0, "action_scale": 0.25}
            for role in leg_pattern
        }
    }
    return contract


def _synthetic_roleword_entity_cfg():
    from mjlab.actuator import XmlActuatorCfg
    from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
    from mjlab.utils.spec_config import CollisionCfg

    return EntityCfg(
        init_state=EntityCfg.InitialStateCfg(pos=(0.0, 0.0, 0.4)),
        collisions=(
            CollisionCfg(
                geom_names_expr=(".*",),
                contype=1,
                conaffinity=0,
                condim={".*foot.*": 3, ".*": 1},
                priority={".*foot.*": 1, ".*": 0},
            ),
        ),
        spec_fn=_synthetic_roleword_spec,
        articulation=EntityArticulationInfoCfg(
            actuators=tuple(
                XmlActuatorCfg(target_names_expr=(f".*_{joint}_joint",), command_field="position")
                for joint in _SYNTHETIC_ROLEWORD_JOINTS
            ),
            soft_joint_pos_limit_factor=0.9,
        ),
    )


class RoleVocabularyMismatchTests(unittest.TestCase):
    """契约角色词与 body 词表不相干的资产：惩罚集合按**结构**派生。"""

    @classmethod
    def setUpClass(cls):
        from adapters.mjlab.kits.quadruped_kit.skills import from_contract

        cls.binding = from_contract(
            _synthetic_roleword_contract(),
            spec_fn=_synthetic_roleword_spec,
            base_entity_cfg=_synthetic_roleword_entity_cfg,
            init_base_height=0.4,
        )

    def test_penalized_links_come_from_structure_not_vocabulary(self):
        # 角色词（hipx/hipy/knee）与 body 词（HIP/THIGH/SHANK/FOOT）无共同 token：
        # 髋外展关节挂在 `<腿>_HIP` 上 ⇒ 该 body 排除；足端 body 排除；余下 THIGH + SHANK。
        self.assertEqual(
            ("r2_THIGH", "r2_SHANK", "l1_THIGH", "l1_SHANK", "r1_THIGH", "r1_SHANK",
             "l2_THIGH", "l2_SHANK"),
            self.binding.penalized_link_bodies(),
        )
        self.assertEqual(
            ("body", r"(?:r2|l1|r1|l2)_(?:THIGH|SHANK)"),
            self.binding.penalized_contact_match(),
        )
        # 角色词拼出来的几何模式在它身上空匹配（正是走 body 的理由）
        resolved = {
            name
            for name in self.binding.geom_names
            if re.fullmatch(self.binding.penalized_geom_pattern, name)
        }
        self.assertEqual(set(), resolved)


if __name__ == "__main__":
    unittest.main()
