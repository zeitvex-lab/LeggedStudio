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


def resolve_gains(entry_contract: dict, sim: dict) -> tuple[dict, dict]:
    """**照抄** `PackageContract.__init__` 的解析链（刻意重复实现：审计必须独立于运行时，
    否则同一处 bug 会同时骗过运行与审计）。"""
    control = sim.get("control") or {}
    ctrl = entry_contract.get("control") or {}
    stiffness = (
        ctrl.get("stiffness") or entry_contract.get("stiffness")
        or control.get("stiffness") or sim.get("stiffness") or {}
    )
    damping = (
        ctrl.get("damping") or entry_contract.get("damping")
        or control.get("damping") or sim.get("damping") or {}
    )
    return stiffness, damping


def gain_for(table: dict, joint: str) -> float:
    """同 `PackageContract.gain_for`：精确名优先、再做子串匹配、兜底 **0.0**。"""
    value = table.get(joint.lower())
    if value is not None:
        return float(value)
    lowered = joint.lower()
    for key, val in table.items():
        if str(key).lower() in lowered:
            return float(val)
    return 0.0


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
                # `contract.json` 的 `action.joint_order`**。漏掉它会把"继承来的关节序"
                # 误读成"没声明"，进而把增益判定也带偏。
                order = list(contract.get("action_joint_order") or [])
                if not order:
                    robot_contract = config_path.parents[1] / "contract.json"
                    if robot_contract.is_file():
                        try:
                            robot_doc = json.loads(robot_contract.read_text(encoding="utf-8-sig"))
                            order = list((robot_doc.get("action") or {}).get("joint_order") or [])
                        except (OSError, json.JSONDecodeError):
                            order = []
                contract = {**contract, "action_joint_order": order}
                stiffness, damping = resolve_gains(contract, sim)
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
    return {
        "schema": "policy-gains-audit-1.0",
        "total": len(rows),
        "problems": problems,
        "ineffective": ineffective,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="策略有效 PD 增益审计（零力矩检出）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = audit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if report["problems"] else 0

    print(f"策略 {report['total']} 条；**零力矩**风险 {len(report['problems'])} 条")
    for row in report["problems"]:
        print(f"  ✗ {row['robot']}/{row['policy_id']}  interface={row['interface']} "
              f"动作关节 {row['joints']} 个，增益来源={row['stiffness_source']} "
              f"→ kp 全 0（腿不会支撑）")
    ineffective = report["ineffective"]
    if ineffective:
        print(f"\n**声明了但进不了仿真**的按策略增益块 {len(ineffective)} 条"
              "（非力矩接口 → PD 由 MJCF 的 kp/kv 决定，这份声明不参与物理）：")
        for row in ineffective:
            print(f"  ⚠ {row['robot']}/{row['policy_id']}  interface={row['interface']} "
                  f"声明 kp={row['kp_min']}~{row['kp_max']} kd={row['kd_max']}"
                  "（来源 policy.control，**实际不生效**）")

    torque_ok = [
        row for row in report["rows"]
        if row.get("interface") == "torque" and not row.get("zero_torque") and row.get("kp_max")
    ]
    print(f"\n力矩接口且增益正常：{len(torque_ok)} 条")
    for row in torque_ok:
        print(f"  ✓ {row['robot']}/{row['policy_id']} kp={row['kp_min']}~{row['kp_max']} "
              f"kd={row['kd_max']}（来源 {row['stiffness_source']}）")
    return 1 if report["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
