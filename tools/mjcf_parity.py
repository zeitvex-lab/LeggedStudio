#!/usr/bin/env python3
"""mjcf_parity.py — 本体保真门：我们的训练 MJCF vs 上游参考 MJCF 的**声明物理逐值 diff**。

## 在保真链里的位置（2026-10-02 补齐的第四道门）

移植性能损失只有五个通道，此前四道门覆盖了四层，唯独**本体层**没有门：

    本体（MJCF 物理）→ 环境（装配）→ 配方（奖惩/课程/命令）→ 管线（PPO）→ 测量
    mjcf_parity(本工具)   golden_env_parity   recipe_parity      rl_cfg 逐字同文  trend_probe/判据

`golden_env_parity` 是「同一个模型 × 双环境」——它**不含**"我们的机器人 vs 上游
机器人"。若转换/规范化时动了质量、惯量、关节阻尼，同一配方训出来就是另一个任务，
而所有既有的门都看不见。本工具把这层封上。

## 口径

* **spec 层声明真值**（`MjSpec.from_file`，不编译）：比的是双方 XML 里写死的物理量
  ——质量/惯量/阻尼/臂架/刚度/轴/行程。上游快照不带 mesh 资产、无法编译，而
  声明值恰是"人写进模型的是什么"的忠实记录（编译级差异留给 golden_env_parity
  的闭环对拍兜底）。
* **按名对拍** bodies（mass/ipos/inertia）/ joints（axis/range/damping/armature/
  stiffness/frictionloss）；**geoms 按多重集**（body+type+size+friction+contype—
  两侧都有无名 geom，签名匹配）；sensors 只列差异不判红（我方训练规格化按
  `KEEP_SENSORS` 裁剪是**已声明口径**）；actuators 双方 MJCF 均无（运行期注入），
  PD 真值在契约（`04_参数真值标准.md`）。

## 用法（控制面 venv，mujoco 已在依赖里）

    python tools/mjcf_parity.py --ours <训练.xml> --theirs <上游.xml> [--json]

退出码：0 = 物理关键类逐值一致；1 = 有 delta（本体保真门红）；2 = 文件缺失/解析失败。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TOL = 1e-9


def _r(values, nd=9):
    """标量或可迭代统一转成数值元组（MjSpec 字段标量/数组不定型）。
    NaN 归一为 "nan" 字符串：未设惯量的 world 体 ipos=(nan,0,0) 两侧同值，
    float('nan') != float('nan') 会制造伪 delta。"""
    if values is None:
        return ()
    if isinstance(values, (int, float)):
        return ("nan",) if values != values else (round(float(values), nd),)
    return tuple(("nan",) if v != v else (round(float(v), nd),) for v in values)


def _bodies(spec):
    out = {}
    for b in spec.bodies:
        if not b.name:
            continue
        out[b.name] = {
            "mass": round(float(b.mass), 9),
            "ipos": _r(b.ipos),
            "inertia": _r(b.inertia),
        }
    return out


def _joints(spec):
    out = {}
    for j in spec.joints:
        if not j.name:
            continue
        out[j.name] = {
            "axis": _r(j.axis if j.axis is not None else []),
            "range": _r(j.range if j.range is not None else []),
            "damping": _r(j.damping if j.damping is not None else []),
            "armature": _r(j.armature if j.armature is not None else []),
            "stiffness": _r(j.stiffness if j.stiffness is not None else []),
            "frictionloss": _r(j.frictionloss if j.frictionloss is not None else []),
        }
    return out


def _geom_sig(g, body_name: str):
    return (
        body_name if body_name else (g.parent.name if g.parent is not None else "?"),
        int(g.type) if g.type is not None else -1,
        _r(g.size if g.size is not None else []),
        _r(g.friction if g.friction is not None else []),
        round(float(g.margin or 0.0), 9),
        int(g.contype or 0),
        int(g.conaffinity or 0),
    )


def _geoms(spec) -> Counter:
    return Counter(_geom_sig(g, None) for g in spec.geoms)


def _sensors(spec) -> list[str]:
    names = []
    for s in spec.sensors:
        try:
            names.append(f"{s.type}:{s.name}")
        except Exception:
            names.append(str(s))
    return sorted(names)


def diff_mjcf(ours, theirs) -> dict:
    """两侧 MjSpec → 分类 delta 报告（纯函数，可测）。delta≠一定错，但必须人裁。"""
    report: dict = {"categories": {}}

    ob, tb = _bodies(ours), _bodies(theirs)
    d = {"missing_in_ours": sorted(set(tb) - set(ob)), "missing_in_theirs": sorted(set(ob) - set(tb)), "fields": []}
    ob.pop("world", None)
    tb.pop("world", None)  # world 体无惯量声明（ipos=nan），非物理差异
    for name in sorted(set(ob) & set(tb)):
        for field in ("mass", "ipos", "inertia"):
            if ob[name][field] != tb[name][field]:
                d["fields"].append({"name": name, "field": field, "ours": ob[name][field], "theirs": tb[name][field]})
    report["categories"]["bodies"] = d

    oj, tj = _joints(ours), _joints(theirs)
    d = {"missing_in_ours": sorted(set(tj) - set(oj)), "missing_in_theirs": sorted(set(oj) - set(tj)), "fields": []}
    for name in sorted(set(oj) & set(tj)):
        for field in oj[name]:
            if oj[name][field] != tj[name][field]:
                d["fields"].append({"name": name, "field": field, "ours": oj[name][field], "theirs": tj[name][field]})
    report["categories"]["joints"] = d

    og, tg = _geoms(ours), _geoms(theirs)
    report["categories"]["geoms"] = {
        "only_in_ours": [list(k) for k in (og - tg)],
        "only_in_theirs": [list(k) for k in (tg - og)],
        "matched": sum((og & tg).values()),
    }

    report["categories"]["sensors"] = {
        "only_in_ours": sorted(set(_sensors(ours)) - set(_sensors(theirs))),
        "only_in_theirs": sorted(set(_sensors(theirs)) - set(_sensors(ours))),
        "note": "我方训练规格化按 KEEP_SENSORS 裁剪（已声明口径），传感差异不判红",
    }
    report["categories"]["actuators"] = {
        "ours": len(ours.actuators), "theirs": len(theirs.actuators),
        "note": "执行器由框架运行期注入（mjlab 常量），PD 真值在机器人契约，MJCF 层无可对声明",
    }
    report["ok"] = not (report["categories"]["bodies"]["fields"]
                        or report["categories"]["bodies"]["missing_in_ours"]
                        or report["categories"]["bodies"]["missing_in_theirs"]
                        or report["categories"]["joints"]["fields"]
                        or report["categories"]["joints"]["missing_in_ours"]
                        or report["categories"]["joints"]["missing_in_theirs"]
                        or report["categories"]["geoms"]["only_in_ours"]
                        or report["categories"]["geoms"]["only_in_theirs"])
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="本体保真门：训练 MJCF vs 上游参考 MJCF 声明物理逐值 diff")
    ap.add_argument("--ours", required=True)
    ap.add_argument("--theirs", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    for tag, path in (("ours", args.ours), ("theirs", args.theirs)):
        if not Path(path).is_file():
            print(f"[env-missing] {tag} MJCF 不存在：{path}", file=sys.stderr)
            return 2

    import mujoco

    try:
        ours = mujoco.MjSpec.from_file(args.ours)
        theirs = mujoco.MjSpec.from_file(args.theirs)
    except Exception as exc:
        print(f"[env-missing] spec 解析失败：{exc}", file=sys.stderr)
        return 2

    report = diff_mjcf(ours, theirs)
    report.update({"ours": args.ours, "theirs": args.theirs})
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print(f"mjcf_parity: {args.ours}")
        print(f"             vs {args.theirs}")
        for cat in ("bodies", "joints"):
            d = report["categories"][cat]
            print(f"  [{cat}] matched={len(set(_bodies(ours)) & set(_bodies(theirs))) if cat == 'bodies' else len(set(_joints(ours)) & set(_joints(theirs)))} "
                  f"fieldsΔ={len(d['fields'])} missing={len(d['missing_in_ours']) + len(d['missing_in_theirs'])}")
            for f in d["fields"][:12]:
                print(f"    Δ {f['name']}.{f['field']}: ours={f['ours']} theirs={f['theirs']}")
        g = report["categories"]["geoms"]
        print(f"  [geoms] matched={g['matched']} only_ours={len(g['only_in_ours'])} only_theirs={len(g['only_in_theirs'])}")
        print(f"  [sensors] 差异 {len(report['categories']['sensors']['only_in_ours']) + len(report['categories']['sensors']['only_in_theirs'])}（规格化口径，不判红）")
        print(f"  → {'✓ 本体物理逐值一致' if report['ok'] else '✗ 本体有 delta——按 aligned/intentional/suspect 裁（delta≠错，但必须人裁并登记）'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
