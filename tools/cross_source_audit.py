#!/usr/bin/env python3
"""跨源对照审计（B20）：把契约真值 的 ``effort`` / ``velocity_limit`` 与**外部源**逐关节对照。

方法（2026-09-13 用户提出并已用 g1 验证，见任务清单 §方法固化）
----------------------------------------------------------------
回答"某个数值是**原本就没有**、**后续被去掉**，还是**我方录入错**"：

1. 找官方项目，**完整 clone**（带历史，放在工作区外 ``/00_open/``，不进 ``00_resources``）；
2. 再找若干非官方提供 URDF/MJCF 的仓，作为**独立实现**；
3. 三向对照（我方契约 ↔ 官方 ↔ 非官方），差异逐条归类：
   * 多源一致且与我方不同 → **我方错**（应改我方）；
   * 单一来源或不同版本给出不同值 → **版本差异**（登记，不改数）；
   * 任何来源都没有 → **原本没有**（登记缺口，或按官方写明的公式推导，不猜）。

本工具只做第 3 步里可自动化的部分：从 URDF（``<limit effort velocity>``）与 MJCF
（``<joint … actuatorfrcrange>``）抽取**关节侧**限值，与契约逐关节对照。

用法
----
    python tools/cross_source_audit.py                 # 全部 14 机型
    python tools/cross_source_audit.py unitree_g1      # 单机型
    python tools/cross_source_audit.py --json          # 机器可读

退出码：恒为 0（审计工具，不是门禁）——**差异需要人判"谁对"**，工具不替人下结论；
若将来要进门禁，可加 ``--strict``（多源一致但与我方不同即失败）。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from contracts.physics_binding import RoleResolver  # noqa: E402

ROBOTS_DIR = ROOT / "assets" / "robots"
RESOURCES = ROOT / "00_resources"

#: 源根：工作区外的**完整克隆**（B19）优先，仓内快照兜底。
#: 为什么克隆不在 `00_resources`：那是要 git 上传的，带历史的 clone 体量太大（实测 5 个仓 ~5.2 GB）。
SOURCE_ROOTS: tuple[tuple[str, pathlib.Path], ...] = (
    ("menagerie", pathlib.Path("/00_open/mujoco_menagerie")),
    ("unitree_ros", pathlib.Path("/00_open/unitree_ros")),
    ("unitree_rl_mjlab", pathlib.Path("/00_open/unitree_rl_mjlab")),
    ("unitree_rl_gym", pathlib.Path("/00_open/unitree_rl_gym")),
    ("unitree_mujoco", pathlib.Path("/00_open/unitree_mujoco")),
    ("resources", RESOURCES),
)

#: 机型 → 路径关键词（小写匹配；`exclude` 用于排除同前缀的姊妹机型，如 b2 vs b2w）。
ROBOT_MATCH: dict[str, dict[str, tuple[str, ...]]] = {
    "unitree_g1": {"include": ("g1",), "exclude": ("g1_d",)},
    "unitree_go1": {"include": ("go1",), "exclude": ()},
    "unitree_go2": {"include": ("go2",), "exclude": ("go2w",)},
    "unitree_go2w": {"include": ("go2w",), "exclude": ()},
    "unitree_b2": {"include": ("b2_description", "unitree_b2"), "exclude": ("b2w",)},
    "unitree_b2w": {"include": ("b2w",), "exclude": ()},
    "deeprobotics_lite3": {"include": ("lite3",), "exclude": ()},
    "deeprobotics_m20": {"include": ("m20",), "exclude": ()},
    "limx_tron1_pf": {"include": ("tron1",), "exclude": ()},
    "limx_tron1_sf": {"include": ("tron1",), "exclude": ()},
    "limx_tron1_wf": {"include": ("tron1",), "exclude": ()},
    "microduck": {"include": ("microduck",), "exclude": ()},
    # zex-w = 自家轮腿（源自 00_resources/rc_old 的 RC_WheelLeg），路径里没有 "zex"
    "zex-w": {"include": ("zex", "wheelleg"), "exclude": ()},
    "wuji_hand": {"include": ("wuji",), "exclude": ()},
}

#: 每个机型最多看多少个源文件（防止在内含 2.4 GB 资源库时扫太久）。
MAX_FILES_PER_ROBOT = 120
SKIP_DIRS = {".git", "node_modules", "__pycache__", "vendor", "assets"}


def _iter_candidates(robot_id: str) -> list[tuple[str, pathlib.Path]]:
    spec = ROBOT_MATCH.get(robot_id)
    if not spec:
        return []
    include, exclude = spec["include"], spec["exclude"]
    found: list[tuple[str, pathlib.Path]] = []
    for source_name, root in SOURCE_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in (".urdf", ".xml"):
                continue
            parts = set(path.parts)
            if parts & SKIP_DIRS:
                continue
            low = str(path).lower()
            if not any(key in low for key in include):
                continue
            if any(bad in low for bad in exclude):
                continue
            found.append((source_name, path))
            if len(found) >= MAX_FILES_PER_ROBOT:
                return found
    return found


_URDF_JOINT = re.compile(r'<joint\s+name="([^"]+)"[^>]*>(.*?)</joint>', re.S)
_URDF_LIMIT = re.compile(r'<limit([^/>]*)/?>')
_URDF_EFFORT = re.compile(r'effort="([0-9.eE+-]+)"')
_URDF_VELOCITY = re.compile(r'velocity="([0-9.eE+-]+)"')
_MJCF_JOINT = re.compile(r'<joint\s+name="([^"]+)"([^>]*)/?>')
#: actuator 级的限力写法（menagerie / 部分 MJCF 把限力写在 <actuator> 上而不是关节上）
_MJCF_ACTUATOR = re.compile(r'<(?:motor|position|velocity|general|intvelocity)\s+([^>]*)/?>')
_ATTR_JOINT = re.compile(r'joint="([^"]+)"')
_ATTR_RANGE = re.compile(r'(?:forcerange|ctrlrange|actuatorfrcrange)="(-?[0-9.eE+-]+)\s+(-?[0-9.eE+-]+)"')
_MJCF_FRC = re.compile(r'actuatorfrcrange="(-?[0-9.eE+-]+)\s+(-?[0-9.eE+-]+)"')


def _extract_limits(path: pathlib.Path) -> dict[str, dict[str, float]]:
    """抽 ``{关节名: {"effort": x, "velocity": y}}``（缺失的键不出现）。"""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    limits: dict[str, dict[str, float]] = {}
    for match in _URDF_JOINT.finditer(text):
        name, body = match.group(1), match.group(2)
        limit = _URDF_LIMIT.search(body)
        if not limit:
            continue
        entry: dict[str, float] = {}
        effort = _URDF_EFFORT.search(limit.group(1))
        velocity = _URDF_VELOCITY.search(limit.group(1))
        if effort:
            entry["effort"] = abs(float(effort.group(1)))
        if velocity:
            entry["velocity"] = abs(float(velocity.group(1)))
        if entry:
            limits.setdefault(name, {}).update(entry)
    for match in _MJCF_JOINT.finditer(text):
        name, attrs = match.group(1), match.group(2)
        frc = _MJCF_FRC.search(attrs)
        if frc:
            magnitude = max(abs(float(frc.group(1))), abs(float(frc.group(2))))
            limits.setdefault(name, {}).setdefault("effort", magnitude)
    # actuator 级限力：只在关节上没给值时补上（menagerie / wuji-mjlab 这类写法）
    for match in _MJCF_ACTUATOR.finditer(text):
        attrs = match.group(1)
        joint = _ATTR_JOINT.search(attrs)
        rng = _ATTR_RANGE.search(attrs)
        if not joint or not rng:
            continue
        magnitude = max(abs(float(rng.group(1))), abs(float(rng.group(2))))
        limits.setdefault(joint.group(1), {}).setdefault("effort", magnitude)
    return limits


def audit_robot(robot_id: str) -> dict:
    contract_path = ROBOTS_DIR / robot_id / "contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
    expanded = RoleResolver(contract).expand_actuator_profile()

    mine: dict[str, dict[str, float]] = {}
    for joint, params in expanded.items():
        entry: dict[str, float] = {}
        if params.get("effort") is not None:
            entry["effort"] = float(params["effort"])
        if params.get("velocity_limit") is not None:
            entry["velocity"] = float(params["velocity_limit"])
        mine[joint] = entry

    # **逐文件**收集（不是逐源合并）——同一源里不同文件常给出不同版本的值，
    # 合并后只看一个值会把"版本差异"误报成"我方错"（lite3 实测踩过这个坑）。
    per_source_files: dict[str, list[tuple[str, dict[str, dict[str, float]]]]] = {}
    for source_name, path in _iter_candidates(robot_id):
        limits = _extract_limits(path)
        if not limits:
            continue
        label = str(path).replace(f"{ROOT}/", "").replace("/00_open/", "@")
        per_source_files.setdefault(source_name, []).append((label, limits))

    def votes(joint: str, key: str) -> list[tuple[str, float]]:
        found: list[tuple[str, float]] = []
        for source_name, files in per_source_files.items():
            for label, limits in files:
                entry = limits.get(joint)
                if entry and key in entry:
                    found.append((f"{source_name}:{label}", entry[key]))
        return found

    def summarize(votes_list: list[tuple[str, float]]) -> tuple[float | None, bool, list[tuple[str, float]]]:
        """返回 (多数值, 是否多源一致, 全部投票)。"""
        if not votes_list:
            return None, False, []
        tally: dict[float, list[tuple[str, float]]] = {}
        for label, value in votes_list:
            tally.setdefault(round(value, 6), []).append((label, value))
        best = max(tally.items(), key=lambda item: len(item[1]))
        return best[0], len(tally) == 1 and len(votes_list) >= 2, votes_list

    effort_diff: list[dict] = []
    velocity_missing: list[dict] = []
    source_conflicts: list[dict] = []
    no_source_joints: list[str] = []
    for joint, expected in sorted(mine.items()):
        effort_votes = votes(joint, "effort")
        velocity_votes = votes(joint, "velocity")
        if not effort_votes and not velocity_votes:
            no_source_joints.append(joint)
            continue
        for key, own_key, own_value, votes_list in (
            ("effort", "effort", expected.get("effort"), effort_votes),
            ("velocity", "velocity", expected.get("velocity"), velocity_votes),
        ):
            if not votes_list:
                continue
            value, agreed, all_votes = summarize(votes_list)
            distinct = sorted({round(v, 6) for _, v in votes_list})
            if len(distinct) > 1:
                source_conflicts.append({
                    "joint": joint,
                    "field": key,
                    "values": distinct,
                    "by_source": sorted({(label.split(":", 1)[0], round(v, 3)) for label, v in all_votes}),
                })
            if own_value is None:
                if key == "velocity":
                    velocity_missing.append({
                        "joint": joint,
                        "value": value,
                        "agreement": "多源一致" if agreed else "单源",
                        "sources": sorted({(label.split(":", 1)[0], round(v, 3)) for label, v in all_votes})[:4],
                    })
                continue
            if all(abs(float(own_value) - v) > 1e-6 for v in distinct):
                effort_diff.append({
                    "joint": joint,
                    "field": own_key,
                    "contract": own_value,
                    "source_value": value,
                    "source_agreement": "多源一致" if agreed else ("源间不一致" if len(distinct) > 1 else "单源"),
                    "sources": sorted({(label.split(":", 1)[0], round(v, 3)) for label, v in all_votes})[:4],
                })

    return {
        "robot_id": robot_id,
        "action_joints": len(mine),
        "sources_with_limits": {
            src: max((len(limits) for _, limits in files), default=0)
            for src, files in per_source_files.items()
        },
        "source_files": sum(len(files) for files in per_source_files.values()),
        "effort_or_velocity_diff": effort_diff,
        "velocity_missing_in_contract": velocity_missing,
        "joints_without_any_source": no_source_joints,
        "source_conflicts": source_conflicts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="契约 ↔ 外部源 跨源对照审计（B20）")
    parser.add_argument("robot_id", nargs="?", help="只审计指定机型")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    robots = sorted(p.name for p in ROBOTS_DIR.iterdir() if (p / "contract.json").is_file())
    if args.robot_id:
        robots = [r for r in robots if r == args.robot_id]
        if not robots:
            print(f"未找到机型 {args.robot_id}", file=sys.stderr)
            return 2

    reports = [audit_robot(robot) for robot in robots]
    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
        return 0

    print(f"跨源对照审计（{len(reports)} 机型）｜源根：{len([r for _, r in SOURCE_ROOTS if r.is_dir()])} 个可用")
    print(f"{'机型':22s} {'驱动关节':>8s} {'有源关节':>8s} {'与我方不一致':>12s} {'缺速度限幅':>10s} {'源内冲突':>8s}")
    for report in reports:
        sourced = set()
        for table in report["sources_with_limits"].values():
            sourced.add(table)
        has_source = report["action_joints"] - len(report["joints_without_any_source"])
        print(
            f"{report['robot_id']:22s} {report['action_joints']:>8d} {has_source:>8d} "
            f"{len(report['effort_or_velocity_diff']):>12d} {len(report['velocity_missing_in_contract']):>10d} "
            f"{len(report['source_conflicts']):>8d}"
        )
    print()
    for report in reports:
        if not (report["effort_or_velocity_diff"] or report["velocity_missing_in_contract"] or report["source_conflicts"]):
            continue
        print(f"■ {report['robot_id']}（源: {report['sources_with_limits']}）")
        for item in report["effort_or_velocity_diff"]:
            kind = "源内一致" if item["source_agreement"] else "源间不一致"
            print(f"   ⚠️ 与我方不同 [{kind}] {item['joint']} {item.get('field', 'effort')}: 我方 {item['contract']} vs {item['sources']}")
        for item in report["velocity_missing_in_contract"]:
            print(f"   ➕ 我方缺速度限幅 {item['joint']} ← 源: {item['sources']}")
        for item in report["source_conflicts"]:
            print(f"   ❗ 源间冲突（版本差异信号）{item['joint']} {item['field']}: {item['by_source']}")
        if report["joints_without_any_source"]:
            print(f"   （{len(report['joints_without_any_source'])} 个关节任何源都没有：{report['joints_without_any_source'][:4]}…）")
    no_source = [r["robot_id"] for r in reports if len(r["joints_without_any_source"]) == r["action_joints"]]
    if no_source:
        print()
        print(f"⛔ 完全无源可对照的机型（需补官方源）：{'、'.join(no_source)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
