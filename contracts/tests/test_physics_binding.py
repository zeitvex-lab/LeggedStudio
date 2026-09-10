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

    def test_packages_without_frictionloss_declare_none(self) -> None:
        for package in packages():
            config = load(package / "simulation" / "config.json")
            if config.get("frictionloss"):
                continue
            with self.subTest(package=package.name):
                facts = physics_facts(package)
                self.assertEqual(facts["by_joint"]["friction_loss"], {})


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
