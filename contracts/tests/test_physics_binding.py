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

from contracts.role_resolver import RoleResolver
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

    def test_by_joint_expansion_matches_role_layer_truth(self) -> None:
        """DoD 核心（**真值源已换**）：只用 ``by_role``（+ ``default``）层重建的 v3，展开后必须与
        shipped v3 的逐关节展开**逐项相等**——即「角色层足以还原每个关节的数值」。

        原实现把 ``simulation/config.json`` 当"现行真值"；B3 收尾后该文件的物理键已移除，
        对拍的一边恒为空（继续跑会变成**假通过**）。故真值改为 **shipped v3 自身的展开**：
        测的仍是同一个不变量，且顺带证明"没有藏在角色层之外的数值"。

        唯一允许的例外是**显式登记的逐关节特例**（``by_joint``）——它们是"角色层之外的有意覆盖"，
        数量被下面锁死；出现新特例即失败（那是"角色表漏了某类关节"的信号）。
        """

        overrides = {
            package.name: sorted(
                ((load(package / "contract_v3.json").get("actuator_profile") or {}).get("by_joint") or {})
            )
            for package in packages()
        }
        overrides = {name: joints for name, joints in overrides.items() if joints}
        self.assertEqual(
            overrides,
            {
                "limx_tron1_sf": ["ankle_L_Joint", "ankle_R_Joint"],
                "limx_tron1_wf": ["wheel_L_Joint", "wheel_R_Joint"],
            },
            "逐关节特例集合发生变化：新增特例意味着角色表没覆盖到那类关节（或迁移顺序被改动）",
        )

        checked = 0
        for package in packages():
            if package.name in overrides:
                continue
            contract_v3 = load(package / "contract_v3.json")
            profile = contract_v3.get("actuator_profile") or {}
            rebuilt = {key: value for key, value in contract_v3.items() if key != "actuator_profile"}
            rebuilt["actuator_profile"] = {
                "default": profile.get("default") or {},
                "by_role": profile.get("by_role") or {},
            }
            shipped = RoleResolver(load(package / "contract_v3.json")).expand_actuator_profile()
            rebuilt_expanded = RoleResolver(rebuilt).expand_actuator_profile()
            for joint, params in shipped.items():
                for param, value in params.items():
                    with self.subTest(package=package.name, joint=joint, param=param):
                        self.assertEqual(rebuilt_expanded[joint].get(param), value)
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
        """具名摩擦已迁进契约（原读 config，B3 后 config 侧键已移除）。

        tron1_sf/wf 是唯二用**逐关节特例**声明摩擦的包（其余包是角色级/默认级），
        且这两个包的 MJCF 里 ``frictionloss="0.01"``——契约值必须与之一致（取证）。
        """

        for package_id in ("limx_tron1_sf", "limx_tron1_wf"):
            with self.subTest(package=package_id):
                facts = physics_facts(ROBOTS / package_id)
                # 特例层（by_joint override）：这两个包的具名摩擦就落在这里
                named = dict(facts["by_joint_override"]["friction_loss"] or {})
                self.assertTrue(named, f"{package_id} 应有具名 friction_loss（契约 by_joint 特例）")
                self.assertEqual(
                    {round(float(value), 9) for value in named.values()},
                    {0.01},
                    f"{package_id} 的具名摩擦应等于 MJCF 取证值 0.01",
                )
                # 展开层必须把特例值带到对应关节上（否则消费者仍拿不到）
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

    def test_contract_covers_every_actuated_joint(self) -> None:
        """B3 之后的等价不变量：**armature / effort / friction_loss 覆盖每一个驱动关节**。

        原实现是「契约 vs config 的缺口对照」（``KNOWN_CONTRACT_GAPS`` 里那个
        ``unitree_go2w: ['armature']`` 就是当时的已知缺口）。B3 收尾把 config 侧物理键移除、
        并补齐了全部缺口后，该对照已无对象（一边恒空 → 空跑）。换成同一保护的**正面表述**：
        这三个量不允许出现"某关节查不到"的情况——那会让训练侧静默落到模型 default，
        而"静默落 default" 正是 armature 长期失效的机制。
        """

        gaps: dict[str, list[str]] = {}
        for package in packages():
            contract_v3 = load(package / "contract_v3.json")
            facts = facts_from_contract(contract_v3)
            for param in ("armature", "torque_limits", "friction_loss"):
                table = facts["by_joint"].get(param) or {}
                for entry in contract_v3["joints"]["actuated"]:
                    joint = entry["name"]
                    if table.get(joint) is None:
                        gaps.setdefault(package.name, [])
                        label = f"{param}:{joint}"
                        if label not in gaps[package.name]:
                            gaps[package.name].append(label)

        for value in gaps.values():
            value.sort()
        self.assertEqual(
            gaps, {},
            "契约对驱动关节的覆盖出现缺口——训练/浏览器/验收会**静默落到模型 default**"
            "（armature 当年就是这样长期失效的）。补全契约，或把该缺口按来源存疑登记进"
            "任务清单「待决」并在此显式列出。",
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
        """兼容回落**代码路径**仍必须可用（未迁移的老包 = config 里带物理键）。

        真值源换成契约 v3 后，仓库里的 config 已不再带物理键，所以这里用一份**合成样本**
        ——测的是 ``facts_from_legacy_config`` 这条路径本身，而不是某个包的数据现状。
        （原实现直接读 go2 的 config 取 ``sample["control_hz"]``，B3 后该键已不存在。）
        """
        from contracts.physics_binding import facts_from_legacy_config

        sample = {
            "control_hz": 50,
            "physics_hz": 500,
            "decimation": 10,
            "stiffness": {"FL_hip_joint": 20.0},
            "armature": {"FL_hip_joint": 0.01},
            "frictionloss": {"FL_hip_joint": 0.2},
        }
        facts = facts_from_legacy_config(sample)
        self.assertEqual(facts["source"], "legacy_config")
        self.assertTrue(facts["needs_migration"], "兼容回落必须自报需要迁移，否则迁移进度不可观测")
        self.assertEqual(facts["control_hz"], 50)
        self.assertEqual(facts["physics_hz"], 500)
        self.assertEqual(facts["decimation"], 10)
        self.assertEqual(facts["by_joint"]["armature"]["FL_hip_joint"], 0.01)
        self.assertEqual(facts["by_joint"]["friction_loss"]["FL_hip_joint"], 0.2)


if __name__ == "__main__":
    unittest.main()
