"""验证器目录（``registry/verify/index.json``）的**控制面访问层**。

## 为什么这层在控制面（Phase 8 开源收口第一刀）

Phase 4 把「门禁清单」从 `.cnb.yml` 手列改成数据（目录 + 派生运行器）。但那时读目录的只有
`tools/audit_plugin_verify.py` —— 那是**仓库自身**的视角。开源收口（`06` §17 Phase 8）要求
第三方也能看见"我们守什么"：目录于是必须成为**控制面可读的一等数据**（产品面 / 文档 /
第三方工具都从这里取同一份），`tools/` 只留仓库自身的判据。

## 判据分层（单一实现，不重写）

* **本模块**（控制面）：目录的**形状与词汇** —— schema、每条 `command` 非空且不重复、
  `seam` 属闭合清单、`env` 属闭合词汇；以及派生视图：
  ``planned``（`env` 为空 ⇒ 由 `.cnb.yml` unit-tests 段跑）与 ``env_gated``
  （声明了但不在 unit-tests 段：要训练栈 / 训练产物 / 可选依赖）；
* **`tools/audit_plugin_verify.py`**（仓库自身）：覆盖率 100%（`tools/` 下每个
  `^(audit|validate|check)_*.py` 都得有家）、声明文件真实存在、`.cnb.yml` 不再手列，
  以及 `--run` 的进程编排。

`summary()` 是**对外**形态：只给仓库相对路径与派生计数，不泄漏绝对路径。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "registry" / "verify" / "index.json"
#: 对外形态里用的仓库相对路径（`summary()` 不吐绝对路径）。
REPO_RELATIVE = "registry/verify/index.json"

CATALOG_SCHEMA = "plugin-verify-1.0"
#: seam 闭合清单（与 `registry/plugin-registry.json` 的 13 seam + `kernel` 一致）。
FROZEN_SEAMS = {
    "robot", "family", "skill", "terrain", "reward", "algorithm",
    "task", "sensor", "evaluator", "panel", "controller", "pack",
    "profile", "kernel",
}
#: `env` 的闭合词汇（非空 = 不进 unit-tests 段；值说明在哪种上下文跑）。
FROZEN_ENVS = {"training-venv", "mjlab", "artifact", "onnxruntime", "manual"}


def load_catalog(path: Path | str | None = None) -> dict[str, Any]:
    """读目录（默认 `registry/verify/index.json`）；顶层不是对象即抛。"""
    target = Path(path) if path is not None else CATALOG_PATH
    payload = json.loads(target.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"验证器目录顶层必须是对象：{target}")
    return payload


def gates(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    """目录条目（按声明顺序）。"""
    found = catalog.get("gates")
    return list(found) if isinstance(found, list) else []


def catalog_problems(catalog: dict[str, Any]) -> list[str]:
    """形状/词汇校验：返回问题列表（空 = 通过）。"""
    problems: list[str] = []
    if catalog.get("schema") != CATALOG_SCHEMA:
        problems.append(f"schema 必须是 {CATALOG_SCHEMA!r}，得到 {catalog.get('schema')!r}")
    entries = catalog.get("gates")
    if not isinstance(entries, list) or not entries:
        problems.append("缺非空 `gates` 数组")
        return problems
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            problems.append(f"gates[{index}] 不是对象")
            continue
        command = entry.get("command")
        if not isinstance(command, str) or not command.strip():
            problems.append(f"gates[{index}] 缺 `command`")
            continue
        if command in seen:
            problems.append(f"gates[{index}] 命令重复：{command}")
        seen.add(command)
        seam = entry.get("seam")
        if seam not in FROZEN_SEAMS:
            problems.append(f"gates[{index}] seam {seam!r} 不在闭合清单")
        env = entry.get("env")
        if env is not None and env not in FROZEN_ENVS:
            problems.append(f"gates[{index}] env {env!r} 不在闭合词汇 {sorted(FROZEN_ENVS)}")
    return problems


def planned_commands(catalog: dict[str, Any]) -> list[str]:
    """`env` 为空的条目 —— 由 `.cnb.yml` unit-tests 段执行（`--run` 的清单）。"""
    return [str(entry["command"]) for entry in gates(catalog) if not entry.get("env")]


def skipped_commands(catalog: dict[str, Any]) -> list[tuple[str, str]]:
    """`env` 非空的条目 —— 声明了但不进 unit-tests 段（返回 `(command, env)`）。"""
    return [(str(entry["command"]), str(entry.get("env")))
            for entry in gates(catalog) if entry.get("env")]


def summary(catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    """**对外形态**：目录 → 可公开的一段数据（相对路径 + 派生计数 + 逐条声明）。

    给产品面 / 协议文档 / 第三方工具用：不吐绝对路径，不含仓库内部判据（覆盖率那类
    是仓库自己的事，见 `tools/audit_plugin_verify.py`）。
    """
    payload = catalog if catalog is not None else load_catalog()
    entries = gates(payload)
    return {
        "schema": payload.get("schema"),
        "catalog": REPO_RELATIVE,
        "note": payload.get("note"),
        "universe": payload.get("universe"),
        "counts": {
            "total": len(entries),
            "planned": len(planned_commands(payload)),
            "env_gated": len(skipped_commands(payload)),
        },
        "gates": [
            {
                "command": entry.get("command"),
                "seam": entry.get("seam"),
                "env": entry.get("env"),
                "note": entry.get("note"),
            }
            for entry in entries
        ],
    }
