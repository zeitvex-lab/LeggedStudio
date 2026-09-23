#!/usr/bin/env python3
"""H23：sim2sim 执行器/滤波一致性审计（浏览器下发 ↔ 契约真值 ↔ rc_old 参考事实）。

## 背景（任务清单 H23）

rc_old 实测部署参数：腿 kp/kd = ``50/1.5``、轮 kd = ``1.0``、力矩上限 ``17 Nm``，
低通 ``lpf_legs 5.0 / lpf_wheels 15.0``（取证路径见 :data:`RC_OLD_CONTRACT_HPP` /
:data:`RC_OLD_BRIDGE_CPP`）。本仓"物理真值唯一"：PD/armature/频率只认契约真值
（``contracts/physics_binding.py``），浏览器 sim2sim 的执行器增益由
``backend/simulation_api.py::browser_simulation_config`` 从
``payload_physics_view(physics_facts(root))`` 下发（``robot.control`` 是显式白名单）。

## 硬不变量（任一破坏 → exit 1）

a) **浏览器下发的每机型执行器增益 == 契约真值 逐关节展开**：按
   ``web/sim2sim/app.js::controlValue`` 的查找顺序（精确关节名 → 去前缀段 →
   分组/角色 → ``joint`` 兜底 → 前端默认）逐关节复核 stiffness/damping/
   torque_limits；armature/frictionloss/velocity_limits 与
   :func:`contracts.physics_binding.joint_constant_tables` 逐键对账。
   端点在载荷为空时会以内置默认（hip/thigh/calf=50/1.5…）顶上——契约没声明的值
   被端点" fabrication "进仿真也判红。
b) **各包 ``simulation/config.json`` 无 B3 废弃物理键残留**（B3 口径 =
   ``LEGACY_CONFIG_PHYSICS_KEYS``，顶层键）。嵌套 ``control.stiffness`` 类死数据
   不判红（B3 口径之外、无任何消费者），但逐条列入报告。
c) **D8 电机参数卡数据源（``backend/package_records.package_contract_views``）与浏览器载荷
   同形状同值**。
d) **端点白名单接线静态钉住**：审计不 import ``simulation_api``（它拉 mujoco），
   而是用同一批原语重建载荷； therefore 必须钉住端点源码仍按
   ``payload_physics_view(physics_facts(root))`` 的六个键原样装配 ``robot.control``
   ——钉住断了说明"重建载荷"与"端点真实载荷"可能分叉，必须人工复核后再放行。

## rc_old 参考事实（**不判红**，gating=false）

rc_old 的 PD/lpf 数字只作为参考事实写进报告：本仓以契约为真值，"上游参照 ≠ 本仓契约"
是预期（两台不同的东西）；判红的只有**我们自己的两端不一致**。参考值缺文件时如实
降级（``status="missing"``），不崩、不判红。

## 用法

    python tools/audit_sim2sim_consistency.py            # 人读报告
    python tools/audit_sim2sim_consistency.py --json     # 机读（CI 门禁判 exit code）

## 依赖边界

零仿真依赖：不 import mujoco / torch / mjlab。只用 contracts 物理绑定与
``backend.simulation_browser`` 的包定位（与端点同一条链），fastapi 随
backend/requirements.txt 提供。
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.physics_binding import (  # noqa: E402
    LEGACY_CONFIG_PHYSICS_KEYS,
    joint_constant_tables,
    payload_physics_view,
    physics_facts,
)
from contracts.role_resolver import RoleResolver  # noqa: E402

SIMULATION_API = ROOT / "backend" / "simulation_api.py"
ROBOTS_DIR = ROOT / "assets" / "robots"
RC_OLD_V3_DIR = ROOT / "00_resources" / "rc_old" / "RC_WheelLeg" / "05_software" / "real" / "sim2real_ros2_v3"
RC_OLD_CONTRACT_HPP = RC_OLD_V3_DIR / "src" / "sim2real_common" / "include" / "sim2real_common" / "deployment_contract.hpp"
RC_OLD_BRIDGE_CPP = RC_OLD_V3_DIR / "src" / "sim2real_hw" / "src" / "hardware_bridge_node.cpp"

SCHEMA = "sim2sim-consistency-audit-1.0"
#: 数值比较容差（JSON 浮点原样透传时应当精确相等；容差只为防御序列化抖动）
TOL = 1e-9

#: ``browser_simulation_config`` 里 ``robot.control`` 两个 ``or {...}`` 回退字面量
#: （backend/simulation_api.py）。契约载荷为空时端点会把它们顶进去——那就是
#: "契约没声明的值进了仿真"，必须判红。
ENDPOINT_STIFFNESS_FALLBACK = {"hip": 50.0, "thigh": 50.0, "calf": 50.0, "joint": 50.0}
ENDPOINT_DAMPING_FALLBACK = {"hip": 1.5, "thigh": 1.5, "calf": 1.5, "wheel": 1.0, "joint": 1.5}

#: 端点接线的静态钉住：这些片段必须原样出现在 backend/simulation_api.py。
#: （审计重建载荷 ≠ 调用端点；钉住断了 = 重建与端点可能分叉，审计结论作废。）
ENDPOINT_WIRING_PINS = (
    ("载荷来源：physics_facts(root)", "physics = physics_facts(root)"),
    ("载荷视图：payload_physics_view(physics)", "payload_physics = payload_physics_view(physics)"),
    ("白名单 stiffness 透传", '"stiffness": payload_physics["stiffness"] or'),
    ("白名单 damping 透传", '"damping": payload_physics["damping"] or'),
    ("白名单 torque_limits 透传", '"torque_limits": payload_physics["torque_limits"] or None'),
    ("白名单 armature 透传", '"armature": payload_physics["armature"] or {}'),
    ("白名单 frictionloss 透传", '"frictionloss": payload_physics["frictionloss"] or {}'),
    ("白名单 velocity_limits 透传", '"velocity_limits": payload_physics.get("velocity_limits") or None'),
    ("滤波参数 action_filter_cutoffs 下发", '"action_filter_cutoffs": ('),
    ("PD settle 下发", '"settle_steps": simulation_config.get("settle_steps"'),
)

#: rc_old 参考事实的抽取规则（对上游文件做正则取证，带行号证据）
_RC_PD_PATTERNS = {
    "leg_kp": (re.compile(r"kLegKp\s*=\s*([0-9.]+)f"), RC_OLD_CONTRACT_HPP),
    "leg_kd": (re.compile(r"kLegKd\s*=\s*([0-9.]+)f"), RC_OLD_CONTRACT_HPP),
    "wheel_kd": (re.compile(r"kWheelKd\s*=\s*([0-9.]+)f"), RC_OLD_CONTRACT_HPP),
}
_RC_LPF_PATTERN = re.compile(
    r"lpf_(legs|wheels)_\s*=\s*std::make_unique<sim2real_common::LowPassFilter>\(\s*([0-9.]+)"
)
_RC_TORQUE_PATTERN = re.compile(r"PARAM_TORQUE_LIMIT,\s*([0-9.]+)f")

# --- 浏览器增益解析（照抄 web/sim2sim/app.js，刻意独立于运行时） --------------------
#
# 审计必须独立复刻浏览器查找顺序（app.js::controlValue / jointSegment / jointGroup），
# 否则同一处 bug 会同时骗过运行与审计（tools/audit_policy_gains.py 同一原则）。


def joint_segment(joint_name: str) -> str:
    """照抄 ``app.js::jointSegment``：去腿侧前缀与结尾 joint/actuator/motor 词元。

    ``fl_hip_abduction_joint -> hip_abduction``、``left_hip_yaw -> hip_yaw``。
    """
    parts = [p for p in re.split(r"[^a-z0-9]+", str(joint_name).lower()) if p]
    if len(parts) > 1 and parts[-1] in ("joint", "actuator", "motor"):
        parts.pop()
    if len(parts) > 1 and parts[0] in (
        "fl", "fr", "rl", "rr", "lf", "rf", "lh", "rh", "l1", "r1",
        "l", "r", "hr", "hl", "front", "rear", "left", "right",
    ):
        parts.pop(0)
    return "_".join(parts) or str(joint_name).lower()


def joint_group(joint_name: str) -> str:
    """照抄 ``app.js::jointGroup``：wheel/foot→wheel、calf、thigh、其余→hip。"""
    name = str(joint_name).lower()
    if "wheel" in name or "foot" in name:
        return "wheel"
    if "calf" in name:
        return "calf"
    if "thigh" in name:
        return "thigh"
    return "hip"


def browser_control_value(table: dict | None, joint_name: str, default=None):
    """``app.js::controlValue`` 的忠实复刻（stiffness/damping/torque 用）。

    键序 = 精确关节名（**原样大小写**）→ 去前缀段 → 分组/角色 → ``joint`` 兜底 → default。
    注意真实实现没有"小写关节名"这一步——审计不复刻不存在的查找路径，
    否则会把浏览器命中不了的键当成命中（假绿）或反之（假红）。
    """
    tab = table or {}
    joint = str(joint_name)
    for key in (joint, joint_segment(joint), joint_group(joint), "joint"):
        if key in tab:
            value = tab[key]
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number):
                return number
    return default


def browser_velocity_value(table: dict | None, joint_name: str, default=None):
    """``app.js::applyVelocityLimits`` 的忠实复刻（velocity_limits 用）。

    键序 = 精确关节名（原样大小写）→ 去前缀段 → 分组/角色 → ``joint.lower()``（**最后**，
    与 controlValue 不同）→ default。真实实现**没有** ``"joint"`` 兜底键——
    故意不一致的两条查找路径必须分别复刻（见 web/sim2sim/app.js 两函数源码）。
    """
    tab = table or {}
    joint = str(joint_name)
    for key in (joint, joint_segment(joint), joint_group(joint), joint.lower()):
        if key in tab:
            value = tab[key]
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number):
                return number
    return default


# --- 端点载荷重建（同一批原语；接线由 ENDPOINT_WIRING_PINS 钉住） --------------------


def joint_order_for(root: Path, v3: dict) -> list[str]:
    """与端点同链的动作关节序：预设 v2 ``contract_legacy_v2.json`` → v3 ``joints.actuated``。"""
    v2_path = root / "contract_legacy_v2.json"
    if v2_path.is_file():
        try:
            v2 = json.loads(v2_path.read_text(encoding="utf-8-sig"))
            order = list((v2.get("action") or {}).get("joint_order") or (v2.get("joints") or {}).get("actuated_joints") or [])
            if order:
                return [str(name) for name in order]
        except (OSError, json.JSONDecodeError):
            pass
    actuated = (v3.get("joints") or {}).get("actuated") or []
    names = [entry.get("name") for entry in actuated if isinstance(entry, dict) and entry.get("name")]
    if not names:
        names = list((v3.get("action") or {}).get("joint_order") or (v3.get("joints") or {}).get("actuated_joints") or [])
    return [str(name) for name in names]


def delivered_control_maps(root: Path) -> tuple[dict, dict, dict]:
    """重建 ``browser_simulation_config`` 下发的 ``robot.control`` 物理载荷。

    返回 ``(facts, payload_view, delivered)``；``delivered`` 含端点两个 ``or {…}``
    回退字面量的效果（载荷为空时以内置默认顶上）。
    """
    facts = physics_facts(root)
    payload = payload_physics_view(facts)
    delivered = {
        "stiffness": dict(payload.get("stiffness") or {}) or dict(ENDPOINT_STIFFNESS_FALLBACK),
        "damping": dict(payload.get("damping") or {}) or dict(ENDPOINT_DAMPING_FALLBACK),
        "torque_limits": dict(payload.get("torque_limits") or {}) or None,
        "armature": dict(payload.get("armature") or {}),
        "frictionloss": dict(payload.get("frictionloss") or {}),
        "velocity_limits": dict(payload.get("velocity_limits") or {}) or None,
    }
    return facts, payload, delivered


def read_simulation_config(root: Path) -> dict:
    path = root / "simulation" / "config.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


# --- 各检查项 ----------------------------------------------------------------------


def check_config_residuals(config: dict) -> tuple[list[str], list[str]]:
    """B3 口径复检：返回 ``(顶层废弃物理键, 嵌套 control 内的物理键)``。"""
    top = [key for key in LEGACY_CONFIG_PHYSICS_KEYS if key in config]
    nested: list[str] = []
    control = config.get("control")
    if isinstance(control, dict):
        nested = [
            key for key in ("stiffness", "damping", "torque_limits", "velocity_limits", "armature", "frictionloss")
            if key in control
        ]
    return top, nested


def check_endpoint_wiring(source: str) -> list[str]:
    """端点接线钉住：返回缺失的钉住名（空 = 接线完好）。"""
    return [name for name, needle in ENDPOINT_WIRING_PINS if needle not in source]


def check_package(root: Path) -> dict:
    """对单个机器人包跑 a/c 全部一致性检查，返回报告行（含 problems）。"""
    rel_root = root
    try:
        rel_root = root.resolve().relative_to(ROOT)
    except ValueError:
        rel_root = root
    problems: list[dict] = []
    gain_problems: list[dict] = []  # a) 增益/常量一致性的判红项（gains_equal_contract 的依据）
    infos: list[dict] = []

    def problem(check: str, detail: str, file: str | None = None, *, gain: bool = False) -> None:
        entry = {
            "robot": root.name,
            "check": check,
            "file": str(file or rel_root),
            "evidence": detail,
        }
        problems.append(entry)
        if gain:
            gain_problems.append(entry)

    facts, payload, delivered = delivered_control_maps(root)
    v3_path = root / "contract.json"
    v3: dict = {}
    if v3_path.is_file():
        try:
            v3 = json.loads(v3_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            problem("contract_truth 可解析", f"读取失败：{exc}", str(v3_path))
    if facts.get("source") != "contract":
        problem(
            "物理真值来源=契约真值",
            f"physics_facts(source)={facts.get('source')!r}（B3 之后浏览器/训练必须同读契约真值，"
            "回落 legacy config 即两端可能各说各话）",
            str(v3_path if not v3_path.is_file() else rel_root),
            gain=True,
        )

    order = joint_order_for(root, v3)
    expanded: dict[str, dict] = {}
    try:
        expanded = RoleResolver(v3).expand_actuator_profile() if v3 else {}
    except Exception as exc:  # noqa: BLE001 单包契约问题不中断整个审计
        problem("契约三级展开", f"RoleResolver 展开失败：{exc}", str(v3_path))

    # a-1) stiffness/damping/torque_limits：浏览器逐关节解析值 == 契约逐关节展开
    for key, delivered_map in (("stiffness", delivered["stiffness"]), ("damping", delivered["damping"])):
        payload_map = payload.get(key) or {}
        if not payload_map and delivered_map:
            problem(
                f"{key} 载荷 fabrication",
                f"契约未声明 {key}，但端点以内置默认下发 {delivered_map}"
                f"（browser_simulation_config 的 `or {{...}}` 回退字面量顶进仿真）",
                gain=True,
            )
        for joint in order:
            truth = (expanded.get(joint) or {}).get(key)
            got = browser_control_value(delivered_map, joint)
            if truth is None and got is None:
                continue
            if truth is None:
                problem(
                    f"{key} 逐关节一致",
                    f"{joint}: 浏览器解析到 {got:g}，契约未声明（前端将静默用默认值）",
                    str(v3_path),
                    gain=True,
                )
            elif got is None:
                problem(
                    f"{key} 逐关节一致",
                    f"{joint}: 契约 {float(truth):g}，浏览器按 controlValue 查找序全部落空"
                    "（键形态与前端查找不匹配，会静默回退前端默认）",
                    str(v3_path),
                    gain=True,
                )
            elif not math.isclose(got, float(truth), rel_tol=TOL, abs_tol=TOL):
                problem(
                    f"{key} 逐关节一致",
                    f"{joint}: 浏览器下发 {got:g} ≠ 契约 {float(truth):g}",
                    str(v3_path),
                    gain=True,
                )

    tau_map = delivered["torque_limits"]
    for joint in order:
        truth = (expanded.get(joint) or {}).get("effort")
        got = browser_control_value(tau_map, joint)
        if truth is None and got is None:
            continue
        if truth is None:
            problem(
                "torque_limits 逐关节一致",
                f"{joint}: 浏览器解析到力矩上限 {got:g}，契约未声明 effort",
                str(v3_path),
                gain=True,
            )
        elif got is None:
            problem(
                "torque_limits 逐关节一致",
                f"{joint}: 契约 effort={float(truth):g}，浏览器力矩上限查找落空（将不设限）",
                str(v3_path),
                gain=True,
            )
        elif not math.isclose(got, float(truth), rel_tol=TOL, abs_tol=TOL):
            problem(
                "torque_limits 逐关节一致",
                f"{joint}: 浏览器下发 {got:g} ≠ 契约 {float(truth):g}",
                str(v3_path),
                gain=True,
            )

    # a-2) armature/frictionloss/velocity_limits：浏览器载荷 == joint_constant_tables()
    #   * armature/frictionloss 是逐关节常量（+ __default__），载荷与常量表必须逐键相等；
    #   * velocity_limits 的载荷视图额外带角色键（hip/thigh/calf…，浏览器逐关节查找
    #     落空时的兜底路径），常量表只收逐关节——故按**浏览器查找序逐关节**对账：
    #     常量表里的每个关节，浏览器解析值必须一致；载荷里多出的"逐关节键"必须
    #     也在常量表里（角色键不算数，它们不是逐关节真值）。
    tables = joint_constant_tables(root)
    for key, table_key in (("armature", "armature"), ("frictionloss", "frictionloss"), ("velocity_limits", "velocity_limits")):
        delivered_map = delivered.get(key) or {}
        table = tables.get(table_key) or {}
        norm = lambda m: {str(k).lower(): float(v) for k, v in m.items()}  # noqa: E731
        if key == "velocity_limits":
            # 逐关节统一对账（覆盖 order ∪ 常量表）：训练侧取 joint.lower() → __default__
            # （scene_builder 的消费口径），浏览器按 applyVelocityLimits 查找序（精确
            # 大小写/段/角色/joint.lower()）——同一关节两端口径必须同值；训练侧没有而
            # 浏览器解析得到（含角色键兜底）也判红。
            problems_before = len(gain_problems)
            table_norm = norm(table)
            order_l = [(str(j), str(j).lower()) for j in order]
            table_joints_l = sorted(k for k in table_norm if k != "__default__")
            known_l = {low for _, low in order_l} | set(table_joints_l)
            check_pairs = [(name, low) for name, low in order_l]
            check_pairs += [(low, low) for low in table_joints_l]
            seen: set[str] = set()
            for name, low in check_pairs:
                if low in seen:
                    continue
                seen.add(low)
                got = browser_velocity_value(delivered_map, name)
                if low in table_norm:
                    training = table_norm[low]
                elif "__default__" in table_norm:
                    training = table_norm["__default__"]
                else:
                    training = None
                if training is None and got is None:
                    continue
                got_text = "None（查找落空）" if got is None else f"{got:g}"
                if training is None:
                    problem(
                        f"{key} == joint_constant_tables",
                        f"{name}: 训练侧常量表无限幅，浏览器却解析到 {got_text}"
                        "（角色/兜底键把限幅带给了训练没有的关节）",
                        gain=True,
                    )
                elif got is None or not math.isclose(got, training, rel_tol=TOL, abs_tol=TOL):
                    problem(
                        f"{key} == joint_constant_tables",
                        f"{name}: 浏览器解析 {got_text} ≠ 训练侧常量表 {training:g}",
                        gain=True,
                    )
            # 判"逐关节键"的口径：键必须是**契约动作关节名**（小写）；角色键（by_role
            # 声明的角色名，g1/microduck 的角色本身就叫 hip_pitch 等）与 joint/__default__
            # 兜底键是载荷视图的合法兜底路径，不算逐关节真值。
            role_names = {str(r).lower() for r in (facts.get("by_role") or {}).get("velocity_limits") or {}}
            extra_joints = sorted(
                k for k in norm(delivered_map)
                if k not in table_joints_l and k not in known_l | role_names | {"joint", "__default__"}
            )
            if extra_joints:
                problem(
                    f"{key} == joint_constant_tables",
                    f"浏览器载荷带常量表没有的**逐关节**速度限幅 {extra_joints[:6]}"
                    "（训练侧没有该关节的限幅，两端不一致）",
                    gain=True,
                )
            if len(gain_problems) == problems_before and not table and delivered_map:
                problem(
                    f"{key} == joint_constant_tables",
                    "契约未声明速度限幅，浏览器载荷却带了 "
                    f"{sorted(norm(delivered_map))[:6]}",
                    gain=True,
                )
            continue
        left, right = norm(delivered_map), norm(table)
        if left != right:
            only_browser = sorted(set(left) - set(right))
            only_tables = sorted(set(right) - set(left))
            differing = sorted(k for k in set(left) & set(right) if not math.isclose(left[k], right[k], rel_tol=TOL, abs_tol=TOL))
            problem(
                f"{key} == joint_constant_tables",
                f"浏览器载荷 {len(left)} 键 vs 训练侧常量表 {len(right)} 键；"
                f"仅浏览器有 {only_browser[:6]}，仅常量表有 {only_tables[:6]}，"
                f"数值不同 {[(k, left[k], right[k]) for k in differing[:6]]}",
                gain=True,
            )

    # b) B3 口径复检（顶层废弃物理键）；嵌套死数据只登记不判红
    config = read_simulation_config(root)
    config_path = root / "simulation" / "config.json"
    top_residuals, nested_residuals = check_config_residuals(config)
    if top_residuals:
        problem(
            "simulation/config.json 无 B3 废弃物理键",
            f"残留 {sorted(top_residuals)}（LEGACY_CONFIG_PHYSICS_KEYS）",
            str(config_path),
        )
    for key in nested_residuals:
        infos.append({
            "robot": root.name,
            "kind": "dead_nested_physics",
            "file": str(config_path),
            "evidence": f"config.control.{key} 仍存物理数据（B3 口径之外的死数据："
                        "端点只从 control 块读 decimation/physics_hz/action_filter_cutoffs/settle_steps，"
                        "增益消费链已全部改读契约真值）——建议随下次保存链清理",
        })

    # c) D8 电机参数卡数据源 == 浏览器载荷（backend/package_records.package_contract_views）
    try:
        from backend.package_records import package_contract_views

        view = package_contract_views(root)["physics"]
        expected = dict(payload)
        expected["source"] = facts.get("source")
        expected["needs_migration"] = bool(facts.get("needs_migration"))
        if view != expected:
            differing = sorted(k for k in set(view) | set(expected) if view.get(k) != expected.get(k))
            problem(
                "D8 电机参数卡 == 浏览器载荷",
                f"package_records.package_contract_views 与 payload_physics_view 在 {differing[:6]} 上不一致",
            )
    except Exception as exc:  # noqa: BLE001
        problem("D8 电机参数卡 == 浏览器载荷", f"package_contract_views 调用失败：{exc}")

    # 滤波参考（H23 的 lpf 一侧）：端点从包配置下发 action_filter_cutoffs
    cutoffs = config.get("action_filter_cutoffs")
    if not isinstance(cutoffs, dict):
        control_block = config.get("control")
        cutoffs = control_block.get("action_filter_cutoffs") if isinstance(control_block, dict) else None

    return {
        "robot": root.name,
        "root": str(rel_root).replace("\\", "/"),
        "physics_source": facts.get("source"),
        "joint_count": len(order),
        "gains_equal_contract": not gain_problems,
        "physics_view_equal_payload": not any(p["check"] == "D8 电机参数卡 == 浏览器载荷" for p in problems),
        "action_filter_cutoffs": {str(k): float(v) for k, v in cutoffs.items()} if isinstance(cutoffs, dict) else None,
        "config_residuals": sorted(top_residuals),
        "problems": problems,
        "infos": infos,
    }


# --- rc_old 参考事实（不判红） ------------------------------------------------------


def _match_with_line(text: str, pattern: re.Pattern) -> tuple[str | None, int | None]:
    match = pattern.search(text)
    if not match:
        return None, None
    return match.group(1), text[: match.start()].count("\n") + 1


def rc_old_reference(rc_old_hpp: Path | None = None, rc_old_cpp: Path | None = None) -> dict:
    """抽取 rc_old 部署侧 PD / lpf / 力矩上限作为**参考事实**；缺文件如实降级。"""
    hpp = rc_old_hpp or RC_OLD_CONTRACT_HPP
    cpp = rc_old_cpp or RC_OLD_BRIDGE_CPP
    result: dict = {
        "gating": False,
        "status": "ok",
        "note": "rc_old 值是上游参考事实：本仓以契约为真值，数值不一致是预期、不判红；"
                "仅用于人工复核『本仓轮足机型参数与上游实测的传承关系』。",
        "files": {"deployment_contract.hpp": str(hpp), "hardware_bridge_node.cpp": str(cpp)},
        "pd": {},
        "lpf": {},
    }
    missing: list[str] = []
    pd: dict = {}
    if hpp.is_file():
        text = hpp.read_text(encoding="utf-8", errors="replace")
        for name, (pattern, _) in _RC_PD_PATTERNS.items():
            value, line = _match_with_line(text, pattern)
            if value is None:
                missing.append(f"{hpp.name}:{name}")
                continue
            pd[name] = {"value": float(value), "evidence": f"{hpp}:{line}"}
    else:
        missing.append(str(hpp))
    if cpp.is_file():
        text = cpp.read_text(encoding="utf-8", errors="replace")
        for name in ("legs", "wheels"):
            match = _RC_LPF_PATTERN.search(text)
            found = None
            for lpf_match in _RC_LPF_PATTERN.finditer(text):
                if lpf_match.group(1) == name:
                    found = lpf_match
                    break
            if found is None:
                missing.append(f"{cpp.name}:lpf_{name}")
                continue
            pd[f"lpf_{name}_hz"] = {
                "value": float(found.group(2)),
                "evidence": f"{cpp}:{text[: found.start()].count(chr(10)) + 1}",
            }
        torque, line = _match_with_line(text, _RC_TORQUE_PATTERN)
        if torque is not None:
            pd["torque_limit_nm"] = {"value": float(torque), "evidence": f"{cpp}:{line}"}
        else:
            missing.append(f"{cpp.name}:torque_limit")
    else:
        missing.append(str(cpp))
    result["pd"] = pd
    result["status"] = "ok" if not missing else "missing"
    if missing:
        result["missing"] = missing
    return result


def _wheel_leg_counterpart(roots: list[Path]) -> Path | None:
    """rc_old RC_WheelLeg 的本仓同构机型：动作关节含 ``hip_abduction`` 的轮足包（= zex-w）。"""
    for root in roots:
        v3_path = root / "contract.json"
        if not v3_path.is_file():
            continue
        try:
            v3 = json.loads(v3_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        names = [str(e.get("name") or "") for e in (v3.get("joints") or {}).get("actuated") or []]
        if any("hip_abduction" in name for name in names):
            return root
    return None


def attach_rc_old_comparison(reference: dict, counterpart: Path | None) -> dict:
    """把 rc_old 参考值与本仓轮足机型当前契约值并排记录（``matches`` 仅供参考）。"""
    if counterpart is None or reference.get("status") != "ok":
        reference["repo_side"] = {"status": "unavailable" if counterpart is None else "reference_missing",
                                  "note": "无同构机型或参考缺失，仅记录参考值本身"}
        return reference
    facts = physics_facts(counterpart)
    by_role = facts.get("by_role") or {}
    damping_roles = by_role.get("damping") or {}
    stiffness_roles = by_role.get("stiffness") or {}
    effort_roles = by_role.get("torque_limits") or {}
    wheel = "wheel" in damping_roles
    leg_values = {v for r, v in damping_roles.items() if r != "wheel"}
    leg_kd = next(iter(leg_values)) if len(leg_values) == 1 else None
    leg_kp_values = {v for r, v in stiffness_roles.items() if r != "wheel"}
    leg_kp = next(iter(leg_kp_values)) if len(leg_kp_values) == 1 else None
    pd = reference.get("pd") or {}

    def compare(ref_key: str, repo_value) -> bool | None:
        entry = pd.get(ref_key)
        if not entry or repo_value is None:
            return None
        return math.isclose(float(entry["value"]), float(repo_value), rel_tol=TOL, abs_tol=TOL)

    repo_values = {
        "leg_kp": leg_kp,
        "leg_kd": leg_kd,
        "wheel_kd": damping_roles.get("wheel") if wheel else None,
        "torque_limit_nm": next(iter({v for v in effort_roles.values()}), None) if len(set(effort_roles.values())) == 1 else None,
        "lpf_legs_hz": None,
        "lpf_wheels_hz": None,
    }
    cutoffs = read_simulation_config(counterpart).get("action_filter_cutoffs")
    if isinstance(cutoffs, dict):
        repo_values["lpf_legs_hz"] = cutoffs.get("leg")
        repo_values["lpf_wheels_hz"] = cutoffs.get("wheel")
    reference["repo_side"] = {
        "status": "ok",
        "robot": counterpart.name,
        "values": repo_values,
        "matches": {key: compare(key, value) for key, value in repo_values.items()},
        "note": "matches=false 是预期（上游参照 vs 本仓契约是两回事），不判红；仅人工复核。",
    }
    return reference


# --- 汇总 --------------------------------------------------------------------------


def _is_repo_owned(root: Path) -> bool:
    """包根是否属于**仓库自带资产**（assets/robots）——这类包的 B3 残留进门禁。

    workspace 导入副本在仓库目录内但属 gitignored 用户状态（CI 不存在），
    其 B3 残留只登记不判红；仓库外的目录同理。
    """
    resolved = root.resolve()
    bundled_root = (ROOT / "assets" / "robots").resolve()
    return resolved == bundled_root or bundled_root in resolved.parents


def bundled_package_roots(robots_dir: Path | None = None) -> list[Path]:
    root = Path(robots_dir) if robots_dir else ROBOTS_DIR
    return sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []


def browser_package_roots() -> tuple[list[Path], list[str]]:
    """端点同链的包定位：mujoco_sim 能力 + ``browser_package``（与路由同一实现）。"""
    roots: list[Path] = []
    notes: list[str] = []
    try:
        from backend.robot_presets import list_robot_presets
        from backend.simulation_browser import browser_package

        for preset in list_robot_presets():
            robot_id = str(preset.get("robot_id") or "")
            capabilities = [str(c) for c in ((preset.get("robot_package") or {}).get("capabilities") or [])]
            if "mujoco_sim" not in capabilities:
                continue
            try:
                root, _ = browser_package(robot_id)
                roots.append(root)
            except Exception as exc:  # noqa: BLE001
                notes.append(f"浏览器包定位失败 {robot_id}: {exc}")
    except Exception as exc:  # noqa: BLE001  环境缺 fastapi 等：降级为只审计 bundled
        notes.append(f"浏览器链路不可用，降级为仅审计 assets/robots：{exc}")
    return roots, notes


def audit(robots_dir: Path | None = None, simulation_api_path: Path | None = None,
          rc_old_hpp: Path | None = None, rc_old_cpp: Path | None = None) -> dict:
    bundled = bundled_package_roots(robots_dir)
    browser_roots, env_notes = browser_package_roots()
    if robots_dir:
        # 测试注入：浏览器链也指向同一批注入包，避免扫到真实仓
        browser_roots = list(bundled)
        env_notes = ["测试注入模式：浏览器链按注入目录解析"]

    scope: dict[Path, str] = {}
    # 键用 resolve() 后的路径：bundled 与浏览器链解析出的是**同一个目录**时必须合并
    # （Path 相等对相对/绝对形式敏感，直接 `in` 会把同目录当两包）。
    for root in bundled:
        scope[root.resolve()] = "bundled"
    for root in browser_roots:
        scope[root.resolve()] = "browser"
    for root in bundled:
        resolved = root.resolve()
        if resolved in scope and scope[resolved] == "browser":
            scope[resolved] = "both"
        elif resolved not in scope:
            scope[resolved] = "bundled"

    rows: list[dict] = []
    environment_notes: list[dict] = list({"note": note} for note in env_notes)
    for root, kind in sorted(scope.items(), key=lambda item: item[0].name):
        row = check_package(root)
        row["scope"] = kind
        if not _is_repo_owned(root):
            # workspace 导入副本（gitignored 用户状态，CI 不存在）：一致性检查照跑
            # （浏览器真的在服务它，增益/常量不一致照判红），但 B3 config 残留键
            # 不作为仓内门禁红项——上移到 environment_notes，保证据、不作失败项。
            kept: list[dict] = []
            for residual_problem in row["problems"]:
                if residual_problem["check"] == "simulation/config.json 无 B3 废弃物理键":
                    environment_notes.append({
                        "robot": root.name,
                        "kind": "workspace_legacy_config_keys",
                        "file": residual_problem["file"],
                        "evidence": residual_problem["evidence"],
                        "note": "workspace 副本的 config.json 仍存 B3 废弃物理键（死数据："
                                "契约真值 存在时 physics_facts 不再读 config）；"
                                "下次经保存链落盘时会被剔除，不作为仓内门禁红项",
                    })
                    continue
                kept.append(residual_problem)
            row["problems"] = kept
            environment_notes.append({
                "robot": root.name,
                "kind": "workspace_package",
                "note": "包根不在 assets/robots（workspace 导入副本等用户状态）："
                        "增益/常量一致性照判红（浏览器在服务它），config 残留键只登记",
            })
        rows.append(row)
        # infos（嵌套死数据登记）保留在行内展示；仓外包的再上移一份到 environment_notes
        for info in row.get("infos") or []:
            environment_notes.append(info)

    api_path = simulation_api_path or SIMULATION_API
    if api_path.is_file():
        wiring_missing = check_endpoint_wiring(api_path.read_text(encoding="utf-8"))
    else:
        wiring_missing = ["backend/simulation_api.py 缺失"]
    wiring_problems = [
        {
            "robot": "backend/simulation_api.py",
            "check": "端点白名单接线钉住",
            "file": str(api_path),
            "evidence": f"端点源码缺少钉住片段：{wiring_missing}——审计重建的载荷可能不再等于端点真实下发，须人工复核接线后更新钉住",
        }
    ] if wiring_missing else []

    counterpart = _wheel_leg_counterpart([root for root, _ in scope.items()] or bundled)
    reference = attach_rc_old_comparison(rc_old_reference(rc_old_hpp, rc_old_cpp), counterpart)

    problems = [*wiring_problems, *(problem for row in rows for problem in row["problems"])]
    return {
        "schema": SCHEMA,
        "ok": not problems,
        "gating": {
            "browser_gains_equal_contract": True,
            "config_no_legacy_physics_keys": True,
            "physics_view_equal_payload": True,
            "endpoint_wiring_pinned": True,
            "rc_old_reference": False,
        },
        "packages": rows,
        "endpoint_wiring": {
            "file": str(api_path),
            "pins": len(ENDPOINT_WIRING_PINS),
            "missing": wiring_missing,
            "note": "审计不 import simulation_api（其拉起 mujoco）；以静态钉住保证重建载荷==端点载荷",
        },
        "rc_old_reference": reference,
        "environment_notes": environment_notes,
        "problems": problems,
        "problem_count": len(problems),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="H23 sim2sim 执行器/滤波一致性审计")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = audit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    print("=" * 74)
    print("H23 sim2sim 执行器/滤波一致性审计（浏览器下发 ↔ 契约真值 ↔ rc_old 参考）")
    print("=" * 74)
    rows = report["packages"]
    consistent = [row for row in rows if not row["problems"]]
    print(f"机型 {len(rows)} 个；两端全一致（无判红项）：{len(consistent)} 个")
    for row in rows:
        cutoffs = row.get("action_filter_cutoffs")
        mark = "✓" if not row["problems"] else "✗"
        extra = f"  lpf(下发)={cutoffs}" if cutoffs else ""
        if row["config_residuals"] and not row["problems"]:
            extra += f"  （config 残留已登记：{row['config_residuals']}）"
        print(f"  {mark} {row['robot']:<22} 来源={row['physics_source']:<12} 关节 {row['joint_count']:>2} 范围={row['scope']}{extra}")

    problems = report["problems"]
    if problems:
        print(f"\n✗ 不一致 {len(problems)} 项：")
        for item in problems:
            print(f"  ✗ [{item['robot']}] {item['check']}（{item['file']}）")
            print(f"      {item['evidence']}")
    else:
        print("\n✓ 我们自己的两端（浏览器下发 ↔ 契约真值 ↔ 训练常量表 ↔ 电机参数卡）全部一致")

    wiring = report["endpoint_wiring"]
    print(f"\n端点接线钉住：{wiring['pins'] - len(wiring['missing'])}/{wiring['pins']} 命中"
          + ("" if not wiring["missing"] else f"；缺失 {wiring['missing']}"))

    reference = report["rc_old_reference"]
    print(f"\nrc_old 参考事实（gating=false，缺文件如实降级）：status={reference['status']}")
    for name, entry in (reference.get("pd") or {}).items():
        print(f"  · {name:<16} = {entry['value']:<6} （{entry['evidence']}）")
    repo_side = reference.get("repo_side") or {}
    if repo_side.get("status") == "ok":
        print(f"  与本仓同构机型 {repo_side['robot']} 对照（matches 仅供参考，不判红）：")
        for key, matched in (repo_side.get("matches") or {}).items():
            value = repo_side["values"].get(key)
            print(f"    · {key:<16} repo={value} match={matched}")

    notes = report["environment_notes"]
    if notes:
        print(f"\n环境备注（不判红）{len(notes)} 条：")
        for note in notes:
            robot = note.get("robot") or ""
            print(f"  · {robot}{'：' if robot else ''}{note.get('note') or note.get('evidence') or ''}")

    print()
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
