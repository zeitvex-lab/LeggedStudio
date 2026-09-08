"""资产体检五卡引擎（T1.1，批次 1 / M2）。

五卡：质量（三来源对比）/ 碰撞 / 惯量 / 电机参数（角色分组 + 官方 diff）/ 关节。
状态三色（pass/warn/fail）+ 中文一句话，对应报告 10 §②资产库区体检卡栏；
mesh 体积质量源在 T1.3 导入管线接入前明确降级"未知"（fail-closed，不出伪精确值，
REF §6.3）。官方部署参数 diff 的参考源为包目录 ``official_actuator.json``
（数据 + 来源引用），Lite3/M20 漂移案例为内建 fixture（DEEPROBOTICS_PORTING 记录）。

参考：URDF-Studio（parsers/inertialDerived——REF §6.2）、robot_mujoco 12 机型作
第二数据源（报告 9 §2.3）、报告 2 §6。
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

_MASS_SPREAD_WARN = 0.20
_EFFORT_DRIFT_WARN = 0.10


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _card(status: str, summary: str, **extra: Any) -> dict:
    return {"status": status, "summary": summary, **extra}


def _mass_card(root: Path, contract_v2: dict) -> dict:
    model_path = _model_path(root)
    sources: dict[str, Any] = {}

    if model_path is not None and model_path.exists():
        declared = 0.0
        explicit = False
        try:
            for inertial in ET.parse(model_path).getroot().findall(".//inertial[@mass]"):
                declared += float(inertial.get("mass", "0"))
                explicit = True
        except ET.ParseError:
            declared = 0.0
        if explicit:
            sources["declared_inertial"] = round(declared, 6)

    compiled_mass = None
    if model_path is not None and model_path.exists():
        try:
            import mujoco

            model = mujoco.MjModel.from_xml_path(str(model_path))
            compiled_mass = float(sum(model.body_mass[1:]))
            sources["compiled_mujoco"] = round(compiled_mass, 6)
        except Exception:
            pass

    recorded = ((contract_v2.get("urdf") or {}).get("total_mass_kg"))
    if isinstance(recorded, (int, float)) and recorded > 0:
        sources["recorded"] = float(recorded)

    # mesh_computed 明确缺位（T1.3 接入前不伪造）
    values = [float(v) for v in sources.values()]
    if len(values) >= 2:
        spread = (max(values) - min(values)) / max(min(values), 1e-9)
        status = "pass" if spread <= _MASS_SPREAD_WARN else "fail"
        summary = f"质量三来源极差 {spread:.1%}（阈值 20%）；mesh 计算源待 T1.3 接入，当前记未知"
    else:
        status = "warn"
        summary = "质量来源不足两个，无法交叉验证（mesh 计算源待 T1.3 接入）——按 fail-closed 记未知"
    return _card(status, summary, sources=sources, mass_source=(contract_v2.get("urdf") or {}).get("mass_source"))


def _model_path(root: Path) -> Path | None:
    manifest = _load_json(root / "robot_package.json") or {}
    rel = str((manifest.get("model") or {}).get("path") or "model/robot.xml")
    path = root / rel
    return path if path.exists() else None


def _collision_card(root: Path) -> dict:
    model_path = _model_path(root)
    if model_path is None or not model_path.exists():
        return _card("warn", "模型文件缺失，碰撞卡不可用")
    try:
        import mujoco

        model = mujoco.MjModel.from_xml_path(str(model_path))
    except Exception as exc:
        return _card("warn", f"模型编译失败：{exc}")
    type_names = {int(v): str(k).split("_")[-1].lower() for k, v in vars(mujoco.mjtGeom).items() if isinstance(v, int)}
    collision = visual = 0
    types: dict[str, int] = {}
    for i in range(model.ngeom):
        geom_type = type_names.get(int(model.geom_type[i]), f"type{int(model.geom_type[i])}")
        types[geom_type] = types.get(geom_type, 0) + 1
        if model.geom_contype[i] or model.geom_conaffinity[i]:
            collision += 1
        else:
            visual += 1
    if collision == 0:
        return _card("fail", "没有任何碰撞几何（contype/conaffinity 全为 0）", collision_geoms=0, visual_geoms=visual, types=types)
    return _card(
        "pass",
        f"碰撞几何 {collision} 个 / 纯视觉 {visual} 个",
        collision_geoms=collision,
        visual_geoms=visual,
        types=types,
    )


def _inertia_card(root: Path) -> dict:
    model_path = _model_path(root)
    if model_path is None or not model_path.exists():
        return _card("warn", "模型文件缺失，惯量卡不可用")
    try:
        import mujoco

        model = mujoco.MjModel.from_xml_path(str(model_path))
    except Exception as exc:
        return _card("warn", f"模型编译失败：{exc}")
    bodies = []
    degenerate = 0
    for i in range(1, model.nbody):
        diag = [float(v) for v in model.body_inertia[i]]
        if any(v <= 0 for v in diag):
            degenerate += 1
        if i <= 12 or degenerate:
            bodies.append({
                "name": model.body(i).name,
                "mass": round(float(model.body_mass[i]), 6),
                "inertia_diag": [round(v, 9) for v in diag],
            })
    if degenerate:
        return _card("fail", f"{degenerate} 个连杆惯量张量存在非正元素", degenerate=degenerate, bodies=bodies[:12])
    return _card("pass", "连杆惯量张量全部为正（列出前 12 个）", degenerate=0, bodies=bodies[:12])


def _motor_card(contract_v3: dict | None, official: dict | None) -> dict:
    if not contract_v3:
        return _card("warn", "契约 v3 缺失，电机参数卡需要先迁移（tools/migrate_contract_v3.py）")
    try:
        from contracts.role_resolver import RoleResolver

        expanded = RoleResolver(contract_v3).expand_actuator_profile()
    except Exception as exc:
        return _card("fail", f"契约 v3 展开失败：{exc}")
    by_role: dict[str, dict[str, Any]] = {}
    for entry in contract_v3["joints"]["actuated"]:
        by_role.setdefault(entry["role"], []).append(entry["name"])
    table = {}
    diffs: list[dict] = []
    for role, joints in by_role.items():
        sample = expanded[joints[0]]
        table[role] = {
            "joints": joints,
            "stiffness": sample.get("stiffness"),
            "damping": sample.get("damping"),
            "effort": sample.get("effort"),
            "armature": sample.get("armature"),
            "mode": sample.get("mode"),
        }
    if official:
        official_roles = official.get("by_role") or {}
        for role, ref in official_roles.items():
            mine = table.get(role) or {}
            for key in ("effort", "stiffness", "damping", "armature"):
                if key not in ref or mine.get(key) in (None, 0):
                    continue
                delta = float(mine[key]) - float(ref[key])
                if abs(ref[key]) > 0 and abs(delta / float(ref[key])) > _EFFORT_DRIFT_WARN:
                    diffs.append({
                        "role": role,
                        "param": key,
                        "package": mine.get(key),
                        "official": ref[key],
                        "delta_pct": round(delta / float(ref[key]), 4),
                    })
    if diffs:
        return _card(
            "fail",
            f"{len(diffs)} 项与官方部署值漂移超过 10%（展开看两边数值）",
            roles=table,
            official_source=official.get("source") if official else None,
            diffs=diffs,
        )
    if official:
        return _card("pass", "与官方部署值一致（±10% 内）", roles=table, official_source=official.get("source"), diffs=[])
    return _card("pass", "无官方参考源（official_actuator.json 缺失），仅展示角色分组参数", roles=table, official_source=None, diffs=[])


def _joint_card(contract_v2: dict, contract_v3: dict | None) -> dict:
    order = contract_v2.get("action", {}).get("joint_order") or []
    limits = contract_v2.get("joints", {}).get("joint_limits") or {}
    default_pose = contract_v2.get("joints", {}).get("default_pose") or []
    reindex = (contract_v3 or {}).get("action", {}).get("reindex_from_model")
    details = []
    for i, name in enumerate(order):
        limit = limits.get(name) or {}
        details.append({
            "name": name,
            "index": i,
            "lower": limit.get("lower"),
            "upper": limit.get("upper"),
            "default": default_pose[i] if i < len(default_pose) else None,
        })
    status = "pass" if order else "fail"
    summary = f"{len(order)} 个驱动关节，默认站姿 {len(default_pose)} 项" + (
        f"，reindex_from_model 已声明（非恒等）" if reindex else ""
    )
    return _card(status, summary, joints=details, reindex_from_model=reindex)


def inspect_package(root: Path) -> dict:
    """五卡体检。root = 机器人包目录（assets/robots/<id> 或 workspace 副本）。"""

    contract_v2 = _load_json(root / "contract.json") or {}
    contract_v3 = _load_json(root / "contract_v3.json")
    official = _load_json(root / "official_actuator.json")
    cards = {
        "mass": _mass_card(root, contract_v2),
        "collision": _collision_card(root),
        "inertia": _inertia_card(root),
        "motor": _motor_card(contract_v3, official),
        "joints": _joint_card(contract_v2, contract_v3),
    }
    worst = "pass"
    for status in ("fail", "warn"):
        if any(card["status"] == status for card in cards.values()):
            worst = status
            break
    return {
        "robot_id": contract_v2.get("robot_id") or root.name,
        "package_root": str(root),
        "overall": worst,
        "cards": cards,
    }
