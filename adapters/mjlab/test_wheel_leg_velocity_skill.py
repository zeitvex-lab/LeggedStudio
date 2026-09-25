"""族级轮足 velocity 技能层：robot-agnostic 绑定 + 工厂的回归锁。

被测对象两部分：

* `adapters/mjlab/kits/wheel_leg_kit/skills/`（族级实现：绑定从契约/MJCF 派生、
  技能配方在配置工厂里，**不得含任何机型名/机型数值**）；
* 它的第一个客户 `assets/robots/unitree_go2w/training/source/go2w_velocity/`
  （薄委托：绑定 + 一份机型 profile 数据）。

覆盖四类判据：
① 族层无机型字面量（文本级 + 声明级）；
② go2w 绑定的腿/轮拆分与动作序 = 契约 `action.joint_order`（**不是** MJCF 序——
   go2w 两者不同，MJCF 是按腿混排、契约是腿先轮后）；
③ 族工厂真跑：建环境 + reset + 非零动作 step，且动作项运行时目标序 = 契约序；
④ 换一台合成机型（另一套腿标记/角色词）只给数据即可产出合法 cfg（"移植只改数据"）。
"""

from __future__ import annotations

import importlib
import json
import re
import sys
import unittest
from dataclasses import is_dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GO2W_ROOT = ROOT / "assets" / "robots" / "unitree_go2w"
GO2W_SOURCE = GO2W_ROOT / "training" / "source"
SKILLS_DIR = ROOT / "adapters" / "mjlab" / "kits" / "wheel_leg_kit" / "skills"

for _path in (str(ROOT), str(GO2W_ROOT), str(GO2W_SOURCE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def _go2w_contract() -> dict:
    return json.loads((GO2W_ROOT / "contract.json").read_text(encoding="utf-8-sig"))


def _skills_module():
    for name in list(sys.modules):
        if name.startswith("go2w_velocity"):
            del sys.modules[name]
    import importlib

    return importlib.import_module("adapters.mjlab.kits.wheel_leg_kit.skills")


def _go2w_profile():
    return importlib.import_module("go2w_velocity.profile")


def _go2w_binding():
    return importlib.import_module("go2w_velocity.binding")


def _resolve_pose(pose: dict, joint: str) -> float | None:
    """按 mjlab 口径解析 `joint_pos` 模式串（精确名优先，再 fullmatch）。"""
    if joint in pose:
        return pose[joint]
    for key, value in pose.items():
        try:
            if re.fullmatch(key, joint):
                return value
        except re.error:
            if key == joint:
                return value
    return None


class KitIsRobotAgnosticTest(unittest.TestCase):
    """族层不得出现机型身份：机型名、腿标记、机型数值。（约束 1）"""

    #: 机型身份词（出现在**代码面**即判红；docstring/注释里的出处说明合法，与
    #: `tools/audit_families.py` 的 Kit 方向判据同口径）。
    FORBIDDEN_WORDS = ("go2w", "unitree")
    #: 机型数值字面量：轮半径/轮距/动作缩放/并行环境数——必须由契约或 profile 传入。
    FORBIDDEN_NUMBERS = ("0.09", "0.19", "35.0", "4096")
    #: 腿标记（go2w = FL/FR/RL/RR；族层只认契约给的 leg_ids）。
    LEG_MARKERS = re.compile(r"(?<![A-Za-z0-9])(FR|FL|RR|RL)(?![A-Za-z0-9])")

    def _skill_sources(self) -> list[Path]:
        return [
            path
            for path in sorted(SKILLS_DIR.rglob("*.py"))
            if "__pycache__" not in path.parts
        ]

    @staticmethod
    def _code_faces(path: Path) -> list[str]:
        """AST 级"代码面"的字面量/标识符（docstring 与注释不算）。"""
        import ast

        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.body and isinstance(node.body[0], ast.Expr):
                    docstrings.add(id(node.body[0].value))
        faces: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and not isinstance(node.value, bool):
                if id(node) not in docstrings and node.value is not None:
                    faces.append(str(node.value))
            elif isinstance(node, ast.Name):
                faces.append(node.id)
            elif isinstance(node, ast.Attribute):
                faces.append(node.attr)
            elif isinstance(node, ast.keyword) and node.arg:
                faces.append(node.arg)
            elif isinstance(node, ast.arg):
                faces.append(node.arg)
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                faces.append(node.name)
            elif isinstance(node, ast.alias):
                faces.append(node.name)
        return faces

    def test_skill_sources_exist_and_are_robot_free(self):
        paths = self._skill_sources()
        self.assertTrue(paths, f"族级技能层不存在：{SKILLS_DIR}")
        problems: list[str] = []
        for path in paths:
            text = path.read_text(encoding="utf-8")
            # 1) 不得 import 机型包（与 tools/audit_families.py 的 Kit 反向依赖同口径）
            for lineno, line in enumerate(text.splitlines(), start=1):
                if re.match(r"^\s*(from|import)\s+[^\n]*?(assets\.robots|local_tasks)", line):
                    problems.append(f"{path.relative_to(ROOT)}:{lineno}: 反向 import 机型包")
            # 2) 代码面不得出现机型身份词/腿标记/机型数值
            for face in self._code_faces(path):
                lowered = face.lower()
                for word in self.FORBIDDEN_WORDS:
                    if word in lowered:
                        problems.append(f"{path.relative_to(ROOT)}: 代码面出现机型身份词 {face!r}")
                for number in self.FORBIDDEN_NUMBERS:
                    if face == number:
                        problems.append(f"{path.relative_to(ROOT)}: 代码面出现机型数值 {face!r}")
                if self.LEG_MARKERS.search(face):
                    problems.append(f"{path.relative_to(ROOT)}: 代码面出现机型腿标记 {face!r}")
        self.assertEqual([], problems, "族级技能层含机型字面量：\n" + "\n".join(problems))

    def test_package_side_does_not_carry_the_skill_implementation(self):
        """客户端不许留第二份实现：env_cfgs 只装配（不得再定义奖励表/事件表）。"""
        text = (GO2W_SOURCE / "go2w_velocity" / "env_cfgs.py").read_text(encoding="utf-8")
        self.assertNotIn("RewardTermCfg(", text, "go2w 客户端仍在自建奖励表（应为薄委托）")
        self.assertNotIn("EventTermCfg(", text, "go2w 客户端仍在自建事件表（应为薄委托）")

    def test_family_module_resolves_the_family_declaration(self):
        skills = _skills_module()
        family = importlib.import_module(
            "adapters.mjlab.kits.wheel_leg_kit.skills.family"
        )
        declaration = json.loads(
            (ROOT / "registry" / "families" / "wheel_leg.json").read_text(encoding="utf-8-sig")
        )
        self.assertEqual(ROOT, family.repo_root())
        self.assertEqual(tuple(declaration["joint_roles"]), family.family_roles())
        aliases = family.role_aliases()
        self.assertEqual(("hip", "hipx", "hip_abduction"), aliases["hip_abduction"])
        self.assertEqual(("thigh", "hipy", "hip_pitch"), aliases["hip_pitch"])
        self.assertEqual(("calf", "knee"), aliases["knee"])
        self.assertEqual(("wheel",), aliases["wheel"])
        # 别名解析是"角色"而不是"字符串匹配 wheel"
        self.assertEqual("wheel", family.role_of_joint("FR_wheel_joint"))
        self.assertEqual("hip_abduction", family.role_of_joint("FL_hip_joint"))
        self.assertEqual("hip_pitch", family.role_of_joint("FL_thigh_joint"))
        self.assertEqual("knee", family.role_of_joint("FL_calf_joint"))
        self.assertIn("VelocityProfile", skills.__all__ if hasattr(skills, "__all__") else dir(skills))
        for name in ("WheelLegSkillBinding", "from_contract", "make_velocity_env_cfg", "VelocityProfile"):
            self.assertTrue(hasattr(skills, name), f"skills 未再导出 {name}")

    def test_binding_and_profile_are_frozen_data(self):
        skills = _skills_module()
        self.assertTrue(is_dataclass(skills.VelocityProfile))
        with self.assertRaises(Exception):
            skills.VelocityProfile().init_base_height = 1.0  # type: ignore[misc]
        self.assertTrue(is_dataclass(skills.WheelLegSkillBinding))


class Go2wBindingTest(unittest.TestCase):
    """绑定 = 契约 + MJCF 真值；动作接口序以契约为准。（约束 1 + 目标形状）"""

    @classmethod
    def setUpClass(cls):
        cls.contract = _go2w_contract()
        cls.binding = _go2w_binding().GO2W
        cls.profile = _go2w_profile().ROUGH

    def test_leg_wheel_split_follows_contract_action_order_not_mjcf(self):
        order = tuple(self.contract["action"]["joint_order"])
        self.assertEqual(order, self.binding.leg_joint_order + self.binding.wheel_joint_order)
        self.assertEqual(12, len(self.binding.leg_joint_order))
        self.assertEqual(4, len(self.binding.wheel_joint_order))
        # 拆分口径 = 族角色（不是字符串找 "wheel"），且腿段里不许混进轮
        family = importlib.import_module("adapters.mjlab.kits.wheel_leg_kit.skills.family")
        roles = [family.role_of_joint(j) for j in self.binding.action_joint_order]
        self.assertNotIn("wheel", roles[:12])
        self.assertEqual(["wheel"] * 4, roles[12:])
        # MJCF 真值序是按腿混排（FL/FR/RL/RR × hip/thigh/calf/wheel）——两者必须不同，
        # 绑定必须站契约序（这正是"不许从 MJCF 推关节序"的理由）。
        model = self.binding.base_entity_cfg().spec_fn().compile()
        mjcf_joints = [
            model.joint(i).name
            for i in range(model.njnt)
            if model.jnt_type[i] != 0 and model.joint(i).name  # 0 = freejoint
        ]
        mjcf_legs = tuple(j for j in mjcf_joints if "wheel" not in j)
        self.assertEqual(16, len(mjcf_joints))
        self.assertNotEqual(self.binding.leg_joint_order, mjcf_legs, "绑定的腿序不该是 MJCF 序")
        self.assertEqual(set(mjcf_legs), set(self.binding.leg_joint_order))
        # 契约 morphology.wheel_indices 是对动作序的声明：交叉核对，防止两处真值漂移
        wheels = tuple(order[i] for i in self.contract["morphology"]["wheel_indices"])
        self.assertEqual(wheels, self.binding.wheel_joint_order)

    def test_action_scales_and_modes_come_from_contract(self):
        by_role = self.contract["actuator_profile"]["by_role"]
        roles = self.contract["morphology"]["leg_pattern"]
        for joint in self.binding.leg_joint_order:
            role = next(r for r in roles if r in joint)
            self.assertEqual("position", self.binding.control_modes[joint])
            self.assertAlmostEqual(by_role[role]["action_scale"], self.binding.action_scales[joint])
        for joint in self.binding.wheel_joint_order:
            self.assertEqual("velocity", self.binding.control_modes[joint])
            self.assertAlmostEqual(35.0, self.binding.action_scales[joint], msg=joint)
        # 分组视图（位置/速度）与 build_joint_actions 的入参口径一致
        self.assertEqual(set(self.binding.leg_joint_order), set(self.binding.position_action_scales))
        self.assertEqual(set(self.binding.wheel_joint_order), set(self.binding.velocity_action_scales))

    def test_actuator_groups_are_derived_suffixes(self):
        groups = {group.role: group for group in self.binding.actuator_groups}
        self.assertEqual(["hip", "thigh", "calf", "wheel"], [g.role for g in self.binding.actuator_groups])
        for role, group in groups.items():
            self.assertEqual(1, len(group.target_names_expr))
            pattern = group.target_names_expr[0]
            self.assertNotIn("FL", pattern, "致动器目标名不许写死腿标记")
            matched = [j for j in self.binding.action_joint_order if re.fullmatch(pattern, j)]
            role_joints = [
                j
                for j in self.binding.action_joint_order
                if importlib.import_module("adapters.mjlab.kits.wheel_leg_kit.skills.family").role_of_joint(j)
                in {
                    "hip": "hip_abduction",
                    "thigh": "hip_pitch",
                    "calf": "knee",
                    "wheel": "wheel",
                }[role]
            ]
            self.assertEqual(set(role_joints), set(matched), f"{role} 的目标名正则解析不一致")
        cfg = self.binding.robot_cfg()
        actuators = cfg.articulation.actuators
        self.assertEqual(4, len(actuators))
        self.assertEqual("BuiltinPositionActuatorCfg", type(actuators[0]).__name__)
        self.assertEqual("BuiltinPositionActuatorCfg", type(actuators[2]).__name__)
        self.assertEqual("BuiltinVelocityActuatorCfg", type(actuators[3]).__name__)
        self.assertAlmostEqual(20.0, actuators[0].stiffness)
        self.assertAlmostEqual(35.5, actuators[2].effort_limit)
        self.assertAlmostEqual(0.5, actuators[3].damping)
        self.assertAlmostEqual(0.9, cfg.articulation.soft_joint_pos_limit_factor)

    def test_pose_root_body_and_contact_pattern_are_declaration_derived(self):
        contract_pose = dict(
            zip(
                [item["name"] for item in self.contract["joints"]["actuated"]],
                self.contract["joints"]["default_pose"],
            )
        )
        self.assertEqual(contract_pose, self.binding.default_pose)
        cfg = self.binding.robot_cfg()
        self.assertEqual((0.0, 0.0, 0.4), cfg.init_state.pos)
        legacy_pose = {
            "FR_hip_joint": 0.1,
            "FR_thigh_joint": 0.9,
            "FR_calf_joint": -1.8,
            "FL_hip_joint": -0.1,
            "FL_thigh_joint": 0.9,
            "FL_calf_joint": -1.8,
            "RR_hip_joint": 0.1,
            "RR_thigh_joint": 0.9,
            "RR_calf_joint": -1.8,
            "RL_hip_joint": -0.1,
            "RL_thigh_joint": 0.9,
            "RL_calf_joint": -1.8,
            "FR_wheel_joint": 0.0,
            "FL_wheel_joint": 0.0,
            "RR_wheel_joint": 0.0,
            "RL_wheel_joint": 0.0,
        }
        # 初始姿必须逐个关节等于源配方的字面表（写法可压缩，解析结果必须一致）
        for joint, value in legacy_pose.items():
            self.assertAlmostEqual(value, _resolve_pose(cfg.init_state.joint_pos, joint), msg=joint)
        self.assertEqual("base_link", self.binding.root_body)
        from mjlab.managers.scene_entity_config import SceneEntityCfg

        leg_cfg = self.binding.leg_joint_cfg()
        wheel_cfg = self.binding.wheel_joint_cfg()
        self.assertIsInstance(leg_cfg, SceneEntityCfg)
        self.assertEqual(tuple(self.binding.leg_joint_order), tuple(leg_cfg.joint_names))
        self.assertTrue(leg_cfg.preserve_order)
        self.assertEqual(tuple(self.binding.wheel_joint_order), tuple(wheel_cfg.joint_names))
        self.assertTrue(wheel_cfg.preserve_order)
        self.assertEqual(r".*(FR|FL|RR|RL)_(wheel|foot).*", self.binding.wheel_contact_pattern)


class FamilyVelocityConfigTest(unittest.TestCase):
    """族工厂产出的 cfg：动作分段、四个变体结构、观测布局、profile 数值落点。"""

    @classmethod
    def setUpClass(cls):
        cls.skills = _skills_module()
        cls.binding = _go2w_binding().GO2W
        cls.profiles = _go2w_profile()

    def _variant(self, variant: str, profile):
        return self.skills.make_velocity_env_cfg(self.binding, profile, variant=variant)

    def test_action_terms_two_segments_in_policy_order(self):
        from mjlab.envs.mdp.actions import JointPositionActionCfg, JointVelocityActionCfg

        for variant, profile in (
            ("rough", self.profiles.ROUGH),
            ("flat", self.profiles.FLAT),
        ):
            with self.subTest(variant=variant):
                cfg = self._variant(variant, profile)
                self.assertEqual(["joint_pos", "wheel_vel"], list(cfg.actions))
                legs, wheels = cfg.actions["joint_pos"], cfg.actions["wheel_vel"]
                self.assertIsInstance(legs, JointPositionActionCfg)
                self.assertIsInstance(wheels, JointVelocityActionCfg)
                self.assertEqual(tuple(self.binding.leg_joint_order), tuple(legs.actuator_names))
                self.assertEqual(tuple(self.binding.wheel_joint_order), tuple(wheels.actuator_names))
                self.assertTrue(legs.preserve_order and wheels.preserve_order)
                self.assertAlmostEqual(0.5, legs.scale)
                self.assertAlmostEqual(35.0, wheels.scale)
                self.assertTrue(legs.use_default_offset)
                self.assertFalse(wheels.use_default_offset)
                self.assertEqual(0.0, wheels.offset)
        # legs-only：只剩腿段，缩放来自 profile（0.35）
        cfg = self._variant("flat_legs_only", self.profiles.LEGS_ONLY)
        self.assertEqual(["joint_pos"], list(cfg.actions))
        self.assertAlmostEqual(self.profiles.LEGS_ONLY.legs_only.action_scale, cfg.actions["joint_pos"].scale)

    def test_variants_keep_source_structure(self):
        rough = self._variant("rough", self.profiles.ROUGH)
        flat = self._variant("flat", self.profiles.FLAT)
        legs_only = self._variant("flat_legs_only", self.profiles.LEGS_ONLY)
        omni = self._variant("flat_legs_only_omni", self.profiles.OMNI)
        # 地形轴：rough = 生成器 + 课程 + 初始等级/profile 子地形；其余三档 = 平面
        self.assertEqual("generator", rough.scene.terrain.terrain_type)
        self.assertIn("terrain_levels", rough.curriculum)
        self.assertEqual(
            self.profiles.ROUGH.terrain_max_init_terrain_level,
            rough.scene.terrain.max_init_terrain_level,
        )
        tg = rough.scene.terrain.terrain_generator
        self.assertAlmostEqual(0.45, tg.sub_terrains["flat"].proportion)
        self.assertAlmostEqual(0.01, tg.sub_terrains["random_rough"].noise_step)
        self.assertAlmostEqual((0.0, 0.25), tuple(tg.sub_terrains["hf_pyramid_slope"].slope_range))
        self.assertAlmostEqual(0.0, tg.sub_terrains["pyramid_stairs"].proportion)
        for cfg in (flat, legs_only, omni):
            self.assertEqual("plane", cfg.scene.terrain.terrain_type)
            self.assertIsNone(cfg.scene.terrain.terrain_generator)
            self.assertNotIn("terrain_levels", cfg.curriculum)
        # 奖励结构：轮变体 = 轮奖励；legs-only = 轮速限幅/身高/站立
        for cfg in (rough, flat):
            for name in ("wheel_roll_tracking", "wheel_contact_bonus", "leg_motion_penalty"):
                self.assertIn(name, cfg.rewards)
            for name in ("wheel_spin_limit", "base_height", "stand_still", "low_base_height"):
                self.assertNotIn(name, cfg.rewards)
            for name in ("foot_air_time", "foot_clearance", "foot_slip", "soft_landing", "angular_momentum"):
                self.assertNotIn(name, cfg.rewards)
        self.assertEqual("leg_motion_penalty", flat.rewards["leg_motion_penalty"].func.__name__)
        self.assertEqual("adaptive_leg_motion_penalty", rough.rewards["leg_motion_penalty"].func.__name__)
        for cfg in (legs_only, omni):
            for name in ("wheel_roll_tracking", "wheel_contact_bonus", "leg_motion_penalty"):
                self.assertNotIn(name, cfg.rewards)
            for name in ("wheel_spin_limit", "base_height", "stand_still"):
                self.assertIn(name, cfg.rewards)
            self.assertIn("low_base_height", cfg.terminations)
        self.assertAlmostEqual(-4.0, legs_only.rewards["flat_orientation_l2"].weight)
        self.assertAlmostEqual(-3.5, omni.rewards["flat_orientation_l2"].weight)
        self.assertAlmostEqual(-0.1, omni.rewards["stand_still"].weight)
        self.assertNotIn("low_base_height", rough.terminations)
        # 传感器：轮-地接触（名字与主匹配都从绑定/族约定派生）
        self.assertEqual(["wheel_ground_contact"], [s.name for s in rough.scene.sensors])
        self.assertEqual(self.binding.wheel_contact_pattern, rough.scene.sensors[0].primary.pattern)

    def test_wheel_numbers_and_profile_land_where_source_had_them(self):
        cfg = self._variant("rough", self.profiles.ROUGH)
        roll = cfg.rewards["wheel_roll_tracking"]
        self.assertAlmostEqual(0.09, roll.params["wheel_radius"])
        self.assertAlmostEqual(0.19, roll.params["wheel_track"])
        self.assertAlmostEqual(8.0, roll.params["std"])
        self.assertAlmostEqual(2.0, roll.weight)
        self.assertAlmostEqual(0.5, cfg.rewards["wheel_contact_bonus"].weight)
        self.assertAlmostEqual(-0.08, cfg.rewards["leg_motion_penalty"].weight)
        self.assertAlmostEqual(-2.5, cfg.rewards["flat_orientation_l2"].weight)
        self.assertAlmostEqual(-0.1, cfg.rewards["body_ang_vel"].weight)
        self.assertEqual(("base_link",), cfg.rewards["body_ang_vel"].params["asset_cfg"].body_names)
        self.assertEqual(("base_link",), cfg.events["base_com"].params["asset_cfg"].body_names)
        self.assertNotIn("push_robot", cfg.events)
        # pose std 表：profile 给"角色→std"，族工厂展开成角色正则（解析集合 = 4 条腿）
        pose = cfg.rewards["pose"].params
        self.assertEqual(tuple(self.binding.leg_joint_order), tuple(pose["asset_cfg"].joint_names))
        for table, expected in (
            (pose["std_standing"], {"hip": 0.05, "thigh": 0.1, "calf": 0.15}),
            (pose["std_walking"], {"hip": 0.15, "thigh": 0.35, "calf": 0.5}),
            (pose["std_running"], {"hip": 0.15, "thigh": 0.35, "calf": 0.5}),
        ):
            resolved = {}
            for pattern, std in table.items():
                matched = [j for j in self.binding.leg_joint_order if re.fullmatch(pattern, j)]
                self.assertEqual(4, len(matched), f"{pattern} 应覆盖每条腿一次")
                resolved[matched[0].split("_", 1)[1].replace("_joint", "")] = std
            self.assertEqual(expected, resolved)

    def test_observations_and_commands_come_from_profile(self):
        cfg = self._variant("rough", self.profiles.ROUGH)
        actor_terms = [
            "base_ang_vel",
            "projected_gravity",
            "command",
            "joint_pos",
            "joint_vel",
            "wheel_joint_pos_rel",
            "wheel_joint_vel_rel",
            "actions",
        ]
        for group, expected_terms in (
            ("actor", actor_terms),
            ("critic", ["base_lin_vel"] + actor_terms),
        ):
            terms = cfg.observations[group].terms
            self.assertEqual(expected_terms, list(terms))
            self.assertEqual(tuple(self.binding.leg_joint_order), tuple(terms["joint_pos"].params["asset_cfg"].joint_names))
            self.assertEqual(tuple(self.binding.wheel_joint_order), tuple(terms["wheel_joint_pos_rel"].params["asset_cfg"].joint_names))
            self.assertEqual("wheel_joint_pos_rel", terms["wheel_joint_pos_rel"].func.__name__)
        actor, critic = cfg.observations["actor"].terms, cfg.observations["critic"].terms
        self.assertAlmostEqual(self.profiles.ROUGH.wheel_joint_pos_noise, actor["wheel_joint_pos_rel"].noise.n_max)
        self.assertAlmostEqual(self.profiles.ROUGH.wheel_joint_vel_noise, actor["wheel_joint_vel_rel"].noise.n_max)
        self.assertIsNone(critic["wheel_joint_pos_rel"].noise)
        self.assertTrue(cfg.observations["actor"].enable_corruption)
        self.assertFalse(cfg.observations["critic"].enable_corruption)
        twist = cfg.commands["twist"]
        self.assertFalse(twist.heading_command)
        self.assertIsNone(twist.ranges.heading)
        self.assertEqual(self.profiles.ROUGH.command_ranges.lin_vel_x, tuple(twist.ranges.lin_vel_x))
        self.assertEqual((0.0, 0.0), tuple(twist.ranges.lin_vel_y))
        self.assertAlmostEqual(self.profiles.ROUGH.rel_standing_envs, twist.rel_standing_envs)
        self.assertEqual(
            [dict(stage) for stage in self.profiles.ROUGH.command_vel_stages],
            [dict(stage) for stage in cfg.curriculum["command_vel"].params["velocity_stages"]],
        )
        self.assertEqual("base_link", cfg.viewer.body_name)

    def test_play_overrides(self):
        cfg = self._variant("rough", self.profiles.ROUGH)
        play = self.skills.make_velocity_env_cfg(self.binding, self.profiles.ROUGH, variant="rough", play=True)
        self.assertFalse(play.observations["actor"].enable_corruption)
        self.assertGreater(play.episode_length_s, cfg.episode_length_s)
        tg = play.scene.terrain.terrain_generator
        self.assertFalse(tg.curriculum)
        self.assertEqual(5, tg.num_cols)
        self.assertEqual(5, tg.num_rows)
        self.assertAlmostEqual(10.0, tg.border_width)
        flat_play = self.skills.make_velocity_env_cfg(self.binding, self.profiles.FLAT, variant="flat", play=True)
        self.assertEqual("plane", flat_play.scene.terrain.terrain_type)


class FamilyVelocityRuntimeTest(unittest.TestCase):
    """真跑：族工厂建环境 + reset + 非零动作 step；动作项运行时序 = 契约序。"""

    def test_go2w_paths_are_end_to_end_alive(self):
        import torch

        skills = _skills_module()
        binding = _go2w_binding().GO2W
        profiles = _go2w_profile()
        contract_order = tuple(_go2w_contract()["action"]["joint_order"])
        for variant, profile in (
            ("rough", profiles.ROUGH),
            ("flat_legs_only", profiles.LEGS_ONLY),
        ):
            with self.subTest(variant=variant):
                cfg = skills.make_velocity_env_cfg(binding, profile, variant=variant)
                cfg.scene.num_envs = 2
                cfg.sim.nconmax = 256
                cfg.sim.njmax = 1024
                from mjlab.envs import ManagerBasedRlEnv

                env = ManagerBasedRlEnv(cfg, device="cpu")
                try:
                    env.reset()
                    observed = [j for name in env.action_manager.active_terms
                                for j in env.action_manager.get_term(name).target_names]
                    expected = list(contract_order)
                    if variant == "flat_legs_only":
                        expected = list(binding.leg_joint_order)
                    self.assertEqual(expected, observed, "动作项运行时目标序必须 = 契约动作序")
                    action = torch.full(
                        (env.num_envs, env.action_manager.total_action_dim), 0.1, device="cpu"
                    )
                    obs, reward, _, _, _ = env.step(action)
                    self.assertTrue(torch.isfinite(obs["actor"]).all())
                    self.assertTrue(torch.isfinite(obs["critic"]).all())
                    self.assertTrue(torch.isfinite(reward).all())
                    # 轮腿档动作 16 维（last_action 16）；纯腿档动作 12 维。
                    expected_dim = 57 if variant == "rough" else 53
                    self.assertEqual(expected_dim, obs["actor"].shape[-1])
                    self.assertEqual(expected_dim + 3, obs["critic"].shape[-1])
                finally:
                    env.close()


class SyntheticSecondRobotTest(unittest.TestCase):
    """换一台机型：只给契约 + MJCF + profile 数据，不动 Kit 一行代码。"""

    LEGS = ("LF", "RF", "LH", "RH")
    LEG_PATTERN = ("hipx", "hipy", "knee", "wheel")
    #: 有意与 go2w 不同：另一套腿标记、另一套（别名内的）角色词、腿序/轮序也不一样
    ORDERED_LEGS = ("RF", "LF", "RH", "LH")

    @classmethod
    def _joint_order(cls) -> tuple[str, ...]:
        """契约动作序：腿段（每腿 3 个位置关节，按 ORDERED_LEGS）× 腿，再轮段。"""
        leg_roles = tuple(role for role in cls.LEG_PATTERN if role != "wheel")
        return tuple(
            f"{leg}_{role}_joint" for leg in cls.ORDERED_LEGS for role in leg_roles
        ) + tuple(f"{leg}_wheel_joint" for leg in cls.ORDERED_LEGS)

    def _synthetic_spec(self):
        import mujoco

        spec = mujoco.MjSpec()
        root = spec.worldbody.add_body(name="trunk")
        root.add_freejoint()
        root.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=(0.2, 0.1, 0.05))
        for leg in self.LEGS:
            parent = root
            for role in self.LEG_PATTERN:
                body = parent.add_body(name=f"{leg}_{role}", pos=(0.0, 0.0, -0.05))
                body.add_joint(name=f"{leg}_{role}_joint", type=mujoco.mjtJoint.mjJNT_HINGE)
                body.add_geom(type=mujoco.mjtGeom.mjGEOM_SPHERE, size=(0.02,))
                parent = body
        return spec

    def _synthetic_contract(self):
        return {
            "robot_id": "synthetic_wheel",
            "morphology": {
                "id": "wheel_leg_16dof",
                "legs": 4,
                "leg_pattern": list(self.LEG_PATTERN),
                "leg_ids": list(self.LEGS),
                "wheel_indices": [12, 13, 14, 15],
            },
            "joints": {
                "actuated": [
                    {
                        "name": f"{leg}_{role}_joint",
                        "leg": leg,
                        "role": role,
                    }
                    for leg in self.LEGS
                    for role in self.LEG_PATTERN
                ],
                "default_pose": [0.05, 0.7, -1.4, 0.0] * 4,
            },
            "actuator_profile": {
                "by_role": {
                    "hipx": {"stiffness": 30.0, "damping": 0.6, "effort": 20.0, "mode": "position", "action_scale": 0.4, "armature": 0.02},
                    "hipy": {"stiffness": 30.0, "damping": 0.6, "effort": 20.0, "mode": "position", "action_scale": 0.4, "armature": 0.02},
                    "knee": {"stiffness": 30.0, "damping": 0.6, "effort": 40.0, "mode": "position", "action_scale": 0.6, "armature": 0.03},
                    "wheel": {"stiffness": 0.0, "damping": 0.4, "effort": 18.0, "mode": "velocity", "action_scale": 12.0, "armature": 0.01},
                }
            },
            "action": {"joint_order": list(self._joint_order()), "action_scale": 0.4},
            "control": {"control_hz": 50, "physics_hz": 200, "decimation": 4},
        }

    def _synthetic_profile(self, skills):
        profile_cls = skills.VelocityProfile
        ranges = skills.CommandRanges(
            lin_vel_x=(-0.2, 0.6), lin_vel_y=(0.0, 0.0), ang_vel_z=(-0.6, 0.6)
        )
        return profile_cls(
            init_base_height=0.55,
            wheel_radius=0.13,
            wheel_track=0.30,
            command_ranges=ranges,
            command_vel_stages=({"step": 0, "lin_vel_x": (-0.2, 0.6), "ang_vel_z": (-0.6, 0.6)},),
            pose_std_standing={"hipx": 0.05, "hipy": 0.1, "knee": 0.15},
            pose_std_walking={"hipx": 0.15, "hipy": 0.35, "knee": 0.5},
            pose_std_running={"hipx": 0.15, "hipy": 0.35, "knee": 0.5},
            terrain_max_init_terrain_level=1,
            terrain_difficulty_range=(0.0, 0.3),
            terrain_overrides={"flat": {"proportion": 1.0}},
        )

    def test_second_robot_needs_data_only(self):
        import mjlab.entity
        import mujoco

        skills = _skills_module()
        spec_fn = lambda: self._synthetic_spec()  # noqa: E731
        base_cfg = lambda: mjlab.entity.EntityCfg(  # noqa: E731
            spec_fn=spec_fn,
            articulation=mjlab.entity.EntityArticulationInfoCfg(
                actuators=(), soft_joint_pos_limit_factor=0.85
            ),
        )
        binding = skills.from_contract(
            self._synthetic_contract(),
            spec_fn=spec_fn,
            base_entity_cfg=base_cfg,
            init_base_height=0.55,
        )
        self.assertEqual(tuple(self._joint_order()[:12]), binding.leg_joint_order)
        self.assertEqual(tuple(self._joint_order()[12:]), binding.wheel_joint_order)
        self.assertEqual("trunk", binding.root_body)
        self.assertEqual([("hipx", ".*_hipx_joint"), ("hipy", ".*_hipy_joint"), ("knee", ".*_knee_joint"), ("wheel", ".*_wheel_joint")],
                         [(g.role, g.target_names_expr[0]) for g in binding.actuator_groups])
        self.assertEqual(r".*(RF|LF|RH|LH)_(wheel|foot).*", binding.wheel_contact_pattern)
        cfg = skills.make_velocity_env_cfg(binding, self._synthetic_profile(skills), variant="flat")
        self.assertEqual(["joint_pos", "wheel_vel"], list(cfg.actions))
        self.assertEqual(tuple(self._joint_order()), tuple(cfg.actions["joint_pos"].actuator_names) + tuple(cfg.actions["wheel_vel"].actuator_names))
        self.assertAlmostEqual(12.0, cfg.actions["wheel_vel"].scale)
        self.assertEqual(tuple(self._joint_order()[:12]), tuple(cfg.observations["actor"].terms["joint_pos"].params["asset_cfg"].joint_names))
        self.assertEqual(tuple(self._joint_order()[12:]), tuple(cfg.observations["actor"].terms["wheel_joint_vel_rel"].params["asset_cfg"].joint_names))
        self.assertAlmostEqual(0.13, cfg.rewards["wheel_roll_tracking"].params["wheel_radius"])
        pose_std = cfg.rewards["pose"].params["std_walking"]
        self.assertEqual({".*_hipx_joint": 0.15, ".*_hipy_joint": 0.35, ".*_knee_joint": 0.5}, pose_std)
        self.assertEqual((0.0, 0.0, 0.55), binding.robot_cfg().init_state.pos)
        # 用**新节点**真跑一次：族工厂对陌生机型同样可建环境、可 step
        import torch
        from mjlab.envs import ManagerBasedRlEnv

        cfg.scene.num_envs = 1
        cfg.sim.nconmax = 64
        cfg.sim.njmax = 256
        env = ManagerBasedRlEnv(cfg, device="cpu")
        try:
            env.reset()
            action = torch.full((env.num_envs, env.action_manager.total_action_dim), 0.05)
            obs, reward, _, _, _ = env.step(action)
            self.assertTrue(torch.isfinite(obs["actor"]).all())
            self.assertTrue(torch.isfinite(reward).all())
        finally:
            env.close()
        _ = mujoco


class Go2wClientEntrypointsTest(unittest.TestCase):
    """客户端公开 API 不动：四个变体入口 + 两个档案入口仍按原名可用。"""

    def test_public_entrypoints_still_exist(self):
        env_cfgs = importlib.import_module("go2w_velocity.env_cfgs")
        names = (
            "unitree_go2w_rough_env_cfg",
            "unitree_go2w_flat_env_cfg",
            "unitree_go2w_flat_legs_only_env_cfg",
            "unitree_go2w_flat_legs_only_omni_env_cfg",
        )
        package = importlib.import_module("go2w_velocity")
        for name in names:
            self.assertTrue(hasattr(package, name), f"包级入口 {name} 丢失")
        cfgs = {name: getattr(env_cfgs, name)(play=False) for name in names}
        self.assertEqual("generator", cfgs["unitree_go2w_rough_env_cfg"].scene.terrain.terrain_type)
        for name in names[1:]:
            self.assertEqual("plane", cfgs[name].scene.terrain.terrain_type)
        self.assertEqual(["joint_pos", "wheel_vel"], list(cfgs["unitree_go2w_flat_env_cfg"].actions))
        self.assertEqual(["joint_pos"], list(cfgs["unitree_go2w_flat_legs_only_env_cfg"].actions))
        # profile 档案声明的入口仍解析到同一符号
        for profile_id in ("go2w-flat", "go2w-rough"):
            record = json.loads(
                (GO2W_ROOT / "training" / "profiles" / f"{profile_id}.json").read_text(encoding="utf-8-sig")
            )
            module_name, _, attr = record["entrypoints"]["env"].partition(":")
            self.assertEqual("go2w_velocity", module_name)
            self.assertTrue(callable(getattr(env_cfgs, attr)))
        # 老 helper 若被删除，不得留下死引用（env_cfgs 不再 import base/go2w_constants 之外的散件）
        self.assertFalse(
            (GO2W_SOURCE / "go2w_velocity" / "base.py").exists(),
            "base.py 已被绑定取代，不应保留重复 helper",
        )


if __name__ == "__main__":
    unittest.main()
