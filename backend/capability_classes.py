# -*- coding: utf-8 -*-
"""能力类反查（registry/families/*.json 的 capability 声明唯一消费口）。

分类原则（用户裁决 2026-10-03）：**能力 = 技能机制 × 地形类**——velocity 训在
复杂地形上就是越障能力（越障基础档），不能都埋在「速度跟踪」一个名下。
族注册表声明两级映射：skill.capability_map（地形→能力类）与
skill.capability_task_split（任务名→能力类分组）。本模块把它们反排成
task_name → capability_class 的单表，供面板/CLI/验收按能力类投影。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FAMILIES_DIR = Path(__file__).resolve().parents[1] / "registry" / "families"

# 控制词汇表也以族注册表为准（两族共享同一份 capability_classes 声明；
# 任一族没声明即视为数据债，fail-loud 不给空表兜底）。


def _load_family(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def capability_index(families_dir: Path | None = None) -> dict[str, dict[str, str]]:
    """{family_id: {task_name: capability_class}}（split 声明优先，反排不覆盖）。"""
    root = Path(families_dir) if families_dir is not None else FAMILIES_DIR
    index: dict[str, dict[str, str]] = {}
    for path in sorted(root.glob("*.json")):
        doc = _load_family(path)
        if not doc.get("family_id"):
            continue  # index.json 之类的目录文件不是族文档
        family = doc["family_id"]
        rows: dict[str, str] = {}
        for skill in doc.get("skills") or []:
            for cls, names in sorted((skill.get("capability_task_split") or {}).items()):
                for name in names or []:
                    if name in rows and rows[name] != cls:
                        raise ValueError(
                            f"{family}/{skill.get('skill_id')}: 任务 {name!r} 在两个能力类里"
                            f"（{rows[name]} 与 {cls}）——分类必须唯一"
                        )
                    rows[name] = cls
        index[family] = rows
    return index


def capability_of(task_name: str, families_dir: Path | None = None) -> dict[str, str]:
    """跨族反查一个训练任务名的能力类：{family: class}；无声明 = 空表（诚实）。"""
    hits: dict[str, str] = {}
    for family, rows in capability_index(families_dir).items():
        if task_name in rows:
            hits[family] = rows[task_name]
    return hits


def declared_vocabulary(families_dir: Path | None = None) -> dict[str, str]:
    """能力类控制词汇表（id → 中文释义），取自任一族的 capability_classes 声明。"""
    root = Path(families_dir) if families_dir is not None else FAMILIES_DIR
    for path in sorted(root.glob("*.json")):
        doc = _load_family(path)
        vocab = doc.get("capability_classes")
        if isinstance(vocab, dict) and vocab:
            return dict(vocab)
    raise ValueError("族注册表没有任何 capability_classes 声明——分类词汇表缺位")
