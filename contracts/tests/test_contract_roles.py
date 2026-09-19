"""Contract v3 role resolver / schema parity 测试（T0.1 DoD）。

DoD：Go2 / A2 / B2 三个 quadruped_12dof 用同一份 morphology 模板 + 各自的
by_role 角色表展开成功，且与现行 simulation/config.json 的逐关节数值一致；
schema → Pydantic（Py）→ TS 三产物 parity；roundtrip 测试通过。

真值直接取自 assets/robots/*/simulation/config.json（运行时读取，而非硬编码），
测试守护的是「角色层 round-trip 不丢数值」这一不变量。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from contracts.generated import RobotContractV3, dump_v3, parse_contract
from contracts.physics_binding import action_scale_facts, payload_action_scale_view
from contracts.role_resolver import (
    RoleResolver,
    build_contract,
    RoleResolverError,
    action_scale_for_contract,
    load_schema,
    naming_pattern,
    role_values_from_per_joint,
    validate_robot_id,
)

WORKSPACE = Path(__file__).resolve().parents[2]

QUADRUPED_TEMPLATE = {
    "id": "quadruped_12dof",
    "legs": 4,
    "leg_pattern": ["hip", "thigh", "calf"],
    "leg_naming": "{LR}_{role}_joint",
    "leg_ids": ["FL", "FR", "RL", "RR"],
}
ROLE_PARAMS = ("stiffness", "damping", "torque_limits", "armature")


def load_sim_config(package_id: str) -> dict:
    """**配置口径的真值视图**（2026-09-13 起由 ``contract.json`` 派生）。

    为什么改源：B3 收尾把 8 个物理键从 14 包的 ``simulation/config.json`` 移除了——
    它不再是物理真值来源，继续拿它当"现行数值"会让本文件的所有对拍一边恒为空
    （表现为 KeyError 或**静默假通过**）。

    本文件要守的不变量**没变**：「角色层（``by_role``）→ 逐关节展开」不丢数值、
    两类键风格（角色键控 / 逐关节）都能收敛。故这里从 shipped v3 派生出一份
    **与旧 config 同形**的视图供各测试消费：

    * 三件套 + ``action_scale`` 取 ``control`` / ``action``；
    * 物理量取**逐关节展开**（所有包都有）；
    * 若该包的 ``by_role`` 键恰好是形态角色名（go2 的 hip/thigh/calf），额外给出
      **角色键控**视图——这样 `test_go2_role_keyed_config_roundtrip` 仍在测角色键路径。
    """

    contract_truth = json.loads(
        (WORKSPACE / "assets" / "robots" / package_id / "contract.json").read_text(encoding="utf-8-sig")
    )
    expanded = RoleResolver(contract_truth).expand_actuator_profile()
    control = contract_truth.get("control") or {}
    view: dict = {
        "control_hz": control.get("control_hz"),
        "physics_hz": control.get("physics_hz"),
        "decimation": control.get("decimation"),
        "action_scale": (contract_truth.get("action") or {}).get("action_scale"),
    }
    param_pairs = (
        ("stiffness", "stiffness"),
        ("damping", "damping"),
        ("torque_limits", "effort"),
        ("armature", "armature"),
        ("frictionloss", "friction_loss"),
    )
    by_role = (contract_truth.get("actuator_profile") or {}).get("by_role") or {}
    role_named = set(by_role) <= {"hip", "thigh", "calf", "wheel"}
    for key, param in param_pairs:
        per_joint = {
            joint: params[param]
            for joint, params in expanded.items()
            if isinstance(params, dict) and params.get(param) is not None
        }
        if per_joint:
            view[key] = per_joint
        if role_named and per_joint:
            role_view = {
                role: params[param]
                for role, params in by_role.items()
                if isinstance(params, dict) and param in params
            }
            if role_view:
                view[key] = role_view
    return view


def truth_by_role(config: dict, key: str) -> dict[str, float]:
    """把现行 config 的 map 收敛为角色表（go2 是角色键控，a2/b2 按关节名解析）。"""

    raw = config.get(key) or {}
    if not raw:
        return {}
    first = next(iter(raw))
    if first in ("hip", "thigh", "calf", "wheel", "joint"):
        # 角色键控风格（go2）；'joint' 是遗留 catch-all，不参与角色表
        return {k: v for k, v in raw.items() if k not in ("joint",)}
    resolved = role_values_from_per_joint(raw, QUADRUPED_TEMPLATE["leg_naming"])
    assert resolved is not None, f"{key} 角色内取值不一致，测试前提失效: {raw}"
    return resolved


def truth_per_joint(config: dict, key: str) -> dict[str, float] | None:
    raw = config.get(key) or {}
    if not raw:
        return None
    first = next(iter(raw))
    if first in ("hip", "thigh", "calf", "wheel", "joint"):
        # 角色键控风格（go2）：按 leg_ids×leg_pattern 展开为逐关节真值
        truth: dict[str, float] = {}
        for leg in QUADRUPED_TEMPLATE["leg_ids"]:
            for role in QUADRUPED_TEMPLATE["leg_pattern"]:
                value = raw.get(role, raw.get("joint"))
                if value is not None:
                    truth[f"{leg}_{role}_joint"] = value
        return truth
    return dict(raw)


def build_contract_from_config(package_id: str, config: dict, observation_components=None) -> dict:
    profile_by_role: dict[str, dict] = {}
    for key, param in (
        ("stiffness", "stiffness"),
        ("damping", "damping"),
        ("torque_limits", "effort"),
        ("armature", "armature"),
    ):
        for role, value in truth_by_role(config, key).items():
            profile_by_role.setdefault(role, {})[param] = value
    control = {
        "control_hz": config["control_hz"],
        "physics_hz": config["physics_hz"],
        "decimation": config["decimation"],
    }
    contract = build_contract(
        robot_id=package_id,
        morphology_id=QUADRUPED_TEMPLATE["id"],
        leg_ids=QUADRUPED_TEMPLATE["leg_ids"],
        leg_pattern=QUADRUPED_TEMPLATE["leg_pattern"],
        leg_naming=QUADRUPED_TEMPLATE["leg_naming"],
        by_role=profile_by_role,
        joint_order=[
            "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
            "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
            "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint",
            "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
        ],
        action_scale=config.get("action_scale") or 0.25,
        observation_components=observation_components or [
            {"name": "base_lin_vel", "width": 3, "scale": 1.0, "source": "imu"},
            {"name": "base_ang_vel", "width": 3, "scale": 0.25, "source": "imu"},
            {"name": "projected_gravity", "width": 3, "scale": 1.0, "source": "imu"},
            {"name": "velocity_command", "width": 3, "scale": 1.0, "source": "cmd"},
            {"name": "joint_pos_err", "width": 12, "scale": 1.0, "source": "actuated"},
            {"name": "joint_vel", "width": 12, "scale": 0.05, "source": "actuated"},
            {"name": "prev_action", "width": 12, "scale": 1.0, "source": "action"},
        ],
        control=control,
        family=f"package {package_id}",
    )
    RoleResolver(contract).ensure_valid()
    return contract


class QuadrupedSharedMorphologyTest(unittest.TestCase):
    def test_go2_b2_share_one_morphology_template(self) -> None:
        # unitree_a1 / unitree_a2 已下线删除。
        contracts = {
            pkg: build_contract_from_config(pkg, load_sim_config(pkg))
            for pkg in ("unitree_go2", "unitree_b2")
        }
        templates = {json.dumps(c["morphology"], sort_keys=True) for c in contracts.values()}
        self.assertEqual(len(templates), 1, "quadruped_12dof 必须共用同一份 morphology 模板")

    def test_actuated_sets_equal_naming_expansion(self) -> None:
        contract = build_contract_from_config("unitree_go2", load_sim_config("unitree_go2"))
        expected = {
            f"{leg}_{role}_joint"
            for leg in QUADRUPED_TEMPLATE["leg_ids"]
            for role in QUADRUPED_TEMPLATE["leg_pattern"]
        }
        self.assertEqual(set(contract["joints"]["actuated"][i]["name"] for i in range(12)), expected)


class ActuatorExpansionMatchesCurrentConfigTest(unittest.TestCase):
    """DoD 核心：同一份角色表展开 == 现行逐关节数值。"""

    def test_go2_role_keyed_config_roundtrip(self) -> None:
        config = load_sim_config("unitree_go2")
        contract = build_contract_from_config("unitree_go2", config)
        expanded = RoleResolver(contract).expand_actuator_profile()
        for key, param in (("stiffness", "stiffness"), ("damping", "damping"), ("torque_limits", "effort")):
            truth = truth_per_joint(config, key)
            assert truth is not None
            for joint, value in truth.items():
                self.assertEqual(expanded[joint][param], value, f"go2 {key}/{joint}")

    def test_go2_armature_role_pattern(self) -> None:
        config = load_sim_config("unitree_go2")
        contract = build_contract_from_config("unitree_go2", config)
        expanded = RoleResolver(contract).expand_actuator_profile()
        # 现行 go2 armature 逐关节散写，但取值按角色恒定：hip/thigh=0.01, calf=0.02
        for joint, params in expanded.items():
            expected = 0.02 if "_calf_" in joint else 0.01
            self.assertEqual(params["armature"], expected, f"go2 armature/{joint}")

    def test_b2_per_joint_config_roundtrip(self) -> None:
        for package_id in ("unitree_b2",):
            config = load_sim_config(package_id)
            contract = build_contract_from_config(package_id, config)
            expanded = RoleResolver(contract).expand_actuator_profile()
            for key, param in (("stiffness", "stiffness"), ("damping", "damping"), ("torque_limits", "effort")):
                truth = truth_per_joint(config, key)
                assert truth is not None
                for joint, value in truth.items():
                    self.assertEqual(expanded[joint][param], value, f"{package_id} {key}/{joint}")

    def test_b2_armature_now_declared_and_matches_evidence(self) -> None:
        """**B3 收尾反转了本测试的前身**（原名 ``test_b2_has_no_armature_key``）。

        原断言是「b2 的展开里**没有** armature」——那时契约确实缺这一项，测试锁的是"缺口"。
        B3 用各包训练树取证补齐 armature 后，不变量**随之反转**：14 包全都必须有 armature，
        而且 b2 的值要等于取证值 0.1。「缺口被填上」这件事必须被锁死，否则会悄悄退回缺失。
        """

        packages = sorted(
            p.name for p in (WORKSPACE / "assets" / "robots").iterdir() if (p / "contract.json").exists()
        )
        self.assertGreaterEqual(len(packages), 14, "内置包数量异常")
        for package_id in packages:
            # 直接读 shipped v3 展开：`build_contract` 用的是 quadruped 模板，
            # 对灵巧手/轮足机型不适用（那会把"模板不适配"误报成"armature 缺失"）。
            contract_truth = json.loads(
                (WORKSPACE / "assets" / "robots" / package_id / "contract.json").read_text(encoding="utf-8-sig")
            )
            expanded = RoleResolver(contract_truth).expand_actuator_profile()
            with self.subTest(package=package_id):
                for joint, params in expanded.items():
                    self.assertIn(
                        "armature", params,
                        f"{package_id} 的 {joint} 缺 armature——B3 已全量补齐，不该再出现缺口",
                    )
        b2 = RoleResolver(
            build_contract_from_config("unitree_b2", load_sim_config("unitree_b2"))
        ).expand_actuator_profile()
        self.assertEqual({params["armature"] for params in b2.values()}, {0.1})

    def test_by_joint_override_wins(self) -> None:
        config = load_sim_config("unitree_go2")
        contract = build_contract_from_config("unitree_go2", config)
        contract["actuator_profile"]["by_joint"] = {
            "FL_hip_joint": {"stiffness": 99.0},
        }
        expanded = RoleResolver(contract).expand_actuator_profile()
        self.assertEqual(expanded["FL_hip_joint"]["stiffness"], 99.0)
        self.assertEqual(expanded["FR_hip_joint"]["stiffness"], 20.0)


class SelfConsistencyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.base = build_contract_from_config("unitree_go2", load_sim_config("unitree_go2"))

    def expect_error(self, mutate) -> None:
        import copy

        contract = copy.deepcopy(self.base)
        mutate(contract)
        errors = RoleResolver(contract).validate()
        self.assertTrue(errors, "变异后必须产生校验错误")

    def test_observation_dimension_mismatch_detected(self) -> None:
        self.expect_error(lambda c: c["observation"].__setitem__("dimension", 45))

    def test_bad_reindex_detected(self) -> None:
        self.expect_error(
            lambda c: c["action"].__setitem__("reindex_from_model", [0, 1, 2, 3])
        )

    def test_naming_mismatch_detected(self) -> None:
        self.expect_error(
            lambda c: c["joints"]["actuated"][0].__setitem__("name", "FL_hip")
        )

    def test_declared_role_mismatch_detected(self) -> None:
        self.expect_error(
            lambda c: c["joints"]["actuated"][0].__setitem__("role", "wheel")
        )

    def test_unknown_by_joint_key_detected(self) -> None:
        self.expect_error(
            lambda c: c["actuator_profile"].__setitem__("by_joint", {"nope": {"stiffness": 1.0}})
        )

    def test_control_decimation_mismatch_detected(self) -> None:
        self.expect_error(lambda c: c["control"].__setitem__("decimation", 20))

    def test_valid_contract_has_no_errors(self) -> None:
        self.assertEqual(RoleResolver(self.base).validate(), [])


class ReindexSemanticsTest(unittest.TestCase):
    def test_m20_style_reindex_is_validated_and_applicable(self) -> None:
        # M20 joint_ids_map（报告 6 §1 关键设计 3 的制度化实例），16 自由度合成契约
        reindex = [0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14, 3, 7, 11, 15]
        leg_ids = ["FL", "FR", "RL", "RR"]
        actuated = [
            {"name": f"{leg}_{role}_joint", "leg": leg, "role": role}
            for leg in leg_ids
            for role in ["hip", "thigh", "calf", "wheel"]
        ]
        contract = {
            "schema_version": "robot-contract-3.0",
            "robot_id": "wheel_leg_synth",
            "morphology": {
                "id": "wheel_leg_16dof",
                "legs": 4,
                "leg_pattern": ["hip", "thigh", "calf", "wheel"],
                "leg_naming": "{LR}_{role}_joint",
                "leg_ids": leg_ids,
                # B4 内核字段：合成契约不走 build_contract，需显式声明（fail-closed）
                "actuator_type": "hybrid",
                "foot_type": "wheel",
                "wheel_indices": [3, 7, 11, 15],
                "mass_source": "mjcf_compiled",
            },
            "joints": {"actuated": actuated},
            "actuator_profile": {
                "by_role": {
                    "hip": {"stiffness": 20.0, "mode": "position"},
                    "thigh": {"stiffness": 20.0, "mode": "position"},
                    "calf": {"stiffness": 40.0, "mode": "position"},
                    "wheel": {"stiffness": 0.0, "damping": 0.6, "mode": "velocity", "armature": 0.0024},
                }
            },
            "action": {"joint_order": [e["name"] for e in actuated], "reindex_from_model": reindex},
            "observation": {
                "components": [
                    {"name": "base_ang_vel", "width": 3, "scale": 0.25, "source": "imu"},
                    {"name": "joint_pos_err", "width": 16, "scale": 1.0, "source": "actuated", "wrap": False},
                ],
                "dimension": 19,
            },
        }
        resolver = RoleResolver(contract)
        resolver.ensure_valid()
        # 轮关节执行器模式按角色声明为 velocity——12 腿+4 轮混排特判由此消失
        expanded = resolver.expand_actuator_profile()
        self.assertEqual(expanded["FL_wheel_joint"]["mode"], "velocity")
        self.assertEqual(expanded["FL_hip_joint"]["mode"], "position")
        self.assertEqual(expanded["FL_wheel_joint"]["armature"], 0.0024)

    def test_robot_id_pattern_accepts_both_existing_styles(self) -> None:
        validate_robot_id("unitree_go2")
        validate_robot_id("zex-w")
        with self.assertRaises(RoleResolverError):
            validate_robot_id("Unitree Go2")


class SchemaParityAndRoundtripTest(unittest.TestCase):
    """schema → Py → TS 三产物 parity + roundtrip。"""

    def setUp(self) -> None:
        self.contract = build_contract_from_config("unitree_go2", load_sim_config("unitree_go2"))

    def test_pydantic_roundtrip(self) -> None:
        model = parse_contract(self.contract)
        dumped = dump_v3(model)
        reparsed = parse_contract(dumped)
        self.assertEqual(dump_v3(reparsed), dumped)
        self.assertEqual(reparsed.robot_id, "unitree_go2")
        self.assertEqual(reparsed.morphology.leg_pattern, ["hip", "thigh", "calf"])

    def test_generated_python_covers_schema_top_level_properties(self) -> None:
        schema = load_schema()
        model_fields = set(RobotContractV3.model_fields.keys())
        for property_name in schema["properties"]:
            self.assertIn(property_name, model_fields, f"Pydantic 模型缺少 schema 字段 {property_name}")

    def test_generated_ts_covers_schema_top_level_properties(self) -> None:
        ts_source = (
            WORKSPACE / "web" / "shared" / "generated" / "types.d.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("interface RobotContractV3", ts_source)
        schema = load_schema()
        for property_name in schema["properties"]:
            self.assertIn(property_name, ts_source, f"types.d.ts 缺少 schema 字段 {property_name}")
        # 任务侧预埋定义必须在三产物中同时存在（报告 6 §4.6）
        self.assertIn("taskRequirements", json.dumps(load_schema()))
        self.assertIn("TaskRequirements", ts_source)


class MorphologyKernelFieldsB4Test(unittest.TestCase):
    """B4（§2.1.1 rev.2）Morphology 内核字段的 DoD：

    1. 14 个内置包都能表达 actuator_type / foot_type / wheel_indices / mass_source；
    2. 缺字段在 verify 阶段 fail-closed（§5.8.4），不静默降级。
    """

    ROBOTS = WORKSPACE / "assets" / "robots"

    # 直接对应 B4 验收原文：TRON1 PF/SF/WF、M20/Go2W/ZEX-W 轮组、MicroDuck
    EXPECTED_FOOT_TYPE = {
        "limx_tron1_pf": "point",
        "limx_tron1_sf": "sole",
        "limx_tron1_wf": "wheel",
        "deeprobotics_m20": "wheel",
        "unitree_go2w": "wheel",
        "unitree_b2w": "wheel",
        "zex-w": "wheel",
        "microduck": "sole",
    }
    EXPECTED_WHEEL_INDICES = {
        "deeprobotics_m20": [12, 13, 14, 15],
        "limx_tron1_wf": [3, 7],
        "unitree_go2w": [12, 13, 14, 15],
        "unitree_b2w": [12, 13, 14, 15],
        "zex-w": [12, 13, 14, 15],
    }

    def _load(self, package_id: str) -> dict:
        path = self.ROBOTS / package_id / "contract.json"
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def _all_contracts(self) -> dict[str, dict]:
        return {
            package.name: json.loads((package / "contract.json").read_text(encoding="utf-8-sig"))
            for package in sorted(p for p in self.ROBOTS.iterdir() if p.is_dir())
            if (package / "contract.json").exists()
        }

    def test_all_packages_declare_kernel_fields(self) -> None:
        contracts = self._all_contracts()
        self.assertGreaterEqual(len(contracts), 14)
        for name, contract in contracts.items():
            with self.subTest(package=name):
                morphology = contract["morphology"]
                self.assertIn(morphology.get("actuator_type"), ("position", "velocity", "hybrid", "bam"))
                self.assertIn(morphology.get("mass_source"), ("mjcf_compiled", "urdf_inertial"))
                if morphology["id"] == "hand":
                    self.assertIsNone(morphology.get("foot_type"))
                else:
                    self.assertIn(morphology.get("foot_type"), ("point", "sole", "wheel"))

    def test_foot_type_and_wheel_indices_match_evidence(self) -> None:
        contracts = self._all_contracts()
        for name, expected in self.EXPECTED_FOOT_TYPE.items():
            with self.subTest(package=name, field="foot_type"):
                self.assertEqual(contracts[name]["morphology"]["foot_type"], expected)
        for name, expected in self.EXPECTED_WHEEL_INDICES.items():
            with self.subTest(package=name, field="wheel_indices"):
                self.assertEqual(contracts[name]["morphology"]["wheel_indices"], expected)

    def test_actuator_type_follows_wheel_presence(self) -> None:
        # microduck 的真实执行器是 BAM（固件 PD + 直流电机 + Stribeck 摩擦，已用真实
        # 台架数据验证，见 microduck_rl/scripts/validate_bam_testbench.py）；其打包模型
        # 的 chosen_actuator kp=0.55 正是 BAM 200 增益的 MuJoCo 等效值（注释 `<!-- 200 kp -->`）。
        # 故如实声明 "bam"（B4 枚举本为此设计），其余机型按轮组推导。
        expected_by_package = {"microduck": "bam"}
        for name, contract in self._all_contracts().items():
            with self.subTest(package=name):
                morphology = contract["morphology"]
                if name in expected_by_package:
                    expected = expected_by_package[name]
                else:
                    expected = "hybrid" if "wheel" in morphology["leg_pattern"] else "position"
                self.assertEqual(morphology["actuator_type"], expected)

    def test_missing_kernel_fields_fail_closed(self) -> None:
        import copy

        base = build_contract_from_config("unitree_go2", load_sim_config("unitree_go2"))
        for field in ("actuator_type", "foot_type", "mass_source"):
            with self.subTest(field=field):
                contract = copy.deepcopy(base)
                contract["morphology"].pop(field)
                errors = RoleResolver(contract).validate()
                self.assertTrue(
                    any(field in error for error in errors),
                    f"缺 {field} 必须 fail-closed，实际错误：{errors}",
                )

    def test_wheel_indices_fail_closed(self) -> None:
        import copy

        base = self._load("unitree_go2w")
        self.assertEqual(RoleResolver(base).validate(), [], "含轮合规契约不应报错")

        contract = copy.deepcopy(base)
        contract["morphology"].pop("wheel_indices")
        self.assertTrue(
            any("wheel_indices" in error for error in RoleResolver(contract).validate()),
            "含 wheel 角色却缺 wheel_indices 必须报错",
        )

        contract = copy.deepcopy(base)
        contract["morphology"]["wheel_indices"] = [0, 1, 2, 3]  # 指向腿关节
        self.assertTrue(
            any("wheel_indices" in error for error in RoleResolver(contract).validate()),
            "wheel_indices 与真实 wheel 槽位不符必须报错",
        )

    def test_foot_type_rejected_on_non_legged_morphology(self) -> None:
        import copy

        base = self._load("wuji_hand")
        self.assertEqual(RoleResolver(base).validate(), [], "hand 构型不应因缺 foot_type 报错")
        contract = copy.deepcopy(base)
        contract["morphology"]["foot_type"] = "point"
        self.assertTrue(
            any("foot_type" in error for error in RoleResolver(contract).validate()),
            "hand 构型声明 foot_type 必须报错",
        )


class ActionScaleRoleLevelB5Test(unittest.TestCase):
    """B5：action_scale 角色级声明的 DoD。

    背景：`action.action_scale` 只是标量缺省，而角色间真实档位不同——
    轮足 leg 0.5 / wheel 35.0（差 70 倍）、G1 髋俯仰 0.55 / 腕俯仰 0.07。
    标量表达不了，只能靠 `actuator_profile.by_role[].action_scale`。

    守护四件事：
      1. 每个驱动角色都声明了 action_scale（数据完整、形状统一）；
      2. 含 wheel 角色的机型必须声明 wheel 的档位（否则轮子被腿档位顶掉）；
      3. 展开视图与证据表一致（g1 来自官方 unitree_rl_mjlab deploy.yaml 的
         JointPositionAction.scale；go2w 来自官方 JointVelocityAction.scale=35.0；
         zex-w 来自自家 v3 deployment_contract.yaml 的 scale 数组）；
      4. **有效 scale 相对旧标量的变更集合恰为 {g1, go2w, zex-w}**——其余机型必须
         逐值等价，防止"补数据"顺手改了别的机器人的训练行为。
    """

    ROBOTS = WORKSPACE / "assets" / "robots"

    EXPECTED_DELTA_ROBOTS = {
        "deeprobotics_lite3",
        "deeprobotics_m20",
        "limx_tron1_wf",
        "unitree_b2",
        "unitree_b2w",
        "unitree_g1",
        "unitree_go2w",
        "zex-w",
    }

    EXPECTED_ROLE_SCALE = {
        "unitree_g1": {
            "hip_pitch": 0.55, "hip_roll": 0.35, "hip_yaw": 0.55, "knee": 0.35,
            "ankle_pitch": 0.44, "ankle_roll": 0.44,
            "shoulder_pitch": 0.44, "shoulder_roll": 0.44, "shoulder_yaw": 0.44,
            "elbow": 0.44, "wrist_roll": 0.44, "wrist_pitch": 0.07, "wrist_yaw": 0.07,
            "waist_yaw": 0.55, "waist_roll": 0.44, "waist_pitch": 0.44,
        },
        "unitree_go2w": {"hip": 0.5, "thigh": 0.5, "calf": 0.5, "wheel": 35.0},
        "zex-w": {"hip_abduction": 0.125, "hip_pitch": 0.25, "knee": 0.25, "wheel": 5.0},
        # tron1_wf 的轮是**独立的 JointVelocityActionCfg(scale=1.0)**（见 tron1-rl-isaaclab
        # cfg/WF/limx_base_env_cfg.py），与腿的 action_scale_pos=0.25 分属两套通路。
        "limx_tron1_wf": {"abad": 0.25, "hip": 0.25, "knee": 0.25, "wheel": 1.0},
        # m20 / b2w 同构：腿=位置档位（髋 0.125、其余 0.25），轮=速度档位 5.0。
        # 见 export_onnx_fast.py 的 _M20_ACTION_SCALE 与 robot_lab b2w 的
        # joint_pos.scale / joint_vel.scale。
        "deeprobotics_m20": {"hipx": 0.125, "hipy": 0.25, "knee": 0.25, "wheel": 5.0},
        "unitree_b2w": {"hip": 0.125, "thigh": 0.25, "calf": 0.25, "wheel": 5.0},
        # b2（无轮四足）与 b2w 的**腿**部分逐字同源：
        # robot_lab b2 rough_env_cfg.py → joint_pos.scale = {".*_hip_joint": 0.125, 其余: 0.25}
        "unitree_b2": {"hip": 0.125, "thigh": 0.25, "calf": 0.25},
        # lite3：isaac 训练 ∩ sdk_deploy 运行时 ∩ export_onnx 元数据三方一致
        # （[0.125,0.25,0.25]×4）——注意 hipx 缩减，不能写成均匀 0.125。
        "deeprobotics_lite3": {"hipx": 0.125, "hipy": 0.25, "knee": 0.25},
    }

    def _contracts(self) -> dict[str, dict]:
        return {
            package.name: json.loads((package / "contract.json").read_text(encoding="utf-8-sig"))
            for package in sorted(p for p in self.ROBOTS.iterdir() if p.is_dir())
            if (package / "contract.json").exists()
        }

    def test_every_actuated_joint_resolves_a_scale(self) -> None:
        contracts = self._contracts()
        self.assertGreaterEqual(len(contracts), 14)
        for name, contract in contracts.items():
            with self.subTest(package=name):
                resolver = RoleResolver(contract)
                self.assertEqual(resolver.validate(), [])
                per_joint = resolver.action_scale_by_joint()
                self.assertEqual(set(per_joint), set(resolver.actuated_names))
                self.assertTrue(all(value > 0 for value in per_joint.values()))

    def test_wheel_robots_declare_role_level_wheel_scale(self) -> None:
        contracts = self._contracts()
        checked = 0
        for name, contract in contracts.items():
            pattern = (contract.get("morphology") or {}).get("leg_pattern") or []
            if "wheel" not in pattern:
                continue
            with self.subTest(package=name):
                by_role = (contract.get("actuator_profile") or {}).get("by_role") or {}
                self.assertIn("wheel", by_role, f"{name} 未声明 wheel 角色")
                self.assertIsNotNone(
                    by_role["wheel"].get("action_scale"),
                    f"{name} 的 wheel 角色缺 action_scale——轮子会被腿的档位顶掉",
                )
            checked += 1
        self.assertEqual(checked, 5, "含轮机型应为 5 个（m20/b2w/go2w/zex-w/tron1_wf）")

    def test_role_scale_matches_evidence(self) -> None:
        contracts = self._contracts()
        for name, expected_roles in self.EXPECTED_ROLE_SCALE.items():
            contract = contracts[name]
            resolver = RoleResolver(contract)
            per_joint = resolver.action_scale_by_joint()
            for entry in contract["joints"]["actuated"]:
                role = entry.get("role")
                if role not in expected_roles:
                    continue
                with self.subTest(package=name, role=role, joint=entry["name"]):
                    self.assertEqual(per_joint[entry["name"]], expected_roles[role])

    def test_effective_scale_delta_set_is_locked(self) -> None:
        """变更集合必须恰为 {g1, go2w, zex-w}：其余机型逐值等价于旧标量。"""

        changed: set[str] = set()
        for name, contract in self._contracts().items():
            scalar = (contract.get("action") or {}).get("action_scale")
            per_joint = RoleResolver(contract).action_scale_by_joint()
            if any(abs(value - float(scalar)) > 1e-12 for value in per_joint.values()):
                changed.add(name)
        self.assertEqual(
            changed, self.EXPECTED_DELTA_ROBOTS,
            "有效 action_scale 的变更集合发生变化——新增变更必须先在证据表里列明",
        )

    def test_g1_declared_scale_matches_mjlab_derivation(self) -> None:
        """g1 的档位须与 mjlab 推导式 ``0.25*effort/stiffness`` 一致（容差 0.01）。

        mjlab 的 asset_zoo 不是硬编码档位，而是用该式生成
        （见 00_resources/lain_job/RoboLab/backends/mjlab/mjlab/src/mjlab/asset_zoo/
        robots/unitree_go1/go1_constants.py：
        ``GO1_ACTION_SCALE[n] = 0.25 * e / s``）。g1 是我们唯一同时具备
        "角色级 effort/stiffness"与"外部权威逐关节档位（官方部署 yaml）"的机型，
        因此用它把**两条独立来源**钉在一起——任一侧被改动都会在这里显形。
        """

        g1 = self._contracts()["unitree_g1"]
        by_role = g1["actuator_profile"]["by_role"]
        for role, params in by_role.items():
            with self.subTest(role=role):
                derived = 0.25 * float(params["effort"]) / float(params["stiffness"])
                self.assertAlmostEqual(
                    float(params["action_scale"]), derived, delta=0.01,
                    msg=f"{role}: 声明 {params['action_scale']} vs 推导 {derived:.4f}",
                )

    def test_contract_helper_returns_scalar_when_uniform(self) -> None:
        """角色内一致 ⇒ 返回 float（与旧行为逐值等价）；分化 ⇒ 返回 dict。"""

        contracts = self._contracts()
        for name, contract in contracts.items():
            with self.subTest(package=name):
                resolved = action_scale_for_contract(contract)
                if name in self.EXPECTED_DELTA_ROBOTS:
                    self.assertIsInstance(resolved, dict)
                    self.assertEqual(
                        resolved, RoleResolver(contract).action_scale_by_joint()
                    )
                else:
                    self.assertIsInstance(resolved, float)


class ActionScalePayloadViewB52Test(unittest.TestCase):
    """B5/2：三端（训练/仿真/部署）读取的 action_scale 载荷视图。

    前端（``web/sim2sim/app.js``）按"精确关节名 → 角色 → 分组 → joint 兜底"多路查找。
    契约换源后必须让**每条路径都命中同一数值**，否则会静默回退到默认值（表现为策略
    抽搐而非报错）。本类守护该性质，并确认轮档位不再被标量拍平。
    """

    ROBOTS = WORKSPACE / "assets" / "robots"

    def _contract(self, package: str) -> dict:
        return json.loads(
            (self.ROBOTS / package / "contract.json").read_text(encoding="utf-8-sig")
        )

    def _view(self, package: str) -> dict:
        return payload_action_scale_view(action_scale_facts(self._contract(package)))

    def _packages(self) -> list[str]:
        return sorted(
            p.name for p in self.ROBOTS.iterdir() if (p / "contract.json").exists()
        )

    def test_role_view_covers_every_joint(self) -> None:
        for package in self._packages():
            contract = self._contract(package)
            view = self._view(package)
            for name in contract["action"]["joint_order"]:
                with self.subTest(package=package, joint=name):
                    self.assertIn(name, view["action_scale_by_joint"])
                    self.assertIn(name, view["action_scale_by_role"])

    def test_uniform_robots_expose_joint_fallback(self) -> None:
        view = self._view("unitree_go2")
        self.assertEqual(view["action_scale"], 0.25)
        self.assertEqual(view["action_scale_by_role"]["joint"], 0.25)

    def test_wheel_scale_not_flattened_by_scalar(self) -> None:
        """轮足机型：轮的档位必须与腿不同且不被标量顶掉。"""

        view = self._view("unitree_go2w")
        self.assertTrue(view["wheel_scale_declared"])
        self.assertEqual(view["action_scale_by_role"]["leg"], 0.5)
        self.assertEqual(view["action_scale_by_role"]["wheel"], 35.0)
        self.assertNotEqual(view["action_scale"], view["action_scale_by_role"]["wheel"])

    def test_leg_group_absent_when_leg_roles_differ(self) -> None:
        """zex-w 腿内分化（横摆 0.125 / 其余 0.25）⇒ 不可伪造 leg 组键。"""

        view = self._view("zex-w")
        self.assertNotIn("leg", view["action_scale_by_role"])
        self.assertEqual(view["action_scale_by_role"]["wheel"], 5.0)

    def test_non_wheel_robots_do_not_claim_wheel(self) -> None:
        for package in ("unitree_g1", "unitree_go2", "wuji_hand"):
            with self.subTest(package=package):
                view = self._view(package)
                self.assertFalse(view["wheel_scale_declared"])
                self.assertNotIn("wheel", view["action_scale_by_role"])


if __name__ == "__main__":
    unittest.main()
