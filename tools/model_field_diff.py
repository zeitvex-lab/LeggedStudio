#!/usr/bin/env python3
"""MJCF 字段级对照（B20 续）：把**我方包内 MJCF** 与**官方 MJCF/URDF** 逐字段比，回答"还缺什么"。

为什么需要它
------------
`tools/cross_source_audit.py` 只比 `effort` / `velocity` 两个关节侧标量；但"我们的模型和官方
差在哪"远不止这两个数：**积分器/求解器设置、关节 armature/frictionloss/damping、几何的
摩擦与 solref/solimp、体质量与惯量、执行器类型与增益**……任何一项缺失或不同，都会让
sim2sim / sim2real 结论偏移，而且**不会报错**。

本工具把两侧都**编译成 MjModel** 再逐数组比对（比文本 diff 可靠：defaults 展开、单位换算、
XML 引用都已生效）。

用法
----
    python tools/model_field_diff.py                      # 有官方 MJCF 的机型全跑
    python tools/model_field_diff.py unitree_go2          # 单机型
    python tools/model_field_diff.py --json
    python tools/model_field_diff.py --detail unitree_go2 # 打印明细

退出码恒为 0（审计工具，差异需人判；不进门禁——依赖 `/00_open` 的官方克隆）。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ROBOTS_DIR = ROOT / "assets" / "robots"

#: 官方 MJCF 候选（按优先级）：官方 unitree_mujoco 仓 → menagerie（独立第三方）。
OFFICIAL_MJCF: tuple[tuple[str, pathlib.Path], ...] = (
    ("unitree_mujoco", pathlib.Path("/00_open/unitree_mujoco/unitree_robots")),
    ("menagerie", pathlib.Path("/00_open/mujoco_menagerie")),
)

#: 官方目录名 → 我方 robot_id（只列有官方 MJCF 的）
ROBOT_DIRS: dict[str, tuple[str, str]] = {
    # 官方 unitree_mujoco 仓里的文件名并不统一（g1 是 g1_29dof.xml、go1 干脆没有），
    # 所以按"先官方仓、再 menagerie"的顺序给出候选，取第一个存在的。
    "unitree_g1": ("unitree_mujoco", "g1/g1_29dof.xml"),
    "unitree_go1": ("menagerie", "unitree_go1/go1.xml"),
    "unitree_go2": ("unitree_mujoco", "go2/go2.xml"),
    "unitree_go2w": ("unitree_mujoco", "go2w/go2w.xml"),
    "unitree_b2": ("unitree_mujoco", "b2/b2.xml"),
    "unitree_b2w": ("unitree_mujoco", "b2w/b2w.xml"),
}

OPTION_FIELDS = ("timestep", "gravity", "integrator", "solver", "iterations", "impratio",
                 "cone", "jacobian", "viscosity", "density", "tolerance", "ls_iterations")


def _load(path: pathlib.Path):
    import mujoco

    return mujoco.MjModel.from_xml_path(str(path))


def _official_path(robot_id: str) -> pathlib.Path | None:
    spec = ROBOT_DIRS.get(robot_id)
    if not spec:
        return None
    source, rel = spec
    # 先按登记的源找，找不到再按优先级兜底（文件名/目录随上游版本会变）
    for name, root in OFFICIAL_MJCF:
        candidate = root / rel if name == source else None
        if candidate and candidate.is_file():
            return candidate
    for name, root in OFFICIAL_MJCF:
        keyword = "unitree_" + robot_id.split("_")[-1]
        for candidate in sorted(root.rglob(f"{keyword}*.xml")):
            if "scene" in candidate.name:
                continue
            return candidate
    return None


def _diff_option(ours, theirs) -> list[dict]:
    out = []
    for field in OPTION_FIELDS:
        a, b = getattr(ours.opt, field, None), getattr(theirs.opt, field, None)
        if a is None or b is None:
            continue
        try:
            same = bool(abs(float(a) - float(b)) < 1e-9) if not hasattr(a, "__len__") else list(a) == list(b)
        except (TypeError, ValueError):
            same = a == b
        if not same:
            out.append({"field": field, "ours": list(a) if hasattr(a, "__len__") else float(a),
                        "official": list(b) if hasattr(b, "__len__") else float(b)})
    return out


def _joint_names(model) -> list[str]:
    import mujoco

    return [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i) or f"joint{i}" for i in range(model.njnt)]


def _dof_by_joint(model) -> dict[str, dict[str, float]]:
    """{关节名: {armature, frictionloss, damping, range_lo, range_hi}}（只含有 dof 的关节）。"""
    import mujoco

    table: dict[str, dict[str, float]] = {}
    for jid in range(model.njnt):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, jid)
        if not name or model.jnt_type[jid] not in (mujoco.mjtJoint.mjJNT_HINGE, mujoco.mjtJoint.mjJNT_SLIDE):
            continue
        dof = int(model.jnt_dofadr[jid])
        entry = {
            "armature": float(model.dof_armature[dof]),
            "frictionloss": float(model.dof_frictionloss[dof]),
            "damping": float(model.dof_damping[dof]),
            "range_lo": float(model.jnt_range[jid][0]),
            "range_hi": float(model.jnt_range[jid][1]),
        }
        table[name.lower()] = entry
    return table


def _geom_summary(model) -> dict[str, dict[str, float]]:
    """{几何名: {friction, solref, solimp, condim, priority}}（无名几何用索引）。"""
    import mujoco

    out: dict[str, dict[str, float]] = {}
    for gid in range(model.ngeom):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, gid) or f"geom{gid}"
        out[name.lower()] = {
            "friction0": float(model.geom_friction[gid][0]),
            "solref0": float(model.geom_solref[gid][0]),
            "solref1": float(model.geom_solref[gid][1]),
            "solimp2": float(model.geom_solimp[gid][2]),
            "condim": float(model.geom_condim[gid]),
            "priority": float(model.geom_priority[gid]),
            "contype": float(model.geom_contype[gid]),
            "conaffinity": float(model.geom_conaffinity[gid]),
        }
    return out


def _body_mass(model) -> dict[str, float]:
    import mujoco

    return {
        (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i) or f"body{i}").lower(): float(model.body_mass[i])
        for i in range(1, model.nbody)
    }


def _actuator_summary(model) -> dict[str, dict[str, float]]:
    import mujoco

    out: dict[str, dict[str, float]] = {}
    for aid in range(model.nu):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, aid) or f"act{aid}"
        out[name.lower()] = {
            "gear0": float(model.actuator_gear[aid][0]),
            "gainprm0": float(model.actuator_gainprm[aid][0]),
            "biasprm1": float(model.actuator_biasprm[aid][1]),
            "biasprm2": float(model.actuator_biasprm[aid][2]),
            "forcerange_lo": float(model.actuator_forcerange[aid][0]),
            "forcerange_hi": float(model.actuator_forcerange[aid][1]),
            "ctrllimited": float(model.actuator_ctrllimited[aid]),
        }
    return out


def compare_robot(robot_id: str, detail: bool = False) -> dict:
    ours_path = ROBOTS_DIR / robot_id / "model" / "robot.xml"
    official_path = _official_path(robot_id)
    report: dict = {"robot_id": robot_id, "official": str(official_path) if official_path else None}
    if not official_path or not ours_path.is_file():
        report["error"] = "缺官方 MJCF 或包内模型"
        return report
    try:
        ours, theirs = _load(ours_path), _load(official_path)
    except Exception as exc:  # noqa: BLE001  编译失败本身就是要报的信息
        report["error"] = f"编译失败：{exc}"
        return report

    report["counts"] = {
        "field": ["nbody", "ngeom", "njnt", "nu", "nq", "nv"],
        "ours": [ours.nbody, ours.ngeom, ours.njnt, ours.nu, ours.nq, ours.nv],
        "official": [theirs.nbody, theirs.ngeom, theirs.njnt, theirs.nu, theirs.nq, theirs.nv],
    }
    report["option_diff"] = _diff_option(ours, theirs)

    ours_dof, theirs_dof = _dof_by_joint(ours), _dof_by_joint(theirs)
    dof_diff, dof_only_us, dof_only_theirs = [], [], []
    for name in sorted(set(ours_dof) | set(theirs_dof)):
        a, b = ours_dof.get(name), theirs_dof.get(name)
        if a and not b:
            dof_only_us.append(name)
            continue
        if b and not a:
            dof_only_theirs.append(name)
            continue
        for field in ("armature", "frictionloss", "damping", "range_lo", "range_hi"):
            if abs(a[field] - b[field]) > 1e-9:
                dof_diff.append({"joint": name, "field": field, "ours": a[field], "official": b[field]})
    report["dof_diff"] = dof_diff
    report["joints_only_ours"] = dof_only_us[:10]
    report["joints_only_official"] = dof_only_theirs[:10]

    ours_geom, theirs_geom = _geom_summary(ours), _geom_summary(theirs)
    geom_diff = []
    for name in sorted(set(ours_geom) & set(theirs_geom)):
        for field, value in ours_geom[name].items():
            if abs(value - theirs_geom[name][field]) > 1e-9:
                geom_diff.append({"geom": name, "field": field, "ours": value,
                                  "official": theirs_geom[name][field]})
    report["geom_diff_count"] = len(geom_diff)
    report["geom_diff_sample"] = geom_diff[:8] if detail else geom_diff[:4]
    report["geoms_only_official"] = sorted(set(theirs_geom) - set(ours_geom))[:10]
    report["geoms_only_ours"] = sorted(set(ours_geom) - set(theirs_geom))[:10]

    ours_mass, theirs_mass = _body_mass(ours), _body_mass(theirs)
    mass_diff = [
        {"body": name, "ours": ours_mass[name], "official": theirs_mass[name]}
        for name in sorted(set(ours_mass) & set(theirs_mass))
        if abs(ours_mass[name] - theirs_mass[name]) > 1e-6
    ]
    report["mass_diff"] = mass_diff[:12]
    report["mass_diff_count"] = len(mass_diff)
    report["bodies_only_official"] = sorted(set(theirs_mass) - set(ours_mass))[:10]

    ours_act, theirs_act = _actuator_summary(ours), _actuator_summary(theirs)
    report["actuator_counts"] = {"ours": len(ours_act), "official": len(theirs_act)}
    act_diff = []
    for name in sorted(set(ours_act) & set(theirs_act)):
        for field, value in ours_act[name].items():
            if abs(value - theirs_act[name][field]) > 1e-9:
                act_diff.append({"actuator": name, "field": field, "ours": value,
                                 "official": theirs_act[name][field]})
    report["actuator_diff_count"] = len(act_diff)
    report["actuator_diff_sample"] = act_diff[:6]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="MJCF 字段级对照（我方 vs 官方）")
    parser.add_argument("robot_id", nargs="?")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--detail", action="store_true", help="打印更多样例")
    args = parser.parse_args()

    robots = [args.robot_id] if args.robot_id else sorted(ROBOT_DIRS)
    reports = [compare_robot(r, detail=args.detail) for r in robots]
    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
        return 0
    for report in reports:
        print(f"■ {report['robot_id']}  ← {report.get('official') or '（无官方 MJCF）'}")
        if report.get("error"):
            print(f"   ⛔ {report['error']}")
            continue
        counts = report["counts"]
        print(f"   规模: " + "  ".join(f"{f} 我方{v}/官方{t}" for f, v, t in zip(counts["field"], counts["ours"], counts["official"])))
        print(f"   option 差异 {len(report['option_diff'])}: " + ", ".join(
            f"{d['field']} 我方{d['ours']}→官方{d['official']}" for d in report["option_diff"]) or "   option 一致")
        print(f"   关节级 dof 差异 {len(report['dof_diff'])} | 我方独有关节 {report['joints_only_ours']} | 官方独有 {report['joints_only_official']}")
        for item in report["dof_diff"][:6]:
            print(f"      · {item['joint']} {item['field']}: 我方 {item['ours']:.6g} vs 官方 {item['official']:.6g}")
        print(f"   几何摩擦/接触参数差异 {report['geom_diff_count']}（仅官方有 {report['geoms_only_official'][:4]}）")
        for item in report["geom_diff_sample"]:
            print(f"      · {item['geom']} {item['field']}: 我方 {item['ours']:.6g} vs 官方 {item['official']:.6g}")
        print(f"   质量差异 {report['mass_diff_count']} | 仅官方有的体 {report['bodies_only_official'][:4]}")
        for item in report["mass_diff"][:3]:
            print(f"      · {item['body']}: 我方 {item['ours']:.6g} vs 官方 {item['official']:.6g}")
        print(f"   执行器: 我方 {report['actuator_counts']['ours']} / 官方 {report['actuator_counts']['official']}，参数差异 {report['actuator_diff_count']}")
        for item in report["actuator_diff_sample"][:3]:
            print(f"      · {item['actuator']} {item['field']}: 我方 {item['ours']:.6g} vs 官方 {item['official']:.6g}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
