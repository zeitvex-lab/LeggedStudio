"""B3 物理事实绑定测试：契约 v3 单一真值 == 各包现行 simulation/config.json。

这是"翻转真值之前"的**等价性证明**（重构方案 §5.7-1）：

* config 侧的键风格跨包不一致——lite3/m20 逐关节、go2/zex-w 角色键控 + ``joint``
  兜底、wuji_hand 只有 ``joint``；本测试按 config 自身风格独立求解逐关节真值，
  再与 ``physics_facts()`` 的 ``by_joint`` 视图逐值比对，避免"自己证明自己"。
* 同时守护 frictionloss 已并入契约（B3 迁移项之一），以及 control 三件套同源。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from contracts.physics_binding import (
    CONTROL_KEYS,
    PARAM_KEYS,
    facts_from_contract,
    physics_facts,
)

WORKSPACE = Path(__file__).resolve().parents[2]
ROBOTS = WORKSPACE / "assets" / "robots"

# config 侧参数名（契约名 -> config 键名）
CONFIG_KEY = {
    "stiffness": "stiffness",
    "damping": "damping",
    "torque_limits": "torque_limits",
    "armature": "armature",
    "friction_loss": "frictionloss",
}
ROLE_KEY_STYLE = {"hip", "thigh", "calf", "wheel", "knee", "joint", "abad"}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def config_truth_per_joint(config: dict, config_key: str, joints: list[dict]) -> dict[str, float] | None:
    """按 config 自身风格求解逐关节真值（角色键控 / 逐关节直读）。"""

    raw = config.get(config_key)
    if not isinstance(raw, dict) or not raw:
        return None
    first = next(iter(raw))
    if (first in ROLE_KEY_STYLE or first.lower() in ROLE_KEY_STYLE) and first not in joints[0]["name"]:
        truth = {}
        for entry in joints:
            value = raw.get(entry["role"], raw.get("joint"))
            if value is not None:
                truth[entry["name"]] = value
        return truth or None
    lowered = {key.lower(): value for key, value in raw.items()}
    truth = {}
    for entry in joints:
        value = lowered.get(entry["name"].lower())
        if value is not None:
            truth[entry["name"]] = value
    return truth or None


def packages() -> list[Path]:
    return sorted(
        p
        for p in ROBOTS.iterdir()
        if p.is_dir() and (p / "contract_v3.json").exists() and (p / "simulation" / "config.json").exists()
    )


class PhysicsFactsFromContractTest(unittest.TestCase):
    def test_all_packages_resolve_to_contract_single_truth(self) -> None:
        for package in packages():
            with self.subTest(package=package.name):
                facts = physics_facts(package)
                self.assertEqual(facts["source"], "contract_v3", "物理真值必须来自契约 v3")
                self.assertNotIn("needs_migration", facts)

    def test_control_triple_matches_config(self) -> None:
        for package in packages():
            config = load(package / "simulation" / "config.json")
            facts = physics_facts(package)
            with self.subTest(package=package.name):
                for key in CONTROL_KEYS:
                    if config.get(key) is None:
                        continue
                    self.assertEqual(facts[key], config[key], f"{package.name} {key}")

    def test_by_joint_expansion_matches_config_values(self) -> None:
        """DoD 核心：契约 v3 展开 == config 现行逐关节数值（含 armature/frictionloss）。"""

        checked = 0
        for package in packages():
            config = load(package / "simulation" / "config.json")
            contract_v3 = load(package / "contract_v3.json")
            joints = contract_v3["joints"]["actuated"]
            facts = facts_from_contract(contract_v3)
            for contract_key, name in PARAM_KEYS:
                truth = config_truth_per_joint(config, CONFIG_KEY[name], joints)
                if truth is None:
                    continue
                for joint, value in truth.items():
                    with self.subTest(package=package.name, param=name, joint=joint):
                        self.assertEqual(facts["by_joint"][name].get(joint), value)
                    checked += 1
        self.assertGreater(checked, 100, "对拍样本过少，测试可能失效")

    def test_role_view_covers_every_role_in_profile(self) -> None:
        for package in packages():
            contract_v3 = load(package / "contract_v3.json")
            by_role = (contract_v3.get("actuator_profile") or {}).get("by_role") or {}
            facts = facts_from_contract(contract_v3)
            with self.subTest(package=package.name):
                for role, params in by_role.items():
                    if "stiffness" in params:
                        self.assertIn(role, facts["by_role"]["stiffness"], f"{package.name} 角色 {role}")
                    if "effort" in params:
                        self.assertIn(role, facts["by_role"]["torque_limits"], f"{package.name} 角色 {role}")


class FrictionLossMigratedTest(unittest.TestCase):
    """frictionloss 原先只存在于 config，B3 已并入契约 actuator_profile。"""

    def test_default_friction_loss_migrated(self) -> None:
        for package_id, expected in (("unitree_go2", 0.2), ("unitree_go2w", 0.2)):
            with self.subTest(package=package_id):
                contract_v3 = load(ROBOTS / package_id / "contract_v3.json")
                default = (contract_v3.get("actuator_profile") or {}).get("default") or {}
                self.assertEqual(default.get("friction_loss"), expected)

    def test_named_friction_loss_migrated(self) -> None:
        for package_id in ("limx_tron1_sf", "limx_tron1_wf"):
            with self.subTest(package=package_id):
                package = ROBOTS / package_id
                config = load(package / "simulation" / "config.json")
                raw = config.get("frictionloss") or {}
                named = {k: v for k, v in raw.items() if k != "__default__"}
                self.assertTrue(named, f"{package_id} 应有具名 frictionloss")
                facts = physics_facts(package)
                for joint, value in named.items():
                    self.assertEqual(facts["by_joint"]["friction_loss"].get(joint), value, joint)

    def test_packages_without_config_frictionloss_now_declared_in_contract(self) -> None:
        """config 未声明摩擦的包，其摩擦已由契约显式补上（原断言"契约也没有"已过时）。"""

        for package in packages():
            config = load(package / "simulation" / "config.json")
            if config.get("frictionloss"):
                continue
            with self.subTest(package=package.name):
                facts = physics_facts(package)
                self.assertNotEqual(facts["by_joint"]["friction_loss"], {})


class ContractCoverageVsLegacyConfigTest(unittest.TestCase):
    """B3/2b 的前置条件：**契约必须 ⊇ config**，否则适配器翻转会丢数据。

    背景（详见 00_know/40_专题报告/B3_物理事实收敛_适配器差异报告.md）：`adapters/mjlab` 的
    `torque_limits` 查找「无任何兜底」，`armature`/`frictionloss` 只做「小写后精确匹配」。
    若契约缺某个 config 已有的物理量，翻转即表现为**静默丢失限幅/臂量**（不是报错）。

    本测试锁定**已知缺口**：缺口集合一旦变化即失败。
    B3/pre 补全契约后，期望值应收紧为空字典。
    """

    # 已知缺口：契约 actuator_profile 尚未收全的项（B3/pre 的补全清单）
    KNOWN_CONTRACT_GAPS = {"unitree_go2w": ["armature"]}

    @staticmethod
    def _loader_lookup(table: dict | None, joint: str):
        """复刻 scene_builder / load_package_model：小写精确匹配 → __default__ → 不应用。"""

        if not table:
            return None
        lowered = joint.lower()
        if lowered in table:
            return float(table[lowered])
        if "__default__" in table:
            return float(table["__default__"])
        return None

    @staticmethod
    def _strict_lookup(table: dict | None, joint: str):
        """复刻 c.torque_limits.get(name.lower())：无兜底。"""

        if not table:
            return None
        value = table.get(joint.lower())
        return float(value) if value is not None else None

    def test_contract_covers_config_physics_except_known_gaps(self) -> None:
        adapter_params = (
            ("armature", "armature", self._loader_lookup),
            ("friction_loss", "frictionloss", self._loader_lookup),
            ("torque_limits", "torque_limits", self._strict_lookup),
        )
        gaps: dict[str, list[str]] = {}
        for package in packages():
            config = load(package / "simulation" / "config.json")
            contract_v3 = load(package / "contract_v3.json")
            facts = facts_from_contract(contract_v3)
            default = facts.get("default") or {}
            for fact_key, config_key, lookup in adapter_params:
                old_table = config.get(config_key) or {}
                new_table = dict(facts["by_joint"].get(fact_key) or {})
                if fact_key in default:
                    new_table["__default__"] = default[fact_key]
                if not old_table:
                    continue
                for entry in contract_v3["joints"]["actuated"]:
                    joint = entry["name"]
                    if lookup(old_table, joint) is None:
                        continue
                    if lookup(new_table, joint) is None:
                        gaps.setdefault(package.name, [])
                        if fact_key not in gaps[package.name]:
                            gaps[package.name].append(fact_key)

        for value in gaps.values():
            value.sort()
        self.assertEqual(
            gaps, self.KNOWN_CONTRACT_GAPS,
            "契约覆盖缺口发生变化——新增缺口会令适配器翻转静默丢数据，"
            "必须先补全契约（B3/pre），见 00_know/40_专题报告/B3_物理事实收敛_适配器差异报告.md",
        )


class FrictionLossPopulatedTest(unittest.TestCase):
    """B3-friction：14 包的关节摩擦必须**全部显式声明**。

    取值分三类（来源与依据见 00_know/40_专题报告/B3_friction_loss_补齐报告.md）：

    * **A 组**：活跃模型编译即带该值 → 写入幂等，不改变仿真物理
    * **B 组**：活跃模型为 0，但 00_resources/ 参考项目声明非零 → 写入**改变仿真物理**
    * **C 组**：模型与参考均未声明 → 真值为 0，写入仅作显式化（幂等）

    这里把三类值全部锁定，避免今后被静默改动；B 组的行为变更是有意为之。
    """

    # 走 actuator_profile.default 的 12 个包
    EXPECTED_DEFAULT = {
        "unitree_go2": 0.2,             # 既有（B3/1 迁入 config 的 __default__）
        "unitree_go2w": 0.2,            # 既有
        "deeprobotics_lite3": 0.2,      # B
        "unitree_g1": 0.2,             # B
        "unitree_go1": 0.2,            # A
        "zex-w": 0.01,                 # A
        "microduck": 0.0048,           # A
        "deeprobotics_m20": 0.0,       # C（参考 M20_Piper.xml 显式 frictionloss="0"）
        "limx_tron1_pf": 0.0,          # C
        "unitree_b2": 0.0,             # C
        "unitree_b2w": 0.0,            # C
        "wuji_hand": 0.0,              # C
    }
    # 走 by_joint 具名逐关节的 2 个包（B3/1 迁入）
    EXPECTED_BY_JOINT = {"limx_tron1_sf": 0.01, "limx_tron1_wf": 0.01}

    def test_every_package_declares_friction_loss(self) -> None:
        contracts = {
            package.name: load(package / "contract_v3.json") for package in packages()
        }
        for name, contract in contracts.items():
            with self.subTest(package=name):
                profile = contract.get("actuator_profile") or {}
                default = profile.get("default") or {}
                by_joint = profile.get("by_joint") or {}
                declared = "friction_loss" in default or any(
                    isinstance(params, dict) and "friction_loss" in params
                    for params in by_joint.values()
                )
                self.assertTrue(declared, f"{name} 未声明关节摩擦")
                # 消费者侧保证：by_joint 展开后每个驱动关节都有值
                facts = physics_facts(ROBOTS / name)
                for entry in contract["joints"]["actuated"]:
                    self.assertIn(
                        entry["name"], facts["by_joint"]["friction_loss"],
                        f"{name} 关节 {entry['name']} 摩擦未落到 by_joint",
                    )

    def test_default_values_locked(self) -> None:
        for name, expected in self.EXPECTED_DEFAULT.items():
            with self.subTest(package=name):
                contract = load(ROBOTS / name / "contract_v3.json")
                default = (contract.get("actuator_profile") or {}).get("default") or {}
                self.assertEqual(default.get("friction_loss"), expected)

    def test_named_values_locked(self) -> None:
        for name, expected in self.EXPECTED_BY_JOINT.items():
            with self.subTest(package=name):
                contract = load(ROBOTS / name / "contract_v3.json")
                by_joint = (contract.get("actuator_profile") or {}).get("by_joint") or {}
                values = {
                    params["friction_loss"]
                    for params in by_joint.values()
                    if isinstance(params, dict) and "friction_loss" in params
                }
                self.assertEqual(values, {expected})

    def test_intended_behaviour_change_set_is_only_lite3_and_g1(self) -> None:
        """B 组是唯一会改变仿真物理的一档——把集合锁死，防止扩大。"""

        changed = {
            name for name in ("deeprobotics_lite3", "unitree_g1")
            if self.EXPECTED_DEFAULT[name] > 0
        }
        self.assertEqual(changed, {"deeprobotics_lite3", "unitree_g1"})


class LegacyFallbackTest(unittest.TestCase):
    """未迁移包仍可从 config 读取，但必须显式标记，不制造静默双真值。"""

    def test_legacy_config_is_marked_needs_migration(self) -> None:
        sample = load(ROBOTS / "unitree_go2" / "simulation" / "config.json")
        from contracts.physics_binding import facts_from_legacy_config

        facts = facts_from_legacy_config(sample)
        self.assertEqual(facts["source"], "legacy_config")
        self.assertTrue(facts["needs_migration"])
        self.assertEqual(facts["control_hz"], sample["control_hz"])


if __name__ == "__main__":
    unittest.main()
