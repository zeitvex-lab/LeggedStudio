"""E7：Skill 包（纯 JSON）的导出 / 校验 / 导入。

## 判据（清单 E7）：**他人可导入并校验**

把一项技能（recipe）连同它的**基座**打成一个**自包含**的 JSON：收到包的人不需要我们仓里的
任何东西，就能 ① 校验它有没有被改过、② 导入自己的注册表。这与 B12 的"整包导出"不同 ——
B12 导出的是**机器人包**（模型/资产/契约），这里导出的是**技能配置**：纯 JSON、可读可审、
可以贴在 issue 里传。

## 三个不将就的地方

1. **摘要，不是"看起来对"**：每个 recipe 带 `sha256`（规范化 JSON 摘要，与 B9 同算法），
   包自身也带摘要 —— 任何一处被改都能查出来；
2. **闭环**：patch 离开基座毫无意义，所以导出时**自动带上 `patch_of` 的基座**，
   校验时**要求闭环**（缺基座即报问题，而不是导入后才发现 `extends` 指向空）；
3. **路径不可信**：包来自外部，里面的 `path` 必须当**敌意输入**处理 ——
   拒绝绝对路径与 `..`（否则一个包就能写到 `registry/` 之外去）。

结构校验**复用 K4**（`skill_registry._validate_recipe`），不另写一套 ——
两套校验迟早会分叉，然后"包验过了、注册表却不认"。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from backend.skill_registry import (  # noqa: PLC2701  复用 K4 结构校验，不另写一套
    SKILL_INDEX_SCHEMA,
    SKILLS_DIR,
    SkillRegistryError,
    _validate_recipe,
)
from backend.training.runs import canonical_digest

#: 包格式版本。
PACK_SCHEMA = "skill-pack-1.0"
INDEX_NAME = "index.json"


def _load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _safe_join(skills_dir: Path, raw: str) -> Path:
    """把包内 ``path`` 拼到 ``skills_dir`` 下；**拒绝绝对路径与 ``..``**。

    包是外部输入：不设这道关，一个包就能把文件写到 `registry/` 之外。
    """
    text = str(raw or "").strip()
    relative = Path(text)
    if not text or relative.is_absolute() or ".." in relative.parts:
        raise SkillRegistryError(f"path 必须是 skills/ 内的相对路径（得到 {raw!r}）")
    return Path(skills_dir) / relative


def _read_index(skills_dir: Path) -> dict[str, Any]:
    path = Path(skills_dir) / INDEX_NAME
    payload = _load_json(path)
    if not isinstance(payload, Mapping) or payload.get("schema") != SKILL_INDEX_SCHEMA:
        raise SkillRegistryError(f"{path} 不是合法的技能清单（schema={SKILL_INDEX_SCHEMA}）")
    return dict(payload)


def export_pack(recipe_id: str, *, skills_dir: Path | str = SKILLS_DIR) -> dict[str, Any]:
    """把一项技能（含其基座）导出为自包含的 Skill 包。"""
    skills = Path(skills_dir)
    manifest = _read_index(skills)
    entries = {str(item["recipe_id"]): dict(item) for item in manifest["skills"]}
    if recipe_id not in entries:
        raise SkillRegistryError(
            f"未知技能 {recipe_id!r}；可用：{', '.join(sorted(entries))}",
        )

    wanted: list[str] = [recipe_id]
    base = str(entries[recipe_id].get("patch_of") or "")
    if base:
        if base not in entries:
            raise SkillRegistryError(f"{recipe_id}: 清单声明 patch_of={base!r}，但清单里没有这条")
        wanted.append(base)          # 闭环：patch 必须带上基座

    records: list[dict[str, Any]] = []
    for item_id in wanted:
        entry = entries[item_id]
        path = _safe_join(skills, str(entry.get("path") or ""))
        if not path.is_file():
            raise SkillRegistryError(f"{item_id}: 清单声明的文件不存在 {path}")
        content = _load_json(path)
        records.append({
            "recipe_id": item_id,
            "role": entry.get("role"),
            "patch_of": entry.get("patch_of"),
            "summary": entry.get("summary"),
            "path": str(entry.get("path")),
            "sha256": canonical_digest(content),
            "content": content,
        })

    pack = {
        "schema": PACK_SCHEMA,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_registry_schema": manifest.get("schema"),
        "recipes": records,
    }
    pack["digest"] = canonical_digest(pack)      # 包自身摘要（覆盖以上全部）
    return pack


def verify_pack(pack: Any) -> dict[str, Any]:
    """校验一个包：格式、逐条摘要、结构（复用 K4）、闭环、包摘要。**返回问题清单，不抛异常**。"""
    problems: list[str] = []
    if not isinstance(pack, Mapping):
        return {"ok": False, "problems": ["包不是 JSON 对象"], "recipes": []}
    if pack.get("schema") != PACK_SCHEMA:
        problems.append(f"schema 不匹配：{pack.get('schema')!r} != {PACK_SCHEMA!r}")

    raw_recipes = pack.get("recipes")
    recipes: list[Mapping[str, Any]] = []
    if not isinstance(raw_recipes, list) or not raw_recipes:
        problems.append("recipes 必须是非空数组")
    else:
        recipes = [item for item in raw_recipes if isinstance(item, Mapping)]
        if len(recipes) != len(raw_recipes):
            problems.append("recipes[] 每项必须是对象")

    ids: set[str] = set()
    for record in recipes:
        rid = str(record.get("recipe_id") or "").strip()
        if not rid:
            problems.append("recipes[] 缺 recipe_id")
            continue
        if rid in ids:
            problems.append(f"recipe_id 重复：{rid}")
        ids.add(rid)

        content = record.get("content")
        if not isinstance(content, Mapping):
            problems.append(f"{rid}: content 缺失或不是对象")
            continue
        recorded = str(record.get("sha256") or "")
        actual = canonical_digest(content)
        if actual != recorded:
            problems.append(
                f"{rid}: 内容摘要不一致（登记 {recorded[:12]}… vs 实算 {actual[:12]}…）—— 包被改动过",
            )
        try:
            _validate_recipe(dict(content), f"{rid}（包内）")
        except SkillRegistryError as exc:
            problems.append(str(exc))
        try:
            _safe_join(Path("."), str(record.get("path") or ""))
        except SkillRegistryError as exc:
            problems.append(f"{rid}: {exc}")

    for record in recipes:                        # 闭环：patch 的基座必须在包内
        base = str(record.get("patch_of") or "")
        if base and base not in ids:
            problems.append(
                f"{record.get('recipe_id')}: patch_of={base!r} 的基座不在包内"
                "（导入后 extends 指向空，等于收了个残包）",
            )

    if "digest" not in pack:
        problems.append("包缺 digest")
    else:
        body = {key: value for key, value in pack.items() if key != "digest"}
        if canonical_digest(body) != pack.get("digest"):
            problems.append("包摘要不一致 —— 包被改动过")

    return {"ok": not problems, "problems": problems, "recipes": sorted(ids)}


def import_pack(
    pack: Any,
    *,
    skills_dir: Path | str = SKILLS_DIR,
    overwrite: bool = False,
    write: bool = False,
) -> dict[str, Any]:
    """把包导入技能注册表。**先校验，校验不过绝不落盘**（fail-closed）。

    * 已存在同名文件且内容不同 → 需显式 ``overwrite=True``（**不静默覆盖别人的技能**）；
    * 本仓清单登记的 ``path`` 与包内不一致 → 报问题（清单是权威，不能被包改写路径）；
    * ``write=False``（默认）只做**预演**：返回将要写入的清单，不动磁盘。
    """
    report = verify_pack(pack)
    if not report["ok"]:
        return {
            "ok": False, "planned": [], "written": [], "index_updated": False,
            "problems": report["problems"],
        }

    skills = Path(skills_dir)
    index_path = skills / INDEX_NAME
    manifest = _read_index(skills) if index_path.is_file() else {
        "schema": SKILL_INDEX_SCHEMA, "skills": [],
    }
    entries = {str(item["recipe_id"]): dict(item) for item in manifest.get("skills") or []}

    problems: list[str] = []
    planned: list[str] = []
    payloads: list[tuple[Path, str]] = []
    index_updated = False

    for record in pack["recipes"]:
        rid = str(record["recipe_id"])
        relative = str(record.get("path"))
        target = _safe_join(skills, relative)
        text = json.dumps(record["content"], ensure_ascii=False, indent=2) + "\n"

        if target.is_file():
            existing = _load_json(target)
            if canonical_digest(existing) != canonical_digest(record["content"]) and not overwrite:
                problems.append(
                    f"{rid}: {relative} 已存在且内容不同；需 overwrite=True 才覆盖"
                    "（不静默覆盖已注册的技能）",
                )
                continue

        entry = entries.get(rid)
        if entry is not None and str(entry.get("path")) != relative:
            problems.append(
                f"{rid}: 本仓清单登记的路径是 {entry.get('path')!r}，与包内 {relative!r} 不同"
                "（路径以本仓清单为准，包不能改写它）",
            )
            continue

        payloads.append((target, text))
        planned.append(relative)
        if entry is None:
            new_entry: dict[str, Any] = {"recipe_id": rid, "path": relative,
                                         "role": record.get("role")}
            for key in ("patch_of", "summary"):
                if record.get(key) is not None:
                    new_entry[key] = record[key]
            entries[rid] = new_entry
            index_updated = True

    if problems:
        return {"ok": False, "planned": planned, "written": [], "index_updated": False,
                "problems": problems}

    written: list[str] = []
    if write:
        for target, text in payloads:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            written.append(str(target.relative_to(skills).as_posix()))
        if index_updated:
            manifest["skills"] = list(entries.values())
            index_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
            )

    return {
        "ok": True, "planned": planned, "written": written,
        "index_updated": index_updated, "problems": [],
    }
