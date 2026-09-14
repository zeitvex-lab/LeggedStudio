#!/usr/bin/env python
"""把「增益正确」的策略的 PD 增益**程序化**补到缺它的包上（修"零力矩"）。

## 背景（2026-09-14）

增益审计（`tools/audit_policy_gains.py`）查出 5 条**零力矩**策略：`g1-velocity` 与
g1 的三条 dance、以及 go2 的 demo。它们的有效契约一条继承链都取不到 stiffness/damping，
`gain_for()` 兜底返回 **0.0** → `actuator_interface="torque"` 下**腿完全不支撑**：
机器人笔直下坠、且对观测/历史的任何改动毫无反应（这正是当时"两次布局实验指标一字不差"的真相）。

正确值**就在同机型已通过的策略里**：`g1-velocity-mjswan` 的逐关节 kp 14.25~99.098 / kd 6.31，
与上游 UniLab `assets/robots/g1/g1.xml:329-361` 的 kp/kv **逐值一致**。

## 为什么补在**包级** `simulation.control` 而不是逐策略

PD 增益是**机器人执行器的属性**，不是某一个策略的属性；运行时的解析链
（`policy_acceptance.PackageContract.__init__`）本来就把包级 `simulation.control`
当作默认值、策略自己的 `contract.control` 覆盖它。所以：
补一次包级 = 所有缺增益的策略（含将来新增的）都拿到正确默认值，而 `g1-velocity-mjswan`
这类自带 `contract.control` 的策略仍是自己的值（优先级更高，不受影响）。

## 为什么不手改 JSON

本轮手改 JSON 括号连续出错三次（多插括号、尾随逗号），每次都让整份 config 非法、
引擎静默跳过该机型。本工具：**读 → 定点插入 → `json.loads` 校验 → 才写**（fail-closed）。

用法::

    python tools/fix_policy_gains.py --robot unitree_g1 --from g1-velocity-mjswan
    python tools/fix_policy_gains.py --robot unitree_g1 --from g1-velocity-mjswan --write
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.policy_artifacts import ROBOTS_DIR  # noqa: E402


def find_control_block(sim: dict, policy_id: str) -> dict | None:
    """从同机型里找一条**已声明** `contract.control` 的策略，取它的增益块作真值。"""
    for section in ("policies", "demo_policies"):
        for entry in sim.get(section) or []:
            if isinstance(entry, dict) and entry.get("id") == policy_id:
                control = (entry.get("contract") or {}).get("control")
                return dict(control) if isinstance(control, dict) else None
    return None


def insert_package_control(text: str, control: dict, *, has_package_control: bool = False) -> tuple[str, bool]:
    """把 `control` 插到包级 JSON 的 `"scene_path"` 之后（该键在所有包里都存在且唯一）。

    返回 (新文本, 是否已插入)。已存在**包级** `control` 时不动（避免覆盖既有真值）。

    判据必须是"**解析后顶层**有没有 control"，不能是"文本里出现过 control"——
    各策略自己的 `contract.control` 也会命中后者，早期版本因此永远判断"已存在"而静默不做事。
    """
    if has_package_control:
        return text, False
    anchor = '"scene_path"'
    index = text.find(anchor)
    if index < 0:
        return text, False
    line_end = text.find("\n", index)
    block = json.dumps({"control": control}, ensure_ascii=False, indent=2)[1:-1].rstrip()
    # `{"control": {...}}` 去掉首尾花括号后，缩进两格即为包级键
    indented = "\n".join(("  " + line) if line.strip() else line for line in block.splitlines())
    return f"{text[:line_end]}\n{indented}," + text[line_end + 1:], True


def apply_fix(*, robot: str, source_policy: str, write: bool = False) -> dict:
    package = Path(ROBOTS_DIR) / robot
    config_path = package / "simulation" / "config.json"
    text = config_path.read_text(encoding="utf-8")
    try:
        sim = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"ok": False, "problems": [f"{robot}：现有 config 就不是合法 JSON（{exc}）"]}

    control = find_control_block(sim, source_policy)
    if not control:
        return {"ok": False, "problems": [f"{robot}：源策略 {source_policy} 没有 contract.control"]}

    updated, inserted = insert_package_control(text, control, has_package_control="control" in sim)
    if not inserted:
        already = "control" in sim
        return {"ok": already, "inserted": False, "control": control,
                "reason": "包级 control 已存在，不动" if already else "找不到插入锚点（scene_path 缺失）",
                "problems": []}

    try:                                   # fail-closed：校验不过绝不写盘
        json.loads(updated)
    except json.JSONDecodeError as exc:
        return {"ok": False, "inserted": False, "problems": [f"{robot}：插入后 JSON 非法（{exc}）"]}

    if write:
        config_path.write_text(updated, encoding="utf-8")
    return {"ok": True, "inserted": True, "written": bool(write), "control": control, "problems": []}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把 PD 增益补到包级 simulation.control")
    parser.add_argument("--robot", required=True, help="机型 id")
    parser.add_argument("--from", dest="source", required=True, help="提供增益真值的策略 id")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    result = apply_fix(robot=args.robot, source_policy=args.source, write=args.write)
    if result.get("inserted"):
        joints = sorted((result["control"].get("stiffness") or {}).keys())
        print(f"{'已写入' if result.get('written') else '待写入'} {args.robot}："
              f"包级 control 补自 {args.source}（{len(joints)} 个关节的 stiffness/damping）")
    elif result.get("reason"):
        print(f"{args.robot}：{result['reason']}")
    for problem in result["problems"]:
        print(f"  ✗ {problem}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
