"""B6/B7：技能注册表加载器（skill-recipe-2.0）。

数据真值 = ``registry/``：
  * ``registry/skills/index.json``     — **技能显式清单（K4 权威）**：recipe_id → 文件
  * ``registry/skills/*.json``         — 技能配方（velocity_base 基座 + 机器人 patch）
  * ``registry/rewards/reward_terms.json`` — 奖励项目录（label/default/supported）
  * ``registry/rewards/presets.json``      — 任务级奖励权重预设

合并语义：沿 ``extends`` 链深合并（dict 递归、标量与列表替换、patch 优先），
环引用报错。

**K4：注册不再由文件系统隐式决定**。此前 ``registry/skills/**/*.json`` 被无差别扫描
——文件放进去就算注册、挪个目录就静默改契约。现在清单是权威：新增技能 = 往
``index.json`` 登记一行 + 放入文件；文件存在但未登记即未注册（由
:func:`unregistered_skill_files` 报出），清单声明了却不存在的文件直接报错。

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
SKILLS_DIR = REGISTRY_DIR / "skills"
#: K4：技能注册的显式清单（权威），取代「扫描目录即注册」
SKILL_INDEX_PATH = SKILLS_DIR / "index.json"
SKILL_INDEX_SCHEMA = "skill-index-1.0"
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


def skill_index_path() -> Path:
    """清单路径（由 :data:`SKILLS_DIR` 动态推导，便于测试替换目录）。"""
    return SKILLS_DIR / "index.json"


@lru_cache(maxsize=None)
def skill_manifest() -> dict[str, Any]:
    """读取并校验 ``registry/skills/index.json``（K4 权威清单）。

    校验项：schema 正确、``recipe_id`` 唯一、``path`` 是 skills/ 内的相对路径且存在、
    文件内声明的 ``recipe_id`` 与清单一致（**清单不能谎报**）。
    """
    index_path = skill_index_path()
    if not index_path.is_file():
        raise SkillRegistryError(
            f"技能清单缺失：{index_path}（期望 schema={SKILL_INDEX_SCHEMA}）。"
            "技能注册以清单为权威，不再扫描目录——请从仓库取回该文件。"
        )
    payload = _load_json(index_path)
    if not isinstance(payload, dict):
        raise SkillRegistryError("registry/skills/index.json 顶层必须是对象")
    if payload.get("schema") != SKILL_INDEX_SCHEMA:
        raise SkillRegistryError(
            f"registry/skills/index.json schema 不匹配：{payload.get('schema')!r} != {SKILL_INDEX_SCHEMA!r}"
        )
    skills = payload.get("skills")
    if not isinstance(skills, list) or not skills:
        raise SkillRegistryError("registry/skills/index.json 的 skills 必须是非空数组")

    seen: set[str] = set()
    for item in skills:
        if not isinstance(item, dict):
            raise SkillRegistryError("skills[] 每项必须是对象")
        recipe_id = str(item.get("recipe_id") or "").strip()
        if not recipe_id:
            raise SkillRegistryError("skills[] 每项必须有 recipe_id")
        if recipe_id in seen:
            raise SkillRegistryError(f"清单内 recipe_id 重复：{recipe_id!r}")
        seen.add(recipe_id)
        raw_path = str(item.get("path") or "")
        relative = Path(raw_path)
        if not raw_path or relative.is_absolute() or ".." in relative.parts:
            raise SkillRegistryError(f"{recipe_id}: path 必须是 skills/ 内的相对路径（得到 {raw_path!r}）")
        target = SKILLS_DIR / relative
        if not target.is_file():
            raise SkillRegistryError(f"{recipe_id}: 清单声明的文件不存在 {target}")
        declared = _load_json(target)
        file_recipe_id = str(declared.get("recipe_id") or target.stem)
        if file_recipe_id != recipe_id:
            raise SkillRegistryError(
                f"{recipe_id}: 清单与文件声明的 recipe_id 不一致（文件里是 {file_recipe_id!r}）"
            )
    return dict(payload)


@lru_cache(maxsize=None)
def _skill_files() -> dict[str, Path]:
    """recipe_id → 文件（由显式清单决定，不再扫描目录）。"""
    files: dict[str, Path] = {}
    for item in skill_manifest()["skills"]:
        files[str(item["recipe_id"])] = SKILLS_DIR / str(item["path"])
    return files


def unregistered_skill_files() -> list[str]:
    """skills/ 下存在但未在清单登记的 ``.json``（诊断用，不参与注册）。

    只用于「把漏登记的技能报出来」，绝不作为注册来源——注册仍以清单为权威。
    """
    registered = {path.resolve() for path in _skill_files().values()}
    index_path = skill_index_path()
    found: list[str] = []
    for path in sorted(SKILLS_DIR.rglob("*.json")):
        if path.resolve() == index_path.resolve():
            continue
        if path.resolve() not in registered:
            found.append(str(path.relative_to(SKILLS_DIR)))
    return found


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
