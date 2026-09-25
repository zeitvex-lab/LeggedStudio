"""族级 WTW（周期步态先验）技能的回归锁：真行为，不是"名字统一"。

覆盖五条判据（每条都对应一次真实的静默失效）：

1. **动作接口**：`joint_pos` 目标名序 == 契约 `action.joint_order`（字面名 + `preserve_order`），
   缩放 == profile 的 `action_scale`（源配方全关节 0.25 标量）——不是 `.*` 正则序；
2. **派生几何**：足端几何模式 / 足端帧 / **足端链接 body** / 非足端 body 模式全部从
   绑定派生，且必须在真实编译 MJCF 上解析（源配方写死的 `FR_foot_collision`、`FL` 站点、
   `<腿>_calf`、`^(?!.*_calf).*` 由族级派生复现 —— 逐字面量核对）；
3. **状态配方**：startup 事件 `wtw_state_init` 携带 profile 数据（θ 池 / 行为区间 / 初值），
   状态可在 manager 构造期（事件应用前）被惰性建立；reset 事件按区间重采样；
4. **profile 驱动**：换一份 profile（动作缩放 / θ 池 / 区间 / 奖励权重）后数值必须跟着变；
5. **族可移植**：第二台真实机型（unitree_b2，腿序 FR/FL/RR/RL 与 go2 不同）用**同一份 Kit
   实现**建出合法 cfg 并在真实环境里 reset + step；足端链接/几何解析各自正确。
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GO2_PACKAGE = ROOT / "assets" / "robots" / "unitree_go2"
GO2_SOURCE = GO2_PACKAGE / "training" / "source"
B2_PACKAGE = ROOT / "assets" / "robots" / "unitree_b2"
B2_SOURCE = B2_PACKAGE / "training" / "source"
for _path in (str(ROOT), str(GO2_PACKAGE), str(GO2_SOURCE), str(B2_PACKAGE), str(B2_SOURCE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:  # 训练栈不可用时整文件跳过（与 adapters/mjlab 其它测试同口径）
    import mjlab  # noqa: F401
    import torch
except ImportError as _exc:  # pragma: no cover
    raise unittest.SkipTest(f"训练栈不可用: {_exc}")

from local_tasks import mjlab_extension  # noqa: E402

mjlab_extension.register()

from adapters.mjlab.kits.quadruped_kit.skills.wtw import config as kit_wtw  # noqa: E402
from adapters.mjlab.kits.quadruped_kit.skills.wtw import mdp as kit_wtw_mdp  # noqa: E402
from adapters.mjlab.kits.quadruped_kit.skills.wtw.profile import WtwProfile  # noqa: E402
from local_tasks.robots.unitree.go2.tasks.locomotion import wtw as go2_wtw  # noqa: E402
from local_tasks.robots.unitree.go2.tasks.locomotion.binding import GO2_VELOCITY  # noqa: E402


def contract(robot: str) -> dict:
    return json.loads(
        (ROOT / "assets" / "robots" / robot / "contract.json").read_text(encoding="utf-8-sig")
    )


def compiled(robot: str):
    if robot == "unitree_go2":
        return mjlab_extension.get_spec().compile()
    import b2_velocity.robot_constants as b2_robot

    return b2_robot.get_spec().compile()


def _model_inventory(model) -> dict[str, list[str]]:
    return {
        "geom": [model.geom(i).name or "" for i in range(model.ngeom)],
        "site": [model.site(i).name or "" for i in range(model.nsite)],
        "body": [model.body(i).name or "" for i in range(model.nbody)],
    }


class Go2WtwCfgTests(unittest.TestCase):
    """纯配置判据（不建环境）：动作序 / 派生几何 / 状态配方 / profile 驱动。"""

    @classmethod
    def setUpClass(cls):
        cls.flat = go2_wtw.go2_wtw_flat_env_cfg()
        cls.rough = go2_wtw.go2_wtw_rough_env_cfg()
        cls.play = go2_wtw.go2_wtw_flat_env_cfg(play=True)
        cls.model = mjlab_extension.get_spec().compile()
        cls.inventory = _model_inventory(cls.model)

    def test_action_interface_is_the_contract_order_and_profile_scale(self):
        order = tuple(contract("unitree_go2")["action"]["joint_order"])
        term = self.flat.actions["joint_pos"]
        self.assertEqual(order, tuple(term.actuator_names))
        self.assertTrue(term.preserve_order)
        self.assertEqual(go2_wtw.WTW.action_scale, term.scale)
        # 源配方：`cfg.actions["joint_pos"].scale = 0.25`（标量，全关节同值）
        self.assertEqual(0.25, term.scale)

    def test_derived_geometry_reproduces_the_source_literals(self):
        inventory = self.inventory
        sensors = {sensor.name: sensor for sensor in self.flat.scene.sensors}
        # 足端几何：契约腿序（= 源实现 FR/FL/RR/RL 的同一集合）
        feet = tuple(sensors["feet_ground_contact"].primary.pattern)
        self.assertEqual(GO2_VELOCITY.foot_geoms, feet)
        self.assertEqual(
            {"FL_foot_collision", "FR_foot_collision", "RL_foot_collision", "RR_foot_collision"},
            set(feet),
        )
        # 足端帧：契约腿序的 site（源实现写 ("FR","FL","RR","RL") —— 同一集合）
        frames = tuple(frame.name for frame in sensors["foot_height_scan"].frame)
        self.assertEqual(("FL", "FR", "RL", "RR"), frames)
        self.assertEqual(set(frames), set(GO2_VELOCITY.foot_sites()))
        # 非足端模式：族角色派生 —— go2 上复现源实现的字面量 `^(?!.*_calf).*`
        pattern = sensors["nonfoot_ground_touch"].primary.pattern
        self.assertEqual(r"^(?!.*_calf).*", pattern)
        resolved = {name for name in inventory["body"] if re.fullmatch(pattern, name)}
        self.assertEqual(
            {name for name in inventory["body"] if name and not name.endswith("_calf")},
            resolved,
        )
        self.assertTrue(resolved)  # 空匹配 = 经典静默失效
        # 根 body 帧（源写 `base_link`）
        self.assertEqual("base_link", sensors["terrain_scan"].frame.name)
        self.assertEqual(GO2_VELOCITY.root_body, sensors["terrain_scan"].frame.name)

    def test_foot_link_bodies_are_derived_from_the_foot_geoms(self):
        """足端位置/速度的 body = 足端几何的父 body（go2 = 小腿，源配方写 `<腿>_calf`）。"""
        bodies = GO2_VELOCITY.foot_link_bodies()
        self.assertEqual(("FL_calf", "FR_calf", "RL_calf", "RR_calf"), bodies)
        for geom, body in zip(GO2_VELOCITY.foot_geoms, bodies, strict=True):
            index = next(i for i in range(self.model.ngeom) if self.model.geom(i).name == geom)
            self.assertEqual(
                body, self.model.body(int(self.model.geom_bodyid[index])).name
            )
        asset_cfg = self.flat.rewards["quad_periodic_gait"].params["asset_cfg"]
        self.assertEqual(bodies, tuple(asset_cfg.body_names))
        self.assertEqual(4, self.flat.rewards["quad_periodic_gait"].params["sensor_cfg"].body_ids[-1] + 1)

    def test_state_recipe_event_carries_the_profile_numbers(self):
        """startup 事件是状态配方（初值 / θ 池 / 采样区间）的唯一声明处。"""
        event = self.flat.events["wtw_state_init"]
        self.assertEqual("startup", event.mode)
        self.assertIs(kit_wtw_mdp.init_behavior_state, event.func)
        params = event.params
        self.assertEqual(4, params["legs"])
        self.assertEqual(go2_wtw.WTW.theta_pool, params["theta_pool"])
        profile = go2_wtw.WTW
        self.assertEqual(
            {
                "gait_period": tuple(profile.gait_period_range),
                "foot_clearance": tuple(profile.foot_clearance_range),
                "base_height": tuple(profile.base_height_range),
                "pitch": tuple(profile.pitch_range),
            },
            {key: tuple(value) for key, value in params["ranges"].items()},
        )
        self.assertEqual(
            {"gait_period": 0.45, "foot_clearance": 0.08, "base_height": 0.27, "pitch": 0.0},
            params["initial"],
        )
        resample = self.flat.events["wtw_behavior_resample"]
        self.assertEqual("reset", resample.mode)
        self.assertEqual({}, resample.params)  # 采样数据来自状态，不从事件参数再抄一份

    def test_profile_numbers_drive_the_family_config(self):
        custom = replace(
            go2_wtw.WTW,
            action_scale=0.5,
            reward_weights={**go2_wtw.WTW.reward_weights, "quad_periodic_gait": 2.5},
            base_height_range=(0.15, 0.25),
            track_ang_vel_std=1.234,
        )
        cfg = kit_wtw.make_env_cfg(GO2_VELOCITY, custom, terrain_profile="flat")
        self.assertEqual(0.5, cfg.actions["joint_pos"].scale)
        self.assertEqual(2.5, cfg.rewards["quad_periodic_gait"].weight)
        self.assertEqual(1.234, cfg.rewards["tracking_ang_vel"].params["std"])
        init = cfg.events["wtw_state_init"].params
        self.assertEqual((0.15, 0.25), init["ranges"]["base_height"])
        # 权重表逐项接线（漏一项就是静默少奖励）
        for name, weight in custom.reward_weights.items():
            self.assertEqual(weight, cfg.rewards[name].weight, name)

    def test_flat_and_play_branches_follow_the_source_recipe(self):
        rough, flat, play = self.rough, self.flat, self.play
        self.assertEqual(500, rough.sim.mujoco.ccd_iterations)
        self.assertEqual(500, rough.sim.contact_sensor_maxmatch)
        self.assertEqual(1500, rough.sim.njmax)
        self.assertEqual(300, flat.sim.njmax)
        self.assertEqual(50, flat.sim.mujoco.ccd_iterations)
        self.assertEqual(64, flat.sim.contact_sensor_maxmatch)
        # flat 档保留基座 nconmax 与 terrain_scan 传感器（与族级 velocity 的 flat 收尾不同）
        self.assertEqual(35, flat.sim.nconmax)
        self.assertIn("terrain_scan", [s.name for s in flat.scene.sensors])
        self.assertIn("height_scan", flat.observations["actor"].terms)
        self.assertEqual("plane", flat.scene.terrain.terrain_type)
        self.assertIsNone(flat.scene.terrain.terrain_generator)
        self.assertNotIn("out_of_terrain_bounds", flat.terminations)
        self.assertEqual(["command_vel"], list(flat.curriculum))
        self.assertEqual(["terrain_levels", "command_vel"], list(rough.curriculum))
        # play：回合拉满 / 关噪声 / 清课程（源实现的四条）
        self.assertEqual(int(1e9), play.episode_length_s)
        self.assertFalse(play.observations["actor"].enable_corruption)
        self.assertEqual({}, play.curriculum)

    def test_reward_table_and_observations_match_the_source_shape(self):
        self.assertEqual(
            [
                "tracking_lin_vel", "tracking_ang_vel", "tracking_base_height",
                "tracking_orientation", "tracking_foot_clearance", "quad_periodic_gait",
                "lin_vel_z", "ang_vel_xy", "dof_vel", "dof_acc", "action_rate",
                "action_smoothness", "torques", "foot_landing_vel", "hip_pos",
                "dof_pos_limits", "collision",
            ],
            list(self.flat.rewards),
        )
        for group in ("actor", "critic"):
            terms = self.flat.observations[group].terms
            self.assertEqual(
                ["wtw_clock", "wtw_theta", "wtw_behavior"],
                [name for name in terms if name.startswith("wtw_")],
            )
            self.assertEqual(0.02, terms["wtw_clock"].params["dt"])
        self.assertEqual(
            r"^(?!.*_calf).*",
            self.flat.scene.sensors[3].primary.pattern,
        )


class Go2WtwRuntimeTests(unittest.TestCase):
    """真实环境判据：状态建立/推进、动作序、reset 重采样、奖励有限。"""

    @classmethod
    def setUpClass(cls):
        from mjlab.envs import ManagerBasedRlEnv

        cls.cfg = go2_wtw.go2_wtw_flat_env_cfg()
        cls.cfg.scene.num_envs = 2
        cls.env = ManagerBasedRlEnv(cls.cfg, device="cpu")

    @classmethod
    def tearDownClass(cls):
        cls.env.close()

    def test_state_is_built_and_advances(self):
        state = self.env._wtw_state
        self.assertEqual((2, 4), tuple(state["theta"].shape))
        self.assertEqual((2, 8), tuple(state["clock"].shape))
        obs, _, _, _, _ = self.env.step(
            torch.full((2, self.env.action_manager.total_action_dim), 0.1, device="cpu")
        )
        self.assertTrue(torch.isfinite(obs["actor"]).all())
        # 相位推进（clock 观测的副作用）与步态时钟形状
        phase = state["phi"].clone()
        self.assertGreater(float(phase.abs().max()), 0.0)
        clock_cfg = self.env.observation_manager.get_term_cfg("actor", "wtw_clock")
        self.assertIsNotNone(clock_cfg)

    def test_reset_resamples_behavior_within_the_profile_ranges(self):
        self.env.reset()
        state = self.env._wtw_state
        pool = go2_wtw.WTW.theta_pool
        for leg_idx in range(4):
            values = state["theta"][:, leg_idx]
            self.assertTrue(
                all(any(abs(float(v) - candidate) < 1e-9 for candidate in pool[leg_idx]) for v in values)
            )
        period = state["gait_period"]
        low, high = go2_wtw.WTW.gait_period_range
        self.assertTrue(bool(((period >= low) & (period <= high)).all()))
        height = state["base_height_target"]
        low, high = go2_wtw.WTW.base_height_range
        self.assertTrue(bool(((height >= low) & (height <= high)).all()))

    def test_hip_pos_counts_the_family_role_joints(self):
        """`hip_pos` 按族角色选髋（源实现按名字含 "hip" 扫实体关节）—— 同集合、同方程。"""
        env = self.env
        env.reset()
        robot = env.scene["robot"]
        hips = [i for i, name in enumerate(robot.joint_names) if "hip" in name]
        ids, _ = robot.find_joints(tuple(contract("unitree_go2")["action"]["joint_order"]), preserve_order=True)
        expected = torch.sum(
            torch.square(
                robot.data.joint_pos[:, ids][:, hips]
                - robot.data.default_joint_pos[:, ids][:, hips]
            ),
            dim=-1,
        )
        got = kit_wtw_mdp.hip_pos(env)
        self.assertTrue(torch.allclose(expected, got, atol=1e-6))

    def test_reward_terms_stay_finite_and_bounded(self):
        env = self.env
        env.reset()
        env.step(torch.full((2, env.action_manager.total_action_dim), 0.0, device="cpu"))
        gauge = float(env.reward_manager.compute(dt=env.step_dt).sum())
        self.assertIsInstance(gauge, float)
        cfg_term = env.reward_manager.get_term_cfg("quad_periodic_gait")
        value = cfg_term.func(
            env,
            sensor_cfg=kit_wtw_mdp.ContactSensorRef("feet_ground_contact", (0, 1, 2, 3)),
            asset_cfg=cfg_term.params["asset_cfg"],
            a_swing=0.0,
            b_swing=0.5,
        )
        self.assertTrue(torch.isfinite(value).all())
        self.assertLessEqual(float(value.max()), 1.0)
        self.assertGreater(float(value.min()), 0.0)

    def test_action_targets_resolve_to_the_contract_order(self):
        term = self.env.action_manager.get_term("joint_pos")
        self.assertEqual(
            tuple(contract("unitree_go2")["action"]["joint_order"]), tuple(term.target_names)
        )
        self.assertEqual(tuple(GO2_VELOCITY.joint_order), tuple(term.target_names))


class B2WtwReuseTests(unittest.TestCase):
    """第二台机型（unitree_b2）：同一份 Kit 实现 + 只给绑定/数据（零 Kit 改动）。"""

    @classmethod
    def setUpClass(cls):
        import b2_wtw.env_cfg as b2_wtw_env

        cls.module = b2_wtw_env
        cls.cfg = b2_wtw_env.b2_wtw_env_cfg()
        cls.model = compiled("unitree_b2")

    def test_action_interface_follows_the_b2_contract_order(self):
        order = tuple(contract("unitree_b2")["action"]["joint_order"])
        term = self.cfg.actions["joint_pos"]
        self.assertEqual(order, tuple(term.actuator_names))
        self.assertTrue(term.preserve_order)
        self.assertEqual(0.25, term.scale)
        # b2 的契约腿序是 FR/FL/RR/RL（与 go2 不同）—— 动作序跟契约，不跟 MJCF
        self.assertEqual("FR_hip_joint", order[0])

    def test_derived_patterns_track_b2_only(self):
        inventory = _model_inventory(self.model)
        sensors = {sensor.name: sensor for sensor in self.cfg.scene.sensors}
        binding = self.module.BINDING
        self.assertEqual(("FR_foot_collision", "FL_foot_collision", "RR_foot_collision", "RL_foot_collision"),
                         tuple(sensors["feet_ground_contact"].primary.pattern))
        for name in sensors["feet_ground_contact"].primary.pattern:
            self.assertIn(name, inventory["geom"])
        frames = tuple(frame.name for frame in sensors["foot_height_scan"].frame)
        self.assertEqual(binding.foot_sites(), frames)
        for name in frames:
            self.assertIn(name, inventory["site"])
        pattern = sensors["nonfoot_ground_touch"].primary.pattern
        resolved = {name for name in inventory["body"] if re.fullmatch(pattern, name)}
        self.assertEqual(
            {name for name in inventory["body"] if name and not name.endswith("_calf")},
            resolved,
        )
        # 足端链接 body：b2 的足端几何挂在小腿上（与 go2 同构）
        self.assertEqual(
            ("FR_calf", "FL_calf", "RR_calf", "RL_calf"), binding.foot_link_bodies()
        )
        asset_cfg = self.cfg.rewards["quad_periodic_gait"].params["asset_cfg"]
        self.assertEqual(binding.foot_link_bodies(), tuple(asset_cfg.body_names))

    def test_b2_env_resets_and_steps(self):
        from mjlab.envs import ManagerBasedRlEnv

        cfg = self.module.b2_wtw_env_cfg()
        cfg.scene.num_envs = 1
        env = ManagerBasedRlEnv(cfg, device="cpu")
        try:
            env.reset()
            obs, reward, terminated, truncated, _ = env.step(
                torch.full((1, env.action_manager.total_action_dim), 0.2, device=cfg and "cpu")
            )
            self.assertTrue(torch.isfinite(obs["actor"]).all())
            self.assertTrue(torch.isfinite(reward).all())
            term = env.action_manager.get_term("joint_pos")
            self.assertEqual(
                tuple(contract("unitree_b2")["action"]["joint_order"]), tuple(term.target_names)
            )
            self.assertIn("_wtw_state", env.__dict__)
            self.assertEqual((1, 4), tuple(env._wtw_state["theta"].shape))
        finally:
            env.close()

    def test_b2_wtw_profile_is_declared_in_the_family_skill(self):
        """新档案的 task_name 必须在族声明里被唯一认领（audit_families 的判据）。"""
        family = json.loads(
            (ROOT / "registry" / "families" / "quadruped.json").read_text(encoding="utf-8-sig")
        )
        profile = json.loads(
            (B2_PACKAGE / "training" / "profiles" / "b2-wtw.json").read_text(encoding="utf-8-sig")
        )
        owners = [
            skill["skill_id"]
            for skill in family["skills"]
            if profile["task_name"] in (skill.get("task_names") or [])
        ]
        self.assertEqual(["velocity"], owners)
        # 入口符号与实现同源（family Kit 的 WTW 技能）
        self.assertTrue(profile["entrypoints"]["env"].startswith("b2_wtw."))
        self.assertIs(kit_wtw.make_env_cfg, go2_wtw.kit_wtw.make_env_cfg)


if __name__ == "__main__":
    unittest.main()
