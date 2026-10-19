#!/usr/bin/env python3
"""Phase 4 验证器事件化（`00_know/06` §14.6 / §17）：门禁清单从 `registry/verify/index.json` 派生。

**要解决的问题**：审计/校验脚本此前**手列在 `.cnb.yml`** —— 清单本身会过期，新增脚本要记得加，
脚本被删了清单还留着（"有测试 ≠ 门禁在守"的同族病，B16 与前端套件清单都踩过）。Phase 4 把发现
方式改成**数据驱动**：每个 audit/validate/check 工具都在 `registry/verify/index.json` 里有一条家，
`--run` 派生出 `.cnb.yml` unit-tests 段要跑的步骤。**脚本本体不重写**。

**`env` 非空的条目**（需训练栈 / 训练产物 / 可选依赖：`training-venv` / `mjlab` / `artifact` /
`onnxruntime` / `manual`）**不进 unit-tests 段**，但仍是目录的一部分 —— 这样"覆盖率"才能守住
"没有游离的审计工具"，而不是靠豁免清单掩盖。

判据：

* `--check`：① schema/形状/`env` 词汇闭集；② 每条声明的 `tools/*.py` 真实存在；
  ③ **覆盖率 100%**（`tools/` 下每个 `^(audit|validate|check)_*.py` 都在目录里）；
  ④ **`.cnb.yml` 不再手列**审计/校验命令（且已挂 `--run`）。
* `--run`：跑 `env` 为空的门禁（`.cnb.yml` unit-tests 段就调这一行），任一非 0 ⇒ 退出 1。

用法::

    python tools/audit_plugin_verify.py --check     # 门禁（覆盖率 + 清单不手维护）
    python tools/audit_plugin_verify.py --list      # 打印派生出的清单（gates / env-gated）
    python tools/audit_plugin_verify.py --run       # 依次执行（CI unit-tests 段）
    python tools/audit_plugin_verify.py --json      # 机器可读
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # 自举仓库根：本工具要读**控制面**的目录访问层（`tools/` 不在 sys.path 上）。
    # 顺带去掉此前"靠环境隐式给 PYTHONPATH"的隐性依赖（给子进程的显式注入见 `_child_env`）。
    sys.path.insert(0, str(ROOT))
CNB_PATH = ROOT / ".cnb.yml"
TOOLS_DIR = ROOT / "tools"

#: 目录的读取与形状校验在**控制面**（`backend/verify_catalog.py`，Phase 8 公开）；
#: 这里同名再导出一次，既有消费方与测试的 `apv.<name>` 引用不必改。
from backend.verify_catalog import (  # noqa: E402
    CATALOG_PATH,
    CATALOG_SCHEMA,
    FROZEN_ENVS,
    FROZEN_SEAMS,
    catalog_problems,
    load_catalog,
    planned_commands,
    skipped_commands,
)

#: 覆盖率宇宙：`tools/` 下名字像"守门"的脚本。
UNIVERSE_RE = re.compile(r"^(audit|validate|check)_[\w]+\.py$")
#: `.cnb.yml` 里**不许再出现**的手列形态（本工具自己是运行器，除外）。
HANDLIST_RE = re.compile(r"^\s*python3?\s+tools/((?:audit|validate|check)_[\w]+\.py)", re.M)
RUNNER_TOKEN = "tools/audit_plugin_verify.py"
#: 本工具自身的文件名（是运行器，不是门禁；不进覆盖率宇宙）。
RUNNER_NAME = "audit_plugin_verify.py"


# ---------------------------------------------------------------------------
# 仓库级判据（纯函数，便于反例注入）
# ---------------------------------------------------------------------------
def declared_tools(catalog: dict[str, Any]) -> set[str]:
    """目录里出现过的 `tools/<name>.py` 基名集合。"""
    found: set[str] = set()
    for entry in catalog.get("gates") or []:
        command = str(entry.get("command") or "")
        for match in re.finditer(r"tools/([\w./-]+\.py)", command):
            found.add(Path(match.group(1)).name)
    return found


def universe_tools() -> set[str]:
    """覆盖率宇宙：`tools/` 下的守门脚本（**本工具自己是运行器，不算门禁**，剔除）。"""
    return {path.name for path in TOOLS_DIR.glob("*.py")
            if UNIVERSE_RE.match(path.name) and path.name != RUNNER_NAME}


def existing_problems(catalog: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for entry in catalog.get("gates") or []:
        command = str(entry.get("command") or "")
        for match in re.finditer(r"tools/([\w./-]+\.py)", command):
            if not (TOOLS_DIR / match.group(1)).is_file():
                problems.append(f"声明的工具不存在：tools/{match.group(1)}（命令：{command}）")
    return problems


def coverage_problems(catalog: dict[str, Any]) -> list[str]:
    """覆盖率 100%：tools/ 下每个守门脚本都必须在目录里有家。"""
    missing = universe_tools() - declared_tools(catalog)
    return [f"游离的守门工具（未登记进 {CATALOG_PATH.relative_to(ROOT)}）：tools/{name}"
            for name in sorted(missing)]


def cnb_problems(text: str) -> list[str]:
    """`.cnb.yml` 不许再手列审计/校验命令，且必须挂上 `--run`。"""
    problems: list[str] = []
    hand = [name for name in HANDLIST_RE.findall(text) if Path(name).name != RUNNER_NAME]
    if hand:
        problems.append(
            "`.cnb.yml` 仍在手列审计/校验命令（应改为 `python tools/audit_plugin_verify.py --run`）："
            + ", ".join(sorted(set(hand)))
        )
    if f"{RUNNER_TOKEN} --run" not in text:
        problems.append(f"`.cnb.yml` 未挂 `python {RUNNER_TOKEN} --run`")
    return problems


def check() -> list[str]:
    catalog = load_catalog()
    problems = catalog_problems(catalog) + existing_problems(catalog) + coverage_problems(catalog)
    if CNB_PATH.is_file():
        problems += cnb_problems(CNB_PATH.read_text(encoding="utf-8"))
    else:
        problems.append(f"缺 {CNB_PATH}")
    return problems


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------
def _child_env() -> dict[str, str]:
    """给子进程补 `PYTHONPATH=仓库根`——工具从 `tools/` 起跑时 `sys.path[0]` 是 tools/，
    只把它交给环境变量，才与"在仓库根跑 python tools/x.py"同语义（此前靠环境隐式给）。"""
    env = dict(os.environ)
    current = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + current if current else "")
    return env


def run_commands(commands: list[str]) -> tuple[int, list[tuple[str, int]]]:
    results: list[tuple[str, int]] = []
    failed = 0
    for command in commands:
        print(f"== {command} ==", flush=True)
        completed = subprocess.run(
            command, shell=True, cwd=ROOT, env=_child_env(),
            capture_output=True, text=True,
        )
        output = completed.stdout
        if completed.stderr:
            output += completed.stderr
        print(output, end="" if output.endswith("\n") else "\n", flush=True)
        results.append((command, completed.returncode))
        if completed.returncode != 0:
            failed += 1
            print(f"[gate!] 退出码 {completed.returncode}：{command}", flush=True)
    return failed, results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 4 验证器事件化门禁（清单从目录派生）")
    parser.add_argument("--check", action="store_true", help="覆盖率 + 清单不手维护（CI）")
    parser.add_argument("--list", action="store_true", help="打印派生清单")
    parser.add_argument("--run", action="store_true", help="依次执行 env 为空的门禁")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    catalog = load_catalog()
    if args.json:
        print(json.dumps({
            "planned": planned_commands(catalog),
            "skipped": skipped_commands(catalog),
            "universe_size": len(universe_tools()),
            "declared_size": len(declared_tools(catalog)),
        }, ensure_ascii=False, indent=2))

    if args.list:
        print(f"== unit-tests 段门禁（{len(planned_commands(catalog))} 条）==")
        for command in planned_commands(catalog):
            print(f"  {command}")
        print(f"== 声明但不进 unit-tests（env 非空，{len(skipped_commands(catalog))} 条）==")
        for command, env in skipped_commands(catalog):
            print(f"  [{env}] {command}")
        universe = universe_tools()
        print(f"== 覆盖率：{len(universe & declared_tools(catalog))} / {len(universe)} ==")

    if args.run:
        failed, _ = run_commands(planned_commands(catalog))
        skipped = skipped_commands(catalog)
        print("-" * 72)
        print(f"派生门禁执行完毕：{len(planned_commands(catalog))} 条，失败 {failed} 条；"
              f"env-gated（未跑）{len(skipped)} 条")
        return 1 if failed else 0

    if args.check:
        problems = check()
        print("Phase 4 验证器目录门禁（registry/verify/index.json）：")
        print(f"  unit-tests 门禁   {len(planned_commands(catalog))}")
        print(f"  env-gated 声明     {len(skipped_commands(catalog))}")
        print(f"  覆盖率             {len(universe_tools() & declared_tools(catalog))}"
              f" / {len(universe_tools())}")
        if problems:
            print("\n判红：")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        print("\n[OK] 目录完整、覆盖率 100%、.cnb.yml 未手列")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
