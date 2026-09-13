#!/usr/bin/env python3
"""doc_reality_check.py — 文档里的数字 vs 仓库实测（B17）。

**为什么需要**：README / `docs/` / `00_know/` 里的「版本号、机器人包数、策略条数、
资源库项目数」都是人手写的，代码一变就会漂移，而且漂移时没有任何东西会报错。
历史上真实发生过：`README.md` 停在 `0.45.0`（三处源文件已到 `0.52.0`）、架构图写
「15 机器人包」（实际 14）、策略数停在「47 条」（声明已增至 48）。

本脚本把**实测真值**与**文档里出现的数字**逐条对账，不一致即非零退出，可直接进 CI。

口径约定（避免再次口径分歧）：
  * 机器人包数   = `assets/robots/` 下的目录数
  * 策略声明数   = 各包 `simulation/config.json` 的 `policies + demo_policies`
  * 可执行策略数 = `tools/baselines/sim2sim_headless_baseline.json` 的条目数
    （= 包内自带 onnx 的策略；`web/sim2sim/models/` 承载的客户端策略与
    TRON1 的 encoder 配套文件不计入）
  * 资源库项目数 = `00_resources/_index.json` 的 `projects` 条目数（由同步工具生成）

用法：
    python tools/doc_reality_check.py            # 人类可读报告
    python tools/doc_reality_check.py --json     # 机器可读
    python tools/doc_reality_check.py -q         # 只打印不一致项
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# 实测真值
# ---------------------------------------------------------------------------
def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def collect_facts() -> dict:
    facts: dict[str, object] = {}

    # --- 版本（三处源文件必须一致） ---
    version_file = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package = _read_json(ROOT / "package.json") or {}
    m = re.search(r'^\s*version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    facts["version"] = version_file
    facts["version_sources"] = {
        "VERSION": version_file,
        "pyproject.toml": m.group(1) if m else "?",
        "package.json": str(package.get("version") or "?"),
    }

    # --- 机器人包与资产 ---
    robots_dir = ROOT / "assets" / "robots"
    robot_ids = sorted(p.name for p in robots_dir.iterdir() if p.is_dir()) if robots_dir.is_dir() else []
    facts["robot_packages"] = len(robot_ids)

    onnx_files = [p for p in robots_dir.rglob("*.onnx")] if robots_dir.is_dir() else []
    facts["onnx_files"] = len(onnx_files)

    declared = 0
    for cfg in sorted(robots_dir.glob("*/simulation/config.json")):
        data = _read_json(cfg) or {}
        declared += len(data.get("policies") or []) + len(data.get("demo_policies") or [])
    facts["policy_declarations"] = declared

    baseline = _read_json(ROOT / "tools" / "baselines" / "sim2sim_headless_baseline.json") or {}
    facts["executable_policies"] = len(baseline.get("results") or [])

    index = _read_json(ROOT / "pretrained_models" / "index.json")
    entries = index if isinstance(index, list) else (index or {}).get("entries") or []
    facts["pretrained_index"] = len(entries)
    facts["pretrained_index_robots"] = len({str(e.get("robot")) for e in entries if e.get("robot")})

    total_bytes = sum(p.stat().st_size for p in robots_dir.rglob("*") if p.is_file()) if robots_dir.is_dir() else 0
    facts["assets_robots_mb"] = round(total_bytes / 1024 / 1024, 1)

    # --- 契约 / Pack / 注册表 ---
    facts["packs"] = len(list((ROOT / "packs").glob("*.pack.json")))
    facts["schemas"] = len(list((ROOT / "contracts" / "schema").glob("*.json")))

    # --- 参考资源库（以生成的索引为准） ---
    res_index = _read_json(ROOT / "00_resources" / "_index.json") or {}
    facts["resources_projects"] = len(res_index.get("projects") or {})

    # --- 测试模块（CI 覆盖口径的基数） ---
    facts["backend_test_modules"] = len(list((ROOT / "backend").glob("test_*.py")))

    return facts


# ---------------------------------------------------------------------------
# 文档对账规则：(文件, 正则, 事实键, 说明)
# 正则第 1 个捕获组必须是数字/版本串。
# ---------------------------------------------------------------------------
CHECKS: list[tuple[str, str, str, str]] = [
    ("README.md", r"^- 版本：`([^`]+)`", "version", "README 版本号"),
    ("README.md", r"内置\s*(\d+)\s*个标准化机器人包", "robot_packages", "README「内置 N 个标准化机器人包」"),
    ("README.md", r"^\│ .*?\│  \│ (\d+) 机器人包", "robot_packages", "README 架构图「N 机器人包」"),
    ("README.md", r"assets/robots/\s*#\s*(\d+)\s*个标准化机器人包", "robot_packages", "README 目录树「assets/robots N 个」"),
    ("README.md", r"当前\s*(\d+)\s*条可执行", "executable_policies", "README 无头 sim2sim 验收条数"),
    ("docs/cloud-dev.md", r"当前\s*(\d+)\s*条可执行", "executable_policies", "cloud-dev 门禁条数"),
    ("00_know/README.md", r"更多参考项目（(\d+)\s*个）", "resources_projects", "00_know README 参考项目数"),
]


def run_checks(facts: dict) -> list[dict]:
    problems: list[dict] = []
    for rel_path, pattern, key, label in CHECKS:
        path = ROOT / rel_path
        if not path.is_file():
            problems.append({"file": rel_path, "label": label, "doc": "<文件缺失>",
                             "actual": facts.get(key), "status": "missing_file"})
            continue
        text = path.read_text(encoding="utf-8")
        found = re.search(pattern, text, re.MULTILINE)
        if not found:
            problems.append({"file": rel_path, "label": label, "doc": "<未匹配到>",
                             "actual": facts.get(key), "status": "pattern_missing"})
            continue
        doc_value = found.group(1)
        expected = str(facts.get(key))
        if doc_value != expected:
            problems.append({"file": rel_path, "label": label, "doc": doc_value,
                             "actual": expected, "status": "mismatch"})
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="文档数字与仓库实测对账")
    ap.add_argument("--json", action="store_true", help="输出机器可读结果")
    ap.add_argument("-q", "--quiet", action="store_true", help="只打印不一致项")
    args = ap.parse_args()

    facts = collect_facts()
    problems = run_checks(facts)

    # 版本三源一致性（文档之外的自检：源文件之间自己不能漂）
    versions = set(facts["version_sources"].values())
    version_consistent = len(versions) == 1

    if args.json:
        print(json.dumps({"facts": facts, "problems": problems,
                          "version_consistent": version_consistent},
                         ensure_ascii=False, indent=2))
        return 0 if not problems and version_consistent else 1

    if not args.quiet:
        print("=" * 68)
        print("实测真值")
        print("-" * 68)
        print(f"  版本              {facts['version']}  (VERSION / pyproject / package.json: "
              f"{'一致' if version_consistent else '不一致 → ' + str(facts['version_sources'])})")
        print(f"  机器人包          {facts['robot_packages']}")
        print(f"  策略声明          {facts['policy_declarations']}")
        print(f"  可执行策略        {facts['executable_policies']}（无头门禁基线）")
        print(f"  包内 onnx 文件    {facts['onnx_files']}")
        print(f"  预训练索引        {facts['pretrained_index']} 条 / {facts['pretrained_index_robots']} 机型")
        print(f"  assets/robots     {facts['assets_robots_mb']} MB")
        print(f"  packs / schemas   {facts['packs']} / {facts['schemas']}")
        print(f"  资源库项目        {facts['resources_projects']}")
        print(f"  backend 测试模块  {facts['backend_test_modules']}")
        print("=" * 68)
        print("文档对账")
        print("-" * 68)
        for rel_path, _pattern, key, label in CHECKS:
            mark = "OK  " if not any(p["file"] == rel_path and p["label"] == label for p in problems) else "FAIL"
            print(f"  [{mark}] {label:<44} 期望 {facts.get(key)}")

    if not version_consistent:
        print("✗ 版本号三处源文件不一致：", facts["version_sources"])
    if problems:
        print("-" * 68)
        print(f"✗ 文档漂移 {len(problems)} 处：")
        for p in problems:
            print(f"  - {p['file']}｜{p['label']}：文档写 {p['doc']!r}，实测 {p['actual']!r}（{p['status']}）")
        return 1
    if not args.quiet:
        print("-" * 68)
        print("✓ 全部一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
