#!/usr/bin/env python
"""策略**有效 PD 增益**审计：找出「力矩接口 + 解析后增益为 0」的策略。

## 为什么需要它（2026-09-14 的真实事故）

`go2-moe-cts` 的契约缺少 `control` 块。增益解析链是

    policy.contract.control → contract.stiffness → 包级 simulation.control → simulation.stiffness

（见 `adapters/mjlab/policy_acceptance.py` 的 `PackageContract.__init__`），一路都取不到值时，
`gain_for()` **兜底返回 0.0** —— 在 `actuator_interface == "torque"` 的包上就是**零力矩**：
腿完全不支撑，机器人**笔直下坠**（实测 pitch 仅 8.7°），而且**对观测/历史的任何改动都毫无反应**
（这才是当时两次布局实验"指标一字不差"的真相 —— 执行器根本没在工作）。

这个失败模式极难从指标上认出来：它长得像"策略不行"，实际是"我们没给力矩"。

## 用法

    python tools/audit_policy_gains.py            # 人读
    python tools/audit_policy_gains.py --json

判据：`actuator_interface == "torque"` 时，解析出的 stiffness/damping 若对**全部动作关节**
都取不到正值 → 该策略在无头/浏览器里都是"零力矩"，必须报出来。
位置执行器（`position_target`）不走这条链，只报告不判问题。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.policy_artifacts import ROBOTS_DIR  # noqa: E402


def resolve_gains(entry_contract: dict, sim: dict,
                  robot_stiffness: dict | None = None,
                  robot_damping: dict | None = None) -> tuple[list, list]:
    """**照抄** `PackageContract.__init__` 的解析链（刻意重复实现：审计必须独立于运行时，
    否则同一处 bug 会同时骗过运行与审计）。

    **2026-09-22 与运行时对齐**：链尾补上**机器人契约 `actuator_profile.by_role`**，并把
    "取第一个非空表"改成**按级解析**（高优先级在前，级内先精确名后子串）。改这两点的原因：
    运行时已按此解析（否则"只想改小腿"的策略会被迫重抄 12×2 个键，漏抄即零力矩），审计若
    不同步就会**把已接上真值的策略误报成零力矩**（本轮实测：`go2-baseline-164k` 正是如此）。
    独立实现的价值在于"不共享 bug"，代价是**链的形状必须逐字同步**——所以另有一条
    `test_audit_matches_engine_gain_chain` 拿真实包逐关节对账，链一漂就红。
    """
    control = sim.get("control") or {}
    ctrl = entry_contract.get("control") or {}
    levels_s = [ctrl.get("stiffness"), entry_contract.get("stiffness"),
                control.get("stiffness"), sim.get("stiffness"), robot_stiffness]
    levels_d = [ctrl.get("damping"), entry_contract.get("damping"),
                control.get("damping"), sim.get("damping"), robot_damping]
    return ([t for t in levels_s if t], [t for t in levels_d if t])


def gain_for(table, joint: str) -> float:
    """同 `PackageContract.gain_for`：`table` 可以是单表或**分级表**（list，高优先级在前）；
    级内精确名优先、再做子串匹配；全查不到兜底 **0.0**（运行时把 0.0 当"缺失"并 fail-closed）。"""
    levels = table if isinstance(table, (list, tuple)) else [table]
    lowered = joint.lower()
    for tbl in levels:
        if not isinstance(tbl, dict):
            continue
        value = tbl.get(lowered)
        if value is not None:
            return float(value)
        for key, val in tbl.items():
            if str(key).lower() in lowered:
                return float(val)
    return 0.0


def _declared_gain(table: dict, joint: str) -> float | None:
    """声明的逐关节增益；**没有该关节时返回 None**（而 :func:`gain_for` 兜底 0.0）。

    区别很重要：`gain_for` 的 0.0 兜底用于运行时（取不到就是零力矩、必须暴露），
    但对账时"没声明"与"声明为 0"是两件事 —— 混为一谈会造出假漂移。
    """
    lowered = joint.lower()
    if lowered in table:
        return float(table[lowered])
    for key, val in table.items():
        if str(key).lower() in lowered:
            return float(val)
    return None


def _contract_profile(robot_dir: Path) -> dict[str, dict[str, float]]:
    """机器人级真值的**逐关节展开**（契约真值 ``actuator_profile``）。

    MJCF 由它固化（`tools/bake_mjcf_physics.py`），`validate_mjcf_contract.py` 已保证两者
    零漂移 —— 所以拿它当参考与拿 MJCF 当参考等价，且不必解析 XML。
    读不动就返回空：**不猜**，也不因此判漂移。
    """
    path = robot_dir / "contract.json"
    if not path.is_file():
        return {}
    try:
        from contracts.physics_binding import RoleResolver  # noqa: PLC0415

        return RoleResolver(json.loads(path.read_text(encoding="utf-8-sig"))).expand_actuator_profile()
    except Exception:  # noqa: BLE001  审计不因单个包读不动而中断
        return {}


def deep_merge(base: dict, overlay: dict) -> dict:
    """与运行时同语义的深合并（`policy_acceptance.deep_merge`）：dict 逐键递归，标量/列表覆盖。

    审计必须照抄这条语义 —— 包级 `policy_contract` 是每个策略契约的**默认值**，
    漏掉它会把"继承来的 action_joint_order"看成"没声明"（早期版本正是如此）。
    """
    out = dict(base or {})
    for key, value in (overlay or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def audit(*, robots_dir: Path | str = ROBOTS_DIR) -> dict:
    root = Path(robots_dir)
    rows: list[dict] = []
    for config_path in sorted(root.glob("*/simulation/config.json")):
        try:
            sim = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            rows.append({"robot": config_path.parents[1].name, "error": str(exc)})
            continue
        robot = config_path.parents[1].name
        interface = str(sim.get("actuator_interface") or "torque").lower()
        for section in ("policies", "demo_policies"):
            for entry in sim.get(section) or []:
                if not isinstance(entry, dict):
                    continue
                # 与运行时同语义：包级 `policy_contract` 先铺底，再用策略条目覆盖
                package_default = (
                    sim.get("policy_contract") or sim.get("default_policy_contract") or {}
                )
                contract = deep_merge(package_default, entry.get("contract") or {})
                # 动作序的第二条继承链（与运行时同语义）：策略没声明时回退到**包级
                # `contract_legacy_v2.json` 的 `action.joint_order`**。漏掉它会把"继承来的关节序"
                # 误读成"没声明"，进而把增益判定也带偏。
                order = list(contract.get("action_joint_order") or [])
                if not order:
                    robot_contract = config_path.parents[1] / "contract_legacy_v2.json"
                    if robot_contract.is_file():
                        try:
                            robot_doc = json.loads(robot_contract.read_text(encoding="utf-8-sig"))
                            order = list((robot_doc.get("action") or {}).get("joint_order") or [])
                        except (OSError, json.JSONDecodeError):
                            order = []
                contract = {**contract, "action_joint_order": order}
                # 机器人级真值（逐关节展开）：既是"声明 vs 真值"的参考，也是解析链的**末位**
                profile = _contract_profile(config_path.parents[1])
                robot_stiffness = {j: p["stiffness"] for j, p in profile.items()
                                   if p.get("stiffness") is not None}
                robot_damping = {j: p["damping"] for j, p in profile.items()
                                 if p.get("damping") is not None}
                stiffness, damping = resolve_gains(contract, sim, robot_stiffness, robot_damping)
                # **声明 vs 真值对账**（非力矩接口）：策略级 `control` 在 position/velocity
                # 下不驱动仿真，它的正确定位是「这条策略上游档位的**断言 + 溯源**」——
                # 那么它就必须与机器人级真值一致。不一致 = 一条会误导人的假声明。
                # 为何不让它"生效"：运行时改写执行器已被明确退役（见
                # `contracts/physics_binding.py` 的 LEGACY_CONFIG_PHYSICS_KEYS 注释与
                # `policy_acceptance.load_package_model`）：真值只在契约、MJCF 由它固化，
                # **漂移由校验器报、不静默修**。
                drift: list[str] = []
                if interface != "torque" and (contract.get("control") or {}).get("stiffness"):
                    for joint in order:
                        entry_params = profile.get(joint) or {}
                        # 对账用**声明表**（策略自己写的），不是解析后的分级表
                        for param, table in (("stiffness", contract.get("control") or {}),
                                             ("damping", contract.get("control") or {})):
                            declared = _declared_gain((table.get(param) or {}), joint)
                            truth = entry_params.get(param)
                            if declared is None or truth is None:
                                continue
                            if abs(declared - float(truth)) > 1e-6:
                                drift.append(f"{joint}.{param}: 声明 {declared:g} ≠ 真值 {float(truth):g}")
                kps = [gain_for(stiffness, name) for name in order]
                kds = [gain_for(damping, name) for name in order]
                rows.append({
                    "robot": robot,
                    "policy_id": entry.get("id"),
                    "kind": section,
                    "interface": interface,
                    "joints": len(order),
                    "order_declared": bool(order),
                    "stiffness_source": (
                        "policy.control" if (contract.get("control") or {}).get("stiffness")
                        else "contract.stiffness" if contract.get("stiffness")
                        else "sim.control" if (sim.get("control") or {}).get("stiffness")
                        else "sim.stiffness" if sim.get("stiffness")
                        else "robot.actuator_profile" if robot_stiffness
                        else "none"
                    ),
                    "kp_min": min(kps) if kps else None,
                    "kp_max": max(kps) if kps else None,
                    "kd_max": max(kds) if kds else None,
                    # 判定：力矩接口 + 有动作关节 + 全部 kp 为 0 → 必然零力矩
                    "zero_torque": bool(
                        interface == "torque" and order and all(kp <= 0.0 for kp in kps)
                    ),
                    # 判定：**声明了按策略增益，但它进不了仿真**（见 gains_ineffective 说明）
                    "gains_ineffective": bool(
                        (contract.get("control") or {}).get("stiffness")
                        and interface != "torque"
                    ),
                    # 声明与机器人级真值的**逐关节差异**（非力矩接口；空 = 声明可信）
                    "declaration_drift": drift,
                })
    problems = [row for row in rows if row.get("zero_torque")]
    #: 第二类事实：**按策略增益在非力矩接口下不参与仿真**。
    #:
    #: `PackageContract` 会把它读进 `self.stiffness`（`policy_acceptance.py`），审计也会标成
    #: `stiffness_source=policy.control` —— **看起来生效**；但 `position`/`velocity` 接口下我们只写
    #: 位置/速度目标，PD 由 **MJCF 执行器的 kp/kv** 决定，这份声明根本不进物理。
    #: 2026-09-14 实测：`lite3-velocity-benchmark` 与 `lite3-velocity-sdk45` 指向同一 onnx、契约里
    #: 唯一差别就是 `control.stiffness`（40 vs 30）——**两条却跑出一字不差的指标**，即由此而来。
    #: 所以它必须被显式报出：要么让它生效，要么承认它只是声明。
    ineffective = [row for row in rows if row.get("gains_ineffective")]
    #: 第三类事实：**声明与真值不符的按策略增益**（假声明）—— 必须为 0。
    drifted = [row for row in rows if row.get("declaration_drift")]
    return {
        "schema": "policy-gains-audit-1.0",
        "total": len(rows),
        "problems": problems,
        "ineffective": ineffective,
        "drifted": drifted,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="策略有效 PD 增益审计（零力矩检出）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = audit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if (report["problems"] or report["drifted"]) else 0

    print(f"策略 {report['total']} 条；**零力矩**风险 {len(report['problems'])} 条")
    for row in report["problems"]:
        print(f"  ✗ {row['robot']}/{row['policy_id']}  interface={row['interface']} "
              f"动作关节 {row['joints']} 个，增益来源={row['stiffness_source']} "
              f"→ kp 全 0（腿不会支撑）")
    ineffective = report["ineffective"]
    if ineffective:
        print(f"\n按策略增益声明 {len(ineffective)} 条（非力矩接口 → PD 由 MJCF 的 kp/kv 决定，"
              "**不驱动仿真**；它的定位是「上游档位的断言 + 溯源」，必须与真值一致）：")
        for row in ineffective:
            print(f"  · {row['robot']}/{row['policy_id']}  interface={row['interface']} "
                  f"声明 kp={row['kp_min']}~{row['kp_max']} kd={row['kd_max']}"
                  "（来源 policy.control）")

    drifted = report["drifted"]
    if drifted:
        print(f"\n✗ **假声明** {len(drifted)} 条（声明值与机器人级真值不符，会误导人）：")
        for row in drifted:
            print(f"  ✗ {row['robot']}/{row['policy_id']}")
            for item in row["declaration_drift"][:6]:
                print(f"      {item}")

    torque_ok = [
        row for row in report["rows"]
        if row.get("interface") == "torque" and not row.get("zero_torque") and row.get("kp_max")
    ]
    print(f"\n力矩接口且增益正常：{len(torque_ok)} 条")
    for row in torque_ok:
        print(f"  ✓ {row['robot']}/{row['policy_id']} kp={row['kp_min']}~{row['kp_max']} "
              f"kd={row['kd_max']}（来源 {row['stiffness_source']}）")
    # 零力矩 = 必然不可用；假声明 = 会误导人 —— 两者都判失败（防止再出现）。
    return 1 if (report["problems"] or report["drifted"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
