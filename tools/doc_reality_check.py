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


def _openapi_paths():
    """控制面 OpenAPI 路径数（B15）。缺依赖导致导入失败时返回 None，对账跳过该项。"""
    try:
        sys.path.insert(0, str(ROOT))
        from backend.api_complete import app  # noqa: F401
        return len(app.openapi().get("paths") or {})
    except Exception:
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
    plain_policies = 0
    demo_policies = 0
    for cfg in sorted(robots_dir.glob("*/simulation/config.json")):
        data = _read_json(cfg) or {}
        n_plain = len(data.get("policies") or [])
        n_demo = len(data.get("demo_policies") or [])
        plain_policies += n_plain
        demo_policies += n_demo
        declared += n_plain + n_demo
    facts["policy_declarations"] = declared
    facts["policies"] = plain_policies
    facts["demo_policies"] = demo_policies
    facts["profiles_json"] = len(list(robots_dir.glob("*/training/profiles/*.json")))
    def _repo_files(root: Path) -> list[Path]:
        """`assets/` 下**属于仓库的**文件 = 已跟踪 + 未跟踪但未被 `.gitignore` 忽略。

        为什么不能直接 `rglob("*")`：跑过测试后包内会留下 `__pycache__/*.pyc`（V8/N7 明令
        不入库），于是**同一条命令在跑过测试的机器上必然报漂移**，而文档里的数字其实是
        "入库资产"的口径 —— 两个口径不同，门禁却在追一个并不存在的差异。没有 git 时
        （例如解包后的发行物）退回纯文件系统枚举。
        """
        import subprocess

        try:
            completed = subprocess.run(
                ["git", "-C", str(ROOT), "ls-files", "--cached", "--others",
                 "--exclude-standard", "--", str(root.relative_to(ROOT))],
                capture_output=True, text=True, encoding="utf-8", check=True, timeout=120,
            )
        except Exception:
            return [p for p in root.rglob("*") if p.is_file()]
        return [ROOT / line.strip() for line in completed.stdout.splitlines() if line.strip()]

    facts["robot_files"] = len(_repo_files(robots_dir))

    baseline = _read_json(ROOT / "tools" / "baselines" / "sim2sim_headless_baseline.json") or {}
    facts["executable_policies"] = len(baseline.get("results") or [])

    index = _read_json(ROOT / "pretrained_models" / "index.json")
    entries = index if isinstance(index, list) else (index or {}).get("entries") or []
    facts["pretrained_index"] = len(entries)
    facts["pretrained_index_robots"] = len({str(e.get("robot")) for e in entries if e.get("robot")})

    # 体积口径：**CRLF → LF 归一后再计字节**（与 pack_catalog._content_sha256、
    # tools/generate_packs.py 同一口径，见 B39）。原实现直接加 `st_size`，于是**同一份
    # 已提交资产在两台机器上是两个数**：Windows 检出 CRLF 实测 427.3 MB、Linux/CI 检出
    # LF 实测 424.7 MB（差额 2.67 MB == assets/robots 下文本文件的行数，可精确对上）——
    # 文档里的数字只能对一台机器成立，CI（Ubuntu）恒红。资产体积不该随检出平台变化。
    total_bytes = 0
    if robots_dir.is_dir():
        for path in _repo_files(robots_dir):
            try:
                total_bytes += len(path.read_bytes().replace(b"\r\n", b"\n"))
            except OSError:
                continue
    facts["assets_robots_mb"] = round(total_bytes / 1024 / 1024, 1)

    # --- 契约 / Pack / 注册表 ---
    facts["packs"] = len(list((ROOT / "packs").glob("*.pack.json")))
    facts["schemas"] = len(list((ROOT / "contracts" / "schema").glob("*.json")))

    # --- 参考资源库（以生成的索引为准） ---
    res_index = _read_json(ROOT / "00_resources" / "_index.json") or {}
    facts["resources_projects"] = len(res_index.get("projects") or {})

    # --- 后端规模 / 测试口径（B16/B17 门禁基数；均为静态可数） ---
    backend_dir = ROOT / "backend"
    facts["backend_test_modules"] = len(list(backend_dir.glob("test_*.py")))
    facts["backend_py_files"] = len(list(backend_dir.rglob("*.py")))
    facts["backend_test_count"] = sum(
        len(re.findall(r"^\s*def test_",
                       p.read_text(encoding="utf-8", errors="ignore"), re.MULTILINE))
        for p in backend_dir.glob("test_*.py")
    )
    facts["routers_files"] = sum(
        1 for p in backend_dir.rglob("*.py")
        if "APIRouter(" in p.read_text(encoding="utf-8", errors="ignore")
    )
    facts["openapi_paths"] = _openapi_paths()

    return facts


# ---------------------------------------------------------------------------
# 文档对账规则：(文件, 正则, [(捕获组序号, 事实键), ...], 说明)
# 一个正则可带多个捕获组，按序号与事实键一一对应（同一行里的多处数字一起守）。
# ---------------------------------------------------------------------------
CHECKS: list[tuple[str, str, list[tuple[int, str]], str]] = [
    ("README.md", r"^- 版本：`([^`]+)`", [(1, "version")], "README 版本号"),
    ("README.md", r"内置\s*(\d+)\s*个标准化机器人包", [(1, "robot_packages")], "README「内置 N 个标准化机器人包」"),
    ("README.md", r"^\│ .*?\│  \│ (\d+) 机器人包", [(1, "robot_packages")], "README 架构图「N 机器人包」"),
    ("README.md", r"assets/robots/\s*#\s*(\d+)\s*个标准化机器人包", [(1, "robot_packages")], "README 目录树「assets/robots N 个」"),
    ("README.md", r"当前\s*(\d+)\s*条可执行", [(1, "executable_policies")], "README 无头 sim2sim 验收条数"),
    ("docs/cloud-dev.md", r"当前\s*(\d+)\s*条可执行", [(1, "executable_policies")], "cloud-dev 门禁条数"),
    ("00_know/README.md", r"更多参考项目（(\d+)\s*个）", [(1, "resources_projects")], "00_know README 参考项目数"),
    # --- 任务清单「0. 现状锚点」（2026-09-13 起纳入：此前只守 README/索引，
    #     任务清单的锚点是"实测"声明却无人守，microduck 纠正后即漂移无人知） ---
    ("00_know/01_任务清单.md",
     r"robot_packages (\d+)\s+profiles_json (\d+)\s+sim_policies_onnx (\d+) 文件",
     [(1, "robot_packages"), (2, "profiles_json"), (3, "onnx_files")],
     "任务清单·包/profile/onnx"),
    ("00_know/01_任务清单.md",
     r"策略声明 (\d+) 条 = policies (\d+) \+ demo_policies (\d+)",
     [(1, "policy_declarations"), (2, "policies"), (3, "demo_policies")],
     "任务清单·策略声明拆分"),
    ("00_know/01_任务清单.md",
     r"pretrained_models/index\.json (\d+) 条 / 覆盖 (\d+) 机型",
     [(1, "pretrained_index"), (2, "pretrained_index_robots")],
     "任务清单·预训练索引"),
    ("00_know/01_任务清单.md",
     r"backend (\d+) py（含子目录）/ (\d+) 个 APIRouter",
     [(1, "backend_py_files"), (2, "routers_files")],
     "任务清单·后端规模/路由"),
    ("00_know/01_任务清单.md",
     r"app\.openapi\(\) 实测生成 (\d+) 条路径",
     [(1, "openapi_paths")],
     "任务清单·openapi 路径数"),
    ("00_know/01_任务清单.md",
     r"assets/robots: (\d+) 文件 / ([\d.]+) MB",
     [(1, "robot_files"), (2, "assets_robots_mb")],
     "任务清单·资产文件数/体积"),
    ("00_know/01_任务清单.md",
     r"测试基线：backend (\d+) 项",
     [(1, "backend_test_count")],
     "任务清单·backend 测试条数"),
    ("00_know/01_任务清单.md",
     r"backend (\d+) 个 test_\*\.py 全量 discover",
     [(1, "backend_test_modules")],
     "任务清单·测试模块数"),
]


def run_checks(facts: dict) -> list[dict]:
    problems: list[dict] = []
    for rel_path, pattern, groups, label in CHECKS:
        path = ROOT / rel_path
        if not path.is_file():
            problems.append({"file": rel_path, "label": label, "doc": "<文件缺失>",
                             "actual": None, "status": "missing_file"})
            continue
        text = path.read_text(encoding="utf-8")
        found = re.search(pattern, text, re.MULTILINE)
        if not found:
            problems.append({"file": rel_path, "label": label, "doc": "<未匹配到>",
                             "actual": None, "status": "pattern_missing"})
            continue
        for idx, key in groups:
            expected = facts.get(key)
            if expected is None:  # 事实取不到（如缺依赖）→ 跳过，不误报
                continue
            doc_value = found.group(idx)
            if doc_value != str(expected):
                problems.append({"file": rel_path, "label": f"{label}[{key}]", "doc": doc_value,
                                 "actual": str(expected), "status": "mismatch"})
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="文档数字与仓库实测对账")
    ap.add_argument("--json", action="store_true", help="输出机器可读结果")
    ap.add_argument("-q", "--quiet", action="store_true", help="只打印不一致项")
    args = ap.parse_args()

    facts = collect_facts()
    problems = run_checks(facts)

    # 清单头的**产品版本**也必须对齐实测：它此前不在锚点里，于是一路停在 0.54.1
    # 而没人发现（2026-09-15 手工对齐后补上这条）。版本是字符串，故不走 CHECKS 的
    # 数字组比较，在这里单列一条同性质的检查。
    try:
        header_text = (ROOT / "00_know" / "01_任务清单.md").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        header_text = ""
    header_match = re.search(r"产品版本\*\*：\*\*([0-9][0-9.]*)\*\*", header_text)
    doc_version = header_match.group(1) if header_match else "<未找到>"
    sources = facts.get("version_sources") if isinstance(facts.get("version_sources"), dict) else {}
    actual_version = str(sources.get("VERSION") or (list(sources.values())[0] if sources else ""))
    if actual_version and doc_version != actual_version:
        problems.append({"file": "00_know/01_任务清单.md", "label": "任务清单·产品版本",
                         "doc": doc_version, "actual": actual_version, "status": "mismatch"})

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
        print(f"  profiles_json     {facts['profiles_json']}")
        print(f"  policies + demo   {facts['policies']} + {facts['demo_policies']} = {facts['policy_declarations']}")
        print(f"  assets/robots     {facts['robot_files']} 文件 / {facts['assets_robots_mb']} MB")
        print(f"  packs / schemas   {facts['packs']} / {facts['schemas']}")
        print(f"  资源库项目        {facts['resources_projects']}")
        print(f"  backend py / 路由 {facts['backend_py_files']} / {facts['routers_files']}")
        print(f"  backend 测试      {facts['backend_test_count']} 项 / {facts['backend_test_modules']} 模块")
        print(f"  openapi 路径      {facts['openapi_paths']}")
        print("=" * 68)
        print("文档对账")
        print("-" * 68)
        for rel_path, _pattern, groups, label in CHECKS:
            failed = any(
                p["file"] == rel_path and (p["label"] == label or p["label"].startswith(label + "["))
                for p in problems
            )
            mark = "FAIL" if failed else "OK  "
            print(f"  [{mark}] {label:<44} 期望 {facts.get(groups[0][1])}")

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
