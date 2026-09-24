"""逐档案的**上游参考对照 + 移植核对**登记与门禁。

回答的问题："每一条训练档案是从哪来的？移植有没有逻辑问题？"
`registry/porting_references.json` 逐 `profile_id` 登记三样东西：

1. **参考出处**（`references[]`）：00_resources 里的仓库 + 路径 + 它扮演什么角色；
   库外/仅快照的来源必须显式标 `outside_library: true` 并写理由（不许含糊）。
2. **核对方式与结论**（`verification`）：`method`（字段对照 / 真跑 / 逐行复核 / 无法核对）、
   `conclusion` ∈ {`aligned` 对齐, `intentional` 有意偏离（须给理由）, `suspect` 疑点, `unverifiable` 无法核对}。
3. **缺口**（`gaps[]`）：疑点/偏离逐条写清位置、影响与"下一步怎么查"。

门禁判据（fail-closed）：
* 每个内置档案（`assets/robots/*/training/profiles/*.json`）都必须登记；出现未登记档案即红；
* 登记的 `profile_id` 必须真实存在（幽灵行即红）；
* `references[].repo` 必须真的在 `00_resources/` 下（或显式 `outside_library`）；
* `conclusion` 必须是枚举值；`intentional` 必须写理由；`suspect` 必须带 gap 条目；
* 每条 entry 必须写 `checked_at`。

用法：
    PYTHONUTF8=1 .venv/Scripts/python.exe tools/audit_porting_references.py          # 核对（进 CI）
    PYTHONUTF8=1 .venv/Scripts/python.exe tools/audit_porting_references.py --list   # 打印对照表
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "registry" / "porting_references.json"
RESOURCES = ROOT / "00_resources"
CONCLUSIONS = {"aligned", "intentional", "suspect", "unverifiable"}


def _load(path: Path) -> dict:
    """读登记表；**缺失**返回空表（由判据报"缺登记"，不是抛 FileNotFoundError）。"""
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def declared_profiles() -> dict[str, str]:
    """内置档案的真值：`{profile_id: robot_id}`（从逐包 profile 文件扫出来，不另立清单）。"""

    out: dict[str, str] = {}
    for path in sorted(glob.glob(str(ROOT / "assets" / "robots" / "*" / "training" / "profiles" / "*.json"))):
        data = _load(Path(path))
        profile_id = str(data.get("profile_id") or "")
        robot = Path(path).parts[-4]
        if profile_id:
            out[profile_id] = robot
    return out


def check(registry: dict | None = None) -> tuple[list[dict], list[str]]:
    payload = registry if registry is not None else _load(REGISTRY)
    entries = list(payload.get("entries") or [])
    problems: list[str] = []
    if not REGISTRY.is_file() and registry is None:
        problems.append(f"登记表缺失：{REGISTRY.relative_to(ROOT)}（先按 tools 说明逐档案登记）")
    known = declared_profiles()
    seen: set[str] = set()
    for entry in entries:
        profile_id = str(entry.get("profile_id") or "")
        if profile_id not in known:
            problems.append(f"{profile_id or '(缺 profile_id)'}: 登记的档案不存在（幽灵行）")
        elif profile_id in seen:
            problems.append(f"{profile_id}: 重复登记")
        seen.add(profile_id)
        if not entry.get("checked_at"):
            problems.append(f"{profile_id}: 缺 checked_at")
        verification = entry.get("verification") or {}
        conclusion = str(verification.get("conclusion") or "")
        if conclusion not in CONCLUSIONS:
            problems.append(f"{profile_id}: conclusion {conclusion!r} 不在 {sorted(CONCLUSIONS)}")
        if conclusion == "intentional" and not verification.get("why"):
            problems.append(f"{profile_id}: 有意偏离必须写 why")
        if conclusion == "suspect" and not (entry.get("gaps") or []):
            problems.append(f"{profile_id}: 疑点必须带 gaps（写清位置/影响/怎么查）")
        for reference in entry.get("references") or []:
            repo = str(reference.get("repo") or "")
            if not repo:
                problems.append(f"{profile_id}: reference 缺 repo")
            elif not reference.get("outside_library") and not (RESOURCES / repo).exists():
                problems.append(f"{profile_id}: 参考仓 {repo!r} 不在 00_resources/ 下（库外须显式标 outside_library）")
    missing = sorted(set(known) - seen)
    if missing:
        problems.append(f"未登记的内置档案 {len(missing)} 条：{missing[:8]}{' …' if len(missing) > 8 else ''}")
    return entries, problems


def main() -> int:
    parser = argparse.ArgumentParser(description="逐档案上游参考对照与移植核对门禁")
    parser.add_argument("--list", action="store_true", help="打印对照表")
    args = parser.parse_args()

    entries, problems = check()
    if args.list:
        print(f"[porting] 对照表：{len(entries)} 条")
        for entry in entries:
            refs = "；".join(f"{r.get('repo')}:{r.get('path', '')}" for r in entry.get("references") or []) or "—"
            verification = entry.get("verification") or {}
            print(f"  {entry.get('robot', ''):22s} {entry.get('profile_id', ''):22s} "
                  f"[{verification.get('conclusion', '?'):12s}] {refs}")
            for gap in entry.get("gaps") or []:
                print(f"      · gap: {str(gap)[:150]}")
    if problems:
        print(f"\n[porting] 判红 {len(problems)} 处：")
        for item in problems:
            print(f"  ✗ {item}")
        return 1
    print(f"\n[porting] 全部通过：{len(entries)} 条档案已登记参考与核对结论")
    return 0


if __name__ == "__main__":
    sys.exit(main())
