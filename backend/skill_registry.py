"""B6/B7：技能注册表加载器（skill-recipe-2.0）。

数据真值 = ``registry/``：
  * ``registry/skills/*.json``        — 技能配方（velocity_base 基座 + 机器人 patch）
  * ``registry/rewards/reward_terms.json`` — 奖励项目录（label/default/supported）
  * ``registry/rewards/presets.json``      — 任务级奖励权重预设

合并语义：沿 ``extends`` 链深合并（dict 递归、标量与列表替换、patch 优先），
环引用报错。新增技能 = 新增一个 JSON 文件，不改任何代码。

结构校验按 schema 文件 ``contracts/schema/skill-recipe-2.0.schema.json`` 的
必填键与已知键类型手工执行（运行时无 jsonschema 依赖）。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_DIR = ROOT / "registry"
SCHEMA_PATH = ROOT / "contracts" / "schema" / "skill-recipe-2.0.schema.json"

REQUIRED_KEYS = ("schema_version", "recipe_id", "display_name")
KNOWN_ENUMS = {"algorithm": {"PPO", "SAC", "TD3"}}


class SkillRegistryError(ValueError):
    """注册表数据不合法。"""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillRegistryError(f"注册表文件不可读 {path.name}: {exc}") from exc


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """递归合并：patch 优先；dict 递归，标量与列表整体替换。"""
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _validate_recipe(recipe: dict[str, Any], source: str) -> None:
    for key in REQUIRED_KEYS:
        if key not in recipe:
            raise SkillRegistryError(f"{source}: 缺少必填键 {key!r}")
    if recipe.get("schema_version") != "skill-recipe-2.0":
        raise SkillRegistryError(
            f"{source}: schema_version 必须为 skill-recipe-2.0（得到 {recipe.get('schema_version')!r}）"
        )
    for key, allowed in KNOWN_ENUMS.items():
        if key in recipe and recipe[key] not in allowed:
            raise SkillRegistryError(f"{source}: {key}={recipe[key]!r} 不在 {sorted(allowed)}")


@lru_cache(maxsize=None)
def _skill_files() -> dict[str, Path]:
    """recipe_id → 文件（skills/ 顶层 + skills/patches/ 均扫描）。"""
    files: dict[str, Path] = {}
    for path in sorted(REGISTRY_DIR.glob("skills/**/*.json")):
        data = _load_json(path)
        recipe_id = str(data.get("recipe_id") or path.stem)
        files[recipe_id] = path
    return files


def resolve_skill(recipe_id: str) -> dict[str, Any]:
    """解析技能配方：沿 extends 深合并（环引用检测）。"""
    files = _skill_files()
    if recipe_id not in files:
        raise SkillRegistryError(
            f"unknown skill recipe {recipe_id!r}; available: {', '.join(sorted(files))}"
        )
    chain: list[str] = []
    current: str | None = recipe_id
    while current:
        if current in chain:
            raise SkillRegistryError(f"extends 环引用: {' -> '.join(chain + [current])}")
        chain.append(current)
        current = _load_json(files[current]).get("extends")
    # 从链根（最远基座）向叶合并：patch 永远覆盖 base。
    merged: dict[str, Any] = {}
    for recipe in reversed(chain):
        data = _load_json(files[recipe])
        _validate_recipe(data, files[recipe].name)
        merged = deep_merge(merged, data)
    return merged


def list_skills() -> list[dict[str, Any]]:
    """全部技能（已合并）的摘要列表。"""
    summaries = []
    for recipe_id in sorted(_skill_files()):
        recipe = resolve_skill(recipe_id)
        summaries.append(
            {
                "recipe_id": recipe_id,
                "display_name": recipe.get("display_name"),
                "extends": recipe.get("extends"),
                "task_name": recipe.get("task_name"),
                "terrain_type": recipe.get("terrain_type"),
                "algorithm": recipe.get("algorithm"),
                "num_envs": recipe.get("num_envs"),
            }
        )
    return summaries


@lru_cache(maxsize=1)
def reward_terms() -> dict[str, dict[str, Any]]:
    """奖励项目录（原始数据，layer 由 env_factory 侧富化）。"""
    data = _load_json(REGISTRY_DIR / "rewards" / "reward_terms.json")
    terms = data.get("terms")
    if not isinstance(terms, dict) or not terms:
        raise SkillRegistryError("reward_terms.json 缺少 terms 对象")
    return terms


@lru_cache(maxsize=1)
def reward_presets() -> dict[str, dict[str, float]]:
    """任务级奖励权重预设。"""
    data = _load_json(REGISTRY_DIR / "rewards" / "presets.json")
    presets = data.get("presets")
    if not isinstance(presets, dict) or not presets:
        raise SkillRegistryError("presets.json 缺少 presets 对象")
    return presets


@lru_cache(maxsize=1)
def task_variants() -> dict[str, dict[str, Any]]:
    """任务变体表：取自含 tasks 键的技能（velocity_base）。"""
    for recipe_id in sorted(_skill_files()):
        recipe = _load_json(_skill_files()[recipe_id])
        tasks = recipe.get("tasks")
        if isinstance(tasks, dict) and tasks:
            return tasks
    raise SkillRegistryError("registry/skills 中没有任何技能声明 tasks 变体表")
