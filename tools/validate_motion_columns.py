#!/usr/bin/env python3
"""N1：动作文件**关节列校验**门禁（`00_know/06` §16.2 N1 的可验证半边）。

挡的是最贵的一类错：**拿错关节序去训模仿**。列序错位不会报错，只会训出一个"看着像、
其实错位"的策略 —— 所以判据必须是"列名与契约 `action.joint_order` 同名同序"。

两种用法：

* ``--self-test``（CI）：造合成样本，断言判据本身有效（干净过 / 顺序不同必抓 / 缺列必抓 /
  无表头如实报 / npz 正常）——**判据只有一处，先保证判据不退化**；
* ``--motion <file> --contract <robot_id>``：校验一份真实动作文件（列序对不上即 exit 1）。

诚实边界：**判据只有列名这一条**。文件没有列名时本工具**不按宽度猜**（宽度是
`registry/motions` 的注册口径，不是训练口径，两件事不许混）——这种情况如实报"无法校验"。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.mjlab.toolchain.motion_io import (  # noqa: E402
    MotionIOError,
    calibrate,
    joint_column_problems,
    load_motion,
)

_ORDER = ["FL_hip", "FL_thigh", "FL_calf", "FR_hip"]


def _write_csv(path: Path, header: list[str] | None, rows: list[list[float]]) -> None:
    lines = []
    if header:
        lines.append(",".join(header))
    lines.extend(",".join(str(value) for value in row) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _self_test() -> list[str]:
    """判据自检：返回问题列表（空 = 判据本身有效）。"""
    problems: list[str] = []
    import numpy as np

    def check(condition: bool, message: str) -> None:
        if not condition:
            problems.append(message)

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)

        # ① 干净 csv（列名同序）→ 通过
        clean = base / "clean.csv"
        _write_csv(clean, ["time", *_ORDER], [[0.0, 1.0, 2.0, 3.0, 4.0]] * 5)
        report = calibrate(clean, expected_order=_ORDER)
        check(report["ok"], f"干净 csv 应通过，得到 {report['problems']}")
        check(report["frames"] == 5 and report["dof_dim"] == 4, f"csv 形状读错：{report}")
        check(load_motion(clean).joint_names == _ORDER,
              "time 列应被丢掉（列名应当恰好是关节序）")

        # ② 顺序不同 → 必抓（最阴的一类）
        swapped = base / "swapped.csv"
        _write_csv(swapped, [_ORDER[1], _ORDER[0], *_ORDER[2:]], [[0.0] * 4] * 3)
        report = calibrate(swapped, expected_order=_ORDER)
        check(not report["ok"] and any("顺序不同" in p for p in report["problems"]),
              f"顺序不同必须被抓：{report}")

        # ③ 缺列 → 必抓
        short = base / "short.csv"
        _write_csv(short, _ORDER[:3], [[0.0] * 3] * 3)
        report = calibrate(short, expected_order=_ORDER)
        check(not report["ok"] and any("缺关节列" in p for p in report["problems"]),
              f"缺列必须被抓：{report}")

        # ④ 无表头 → 如实报"无法校验"，不按宽度猜
        bare = base / "bare.csv"
        _write_csv(bare, None, [[0.0] * 4] * 3)
        motion = load_motion(bare)
        check(motion.joint_names is None, "纯数值 csv 不该被当成有列名")
        report = calibrate(bare, expected_order=_ORDER)
        check(not report["ok"] and any("没有关节列名" in p for p in report["problems"]),
              f"无列名必须如实报：{report}")

        # ⑤ npz（frames + joint_names + fps）→ 通过
        packed = base / "packed.npz"
        np.savez(packed, frames=np.zeros((6, 4)), joint_names=np.array(_ORDER), fps=np.array(30.0))
        report = calibrate(packed, expected_order=_ORDER)
        check(report["ok"], f"npz 应通过：{report}")
        check(report["frames"] == 6 and report["fps"] == 30.0, f"npz 元数据读错：{report}")

        # ⑥ npz 缺帧数组 → fail-loud
        broken = base / "broken.npz"
        np.savez(broken, unrelated=np.zeros((2, 2)))
        try:
            load_motion(broken)
            problems.append("npz 缺帧数组应抛错")
        except MotionIOError:
            pass

    # ⑦ 列名集合相同但顺序不同（纯函数级）
    check(joint_column_problems(_ORDER, _ORDER) == [], "同序应零问题")
    check(bool(joint_column_problems(None, _ORDER)), "无列名应有问题")
    return problems


def _contract_order(robot_id: str) -> list[str]:
    contract = json.loads(
        (ROOT / "assets" / "robots" / robot_id / "contract.json").read_text(encoding="utf-8-sig"))
    order = (contract.get("action") or {}).get("joint_order")
    if not order:
        raise SystemExit(f"{robot_id}: 契约没有 action.joint_order")
    return [str(name) for name in order]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="N1 动作文件关节列校验")
    parser.add_argument("--self-test", action="store_true", help="判据自检（CI）")
    parser.add_argument("--motion", type=Path, default=None)
    parser.add_argument("--contract", default=None, help="机型包 id（取 action.joint_order 当基准）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test or (args.motion is None):
        problems = _self_test()
        if problems:
            print("判据自检判红：")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        print("✓ 关节列校验判据自检通过（干净过 / 顺序不同必抓 / 缺列必抓 / 无表头如实报 / npz 正常）")
        return 0

    if not args.contract:
        raise SystemExit("--motion 模式必须给 --contract <robot_id>")
    report = calibrate(args.motion, expected_order=_contract_order(args.contract))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{report['source']}：{report['frames']} 帧 × {report['dof_dim']} 列，"
              f"fps={report['fps']}，列名={'有' if report['has_joint_names'] else '无'}")
        for problem in report["problems"]:
            print(f"  ✗ {problem}")
        print("✓ 列序与契约一致" if report["ok"] else "✗ 列序校验未过")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
