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

from contracts.generated import RobotContractV3, dump_v3, parse_v3
from contracts.role_resolver import (
    RoleResolver,
    RoleResolverError,
    build_v3_contract,
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
    path = WORKSPACE / "assets" / "robots" / package_id / "simulation" / "config.json"
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


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


def build_contract(package_id: str, config: dict, observation_components=None) -> dict:
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
    contract = build_v3_contract(
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
            pkg: build_contract(pkg, load_sim_config(pkg))
            for pkg in ("unitree_go2", "unitree_b2")
        }
        templates = {json.dumps(c["morphology"], sort_keys=True) for c in contracts.values()}
        self.assertEqual(len(templates), 1, "quadruped_12dof 必须共用同一份 morphology 模板")

    def test_actuated_sets_equal_naming_expansion(self) -> None:
        contract = build_contract("unitree_go2", load_sim_config("unitree_go2"))
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
        contract = build_contract("unitree_go2", config)
        expanded = RoleResolver(contract).expand_actuator_profile()
        for key, param in (("stiffness", "stiffness"), ("damping", "damping"), ("torque_limits", "effort")):
            truth = truth_per_joint(config, key)
            assert truth is not None
            for joint, value in truth.items():
                self.assertEqual(expanded[joint][param], value, f"go2 {key}/{joint}")

    def test_go2_armature_role_pattern(self) -> None:
        config = load_sim_config("unitree_go2")
        contract = build_contract("unitree_go2", config)
        expanded = RoleResolver(contract).expand_actuator_profile()
        # 现行 go2 armature 逐关节散写，但取值按角色恒定：hip/thigh=0.01, calf=0.02
        for joint, params in expanded.items():
            expected = 0.02 if "_calf_" in joint else 0.01
            self.assertEqual(params["armature"], expected, f"go2 armature/{joint}")

    def test_b2_per_joint_config_roundtrip(self) -> None:
        for package_id in ("unitree_b2",):
            config = load_sim_config(package_id)
            contract = build_contract(package_id, config)
            expanded = RoleResolver(contract).expand_actuator_profile()
            for key, param in (("stiffness", "stiffness"), ("damping", "damping"), ("torque_limits", "effort")):
                truth = truth_per_joint(config, key)
                assert truth is not None
                for joint, value in truth.items():
                    self.assertEqual(expanded[joint][param], value, f"{package_id} {key}/{joint}")

    def test_b2_has_no_armature_key(self) -> None:
        config = load_sim_config("unitree_b2")
        contract = build_contract("unitree_b2", config)
        expanded = RoleResolver(contract).expand_actuator_profile()
        for params in expanded.values():
            self.assertNotIn("armature", params)

    def test_by_joint_override_wins(self) -> None:
        config = load_sim_config("unitree_go2")
        contract = build_contract("unitree_go2", config)
        contract["actuator_profile"]["by_joint"] = {
            "FL_hip_joint": {"stiffness": 99.0},
        }
        expanded = RoleResolver(contract).expand_actuator_profile()
        self.assertEqual(expanded["FL_hip_joint"]["stiffness"], 99.0)
        self.assertEqual(expanded["FR_hip_joint"]["stiffness"], 20.0)


class SelfConsistencyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.base = build_contract("unitree_go2", load_sim_config("unitree_go2"))

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
                # B4 内核字段：合成契约不走 build_v3_contract，需显式声明（fail-closed）
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
        self.contract = build_contract("unitree_go2", load_sim_config("unitree_go2"))

    def test_pydantic_roundtrip(self) -> None:
        model = parse_v3(self.contract)
        dumped = dump_v3(model)
        reparsed = parse_v3(dumped)
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
        path = self.ROBOTS / package_id / "contract_v3.json"
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def _all_contracts(self) -> dict[str, dict]:
        return {
            package.name: json.loads((package / "contract_v3.json").read_text(encoding="utf-8-sig"))
            for package in sorted(p for p in self.ROBOTS.iterdir() if p.is_dir())
            if (package / "contract_v3.json").exists()
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
        for name, contract in self._all_contracts().items():
            with self.subTest(package=name):
                morphology = contract["morphology"]
                expected = "hybrid" if "wheel" in morphology["leg_pattern"] else "position"
                self.assertEqual(morphology["actuator_type"], expected)

    def test_missing_kernel_fields_fail_closed(self) -> None:
        import copy

        base = build_contract("unitree_go2", load_sim_config("unitree_go2"))
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


if __name__ == "__main__":
    unittest.main()
