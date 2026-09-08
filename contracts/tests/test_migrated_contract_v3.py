"""T0.2 DoD：16 包 contract_v3.json 全量守护测试。

每包断言：
  1. RoleResolver 自洽校验通过、Pydantic v3 模型可解析；
  2. actuator_profile 三级展开 == 现行 simulation/config.json 逐关节数值
     （go2w/b2w/m20/zex-w/wuji_hand/microduck 异构包的"人工校对"由此程序化替代）；
  3. action.joint_order 与 v2 contract 完全一致；reindex（m20/g1）为合法置换。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from contracts.generated import parse_v3
from contracts.role_resolver import RoleResolver

WORKSPACE = Path(__file__).resolve().parents[2]
ROBOTS = WORKSPACE / "assets" / "robots"

PARAM_KEYS = (
    ("stiffness", "stiffness"),
    ("damping", "damping"),
    ("torque_limits", "effort"),
    ("armature", "armature"),
)
ROLE_KEY_STYLE = {"hip", "thigh", "calf", "wheel", "knee", "joint", "abad"}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def config_truth_per_joint(config: dict, key: str, joints: list[dict]) -> dict[str, float] | None:
    """现行 config 的 map → 逐关节真值（角色键控展开 / 逐关节直读）。"""

    raw = config.get(key)
    if not isinstance(raw, dict) or not raw:
        return None
    first = next(iter(raw))
    if first in ROLE_KEY_STYLE or first.lower() in ROLE_KEY_STYLE:
        if first.lower() in ROLE_KEY_STYLE and first not in joints[0]["name"]:
            # 角色键控（可能含遗留 'joint' catch-all）
            truth = {}
            for entry in joints:
                value = raw.get(entry["role"], raw.get("joint"))
                if value is not None:
                    truth[entry["name"]] = value
            return truth or None
    lowered = {k.lower(): v for k, v in raw.items()}
    truth = {}
    for entry in joints:
        value = lowered.get(entry["name"].lower())
        if value is not None:
            truth[entry["name"]] = value
    return truth or None


class MigratedContractV3Test(unittest.TestCase):
    def _packages(self) -> list[Path]:
        return sorted(p for p in ROBOTS.iterdir() if (p / "contract_v3.json").exists())

    def test_all_16_packages_migrated(self) -> None:
        self.assertGreaterEqual(len(self._packages()), 16)

    def test_every_v3_contract_valid_and_expansion_matches_config(self) -> None:
        for package_dir in self._packages():
            with self.subTest(package=package_dir.name):
                v3 = load_json(package_dir / "contract_v3.json")
                v2 = load_json(package_dir / "contract.json")
                config = load_json(package_dir / "simulation" / "config.json")

                errors = RoleResolver(v3).validate()
                self.assertEqual(errors, [], f"{package_dir.name} 自洽校验失败")
                model = parse_v3(v3)
                self.assertEqual(model.robot_id, v2["robot_id"])

                resolver = RoleResolver(v3)
                expanded = resolver.expand_actuator_profile()
                joints = v3["joints"]["actuated"]
                for config_key, param in PARAM_KEYS:
                    truth = config_truth_per_joint(config, config_key, joints)
                    if truth is None:
                        continue
                    for joint, value in truth.items():
                        self.assertEqual(
                            expanded[joint].get(param),
                            value,
                            f"{package_dir.name} {config_key}/{joint}",
                        )

                # 动作槽序与 v2 完全一致；reindex 若存在必为合法置换
                self.assertEqual(v3["action"]["joint_order"], v2["action"]["joint_order"])
                reindex = v3["action"].get("reindex_from_model")
                if reindex is not None:
                    self.assertEqual(sorted(reindex), list(range(len(reindex))))

    def test_heterogeneous_packages_keep_structure(self) -> None:
        """异构包的 extra_roles / reindex / wheel 角色不被迁移丢失。"""

        microduck = load_json(ROBOTS / "microduck" / "contract_v3.json")
        self.assertEqual(
            microduck["morphology"]["extra_roles"],
            ["neck_pitch", "head_pitch", "head_yaw", "head_roll"],
        )
        m20 = load_json(ROBOTS / "deeprobotics_m20" / "contract_v3.json")
        self.assertEqual(
            m20["action"]["reindex_from_model"],
            [0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14, 3, 7, 11, 15],
        )
        self.assertIn("wheel", m20["morphology"]["leg_pattern"])
        g1 = load_json(ROBOTS / "unitree_g1" / "contract_v3.json")
        self.assertEqual(g1["morphology"]["id"], "humanoid")
        self.assertIn("waist_yaw", g1["morphology"]["extra_roles"])
        self.assertIsNotNone(g1["action"]["reindex_from_model"])


if __name__ == "__main__":
    unittest.main()
