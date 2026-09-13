#!/usr/bin/env python3
"""motrixsim 可安装性 / MJCF 兼容性探针（**已搁置**，取证脚本，不参与构建）

> **状态（2026-09-13 用户裁决）**：第二物理后端（motrixsim）的接入规划**已删除**，
> 路线改为**先把 mjlab + MuJoCo 这一套做精**。本脚本作为当时的取证留存，**不属于
> 任何里程碑**，也不要在 CI / MCP / 文档里引用为"下一步"。若将来重新评估第二后端，
> 这份结论（14/14 包可加载 + step）仍可直接复用。

用途：为 00_know/90_归档/参考项目_UniLab与motrixsim评估.md 的
「移植可行性」结论提供可复现证据：本仓库 14 包 MJCF 在 motrixsim 下能否
加载并 step。

用法（需先 pip install motrixsim-core==0.8.2，可选依赖，不进默认环境）：
    python tools/probe_motrixsim.py            # 只探测本机已装版本
    python tools/probe_motrixsim.py --all      # 逐包加载 + 5 步 step

退出码：0 全部通过（或包未安装时给出明确提示并不失败）。
"""
from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL = "model/robot.xml"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="逐包加载并 step")
    args = ap.parse_args()

    try:
        import motrixsim as mtx  # type: ignore
    except ImportError as exc:
        print(f"[skip] motrixsim 未安装：{exc}")
        print("       安装：pip install motrixsim-core==0.8.2")
        return 0

    print(f"[ok] import motrixsim  {getattr(mtx, '__version__', '?')}")

    robots = sorted(p.name for p in (ROOT / "assets" / "robots").iterdir() if p.is_dir())
    if not args.all:
        robots = robots[:1]

    ok, fail, missing = [], [], []
    for rid in robots:
        xml = ROOT / "assets" / "robots" / rid / MODEL
        if not xml.exists():
            missing.append(rid)
            continue
        try:
            model = mtx.load_model(str(xml))
            data = mtx.SceneData(model)
            for _ in range(5):
                mtx.step(model, data)
            ok.append(rid)
            print(f"[ok]   {rid}")
        except Exception as exc:  # noqa: BLE001 - 探针要如实报告任何异常
            fail.append(rid)
            print(f"[fail] {rid}: {type(exc).__name__}: {str(exc)[:120]}")

    print(f"\n通过 {len(ok)} / 失败 {len(fail)} / 无 MJCF {len(missing)}")
    if missing:
        print("无 model/robot.xml：" + ", ".join(missing))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
