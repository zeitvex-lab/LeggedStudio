#!/usr/bin/env python3
"""B37 门禁：内嵌训练源码的"观测组名 / mjlab API 残留"排雷（**按包语义判定**）。

## 为什么不能只按行扫（第一版就错了）

第一版规则把 `obs_groups={"actor": ("policy",)}` 直接判红 —— **错了**。mjlab 的 `obs_groups`
是「runner 侧名字 → env 组名」的映射：只要 env 真的定义了 `"policy"` 组，把它挂到 runner 的
`actor` 槽是**自洽且能跑**的（`wuji_hand` 就是这样）。真正的 bug 是另一种组合：

* env 只定义了 `"policy"` 组，**而 runner 没有 `obs_groups` 映射**（或用默认映射
  `{"actor": ("actor",)}`）⇒ runner 找不到 actor 组，**env 构建即崩**
  （`Available: ['policy', 'critic']`）。microduck testbench 就是这一种。
* 引用了 **mjlab 1.6 已不存在的符号**（`RslRlPpoActorCriticCfg`）。

所以判定必须**按包**做（组定义与 runner 配置常在不同文件），并且区分"自洽"与"断裂"。

## 边界（很重要）

**静态扫描，不运行 mjlab**：绿 = "没有断裂配置"，**不等于**"这些任务能跑起来"。
容器里已验的是 mjlab 1.6 的真实符号与字段名（`mjlab/rl/config.py`：`RslRlModelCfg`、
`RslRlOnPolicyRunnerCfg.actor/critic`），任务能不能构建仍需在真环境跑一次。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCAN_GLOB = "assets/robots/*/training/source/**/*.py"

GROUP_DEF = re.compile(r'^\s*["\'](?P<name>\w+)["\']\s*:\s*ObservationGroupCfg\(')
OBS_GROUPS = re.compile(r"obs_groups\s*=\s*\{(?P<body>[^}]*)\}", re.S)
PAIR = re.compile(r'["\'](?P<slot>\w+)["\']\s*:\s*\((?P<names>[^)]*)\)')
RUNNER_CFG = re.compile(r"\bRslRl\w*RunnerCfg\(")
REMOVED_SYMBOLS = (
    ("RslRlPpoActorCriticCfg",
     "mjlab 1.6 已不存在（单模型配置拆成 actor/critic 两份 RslRlModelCfg）"),
)
#: `group_obs_dim["policy"]` 这类硬读：未接线目录里的潜在雷，双兼容（含 B37 标记）即可豁免
HARD_GROUP_READ = re.compile(r'group_obs_dim\s*\[\s*["\'](?P<name>\w+)["\']\s*\]')


def _iter_files(package: Path) -> list[Path]:
    return sorted(path for path in package.rglob("*.py") if path.is_file())


def audit_package(package: Path) -> dict:
    """按包判定：组定义、obs_groups 映射、runner 配置、已删除符号。"""

    files = _iter_files(package)
    defined_groups: set[str] = set()
    mapped_slots: dict[str, list[str]] = {}
    has_runner_cfg = False
    removed: list[dict] = []
    hard_reads: list[dict] = []

    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relative = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        for index, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            match = GROUP_DEF.match(line)
            if match:
                defined_groups.add(match.group("name"))
            if RUNNER_CFG.search(line):
                has_runner_cfg = True
        if "B37" in text and "双兼容" in text:
            pass  # 该文件已显式处理过组名兼容，下面的硬读不再单独报
        else:
            for index, line in enumerate(text.splitlines(), 1):
                for match in HARD_GROUP_READ.finditer(line):
                    hard_reads.append({"file": relative, "line": index, "group": match.group("name")})
        for match in OBS_GROUPS.finditer(text):
            line = text[: match.start()].count("\n") + 1
            for pair in PAIR.finditer(match.group("body")):
                names = [item.strip().strip("\"'") for item in pair.group("names").split(",") if item.strip()]
                mapped_slots.setdefault(pair.group("slot"), []).extend(names)
                if names:
                    defined_groups.update(names)  # 映射里出现的名字视为"env 确实提供"
            _ = line
        for symbol, reason in REMOVED_SYMBOLS:
            for index, line in enumerate(text.splitlines(), 1):
                if re.search(rf"\b{symbol}\b", line) and not line.strip().startswith("#"):
                    removed.append({"file": relative, "line": index, "symbol": symbol, "reason": reason})

    # ---- 判定 ----
    errors: list[dict] = []
    for item in removed:
        errors.append({
            "kind": "removed-symbol",
            "package": package.parents[1].name,
            **item,
            "hint": "改用 actor/critic 两份 RslRlModelCfg（字段：hidden_dims/obs_normalization，噪声走 distribution_cfg）",
        })

    actor_slot = mapped_slots.get("actor")
    if has_runner_cfg and defined_groups and actor_slot is None:
        # 没有 obs_groups 映射 ⇒ 用 mjlab 默认 {"actor": ("actor",)}；env 里没有 "actor" 组就是断裂
        if actor_slot is None and "actor" not in defined_groups:
            errors.append({
                "kind": "broken-group-mapping",
                "package": package.parents[1].name,
                "file": str(package.relative_to(ROOT)) if package.is_relative_to(ROOT) else str(package),
                "line": 0,
                "group": "actor",
                "reason": f"env 定义的观测组是 {sorted(defined_groups)}，而 runner 未设 obs_groups"
                          f"（默认 actor→('actor',)）⇒ runner 找不到 actor 组，env 构建即崩",
                "hint": "把 env 组名改成 \"actor\"，或显式写 obs_groups={\"actor\": (...)}",
            })
    elif has_runner_cfg and actor_slot is not None:
        missing = [name for name in actor_slot if name not in defined_groups]
        if missing and not any(name in defined_groups for name in actor_slot):
            errors.append({
                "kind": "broken-group-mapping",
                "package": package.parents[1].name,
                "file": str(package.relative_to(ROOT)) if package.is_relative_to(ROOT) else str(package),
                "line": 0,
                "group": "actor",
                "reason": f"obs_groups 的 actor 指向 {actor_slot}，但 env 未定义这些组 {sorted(defined_groups)}",
                "hint": "对齐组名，或把映射改到实际存在的组",
            })

    return {
        # 显示用标签：机型目录名（source → training → <机型>）
        "package": package.parents[1].name if len(package.parts) >= 2 else package.name,
        "path": str(package.relative_to(ROOT)) if package.is_relative_to(ROOT) else str(package),
        "files": len(files),
        "defined_groups": sorted(defined_groups),
        "actor_slot": actor_slot,
        "hard_reads": hard_reads,
        "errors": errors,
    }


def audit(root: Path = ROOT) -> dict:
    # 包 = 一个机型的训练源码根（assets/robots/<机型>/training/source）。
    # 归组必须按机型：把不同机型混在一起会**互相污染**（一个机型的 runner 配上另一个机型的组名 ⇒ 漏报）。
    packages = sorted(
        [path for path in root.glob("assets/robots/*/training/source") if path.is_dir()],
        key=lambda item: str(item),
    )
    reports = [audit_package(package) for package in packages]
    errors = [error for report in reports for error in report["errors"]]
    return {
        "ok": not errors,
        "packages": [report["package"] for report in reports],
        "reports": reports,
        "errors": errors,
        # 如实声明边界
        "runs_mjlab": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="B37 观测组名/mjlab API 残留门禁")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = audit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    print("=" * 78)
    print(f"B37 观测组名/API 残留排雷（按包语义判定，{len(report['packages'])} 个机型的内嵌训练源码）")
    print("=" * 78)
    for item in report["reports"]:
        slot = item["actor_slot"]
        mapping = f"actor→{slot}" if slot else "无 obs_groups 映射（用默认 actor→('actor',)）"
        status = "✗" if item["errors"] else "✓"
        print(f"{status} {item['package']:<22} 组={item['defined_groups']} {mapping}")
    if report["errors"]:
        print("-" * 78)
        for error in report["errors"]:
            print(f"✗ [{error['kind']}] {error['package']} @ {error['file']}:{error['line']}")
            print(f"    {error.get('reason', error.get('symbol'))}")
            print(f"    → {error['hint']}")
    print("-" * 78)
    print("注意：**静态扫描，不运行 mjlab** —— 绿 = 没有断裂配置，不等于这些任务能跑起来。")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
