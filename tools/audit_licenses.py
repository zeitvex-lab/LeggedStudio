#!/usr/bin/env python3
"""I5 许可与出处取证 + 许可门（缺许可的内置包不得进索引）。

## 为什么要有它

`contracts/schema/robot-package-1.1.schema.json` 早就声明了 `license`（`{spdx, source,
redistribution}`，注释写着"T6.3 许可门消费"），但**14 个内置包一份都没填** —— 字段声明了
却没有任何数据，也没有任何东西会因此报错。I5 的验收是"许可与出处字段随资源"+"缺许可的包
不得进内置索引"，所以先要解决**能不能取证**，再解决**怎么守**。

## 取证规则（可复核，不是猜）

出处来自 `registry/porting_evidence.json`（每台机器人的上游证据文件清单）。对**每一条**
证据文件，从它所在目录**逐级向上**找到第一个 `LICENSE*` / `COPYING*`（`00_resources/`
内），该文件即这条证据的许可依据。这样一个上游仓库里"主仓 Apache-2.0 + 子目录另有许可"
的情况不会被拍平成一个值。

SPDX 识别**保守**：只在文本**无歧义**时给 id；认不出就 `spdx: null` 并把首行原文记进
`name`（**不猜**——猜错的许可证比"不知道"危险得多）。许可证文件本身的 sha256 一并登记，
所以"许可依据被换掉"也能被检出。

## 用法

    python tools/audit_licenses.py            # 对账：registry/licenses.json vs 实测证据
    python tools/audit_licenses.py --json     # 机器可读
    python tools/audit_licenses.py --apply    # 显式动作：按实测重写 registry/licenses.json
    python tools/audit_licenses.py --sample 6 # 打印前 N 个许可文件的识别结果（人工复核用）

退出码：0 对账通过；1 有缺口/不一致（可进 CI）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESOURCES_ROOT = PROJECT_ROOT / "00_resources"
EVIDENCE_PATH = PROJECT_ROOT / "registry" / "porting_evidence.json"
REGISTRY_PATH = PROJECT_ROOT / "registry" / "licenses.json"
SCHEMA_VERSION = "license-registry-1.0"

#: 许可文件名（大小写/后缀宽容：LICENSE、LICENCE、LICENSE.md、COPYING、COPYING.txt…）
_LICENSE_NAME = re.compile(r"^(licen[cs]e|copying)(\.(md|txt|rst|html))?$", re.IGNORECASE)

#: 自产打包许可的出处（我们自己的代码与打包，不是上游资产）。
PACKAGING_LICENSE = {"spdx": "MIT", "source": "package.json#license"}

#: **已登记**的取证缺口（2026-09-16 实测）。登记 ≠ 放行：报告里照样列出来，只是不再判红，
#: 这样"缺口"是可枚举、可追溯的一小串，而不是一片静默。**新增**缺口一律判红。
#: 后续动作（属 I5 收尾，需人/上游动作，不在代码里猜）：
#:   * zex-w ← rc_old：`rc_old/RC_WheelLeg` 树内没有该来源的许可文件（仅 vendored mjlab
#:     与 odin 驱动各有自己的 LICENSE，不属于 `rc_mjlab/src/robot`）；需向上游取许可或明确口径；
#:   * microduck ← microduck_all：同快照里其它子仓有 LICENSE，但证据文件所在子目录没有；
#:   * unitree_go2 ← parkour_mjlab：该快照整棵树没有许可文件；
#:   * unitree_g1 ← AMP_mjlab：许可放在 `rsl_rl/licenses/` 目录里（线索），不在证据文件祖先链上。
EXPECTED_UNRESOLVED: frozenset[tuple[str, str]] = frozenset({
    ("zex-w", "rc_old"),
    ("microduck", "microduck_all"),
    ("unitree_go2", "parkour_mjlab"),
    ("unitree_g1", "AMP_mjlab"),
})

#: **一条许可依据都取不到**的包（须显式登记，否则判红）。理由见上：zex-w 的上游快照里
#: 没有可主张的许可文件 —— 记录"未取证"是真话，给它安一个许可则是假话。
EXPECTED_ZERO_LICENSE: frozenset[str] = frozenset({"zex-w"})


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def identify_spdx(text: str) -> tuple[str | None, str]:
    """从许可文本识别 SPDX id（保守）；返回 ``(spdx_or_None, 人类可读名)``。

    判据顺序是刻意的：**先具体后一般**（LGPL 里也含 "GNU GENERAL PUBLIC LICENSE" 字样、
    CC-BY-NC 里也含 "Creative Commons"），否则会系统性识别错一类。
    """

    head = "\n".join(line.strip() for line in text.splitlines()[:40] if line.strip())
    lowered = head.lower()
    first_line = next((line for line in head.splitlines() if line), "")[:120]

    def has(*needles: str) -> bool:
        return all(needle in lowered for needle in needles)

    # CC 的正文样式不统一：有的文件把 "Creative Commons" 写在后面（例：UFO/LICENSE 首行
    # 只有 "Attribution-NonCommercial 4.0 International"），所以两种写法都要认。
    if has("attribution-noncommercial 4.0 international"):
        return "CC-BY-NC-4.0", "Creative Commons Attribution-NonCommercial 4.0"
    if has("attribution 4.0 international"):
        return "CC-BY-4.0", "Creative Commons Attribution 4.0"
    if has("gnu lesser general public license") and has("version 3"):
        return "LGPL-3.0-only", "GNU Lesser General Public License v3"
    if has("gnu lesser general public license") and has("version 2.1"):
        return "LGPL-2.1-only", "GNU Lesser General Public License v2.1"
    if has("gnu general public license") and has("version 3"):
        return "GPL-3.0-only", "GNU General Public License v3"
    if has("gnu general public license") and has("version 2"):
        return "GPL-2.0-only", "GNU General Public License v2"
    if has("apache license") and has("version 2.0"):
        return "Apache-2.0", "Apache License 2.0"
    if has("mozilla public license") and has("2.0"):
        return "MPL-2.0", "Mozilla Public License 2.0"
    if has("mit license") or has("permission is hereby granted, free of charge"):
        return "MIT", "MIT License"
    if has("redistribution and use in source and binary forms") and has("neither the name"):
        return "BSD-3-Clause", "BSD 3-Clause License"
    if has("redistribution and use in source and binary forms"):
        return "BSD-2-Clause", "BSD 2-Clause License"
    if has("isc license") or ("permission to use, copy, modify" in lowered and "and/or distribute this software" in lowered):
        return "ISC", "ISC License"
    return None, first_line or "(空文件)"


def nearest_license(relative_path: str) -> Path | None:
    """**祖先链**规则：从证据文件所在目录逐级向上找第一个许可文件。

    这条规则给出的许可**可以主张**（覆盖该目录下的内容），所以只有它算"许可依据"。
    """

    parts = Path(relative_path).parts
    for depth in range(len(parts), 0, -1):
        directory = RESOURCES_ROOT.joinpath(*parts[:depth])
        if not directory.is_dir():
            continue
        for candidate in sorted(directory.iterdir()):
            if candidate.is_file() and _LICENSE_NAME.match(candidate.name):
                return candidate
    return None


#: 同项目子树里找"许可线索"的深度上限（够覆盖 `X/rsl_rl/licenses/` 这类一层包装）。
_LEAD_MAX_DEPTH = 4
_LEAD_LIMIT = 5


def nearby_license_leads(relative_path: str) -> list[str]:
    """**线索**规则：祖先链上没有许可文件时，在同一顶层项目子树里找许可文件/``licenses`` 目录。

    刻意**只登记为线索、不做主张**：子树里的许可很可能属于**随包 vendor 进来的依赖**
    （例：`rc_mjlab/mjlab/LICENSE` 是 vendored mjlab 的 Apache-2.0，不是 `rc_mjlab/src/robot`
    那份代码的许可）。把依赖的许可挂到主代码头上，比"不知道"错得更远。
    """

    parts = Path(relative_path).parts
    if not parts:
        return []
    project = RESOURCES_ROOT / parts[0]
    if not project.is_dir():
        return []
    leads: list[str] = []
    for candidate in sorted(project.rglob("*")):
        depth = len(candidate.relative_to(project).parts)
        if depth > _LEAD_MAX_DEPTH:
            continue
        if candidate.is_dir() and candidate.name.lower() in ("licenses", "license", "licences"):
            leads.append(candidate.relative_to(PROJECT_ROOT).as_posix())
        elif candidate.is_file() and _LICENSE_NAME.match(candidate.name):
            leads.append(candidate.relative_to(PROJECT_ROOT).as_posix())
        if len(leads) >= _LEAD_LIMIT:
            break
    return leads


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    except OSError:
        return None


def evidence_files_per_robot() -> dict[str, list[str]]:
    """``{robot_id: [上游证据文件相对路径, ...]}``（出处清单缺失时返回空）。"""

    evidence = _read_json(EVIDENCE_PATH) or {}
    robots = evidence.get("robots") or evidence
    result: dict[str, list[str]] = {}
    for robot, value in (robots.items() if isinstance(robots, dict) else []):
        files = value.get("files") if isinstance(value, dict) else value
        result[str(robot)] = [str(item) for item in (files or [])]
    return result


def derive() -> dict[str, dict[str, Any]]:
    """按取证规则派生每台机器人的许可记录（**纯派生，不读 registry**）。"""

    packages: dict[str, dict[str, Any]] = {}
    for robot, files in sorted(evidence_files_per_robot().items()):
        components: dict[str, dict[str, Any]] = {}
        unresolved: dict[str, dict[str, Any]] = {}
        for relative in files:
            license_path = nearest_license(relative)
            if license_path is None:
                project = str(Path(relative).parts[0])
                gap = unresolved.get(project)
                if gap is None:
                    gap = unresolved[project] = {
                        "upstream": project,
                        "reason": "祖先链上没有许可文件（LICENSE/COPYING）——该来源的许可未取证",
                        "evidence_files": 0,
                        "leads": nearby_license_leads(relative),
                    }
                gap["evidence_files"] += 1
                continue
            key = license_path.relative_to(PROJECT_ROOT).as_posix()
            entry = components.get(key)
            if entry is None:
                text = license_path.read_text(encoding="utf-8", errors="replace")
                spdx, name = identify_spdx(text)
                entry = components[key] = {
                    "root": license_path.parent.relative_to(PROJECT_ROOT).as_posix(),
                    "path": key,
                    "sha256": _sha256(license_path),
                    "spdx": spdx,
                    "name": name,
                    "evidence_files": 0,
                }
            entry["evidence_files"] += 1
        packages[robot] = {
            "packaging": dict(PACKAGING_LICENSE),
            "components": [components[key] for key in sorted(components)],
            "unresolved": [unresolved[key] for key in sorted(unresolved)],
        }
    return packages


def audit() -> dict[str, Any]:
    """对账：``registry/licenses.json`` 的声明 vs 实测派生。"""

    derived = derive()
    recorded = _read_json(REGISTRY_PATH)
    problems: list[str] = []
    if not isinstance(recorded, dict):
        problems.append(f"缺 {REGISTRY_PATH.relative_to(PROJECT_ROOT).as_posix()}（先跑 --apply 生成）")
        return {"ok": False, "packages": len(derived), "components": 0, "problems": problems}

    declared = recorded.get("packages")
    if not isinstance(declared, dict):
        problems.append("licenses.json 缺 packages 段")
        return {"ok": False, "packages": len(derived), "components": 0, "problems": problems}

    for robot, expected in sorted(derived.items()):
        actual = declared.get(robot)
        if not isinstance(actual, dict):
            problems.append(f"{robot}: 注册表里没有许可记录（缺许可的内置包不得进索引）")
            continue
        actual_components = {
            str(item.get("path")): item for item in (actual.get("components") or []) if isinstance(item, dict)
        }
        for entry in expected["components"]:
            found = actual_components.get(entry["path"])
            if found is None:
                problems.append(f"{robot}: 注册表缺许可依据 {entry['path']}（上游 {entry['root']}）")
                continue
            for field in ("sha256", "spdx", "name", "root"):
                if found.get(field) != entry[field]:
                    problems.append(
                        f"{robot}: {entry['path']} 的 {field} 与实测不符"
                        f"（注册表 {found.get(field)!r} vs 实测 {entry[field]!r}）"
                    )
        for path in sorted(set(actual_components) - {entry["path"] for entry in expected["components"]}):
            problems.append(f"{robot}: 注册表里的 {path} 已不再是任何证据的许可依据（上游变了？）")
        recorded_gaps = {
            str(item.get("upstream")): item for item in (actual.get("unresolved") or []) if isinstance(item, dict)
        }
        for gap in expected["unresolved"]:
            registered = recorded_gaps.get(gap["upstream"])
            if registered is None:
                problems.append(
                    f"{robot}: 上游 {gap['upstream']} 的许可没取到证据，且注册表里没如实登记"
                    f"（{gap['evidence_files']} 条证据受影响）"
                )
                continue
            if registered.get("evidence_files") != gap["evidence_files"]:
                problems.append(
                    f"{robot}: 上游 {gap['upstream']} 的取证缺口条数变了"
                    f"（注册表 {registered.get('evidence_files')} vs 实测 {gap['evidence_files']}）——两侧一起改"
                )
            if list(registered.get("leads") or []) != list(gap["leads"]):
                problems.append(f"{robot}: 上游 {gap['upstream']} 的许可线索变了（注册表与实测不一致）")
            if (robot, gap["upstream"]) not in EXPECTED_UNRESOLVED:
                problems.append(
                    f"{robot}: 上游 {gap['upstream']} 出现了**未登记**的取证缺口 —— "
                    "新缺口必须显式登记（并说明后续动作），否则它会静默留在索引里"
                )
        for upstream in sorted(set(recorded_gaps) - {gap["upstream"] for gap in expected["unresolved"]}):
            problems.append(f"{robot}: 注册表登记的缺口 {upstream} 已不再成立（上游补了许可？）——请重新 --apply")

        if not expected["components"]:
            if robot not in EXPECTED_ZERO_LICENSE:
                problems.append(
                    f"{robot}: 一条许可依据都取不到，且不在已登记清单里"
                    "（缺许可的内置包不得进索引；确无上游许可时须显式登记）"
                )

    extra = sorted(set(declared) - set(derived))
    if extra:
        problems.append(f"注册表里有派生不出的包：{', '.join(extra)}")
    if recorded.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version 应为 {SCHEMA_VERSION!r}，得到 {recorded.get('schema_version')!r}")

    components = sum(len(item["components"]) for item in derived.values())
    unknown = [
        f"{robot}/{entry['path']}"
        for robot, item in sorted(derived.items())
        for entry in item["components"] if entry["spdx"] is None
    ]
    return {
        "ok": not problems,
        "packages": len(derived),
        "components": components,
        "unresolved_packages": sorted(r for r, item in derived.items() if item["unresolved"]),
        "unidentified": unknown,
        "problems": problems,
    }


def apply_registry() -> dict[str, Any]:
    """按实测重写 ``registry/licenses.json``（**显式动作**：只有 --apply 才写）。"""

    packages = derive()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "tools/audit_licenses.py --apply",
        "rules": {
            "source": "出处取自 registry/porting_evidence.json（每台机器人的上游证据文件清单）",
            "license_lookup": "对每条证据文件，从其所在目录逐级向上取第一个 LICENSE*/COPYING*",
            "spdx": "只在文本无歧义时给 id，否则 null（不猜）",
            "packaging": "packaging 段是**我们自己的**打包许可（MIT，见 package.json），非上游资产许可",
        },
        "packages": packages,
    }
    REGISTRY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="I5 许可与出处取证 + 许可门")
    parser.add_argument("--apply", action="store_true", help="按实测重写 registry/licenses.json（显式动作）")
    parser.add_argument("--json", action="store_true", help="机器可读输出")
    parser.add_argument("--sample", type=int, default=0, help="打印前 N 个许可文件的识别结果供人工复核")
    args = parser.parse_args(argv)

    if args.apply:
        payload = apply_registry()
        print(f"已写入 {REGISTRY_PATH.relative_to(PROJECT_ROOT).as_posix()}："
              f"{len(payload['packages'])} 个包 / "
              f"{sum(len(item['components']) for item in payload['packages'].values())} 条许可依据")

    report = audit()

    if args.sample:
        shown = 0
        for robot, item in sorted(derive().items()):
            for entry in item["components"]:
                print(f"  [{robot}] {entry['path']} → spdx={entry['spdx']} ({entry['name']}) "
                      f"证据 {entry['evidence_files']} 条")
                shown += 1
                if shown >= args.sample:
                    break
            if shown >= args.sample:
                break

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    print("=" * 78)
    print("I5 许可与出处对账")
    print("=" * 78)
    print(f"{'机型':<22}{'许可依据':>9}{'未识别':>8}{'取证缺口':>10}")
    print("-" * 78)
    derived = derive()
    for robot, item in sorted(derived.items()):
        unidentified = sum(1 for entry in item["components"] if entry["spdx"] is None)
        print(f"{robot:<22}{len(item['components']):>9}{unidentified:>8}{len(item['unresolved']):>10}")
    print("-" * 78)
    counts = Counter(
        entry["spdx"] or "(未识别)"
        for item in derived.values() for entry in item["components"]
    )
    print("许可分布：" + "，".join(f"{name}×{count}" for name, count in sorted(counts.items(), key=lambda kv: -kv[1])))
    if report["unresolved_packages"]:
        print(f"取证缺口（如实登记，不阻断）：{', '.join(report['unresolved_packages'])}")
    if report["problems"]:
        print(f"\n✗ 不达标 {len(report['problems'])} 项：")
        for item in report["problems"]:
            print(f"  - {item}")
        return 1
    print("\n全部内置包都有许可记录，且与实测证据逐项一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
