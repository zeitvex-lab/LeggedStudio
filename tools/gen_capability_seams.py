#!/usr/bin/env python3
"""seam 图生成器（``00_know/08`` v3.0 §4.7）：从插件总表派生"新行为去哪"地图。

上游依据：dsh 的 ``docs/capability-seams.md``（机器生成、进 CI）——"框架零特判"
从 grep 纪律升级为**机器可查结构**的门。本工具生成 ``docs/capability-seams.md``：

* 13 个 seam 的冻结清单与当前承载（总表 registries + manifest 目录）；
* "新增一个 X 该挂哪"表（新增能力 = 加声明，不改框架）；
* 生成头标明真值来源（``registry/plugin-registry.json``），手改会被覆盖。

用法：``python tools/gen_capability_seams.py [--check]``（--check 只比对不写，CI 用）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER_TABLE = ROOT / "registry" / "plugin-registry.json"
OUTPUT = ROOT / "docs" / "capability-seams.md"

GENERATED_HEADER = (
    "<!-- 由 tools/gen_capability_seams.py 生成——真值是 registry/plugin-registry.json，"
    "手改会被覆盖。再生成：python tools/gen_capability_seams.py -->"
)

#: "新增一个 X 该挂哪"（seam → 声明落点 + 一句话判据）
NEW_BEHAVIOR_TABLE = [
    ("机器人", "robot", "`assets/robots/<id>/`（契约 v3 + MJCF + 包声明，经 onboard 导入）", "包过校验进索引；族通用技能即插即训"),
    ("形态族", "family", "`registry/families/<id>.json`", "`tools/audit_families.py` 全绿"),
    ("技能 / 任务配方", "skill", "`registry/skills/<recipe>.json`（K4：先登记 index 再放文件）", "`backend/skill_registry` 校验 + 冒烟"),
    ("地形档", "terrain", "`registry/terrains/profiles.json`", "`tools/audit_terrain_profiles.py`"),
    ("奖励项 / 预设", "reward", "`registry/rewards/*.json`", "技能配方 reward_terms 引用可解析"),
    ("算法插件", "algorithm", "`adapters/mjlab/algorithms/<algo>/` + `registry.json` 登记", "`verify_plugin` fail-closed + `test_algorithm_plugins`"),
    ("任务插件（感知×判据）", "task", "`registry/task_plugins/index.json`", "`contracts/task_plugin_contract` 同一道闸"),
    ("传感器 / 感知 provider", "sensor", "`registry/perception_providers/`、`cameras.json`", "`sensor_plugin_contract` 词表核对"),
    ("验收判据 / 效果口径", "evaluator", "`arrival_criteria.json`、`effect_criterion.json`", "判据声明可被验收器执行"),
    ("页面 / 面板（四投影）", "panel", "`registry/plugins/panel/<id>.json`（legged-plugin-1.0）", "manifest 校验 + provider 真 module:attr"),
    ("控制器（MPC 轴）", "controller", "`registry/controllers/index.json`", "`backend/controller_plugins` fail-loud"),
    ("资源包 / 许可与出处", "pack", "`registry/packs/`、`licenses.json`、`porting_*.json`", "`tools/validate_packs.py` + `audit_licenses`"),
    ("训练 / 命令档位", "profile", "`registry/tasks/profiles.json`、`motion_commands.json`", "`runtime_registry` 总表派生 + schema 门"),
]


def _load_master() -> dict:
    doc = json.loads(MASTER_TABLE.read_text(encoding="utf-8-sig"))
    if doc.get("schema") != "plugin-registry-1.0":
        raise SystemExit(f"总表 schema 不符：{MASTER_TABLE}")
    return doc


def _seam_rows(master: dict) -> list[tuple[str, int, int, str]]:
    seams = master["seams"]
    by_seam: dict[str, dict[str, int]] = {s: {"registries": 0, "manifests": 0} for s in seams}
    for spec in master["registries"].values():
        seam = spec["seam"]
        if seam in by_seam:
            by_seam[seam]["registries"] += 1
    manifest_dir = ROOT / "registry" / master.get("manifest_dir", "plugins")
    for path in manifest_dir.rglob("*.json"):
        try:
            doc = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        seam = doc.get("seam")
        if seam in by_seam:
            by_seam[seam]["manifests"] += 1
    return [(s, v["registries"], v["manifests"],
             "✓ 有承载" if (v["registries"] or v["manifests"]) else "—（该 seam 尚无声明，属待扩展位）")
            for s, v in by_seam.items()]


def render(master: dict) -> str:
    rows = _seam_rows(master)
    lines = [
        GENERATED_HEADER,
        "",
        "# Capability Seams：能力面地图（机器生成）",
        "",
        "一切即插件（`00_know/08` v3.0）：能力挂在 13 个冻结 seam 上，新增行为 = 加声明，不改框架。",
        f"真值：`registry/plugin-registry.json`（schema `plugin-registry-1.0`，",
        f"{len(master['registries'])} 条注册表条目 + `registry/plugins/` 插件清单目录）。",
        "",
        "## seam × 承载",
        "",
        "| seam | 数据注册表 | 插件清单 | 状态 |",
        "|---|---:|---:|---|",
    ]
    for seam, reg, man, status in rows:
        lines.append(f"| {seam} | {reg} | {man} | {status} |")
    lines += [
        "",
        "## 新增一个 X 该挂哪（新增能力不改框架代码）",
        "",
        "| 要加什么 | seam | 声明落点 | 门禁 |",
        "|---|---|---|---|",
    ]
    for what, seam, where, gate in NEW_BEHAVIOR_TABLE:
        lines.append(f"| {what} | {seam} | {where} | {gate} |")
    lines += [
        "",
        "## 内核与投影",
        "",
        "* 内核：`plugins/runtime.py`（服务上下文 + 事件五模式 + patch 整行替换；纯度由",
        "  `backend/test_plugin_kernel_purity.py` AST 守卫：≤400 行 / 零本仓 import / 零业务词）。",
        "* provider 解析：**真 `module:attr`**（importlib，可指向任何模块）——",
        "  `backend/cli_panels.py::resolve_provider`。",
        "* 统一度计数器：`tools/audit_plugin_unification.py --check`（旧机制只许减少不许回涨）。",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 capability-seams.md（seam 地图）")
    parser.add_argument("--check", action="store_true", help="只比对不写（CI 模式：漂移判红）")
    args = parser.parse_args(argv)

    master = _load_master()
    content = render(master)

    if args.check:
        if not OUTPUT.is_file():
            print(f"判红：{OUTPUT} 不存在（先跑生成）")
            return 1
        current = OUTPUT.read_text(encoding="utf-8")
        if current != content:
            print(f"判红：{OUTPUT} 与总表漂移（再生成：python tools/gen_capability_seams.py）")
            return 1
        print("✓ seam 图与总表一致")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"已生成 {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
