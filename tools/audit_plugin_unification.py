#!/usr/bin/env python3
"""插件统一度门禁（``00_know/08`` v3.0 §8 不变式 8）：旧机制残留**只许减少，不许回涨**。

v2.1 的教训（宣称 Phase 0–7 完成、实为零消费）根因是**没有机器判据**。本工具把
"插件化真实进度"变成一行行可数的东西，与基线（``tools/baselines/plugin_unification.json``）
对账：

| 计数器 | 目标 | 含义 |
|---|---|---|
| schema_version_fields | 0 | registry/ 与算法注册表里的旧字段名（Phase 0 判据） |
| registries_missing_schema | 0 | 没声明 schema 的注册表文件 |
| unregistered_catalog_files | 0 | 游离注册表（不在总表里） |
| master_entries_dangling | 0 | 总表谎报（条目文件不存在 / schema 不符） |
| hardcoded_registry_files | 0 | ``runtime_registry`` 旧硬编码字典（已删，回涨即红） |
| fake_provider_resolution | 0 | ``globals().get`` 式假 module:attr（provider 解析） |
| legacy_panel_index | 0 | 旧 ``registry/panels/index.json`` 单文件数组形态 |
| plugin_kernel_dead | 0 | 内核零生产消费（= v2.1 病灶：``plugins.core`` 只被测试 import） |
| inline_routes_api_complete | 单调 | ``api_complete.py`` 内联 ``@app`` 路由数（Phase 2 目标：只降不升） |

用法：

* ``--check``（CI）：任一"目标 0"计数器非 0，或任一计数器**高于基线** ⇒ 退出码 1；
* ``--write``：把当前计数写进基线（只许在**清理了旧机制之后**执行，不许用来掩盖回涨）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_DIR = ROOT / "registry"
MASTER_TABLE = REGISTRY_DIR / "plugin-registry.json"
BASELINE = ROOT / "tools" / "baselines" / "plugin_unification.json"

#: 目标为 0 的计数器（非 0 即红，不看基线）
ZERO_TARGETS = (
    "schema_version_fields", "registries_missing_schema", "unregistered_catalog_files",
    "master_entries_dangling", "hardcoded_registry_files", "fake_provider_resolution",
    "legacy_panel_index", "plugin_kernel_dead",
)
#: 只要求单调不涨的计数器（对照基线）
MONOTONE = ("inline_routes_api_complete",)


def _catalog_files() -> list[Path]:
    return [p for p in REGISTRY_DIR.rglob("*.json")
            if "plugins" not in p.parts and p.name != "plugin-registry.json"]


def count_schema_version_fields() -> int:
    """registry/ 全树 + 算法注册表里的 ``"schema_version"`` 键出现次数（含内层）。"""
    total = 0
    targets = list(_catalog_files()) + [ROOT / "adapters" / "mjlab" / "algorithms" / "registry.json"]
    for path in targets:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError:
            continue
        total += text.count('"schema_version"')
    return total


def count_registries_missing_schema() -> int:
    bad = 0
    for path in _catalog_files():
        try:
            doc = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            bad += 1
            continue
        if not isinstance(doc, dict) or not doc.get("schema"):
            bad += 1
    return bad


def _master() -> dict | None:
    try:
        return json.loads(MASTER_TABLE.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def count_unregistered_catalog_files() -> int:
    master = _master()
    if master is None:
        return len(_catalog_files())
    registered = {spec["path"] for spec in master.get("registries", {}).values()
                  if not str(spec.get("path", "")).startswith("../")}
    on_disk = {p.relative_to(REGISTRY_DIR).as_posix() for p in _catalog_files()}
    return len(on_disk - registered) + len(registered - on_disk)


def count_master_entries_dangling() -> int:
    master = _master()
    if master is None:
        return 1
    bad = 0
    for name, spec in master.get("registries", {}).items():
        path = REGISTRY_DIR / str(spec.get("path", ""))
        try:
            doc = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            bad += 1
            continue
        if doc.get("schema") != spec.get("schema"):
            bad += 1
    return bad


def count_hardcoded_registry_files() -> int:
    """``runtime_registry.py`` 里旧的 ``name → (file, schema)`` 字典残留（回涨即红）。"""
    source = (ROOT / "backend" / "runtime_registry.py").read_text(encoding="utf-8")
    return len(re.findall(r'REGISTRY_FILES\s*[:=]\s*\{', source))


def count_fake_provider_resolution() -> int:
    """provider 解析里的 ``globals().get``（假 module:attr；api_complete 的导入错误
    记录不算——那是模块级变量读取，不是 provider 解析）。"""
    source = (ROOT / "backend" / "cli_panels.py").read_text(encoding="utf-8")
    return len(re.findall(r'globals\(\)\.get', source))


def count_legacy_panel_index() -> int:
    return 1 if (REGISTRY_DIR / "panels" / "index.json").is_file() else 0


def count_plugin_kernel_dead() -> int:
    """内核死代码检测：``plugins.core`` / ``plugins.runtime`` 被生产代码 import 的处数。

    生产代码 = backend/ + adapters/ + tools/ + scripts/ + contracts/（测试除外）。
    v2.1 病灶正是"内核只被自己的测试 import"。
    """
    importers = 0
    for directory in ("backend", "adapters", "tools", "scripts", "contracts"):
        for path in (ROOT / directory).rglob("*.py"):
            if path.name.startswith("test_"):
                continue
            try:
                text = path.read_text(encoding="utf-8-sig")
            except OSError:
                continue
            if re.search(r'^\s*(from|import)\s+plugins\.(core|runtime)\b', text, re.M):
                importers += 1
    return 0 if importers > 0 else 1


def count_inline_routes() -> int:
    source = (ROOT / "backend" / "api_complete.py").read_text(encoding="utf-8")
    return len(re.findall(r'^@app\.(get|post|put|delete|patch)\(', source, re.M))


def collect() -> dict[str, int]:
    return {
        "schema_version_fields": count_schema_version_fields(),
        "registries_missing_schema": count_registries_missing_schema(),
        "unregistered_catalog_files": count_unregistered_catalog_files(),
        "master_entries_dangling": count_master_entries_dangling(),
        "hardcoded_registry_files": count_hardcoded_registry_files(),
        "fake_provider_resolution": count_fake_provider_resolution(),
        "legacy_panel_index": count_legacy_panel_index(),
        "plugin_kernel_dead": count_plugin_kernel_dead(),
        "inline_routes_api_complete": count_inline_routes(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="插件统一度门禁（旧机制只许减少不许回涨）")
    parser.add_argument("--check", action="store_true", help="对照基线判红（CI 模式）")
    parser.add_argument("--write", action="store_true", help="把当前计数写进基线（清理后显式执行）")
    args = parser.parse_args(argv)

    counts = collect()
    print("插件统一度计数（00_know/08 v3.0）：")
    for key, value in counts.items():
        marker = "" if key not in ZERO_TARGETS or value == 0 else "  ← 目标 0"
        print(f"  {key:32s} {value}{marker}")

    if args.write:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(
            {"schema": "plugin-unification-baseline-1.0", "counts": counts,
             "written_by": "tools/audit_plugin_unification.py --write"},
            ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"已写入基线 {BASELINE}")
        return 0

    if not args.check:
        return 0

    problems: list[str] = []
    for key in ZERO_TARGETS:
        if counts[key] != 0:
            problems.append(f"{key} = {counts[key]}（目标 0）")
    if BASELINE.is_file():
        baseline = json.loads(BASELINE.read_text(encoding="utf-8-sig")).get("counts", {})
        for key in MONOTONE:
            if key in baseline and counts[key] > baseline[key]:
                problems.append(f"{key} = {counts[key]} 高于基线 {baseline[key]}（只许减少）")
    else:
        problems.append(f"基线缺失：{BASELINE}（先跑 --write）")

    if problems:
        print("\n判红：")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\n✓ 全部达标（零目标计数器为 0；单调计数器不高于基线）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
