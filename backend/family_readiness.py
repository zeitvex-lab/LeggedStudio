"""族通用就绪：这台机器人**能不能用族架构训、能训哪几档**（"一键导入"的判定半边）。

## 为什么要有它

导入一台同族新机型后，用户要立刻知道两件事：**能不能训**、**能训哪几个地形档**。
"资产体检五卡"回答的是资产质量（质量/碰撞/惯量/电机/关节），不回答"族级通用架构吃不吃得下"。
本模块就补这一块，判据全部**静态可算**（纯 stdlib：v3 契约 + MJCF 文本 + 族/地形注册表），
不进训练栈、不跑仿真：

| 检查 | 判据 | 抓什么 |
|---|---|---|
| 契约在场 | `contract.json`（v3）可读 | 没有 v3 契约 ⇒ 判不了族、也拿不到字段级表述 |
| 族归属 | 契约 `morphology.id` 落在**族注册表**的 `morphology_ids` 里 | 新机型形态没登记（族架构无从接入） |
| 关节接口 | `action.joint_order` 非空、`joints.actuated` 与之一致、`default_pose` 长度匹配 | 关节序/默认姿缺失或不自洽（装配即崩） |
| 执行器可解 | 每个 `joint_order` 关节在 MJCF 里有 actuator，且类型 ∈ {position, velocity, motor} | 漏执行器 / 用了通用 general（训练侧认不出命令域） |
| 执行器 PD | 每个关节能经 `actuator_profile`（by_joint → by_role → default）解析出刚度/阻尼 | 缺 PD 声明（装配时只能瞎猜） |
| 质量非零 | v2 `urdf.total_mass_kg` > 0 | 质量为 0（惯量/质量控制全失效） |
| 观测骨架 | 观测项序列与族声明一致（**已登记偏差放行**） | 同族观测不同构且没人登记 |

输出还带 **`trainable_terrain_profiles`**：本族 `ready` 的地形档 id 清单（见
`registry/terrains`）——这就是"导入后一键开训"能选的那些档。

**导入侧另有两只手**（同一份族声明的另一面，2026-09-24 补）：`judge_family`（按族注册表
判定「这批执行关节属于哪个族」，判不出就如实说不判）与 `family_observation_components`
（取族 actor 观测项序列）——导入那一刻据此决定「按族骨架落观测」还是「如实标非族成员」。
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Sequence

#: MuJoCo actuator 元素标签 → mjlab 认得的命令域（与 `detect_command_field` 同口径）。
_ACTUATOR_TAGS = {"position": "position", "velocity": "velocity", "motor": "effort"}


def _load(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _model_path(root: Path) -> Path | None:
    manifest = _load(root / "robot_package.json") or {}
    rel = str((manifest.get("model") or {}).get("path") or "model/robot.xml")
    path = root / rel
    return path if path.exists() else None


def _xml_actuators(model: Path) -> dict[str, str]:
    """关节名 → 命令域（position/velocity/effort）；`<include>` 追一层。"""
    found: dict[str, str] = {}

    def scan(path: Path) -> None:
        try:
            tree = ET.parse(path)
        except (OSError, ET.ParseError):
            return
        root_el = tree.getroot()
        for include in root_el.findall(".//include[@file]"):
            nested = (path.parent / str(include.get("file"))).resolve()
            if nested.is_file():
                scan(nested)
        for element in root_el.iter():
            tag = element.tag.lower()
            if tag not in _ACTUATOR_TAGS:
                continue
            joint = element.get("joint")
            if joint:
                found.setdefault(str(joint), _ACTUATOR_TAGS[tag])

    scan(model)
    return found


def _pd_for(joint: str, actuator_profile: dict) -> dict | None:
    by_joint = actuator_profile.get("by_joint") or {}
    if isinstance(by_joint, dict) and joint in by_joint:
        entry = by_joint[joint]
        return entry if isinstance(entry, dict) else None
    by_role = actuator_profile.get("by_role") or {}
    if isinstance(by_role, dict):
        for role, entry in by_role.items():
            if role and role in joint and isinstance(entry, dict):
                return entry
    fallback = actuator_profile.get("default")
    return fallback if isinstance(fallback, dict) else None


def _families(families_dir: Path | None = None) -> dict[str, dict]:
    """按 `registry/families/index.json` 读全部族声明（`families_dir` 仅供测试注入）。"""
    families_dir = Path(families_dir) if families_dir else Path(__file__).resolve().parents[1] / "registry" / "families"
    index = _load(families_dir / "index.json") or {}
    out: dict[str, dict] = {}
    for entry in index.get("families") or []:
        declared = _load(families_dir / str(entry.get("path")))
        if declared:
            out[str(declared.get("family_id"))] = declared
    return out


def _families_index() -> dict[str, dict]:
    return _families()


def _morphology_dof(morphology_id: str) -> int | None:
    """``quadruped_12dof`` → 12（形态 id 里的自由度数是与族声明对账的锚点）。"""
    match = re.search(r"(\d+)dof$", morphology_id)
    return int(match.group(1)) if match else None


def judge_family(actuated_joints: Sequence[str], *, families_dir: Path | None = None) -> dict[str, Any]:
    """按**族注册表**判定这批执行关节属于哪个族；判不出就如实说判不出（不猜）。

    与 `backend.contract_migration.guess_morphology_id` 的分工：那个只按命名**猜**一个形态 id；
    这里把结论回注册表对账——腿数 == 族声明 `legs`；每腿角色（经 `role_aliases` 归一）恰好
    覆盖族 `joint_roles` 且**各腿顺序一致**；形态 id 必须在该族 `morphology_ids` 里、且与
    "腿数 × 角色数" 相符。导入侧据此决定"按族骨架落观测"还是"如实标非族成员"。

    返回 `{family, morphology_id, legs, roles_by_leg, reason}`；判不出时 `family` 为 None
    且 `reason` 写清差在哪一步。
    """
    from backend.contract_migration import split_joint  # 角色切词的真值只有这一份

    roles_by_leg: dict[str, list[str]] = {}
    unparsed: list[str] = []
    for raw in actuated_joints:
        leg, role_token = split_joint(str(raw))
        if leg is None or not role_token:
            unparsed.append(str(raw))
            continue
        roles_by_leg.setdefault(leg, []).append(role_token)
    if unparsed:
        return {"family": None, "morphology_id": None, "legs": [], "roles_by_leg": {},
                "reason": f"{len(unparsed)} 个关节名切不出「腿_角色」结构（如 {unparsed[0]}）"}
    if not roles_by_leg:
        return {"family": None, "morphology_id": None, "legs": [], "roles_by_leg": {},
                "reason": "没有可判的执行关节"}

    blockers: list[str] = []
    for family_id, doc in _families(families_dir).items():
        declared_roles = [str(role) for role in doc.get("joint_roles") or []]
        aliases = {str(role): [str(x) for x in (values or [])]
                   for role, values in (doc.get("role_aliases") or {}).items()}
        canonical = {alias: role for role in declared_roles for alias in [role, *aliases.get(role, [])]}
        legs = list(roles_by_leg)
        if len(legs) != int(doc.get("legs") or 0):
            blockers.append(f"{family_id}: 腿数 {len(legs)} ≠ 声明 {doc.get('legs')}")
            continue
        mapped: dict[str, list[str]] = {}
        unknown: list[str] = []
        for leg, tokens in roles_by_leg.items():
            mapped[leg] = []
            for token in tokens:
                role = canonical.get(token)
                if role is None:
                    unknown.append(f"{leg}:{token}")
                else:
                    mapped[leg].append(role)
        if unknown:
            blockers.append(f"{family_id}: 角色未登记（{', '.join(unknown[:4])}）")
            continue
        first = mapped[legs[0]]
        if set(first) != set(declared_roles) or len(first) != len(declared_roles):
            blockers.append(f"{family_id}: 每腿角色 {first} ≠ 声明 {declared_roles}")
            continue
        if any(mapped[leg] != first for leg in legs):
            blockers.append(f"{family_id}: 各腿角色顺序不一致")
            continue
        expected_dof = len(legs) * len(first)
        candidates = [str(item) for item in doc.get("morphology_ids") or []
                      if _morphology_dof(str(item)) == expected_dof]
        if len(candidates) != 1:
            blockers.append(f"{family_id}: 形态 id 与腿×角色（{expected_dof}）对不上："
                            f"{list(doc.get('morphology_ids') or [])}")
            continue
        return {"family": family_id, "morphology_id": candidates[0], "legs": legs,
                "roles_by_leg": mapped, "reason": ""}
    return {"family": None, "morphology_id": None, "legs": [], "roles_by_leg": {},
            "reason": "不匹配任何族声明（" + "；".join(blockers) + "）"}


def family_observation_components(family_id: str, *, families_dir: Path | None = None) -> list[str] | None:
    """族声明的 actor 观测**项序列**（顺序即布局）；族未登记或未声明骨架时返回 None。"""
    doc = _families(families_dir).get(str(family_id))
    if not doc:
        return None
    actor = ((doc.get("observation_skeleton") or {}).get("actor")) or []
    names = [str(item) for item in actor]
    return names or None


def _terrain_profiles_ready(family: str) -> list[str]:
    from adapters.mjlab import terrain_profiles

    return [pid for pid in terrain_profiles.declared_ids()
            if terrain_profiles.availability(pid, family) == "ready"]


def readiness(root: Path, *, contract_v3: dict | None = None) -> dict:
    """静态就绪判定：返回 {verdict, checks, family, trainable_terrain_profiles}。"""
    root = Path(root)
    checks: list[dict[str, Any]] = []

    def add(check_id: str, ok: bool | None, summary: str) -> None:
        checks.append({"id": check_id, "status": "pass" if ok else ("fail" if ok is False else "warn"), "summary": summary})

    if contract_v3 is None:
        contract_v3 = _load(root / "contract.json")
    if not contract_v3:
        add("contract", False, "缺 contract.json（v3）：族归属与字段级表述都判不了")
        return {"verdict": "not_ready", "family": None, "checks": checks, "trainable_terrain_profiles": []}

    morphology_id = str((contract_v3.get("morphology") or {}).get("id") or "")
    families = _families_index()
    family = next((fid for fid, declared in families.items()
                   if morphology_id in [str(x) for x in declared.get("morphology_ids") or []]), None)
    add("family", bool(family),
        f"形态 {morphology_id or '（未声明）'} → 族 {family}" if family
        else f"形态 {morphology_id or '（未声明）'} 不在任何族注册表的 morphology_ids 里")

    joint_order = [str(x) for x in (contract_v3.get("action") or {}).get("joint_order") or []]
    raw_actuated = (contract_v3.get("joints") or {}).get("actuated") or []
    # `joints.actuated` 是对象数组（{name, leg, role}），不是字符串数组。
    actuated = [str(item.get("name")) if isinstance(item, dict) else str(item) for item in raw_actuated]
    pose = list((contract_v3.get("joints") or {}).get("default_pose") or [])
    add("joint_order", bool(joint_order) and (not actuated or set(joint_order) == set(actuated)),
        f"关节序 {len(joint_order)} 个" if joint_order else "缺 action.joint_order")
    add("default_pose", len(pose) == len(joint_order) and bool(joint_order),
        f"默认姿 {len(pose)} 项 / 关节 {len(joint_order)} 个" if joint_order else "无关节序可比")

    model = _model_path(root)
    if model is None:
        add("actuators", False, "包内找不到模型文件（robot_package.json 的 model.path）")
    else:
        actuators = _xml_actuators(model)
        missing = [j for j in joint_order if j not in actuators]
        add("actuators", not missing,
            f"{len(joint_order) - len(missing)}/{len(joint_order)} 个关节在 MJCF 里有可识别的执行器"
            + (f"；缺 {missing[:4]}" if missing else ""))

    actuator_profile = contract_v3.get("actuator_profile") or {}
    no_pd = [j for j in joint_order if not _pd_for(j, actuator_profile)]
    add("actuator_pd", not no_pd,
        f"PD 声明覆盖 {len(joint_order) - len(no_pd)}/{len(joint_order)} 个关节"
        + (f"；缺 {no_pd[:4]}" if no_pd else ""))

    legacy = _load(root / "contract_legacy_v2.json") or {}
    mass = ((legacy.get("urdf") or {}).get("total_mass_kg"))
    try:
        mass_val = float(mass)
    except (TypeError, ValueError):
        mass_val = 0.0
    add("mass", mass_val > 0, f"总质量 {mass_val} kg" if mass_val else "v2 契约缺 urdf.total_mass_kg（质量为 0）")

    skeleton = (families.get(family or "") or {}).get("observation_skeleton") or {}
    expected = [str(x) for x in skeleton.get("actor") or []]
    observed = [str(item.get("name")) for item in (contract_v3.get("observation") or {}).get("components") or []
                if isinstance(item, dict) and item.get("role", "actor") == "actor"]
    if not expected:
        add("observation_skeleton", None, "族声明没有观测骨架，无法比对（先补族声明）")
    else:
        deviations = (skeleton.get("deviations") or {})
        matches = observed == expected
        declared_dev = str(deviations.get(str(contract_v3.get("robot_id")) or root.name) or "")
        add("observation_skeleton", matches or bool(declared_dev),
            "观测骨架与族一致" if matches
            else ("与族不同但已登记偏差" if declared_dev else f"观测骨架与族不一致且未登记偏差：{observed} ≠ {expected}"))

    hard_fail = [c for c in checks if c["status"] == "fail"]
    verdict = "not_ready" if hard_fail else "ready"
    return {
        "verdict": verdict,
        "family": family,
        "checks": checks,
        "trainable_terrain_profiles": _terrain_profiles_ready(family) if family else [],
    }
