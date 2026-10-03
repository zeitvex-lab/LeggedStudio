"""T0.2 DoD：内置包契约全量守护测试（真值 contract.json + v2 视图 contract_legacy_v2.json）。

每包断言：
  1. RoleResolver 自洽校验通过、生成的 Pydantic 模型可解析；
  2. actuator_profile 三级展开 == 现行 simulation/config.json 逐关节数值
     （go2w/b2w/m20/zex-w/wuji_hand/microduck 异构包的"人工校对"由此程序化替代）；
  3. action.joint_order 与 v2 视图完全一致；reindex（m20/g1）为合法置换。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from contracts.tests._roster import declared_members, require_package
from contracts.generated import parse_contract
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


class MigratedContractTest(unittest.TestCase):
    def _packages(self) -> list[Path]:
        return sorted(p for p in ROBOTS.iterdir() if (p / "contract.json").exists())

    def test_roster_matches_declared_members(self) -> None:
        # 名册 = 族注册表声明的成员并集（声明驱动；族收敛后旧魔法数字 14/16 作废，
        # agibot_d1 下线、x30 移出、limx/microduck/wuji/g1 不在此分支名册）。
        self.assertEqual({p.name for p in self._packages()}, set(declared_members()))

    def test_every_v3_contract_valid_and_expansion_matches_config(self) -> None:
        for package_dir in self._packages():
            with self.subTest(package=package_dir.name):
                contract = load_json(package_dir / "contract.json")
                legacy = load_json(package_dir / "contract_legacy_v2.json")
                config = load_json(package_dir / "simulation" / "config.json")

                errors = RoleResolver(contract).validate()
                self.assertEqual(errors, [], f"{package_dir.name} 自洽校验失败")
                model = parse_contract(contract)
                self.assertEqual(model.robot_id, legacy["robot_id"])

                resolver = RoleResolver(contract)
                expanded = resolver.expand_actuator_profile()
                joints = contract["joints"]["actuated"]
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
                self.assertEqual(contract["action"]["joint_order"], legacy["action"]["joint_order"])
                reindex = contract["action"].get("reindex_from_model")
                if reindex is not None:
                    self.assertEqual(sorted(reindex), list(range(len(reindex))))

    def test_heterogeneous_packages_keep_structure(self) -> None:
        """异构包的 extra_roles / reindex / wheel 角色不被迁移丢失。"""

        if require_package(self, "microduck"):
            microduck = load_json(ROBOTS / "microduck" / "contract.json")
            self.assertEqual(
                microduck["morphology"]["extra_roles"],
                ["neck_pitch", "head_pitch", "head_yaw", "head_roll"],
            )
        m20 = load_json(ROBOTS / "deeprobotics_m20" / "contract.json")
        self.assertEqual(
            m20["action"]["reindex_from_model"],
            [0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14, 3, 7, 11, 15],
        )
        self.assertIn("wheel", m20["morphology"]["leg_pattern"])
        if require_package(self, "unitree_g1"):
            g1 = load_json(ROBOTS / "unitree_g1" / "contract.json")
            self.assertEqual(g1["morphology"]["id"], "humanoid")
            self.assertIn("waist_yaw", g1["morphology"]["extra_roles"])
            self.assertIsNotNone(g1["action"]["reindex_from_model"])


if __name__ == "__main__":
    unittest.main()
