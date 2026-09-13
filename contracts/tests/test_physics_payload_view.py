"""B3/2 载荷等价性测试：换用契约真值后，前端逐关节解析结果不变。

风险背景（本切片的核心）
------------------------
浏览器载荷原先直传 ``simulation/config.json`` 的 ``stiffness`` / ``damping`` /
``torque_limits``，而各包键风格并不一致：

* ``lite3`` / ``m20``：**逐关节**键（``FL_HipX_joint`` …）
* ``go2`` / ``zex-w``：**角色键控**（``hip`` / ``thigh`` …）+ ``joint`` 兜底
* ``wuji_hand``：**仅** ``joint``

前端 ``web/sim2sim/app.js`` 的 ``controlValue`` 按
``精确关节名 → jointSegment → 分组/角色 → joint → 调用方默认值`` 依次查找。
若换源时只给角色键，"精确关节名"这条路会失配并**静默回退到默认值**——不报错，
只表现为浏览器里策略抽搐。故本测试：

1. 复刻前端解析逻辑，断言**每个关节都被显式覆盖**（绝不回退到 fallback）；
2. 断言解析值与契约 ``by_joint`` 真值一致；
3. 断言与旧 config 的解析结果逐关节相同（过渡期对拍）；
4. 把唯一的有意行为变更（zex-w 获得力矩限幅）**显式锁死**，防止意外漂移混入。
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from contracts.physics_binding import (
    PAYLOAD_MAP_KEYS,
    payload_physics_view,
    physics_facts,
)

WORKSPACE = Path(__file__).resolve().parents[2]
ROBOTS = WORKSPACE / "assets" / "robots"

# config 侧键名（载荷键 -> config 键）
CONFIG_KEY = {"stiffness": "stiffness", "damping": "damping", "torque_limits": "torque_limits"}

_SENTINEL = object()
_LEG_PREFIX = re.compile(
    r"^(fl|fr|rl|rr|lf|rf|lh|rh|l1|r1|l|r|hr|hl|front|rear|left|right)$"
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def joint_segment(joint_name: str) -> str:
    """复刻 web/sim2sim/app.js 的 jointSegment（去腿前缀与尾部 joint 记号）。"""

    parts = [p for p in re.split(r"[^a-z0-9]+", str(joint_name).lower()) if p]
    if len(parts) > 1 and parts[-1] in ("joint", "actuator", "motor"):
        parts.pop()
    if len(parts) > 1 and _LEG_PREFIX.fullmatch(parts[0]):
        parts.pop(0)
    return "_".join(parts) or str(joint_name).lower()


def control_value(values: dict | None, joint_name: str, group: str | None, fallback=_SENTINEL):
    """复刻 controlValue 的四级查找顺序。"""

    table = values or {}
    for key in (joint_name, joint_segment(joint_name), group, "joint"):
        if key is None:
            continue
        if key in table:
            try:
                return float(table[key])
            except (TypeError, ValueError):
                continue
    return fallback


def packages() -> list[Path]:
    return sorted(
        p
        for p in ROBOTS.iterdir()
        if p.is_dir() and (p / "contract_v3.json").exists() and (p / "simulation" / "config.json").exists()
    )


class PayloadResolutionEquivalenceTest(unittest.TestCase):
    def test_every_joint_is_explicitly_covered_never_falls_back(self) -> None:
        """最关键的不变量：任何关节都不许落到 fallback（那正是静默失配的表现）。"""

        for package in packages():
            facts = physics_facts(package)
            view = payload_physics_view(facts)
            joints = load(package / "contract_v3.json")["joints"]["actuated"]
            for param in PAYLOAD_MAP_KEYS:
                # 该参数在契约里整体缺失（如 wuji_hand 无力矩上限）时无覆盖可言，
                # 前端 applyTorqueLimits(None) 本就早退——不属静默失配。
                if not view[param]:
                    continue
                for entry in joints:
                    name, role = entry["name"], entry.get("role")
                    for group in (role, None):
                        with self.subTest(package=package.name, param=param, joint=name, group=group):
                            resolved = control_value(view[param], name, group, _SENTINEL)
                            self.assertIsNot(
                                resolved, _SENTINEL,
                                f"{package.name} {param}: 关节 {name} 未被子表覆盖，将静默回退默认值",
                            )

    def test_resolved_values_equal_contract_truth(self) -> None:
        for package in packages():
            facts = physics_facts(package)
            view = payload_physics_view(facts)
            for param in PAYLOAD_MAP_KEYS:
                for joint, expected in (facts["by_joint"][param] or {}).items():
                    with self.subTest(package=package.name, param=param, joint=joint):
                        self.assertEqual(control_value(view[param], joint, None, _SENTINEL), float(expected))

    def test_resolution_matches_legacy_config_where_declared(self) -> None:
        """过渡期对拍：旧 config 声明过该参数时，新旧解析结果必须逐关节一致。"""

        compared = 0
        for package in packages():
            config = load(package / "simulation" / "config.json")
            view = payload_physics_view(physics_facts(package))
            joints = load(package / "contract_v3.json")["joints"]["actuated"]
            for param in PAYLOAD_MAP_KEYS:
                legacy = config.get(CONFIG_KEY[param])
                if not isinstance(legacy, dict) or not legacy:
                    continue
                for entry in joints:
                    old = control_value(legacy, entry["name"], entry.get("role"), _SENTINEL)
                    new = control_value(view[param], entry["name"], entry.get("role"), _SENTINEL)
                    if old is _SENTINEL:
                        continue
                    with self.subTest(package=package.name, param=param, joint=entry["name"]):
                        self.assertIsNot(new, _SENTINEL)
                        self.assertAlmostEqual(float(new), float(old), places=9)
                    compared += 1
        self.assertGreater(compared, 50, "对拍样本过少，测试可能失效")


class IntendedBehaviourDeltaTest(unittest.TestCase):
    """换源后**唯一**的有意变更必须被显式锁定，其余一律不得漂移。"""

    def test_intended_behaviour_delta_set_is_locked(self) -> None:
        deltas: dict[str, list[str]] = {}
        for package in packages():
            config = load(package / "simulation" / "config.json")
            view = payload_physics_view(physics_facts(package))
            for param in PAYLOAD_MAP_KEYS:
                if bool(config.get(CONFIG_KEY[param])) != bool(view[param]):
                    deltas.setdefault(package.name, []).append(param)
        self.assertEqual(
            deltas,
            {
                "zex-w": ["torque_limits"],
                "microduck": ["torque_limits"],
                "wuji_hand": ["torque_limits"],
            },
            "有意变更集合（00_know/30_参数标准/全部机型_参数来源对照与标准.md §2.6）："
            "zex-w 原本就由契约供给力矩限幅；microduck / wuji_hand 的 effort 原缺失，"
            "现按打包模型补齐（R2 模型层），浏览器由此新增力矩限幅。"
            "除此之外不得出现任何行为漂移",
        )

    def test_zex_w_gains_torque_limits_from_contract(self) -> None:
        config = load(ROBOTS / "zex-w" / "simulation" / "config.json")
        self.assertIsNone(config.get("torque_limits"), "前提：config 侧确实未声明 torque_limits")
        view = payload_physics_view(physics_facts(ROBOTS / "zex-w"))
        self.assertTrue(view["torque_limits"], "契约 by_role.effort 有值，应供给浏览器")
        # 每个驱动关节都能解析出力矩上限（含轮）
        for entry in load(ROBOTS / "zex-w" / "contract_v3.json")["joints"]["actuated"]:
            self.assertIsNot(control_value(view["torque_limits"], entry["name"], entry.get("role")), _SENTINEL)


class FrictionLossDefaultPreservedTest(unittest.TestCase):
    def test_default_key_preserved_for_model_layer(self) -> None:
        """armature/frictionloss 的 __default__ 必须保留（覆盖非驱动 dof）。"""

        view = payload_physics_view(physics_facts(ROBOTS / "unitree_go2"))
        self.assertEqual(view["frictionloss"].get("__default__"), 0.2)

    def test_default_key_matches_contract_declaration(self) -> None:
        """载荷的 __default__ 必须等于契约 default.friction_loss——不凭空造值。"""

        for name in ("unitree_go2", "deeprobotics_lite3", "microduck", "zex-w"):
            with self.subTest(package=name):
                contract = json.loads(
                    (ROBOTS / name / "contract_v3.json").read_text(encoding="utf-8-sig")
                )
                declared = (
                    (contract.get("actuator_profile") or {}).get("default") or {}
                ).get("friction_loss")
                view = payload_physics_view(physics_facts(ROBOTS / name))
                self.assertEqual(view["frictionloss"].get("__default__"), declared)


if __name__ == "__main__":
    unittest.main()
