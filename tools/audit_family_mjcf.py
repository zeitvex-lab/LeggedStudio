"""族 MJCF 约定门禁：同族机型在**规范化后**还有哪些不一样，逐项可核对。

回答的问题：**"同架构"的 MJCF 基准到底统一到哪一步了**——规范化（`adapters/mjlab/spec_utils.py`：
补传感器名 + 按需撤 XML 执行器并修 ctrl 型 keyframe）之后，同族各机型仍不相同的项分三类：

* **口径类**（执行器声明归属 / margin 政策）：族声明 `mjcf_conventions` 给**目标口径**，
  任何偏离必须逐条登记在 `mjcf_deviations`（登记了又与实测一致也判红——防静默统一/静默放宽）；
* **结构事实类**（被动关节数、关节名字符串、mesh 数）：**只登记不抹平**，进摘要供两台机型 diff；
* **语义类**（关节角色序列 / 观测骨架 / 地形档）：已由 `tools/audit_families.py` 与
  `registry/terrains` 管，这里不重复。

判据（全部 fail-closed）：
1. 族必须声明 `mjcf_conventions`；
2. 每个成员的**实测** `actuator_binding` / `margin_policy` == 声明值，或已登记偏离（含 why）；
3. 登记表里出现未知键 / 空登记 → 红；
4. 规范化后仍有**无名传感器** → 红（mjlab scene 建环境会 `Invalid name ''`）；
5. 「撤 XML 执行器」口径必须**真能编译**（`normalize_spec(strip_actuators=True).compile()`）——
   这条会抓 keyframe 带 ctrl 那类问题（go1/b2 各一个 keyframe，实测踩过）；
6. MJCF 总关节 − 驱动关节 == 契约 `joints.passive_joints` 数。

用法：
    PYTHONUTF8=1 .venv/Scripts/python.exe tools/audit_family_mjcf.py            # 打印 + 落基线
    PYTHONUTF8=1 .venv/Scripts/python.exe tools/audit_family_mjcf.py --check    # 只核对不写基线（进 CI）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FAMILIES_DIR = ROOT / "registry" / "families"
ROBOTS_DIR = ROOT / "assets" / "robots"
BASELINE = ROOT / "tools" / "baselines" / "family_mjcf.json"

_KNOWN_DEVIATION_KEYS = ("actuator_binding", "margin_policy")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _families() -> dict[str, dict]:
    index = _load(FAMILIES_DIR / "index.json")
    out: dict[str, dict] = {}
    for entry in index.get("families") or []:
        doc = _load(FAMILIES_DIR / str(entry.get("path")))
        out[str(doc.get("family_id"))] = doc
    return out


def _member_summary(robot_id: str, problems: list[str]) -> dict | None:
    """实测一个成员的 MJCF 事实（规范化前后都记），供核对与 diff。"""
    import mujoco

    from adapters.mjlab.spec_utils import normalize_spec

    package = ROBOTS_DIR / robot_id
    contract_path = package / "contract.json"
    legacy_path = package / "contract_legacy_v2.json"
    if not contract_path.is_file():
        problems.append(f"{robot_id}: 缺 v3 契约，判不了")
        return None
    contract = _load(contract_path)
    legacy = _load(legacy_path) if legacy_path.is_file() else {}
    asset = Path(str((legacy.get("urdf") or {}).get("path") or ""))
    xml_path = asset if asset.is_absolute() else ROOT / asset
    if not xml_path.is_file():
        problems.append(f"{robot_id}: 契约资产不存在 {xml_path}")
        return None

    raw = mujoco.MjSpec.from_file(str(xml_path))
    unnamed_before = sum(1 for sensor in raw.sensors if not sensor.name)
    keys_with_ctrl = [str(key.name) for key in raw.keys if len(getattr(key, "ctrl", []) or [])]
    domains = _actuator_domains(xml_path)

    normalized = mujoco.MjSpec.from_file(str(xml_path))
    report = normalize_spec(normalized)
    unnamed_after = sum(1 for sensor in normalized.sensors if not sensor.name)
    compiled = normalized.compile()
    margins = sorted({round(float(compiled.geom_margin[index]), 6) for index in range(compiled.ngeom)} - {0.0})

    strip_ok, strip_error = True, ""
    try:
        stripped = mujoco.MjSpec.from_file(str(xml_path))
        normalize_spec(stripped, strip_actuators=True)
        stripped.compile()
    except Exception as exc:  # noqa: BLE001
        strip_ok, strip_error = False, f"{type(exc).__name__}: {exc}"

    actuated = [str(item.get("name")) for item in contract["joints"]["actuated"]]
    declared_passive = [str(item.get("name")) for item in (legacy.get("joints") or {}).get("passive_joints") or []]
    # **排除浮动基座**（`type=free`，各机型的 `floating_base` / `floating_base_joint`）：它是基座
    # 自由度、不是"被动关节"；mjlab 侧由根 body 处理。只数铰接/滑动的非驱动关节。
    hinge_like = [joint.name for joint in normalized.joints if joint.name and int(joint.type) != 0]
    joints_total = len(hinge_like)
    bodies = [body.name for body in normalized.worldbody.bodies]
    named_geoms = sum(1 for geom in normalized.geoms if geom.name)

    if joints_total - len(actuated) != len(declared_passive):
        problems.append(
            f"{robot_id}: 被动关节对不上（MJCF {joints_total} − 驱动 {len(actuated)} ≠ "
            f"契约登记 {len(declared_passive)}）"
        )
    if unnamed_after:
        problems.append(f"{robot_id}: 规范化后仍有 {unnamed_after} 个无名传感器")
    if not strip_ok:
        problems.append(f"{robot_id}: 「撤 XML 执行器」口径不可用（{strip_error}）")

    return {
        "robot_id": robot_id,
        "actuator_binding": _actuator_binding(package),
        "sensors_total": len(list(normalized.sensors)),
        "sensors_unnamed_before": unnamed_before,
        # 没有传感器 ≠ 有无名传感器（zex-w 的 MJCF 一个传感器都没有，规范仍然成立）
        "sensors_named_after": not unnamed_after,
        "actuator_domains": domains,
        "keys_with_ctrl": keys_with_ctrl,
        "strip_compiles": strip_ok,
        "margins_nonzero": margins,
        "margin_policy": "warp_ccd_off" if margins else "zero",
        "joints_total": joints_total,
        "joints_actuated": len(actuated),
        "roots": bodies,
        "geoms_named": f"{named_geoms}/{compiled.ngeom}",
        "meshes": len([mesh for mesh in normalized.meshes]),
        "normalize_report": report.as_dict(),
    }


def _actuator_domains(xml_path: Path) -> list[str]:
    """XML 执行器元素类型（`position` / `velocity` / `motor` / `general` …）——按标签直读，不猜。"""

    import xml.etree.ElementTree as ET

    try:
        root = ET.parse(xml_path).getroot()
    except (OSError, ET.ParseError):
        return []
    return sorted({child.tag for child in root.findall(".//actuator/*")})


def _actuator_binding(package: Path) -> str:
    """实测执行器声明归属（**文本级**，认两种写法，与 `audit_*` 家族同口径）。

    `mjcf_wrapped` = 包内直接构造 `XmlActuatorCfg(...)`，或调族 Kit 的
    `position_actuator_trio(...)`（该工厂返回的就是 `XmlActuatorCfg` 组）；
    `cfg_declared` = 都没有（执行器由 cfg 的 builtin 组声明，MJCF 那份要撤）。
    实体级对账（真建出来看执行器类）在 `adapters/mjlab/test_package_entity_build.py`。
    """

    source = package / "training" / "source"
    patterns = (re.compile(r"\bXmlActuatorCfg\s*\("), re.compile(r"\bposition_actuator_trio\s*\("))
    for path in sorted(source.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(pattern.search(text) for pattern in patterns):
            return "mjcf_wrapped"
    return "cfg_declared"


def check_conventions(summary: dict, conventions: dict, registered: dict, problems: list[str]) -> None:
    """口径类逐项对账：实测 == 声明，或**已登记偏离**；登记了又与实测一致也判红。

    抽成纯函数是为了能拿合成数据做反例注入测试（`backend/test_family_mjcf_conventions.py`）。
    """

    label = f"{summary.get('family')}/{summary.get('robot_id')}"
    for key, entry in registered.items():
        if key not in _KNOWN_DEVIATION_KEYS:
            problems.append(f"{label}: mjcf_deviations 里出现未知键 {key!r}")
        elif not (entry or {}).get("why"):
            problems.append(f"{label}: 偏离 {key} 没写 why")
    for key in _KNOWN_DEVIATION_KEYS:
        actual = summary[key]
        declared = conventions.get(key)
        deviation = (registered.get(key) or {}).get("value")
        if actual == declared:
            if deviation is not None:
                problems.append(
                    f"{label}: {key} 登记了偏离 {deviation!r}，但实测就是声明值 {declared!r}（登记该撤掉）"
                )
        elif deviation != actual:
            problems.append(
                f"{label}: {key} 实测 {actual!r} ≠ 族声明 {declared!r}，且未登记（登记表里是 {deviation!r}）"
            )


def audit() -> tuple[list[dict], list[str]]:
    problems: list[str] = []
    rows: list[dict] = []
    for family_id, family in _families().items():
        conventions = family.get("mjcf_conventions")
        if not conventions:
            problems.append(f"{family_id}: 族声明缺 mjcf_conventions")
            continue
        deviations = family.get("mjcf_deviations") or {}
        for robot_id in family.get("members") or []:
            summary = _member_summary(str(robot_id), problems)
            if summary is None:
                continue
            check_conventions(summary, conventions, deviations.get(str(robot_id)) or {}, problems)
            summary["family"] = family_id
            rows.append(summary)
    return rows, problems


def main() -> int:
    parser = argparse.ArgumentParser(description="族 MJCF 约定门禁（规范化后逐项核对）")
    parser.add_argument("--check", action="store_true", help="只核对、不写基线（CI 用）")
    args = parser.parse_args()

    rows, problems = audit()
    print("[mjcf] 规范化后摘要（family / robot / 执行器归属 / 根 body / margin / 具名 geom / 被动关节）")
    for row in rows:
        passive = row["joints_total"] - row["joints_actuated"]
        print(f"  {row['family']:9s} {row['robot_id']:22s} {row['actuator_binding']:13s} "
              f"root={str(row['roots'][0] if row['roots'] else '?'):10s} "
              f"margin={row['margins_nonzero'] or 0} geom={row['geoms_named']:>7s} "
              f"被动={passive} 传感器={row['sensors_total']}(补名 {row['sensors_unnamed_before']}) "
              f"keyframes={row['keys_with_ctrl'] or 0}")
    if problems:
        print(f"\n[mjcf] 判红 {len(problems)} 处：")
        for item in problems:
            print(f"  ✗ {item}")
        return 1
    if not args.check:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps({
            "schema": "family-mjcf-1.0",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "note": "族内 MJCF **规范化后**的实测摘要（规范化 = adapters/mjlab/spec_utils.normalize_spec）。"
                    "口径类偏离登记在 registry/families/*.json 的 mjcf_deviations；结构事实类只登记不抹平。",
            "results": rows,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n[mjcf] 全部通过；基线已落 {BASELINE.relative_to(ROOT)}")
    else:
        print("\n[mjcf] 全部通过（--check 未写基线）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
