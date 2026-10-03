"""profile 层叠解析（Phase 2 插件化，2026-10-02）——组合实验从"新建全量档案"变"3 行覆盖"。

## 语法（浅合并、fail-loud）

档案 JSON 顶层可选 `"extends": "<base_profile_id>"`（同包 profiles 目录内）。
展开规则（dsh patch 语义的档案级子集）：

* 子档案的标量/列表字段**整键覆盖**基档案（数组不合并——entrypoints/note 全换就是意图）；
* 仅 `overrides` 键做**深合并**（键路径覆盖：`{"terrain": {"border_width": 15}}`）——
  这是"只动一个参数跑对照实验"的正门，替代此前"复制整份档案改一行"的做法；
* `extends` 链不允许环（A→B→A），深度 ≤8；基档案必须真实存在（fail-loud 报可用清单）；
* 无 `extends` 的档案原样返回——**55 份存量零迁移、零风险**。

## 消费点

`task_config.find_training_profile` 找到 raw 档案后过 `resolve_profile_extends`
再返回——所有下游（load_profile_bundle/native_worker 装配/冒烟指纹）看到的都是
**展开后的全量视图**，装配器无感知。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

MAX_EXTENDS_DEPTH = 8


class ProfileExtendsError(ValueError):
    """extends 链错误（缺基档案/环/过深）——fail-loud，不猜。"""


def _deep_merge(base: dict[str, Any], override: Mapping) -> dict[str, Any]:
    """深合并（dict 递归，list/标量整键替换）。"""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(dict(out[key]), value)
        else:
            out[key] = value
    return out


def resolve_profile_extends(profile: dict, profiles_dir: Path,
                            *, _seen: frozenset[str] = frozenset()) -> dict:
    """展开 `extends` 链：base ← 逐层覆盖 → 返回全量视图（原 dict 不改）。"""
    extends = profile.get("extends")
    if not extends:
        return profile
    if not isinstance(extends, str):
        raise ProfileExtendsError(
            f"profile {profile.get('profile_id')}: extends 必须是基档案 id 字符串，得到 {extends!r}")
    profile_id = str(profile.get("profile_id") or "?")
    if profile_id in _seen or len(_seen) >= MAX_EXTENDS_DEPTH:
        raise ProfileExtendsError(f"profile {profile_id}: extends 环或过深（链 {sorted(_seen | {profile_id})}）")
    base_path = profiles_dir / f"{extends}.json"
    if not base_path.is_file():
        available = sorted(p.stem for p in profiles_dir.glob("*.json"))
        raise ProfileExtendsError(
            f"profile {profile_id}: extends 指向不存在的基档案 {extends!r}（可用：{available}）")
    base = json.loads(base_path.read_text(encoding="utf-8-sig"))
    base = resolve_profile_extends(base, profiles_dir, _seen=_seen | {profile_id})
    overrides = profile.get("overrides") or {}
    if overrides and not isinstance(overrides, Mapping):
        raise ProfileExtendsError(f"profile {profile_id}: overrides 必须是对象，得到 {type(overrides).__name__}")

    merged = dict(base)
    shallow = {k: v for k, v in profile.items() if k not in ("extends", "overrides")}
    merged.update(shallow)  # 浅键整覆盖（note/source/entrypoints…全换就是意图）
    if overrides:
        merged = _deep_merge(merged, overrides)
    # 展开产物仍是"全量视图"：profile_id 保持子档案自己的 id
    merged["profile_id"] = profile.get("profile_id") or extends
    return merged


def find_profile_path(profiles_dir: Path, profile_id: str) -> Path | None:
    """profile_id → 档案路径（原 find_training_profile 的扫描逻辑，独立出来复用）。"""
    for path in sorted(profiles_dir.glob("*.json")):
        try:
            profile = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if profile.get("profile_id") == profile_id:
            return path
    return None
