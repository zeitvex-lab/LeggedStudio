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
    LEGACY_CONFIG_PHYSICS_KEYS,
    PAYLOAD_MAP_KEYS,
    payload_physics_view,
    physics_facts,
)

WORKSPACE = Path(__file__).resolve().parents[2]
ROBOTS = WORKSPACE / "assets" / "robots"

# config 侧键名（载荷键 -> config 键）
CONFIG_KEY = {"stiffness": "stiffness", "damping": "damping", "torque_limits": "torque_limits"}

#: 已登记的**载荷覆盖缺口**（package → param → 未被子表覆盖的关节）。
#:
#: 本文件最关键的不变量是"任何关节都不许落到 fallback"——浏览器 ``controlValue`` 查不到
#: 就用调用方默认值，**不报错**，只表现为策略抽搐。所以缺口必须显式登记、**只能减不能增**，
#: 而不是把断言放宽。
#:
#: **当前为空**（2026-09-13 多源对照后补齐）。历史唯一一条缺口
#: ``unitree_g1 / velocity_limits``（6 个关节 = ankle_pitch/ankle_roll/waist_roll/waist_pitch
#: 四个角色）的查清过程，正是"多源对照"方法的样板：
#:
#: * 最初只按训练树 ``g1_constants.py`` 的**电机型号**反查——该表只有 5/10/25/88/139 五种
#:   ``effort_limit``，而这四个角色是 ``50``，于是判为"来源存疑"；
#: * 转去对照**官方 URDF** ``unitree_robotics/g1_description/g1_29dof.urdf``：四个角色写得
#:   明明白白 ``effort="50" velocity="37"``，且同文件 ``waist_yaw``（``88 / 32``）与本契约
#:   已填的 32 完全一致 → 两套官方来源互证；
#: * 官方训练常量里的注释给出了 50 的来历：「Waist pitch/roll and ankles are 4-bar linkages
#:   with 2 5020 actuators … assume a nominal 1:1 gear ratio … ``effort_limit = 5020 × 2``」——
#:   并联 2 电机力矩相加、速度不变 ⇒ 关节侧速度 = 5020 自身 ``velocity_limit`` = 37。
#:
#: 结论：**原本就有**（写在官方 URDF 的 ``<limit>`` 里），不是迁移时被去掉的；缺的原因是
#: 我们只看了电机型号表、没看关节侧 URDF。故按 37.0 补齐。
#:
#: **现存缺口（2026-09-13 全 14 机型跨源审计后）**：轮腿机的**轮关节在任何源里都没有 velocity**
#: ——
#: * `unitree_b2w`：官方 URDF `b2w_description.urdf` 里**根本没有** `*_wheel_joint`（轮只出现在
#:   MJCF 里，且只给了 `actuatorfrcrange`）；官方 MJCF 同样只有力、没有速度上限；
#: * `unitree_go2w`：同上（官方 URDF 的轮写成 `*_foot_joint`/`*_foot_motor_joint`，
#:   且只有 `effort`）。
#:
#: 按方法判定属「**原本就没有**」——不是我们没填，也不是迁移时丢的。故登记为已知缺口。
#: 新增缺口时同样必须给出**来源依据**（哪个源、哪个文件、哪一行），不许凭感觉填。
KNOWN_COVERAGE_GAPS: dict[str, dict[str, list[str]]] = {
    "unitree_b2w": {
        "velocity_limits": [
            "FR_wheel_joint",
            "FL_wheel_joint",
            "RR_wheel_joint",
            "RL_wheel_joint",
        ],
    },
    "unitree_go2w": {
        "velocity_limits": [
            "FL_wheel_joint",
            "FR_wheel_joint",
            "RL_wheel_joint",
            "RR_wheel_joint",
        ],
    },
}

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
        """最关键的不变量：任何关节都不许落到 fallback（那正是静默失配的表现）。

        已知缺口逐项登记在 :data:`KNOWN_COVERAGE_GAPS`；**出现新缺口即失败**，
        且失败信息给出完整集合差异（比逐条 subTest 更容易看出"哪个包新掉了哪个参数"）。
        """

        actual: dict[str, dict[str, list[str]]] = {}
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
                    # 前端按 role 作为 group 查表；两条路径（role / None）都必须命中
                    if all(
                        control_value(view[param], name, group, _SENTINEL) is not _SENTINEL
                        for group in (role, None)
                    ):
                        continue
                    bucket = actual.setdefault(package.name, {}).setdefault(param, [])
                    if name not in bucket:
                        bucket.append(name)

        self.assertEqual(
            actual,
            KNOWN_COVERAGE_GAPS,
            "载荷覆盖缺口集合发生变化：新缺口会让浏览器**静默回退默认值**（表现为策略抽搐）；"
            "若确属有意（数据不足且已登记来源存疑），把它写进 KNOWN_COVERAGE_GAPS 并附依据。",
        )

    def test_resolved_values_equal_contract_truth(self) -> None:
        for package in packages():
            facts = physics_facts(package)
            view = payload_physics_view(facts)
            for param in PAYLOAD_MAP_KEYS:
                for joint, expected in (facts["by_joint"][param] or {}).items():
                    with self.subTest(package=package.name, param=param, joint=joint):
                        self.assertEqual(control_value(view[param], joint, None, _SENTINEL), float(expected))

    def test_legacy_config_no_longer_carries_physics_keys(self) -> None:
        """B3 已完成：``simulation/config.json`` 不许再出现任何物理键。

        原先这里是「新旧逐关节对拍」（过渡期护栏）。B3 收尾把 8 个重复物理键从 14 包移除后，
        对拍的一边恒为空——继续留着只会变成**假通过**。取而代之的新不变量更硬：
        **真值只剩契约一处**，任何物理键重新出现在 config 里即失败（防双写回潮）。
        """

        for package in packages():
            config = load(package / "simulation" / "config.json")
            leftover = sorted(key for key in config if key in LEGACY_CONFIG_PHYSICS_KEYS)
            with self.subTest(package=package.name):
                self.assertEqual(
                    leftover, [],
                    f"{package.name} 的 simulation/config.json 又出现了物理键 {leftover}——"
                    f"B3 已把物理真值收敛到契约 v3，写回去等于重开两个家",
                )


class IntendedBehaviourDeltaTest(unittest.TestCase):
    """换源后**唯一**的有意变更必须被显式锁定，其余一律不得漂移。"""

    def test_intended_behaviour_delta_set_is_locked(self) -> None:
        """换源带来的**有意变更**锁定为一条可长期复跑的语义。

        原实现是与旧 config 对拍算出"行为变更集合"；B3 之后 config 侧已无物理键，
        对拍无从进行（会变成"14 包全部新增"的假结论）。改为直接锁死那条语义本身
        （00_know/04_参数真值标准.md §4.6）：
        **zex-w 原本就由契约供给力矩限幅；microduck / wuji_hand 的 effort 原缺失，
        现按打包模型补齐（R2 模型层）→ 浏览器由此新增力矩限幅**。其余包不得出现漂移：
        即"力矩限幅供给包"恰好是这三个 + 本来就有的那些。
        """

        supplied = sorted(
            package.name
            for package in packages()
            if payload_physics_view(physics_facts(package))["torque_limits"]
        )
        intended = {"zex-w", "microduck", "wuji_hand"}
        self.assertTrue(intended <= set(supplied), f"这三个包必须由契约供给力矩限幅，实际 {supplied}")
        self.assertEqual(
            supplied,
            sorted(package.name for package in packages()),
            "力矩限幅供给集合发生变化：换源后应为**全部 14 包**都由契约供给"
            "（其中 zex-w / microduck / wuji_hand 是换源时新增的三个，属有意变更）",
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
