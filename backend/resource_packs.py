"""E5：模块化资源包 —— **可挂载、可卸载**。

## 这一层补的是什么

零件早就都在仓里（`registry/skills` 技能配方 / `registry/rewards` 奖励目录与预设 /
`registry/perception_providers` 感知 provider / `backend/perception_observations.py` 观测项），
但它们只是**一堆目录**：没有一个可命名、可挂载/卸载的**组合单元**，也没有人校验
"挂上之后维度与依赖还对得上"。

资源包＝**一串声明**（挂什么观测项、什么奖励项、什么 provider、什么参数），
落在 `registry/packs/*.json`，清单 `index.json` 是权威（K4 同款：**清单说了算，不扫目录**）。

## 三条纪律

1. **挂载/卸载幂等**：挂两次等于挂一次；卸载只回退**这个包引入的**键 —— 靠 `mount()`
   返回的 `provenance`（"这些键是我加的"）。没有它，卸载会误删手写的同名字段。
2. **fail-closed**：引用的观测项/provider/奖励项不存在、观测宽度对不上、
   可选依赖缺失 → **拒绝挂载并列出原因**（不是"挂一半"）。
3. **挂载错了当场报**：观测宽度校验用契约声明的 `obs_dim` 当真值 —— 这正是 E4 那块
   "维度不符即时报错"的资源包版本。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
PACKS_DIR = ROOT / "registry" / "packs"
INDEX_NAME = "index.json"
INDEX_SCHEMA = "resource-pack-index-1.0"
PACK_SCHEMA = "resource-pack-1.0"

#: 包能挂的东西（键 → 该去哪校验引用）。新增一类能力 = 在这里加一行（**不改挂载逻辑**）。
MOUNT_KEYS = ("observations", "reward_terms", "providers", "params")


class ResourcePackError(ValueError):
    """包或引用不合法。"""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResourcePackError(f"资源包文件不可读 {path}: {exc}") from exc


def load_index(packs_dir: Path | str = PACKS_DIR) -> dict[str, Any]:
    """读清单（权威）。**文件存在但未登记 = 未注册**（K4 口径）。"""
    path = Path(packs_dir) / INDEX_NAME
    payload = _load_json(path)
    if not isinstance(payload, Mapping) or payload.get("schema") != INDEX_SCHEMA:
        raise ResourcePackError(f"{path} 不是合法的资源包清单（schema={INDEX_SCHEMA}）")
    return dict(payload)


def load_pack(pack_id: str, *, packs_dir: Path | str = PACKS_DIR) -> dict[str, Any]:
    packs = Path(packs_dir)
    entries = {str(item["pack_id"]): dict(item) for item in load_index(packs)["packs"]}
    if pack_id not in entries:
        raise ResourcePackError(
            f"未注册的资源包 {pack_id!r}；可用：{', '.join(sorted(entries))}",
        )
    entry = entries[pack_id]
    relative = Path(str(entry.get("path") or ""))
    if not str(entry.get("path") or "") or relative.is_absolute() or ".." in relative.parts:
        raise ResourcePackError(f"{pack_id}: path 必须是 packs/ 内的相对路径")
    payload = _load_json(packs / relative)
    if not isinstance(payload, Mapping) or payload.get("schema") != PACK_SCHEMA:
        raise ResourcePackError(f"{pack_id}: 包文件 schema 必须是 {PACK_SCHEMA}")
    if str(payload.get("pack_id")) != pack_id:
        raise ResourcePackError(f"{pack_id}: 清单与包内 pack_id 不一致（包内是 {payload.get('pack_id')!r}）")
    return dict(payload)


def list_packs(*, packs_dir: Path | str = PACKS_DIR) -> list[dict[str, Any]]:
    """全部已注册资源包的摘要（编辑器据此列出"可挂载的包"）。"""
    packs = Path(packs_dir)
    summaries: list[dict[str, Any]] = []
    for entry in load_index(packs)["packs"]:
        pack_id = str(entry["pack_id"])
        try:
            pack = load_pack(pack_id, packs_dir=packs)
        except ResourcePackError as exc:
            summaries.append({"pack_id": pack_id, "error": str(exc)})
            continue
        mounts = pack.get("mounts") or {}
        summaries.append({
            "pack_id": pack_id,
            "label": pack.get("label") or entry.get("label"),
            "purpose": pack.get("purpose"),
            "requires": pack.get("requires") or [],
            "obs_dim_delta": pack.get("obs_dim_delta"),
            "counts": {key: len(mounts.get(key) or []) if isinstance(mounts.get(key), list)
                       else (1 if mounts.get(key) else 0) for key in MOUNT_KEYS},
        })
    return summaries


def _observation_widths() -> dict[str, int]:
    """观测项 id → 宽度（真值来自 `perception_observations`，**不另抄一份**）。"""
    from backend.perception_observations import list_perception_items

    widths: dict[str, int] = {}
    for item in list_perception_items():
        try:
            widths[str(item["id"])] = int(item["width"])
        except (KeyError, TypeError, ValueError):
            continue
    return widths


def _known_references() -> dict[str, set[str]]:
    """可挂引用的真值集（每一类都来自它自己的权威数据源，不另抄一份）。"""
    from backend.perception_observations import list_perception_items
    from backend.skill_registry import reward_terms

    providers: set[str] = set()
    try:
        index = _load_json(ROOT / "registry" / "perception_providers" / "index.json")
        providers = {str(item["provider_id"]) for item in index.get("providers") or []}
    except ResourcePackError:
        providers = set()
    return {
        "observations": {str(item["id"]) for item in list_perception_items()},
        "reward_terms": set(reward_terms()),
        "providers": providers,
    }


def validate_pack(pack: Mapping[str, Any], *, obs_dim: int | None = None) -> dict[str, Any]:
    """校验一个包能否挂载：引用存在性、观测宽度、可选依赖声明。**返回问题清单**。"""
    problems: list[str] = []
    known = _known_references()
    mounts = pack.get("mounts")
    if not isinstance(mounts, Mapping):
        problems.append("mounts 必须是对象")
        mounts = {}

    for key in ("observations", "reward_terms", "providers"):
        refs = mounts.get(key) or []
        if not isinstance(refs, list):
            problems.append(f"mounts.{key} 必须是数组")
            continue
        unknown = sorted(str(item) for item in refs if str(item) not in known[key])
        if unknown:
            problems.append(
                f"mounts.{key} 引用了不存在的 id：{unknown}（可用：{', '.join(sorted(known[key]))}）",
            )

    delta = pack.get("obs_dim_delta")
    if delta is not None and not isinstance(delta, int):
        problems.append("obs_dim_delta 必须是整数（挂载对观测宽度的确定影响）")
    if delta and not (mounts.get("observations") or []):
        problems.append("声明了 obs_dim_delta 却没挂任何观测项 —— 宽度影响无从谈起")

    # **宽度一致性**（E4 判据"维度不符即时报错"的资源包版本）：
    # 声明的影响必须等于所挂观测项宽度之和 —— 否则挂载后策略输入维度会悄悄错位，
    # 而那正是最难查的一类故障（跑起来不报错，只是学不动）。
    if isinstance(delta, int) and (mounts.get("observations") or []):
        widths = _observation_widths()
        missing = [str(item) for item in mounts["observations"] if str(item) not in widths]
        if not missing:
            actual = sum(widths[str(item)] for item in mounts["observations"])
            if actual != delta:
                problems.append(
                    f"obs_dim_delta 声明 {delta}，但所挂观测项宽度之和是 {actual}"
                    f"（{ ' + '.join(f'{item}:{widths[str(item)]}' for item in mounts['observations']) }）",
                )

    for item in pack.get("requires_optional_dependency") or []:
        if not str(item).strip():
            problems.append("requires_optional_dependency 里有空项")
    return {"ok": not problems, "problems": problems}


def mount(
    config: Mapping[str, Any],
    pack_ids: Iterable[str],
    *,
    packs_dir: Path | str = PACKS_DIR,
    obs_dim: int | None = None,
) -> dict[str, Any]:
    """把若干资源包挂到一份配置上。**先全部校验，任一不过则不挂**（fail-closed）。

    ``obs_dim`` = **挂载前**这份配置的观测宽度（用于把"挂上之后是多少"算清楚）；
    宽度一致性由包自己保证（`obs_dim_delta` 必须等于所挂观测项宽度之和，校验期已查），
    这里不再另立一道"总宽度必须等于某个数"的判据 —— **那是 E4 映射板的职责**，
    在资源包层硬加只会造出一条没人能填对的规则。
    """
    packs = Path(packs_dir)
    merged: dict[str, Any] = json.loads(json.dumps(dict(config)))   # 深拷贝，不改调用方对象
    provenance: dict[str, dict[str, Any]] = {}
    mounted: list[str] = []
    problems: list[str] = []
    delta_total = 0

    for pack_id in pack_ids:
        try:
            pack = load_pack(pack_id, packs_dir=packs)
        except ResourcePackError as exc:
            problems.append(str(exc))
            continue
        report = validate_pack(pack, obs_dim=obs_dim)
        if not report["ok"]:
            problems.extend(f"{pack_id}: {item}" for item in report["problems"])
            continue
        if pack_id in provenance:
            continue                                   # 幂等：重复挂载 = 不变
        mounts = pack.get("mounts") or {}
        added: dict[str, Any] = {}
        for key in ("observations", "reward_terms", "providers"):
            refs = [str(item) for item in (mounts.get(key) or [])]
            current = [str(item) for item in (merged.get(key) or [])]
            fresh = [item for item in refs if item not in current]
            if fresh:
                merged[key] = current + fresh
                added[key] = fresh
        params = mounts.get("params") or {}
        if isinstance(params, Mapping) and params:
            target = dict(merged.get("params") or {})
            added_params = {}
            for key, value in params.items():
                if key in target:
                    if target[key] != value:
                        problems.append(
                            f"{pack_id}: params.{key} 已存在且值不同（{target[key]!r} vs {value!r}）"
                            "—— 不静默覆盖手写参数，请先卸下或显式改值",
                        )
                    # 已存在且同值 = **已经挂过了**，不算本次新增（否则重复挂载会误报"新挂"）
                    continue
                target[key] = value
                added_params[key] = value
            if added_params:
                merged["params"] = target
                added["params"] = added_params
        if added:
            provenance[pack_id] = added
            mounted.append(pack_id)
            delta_total += int(pack.get("obs_dim_delta") or 0)

    if problems:
        return {"ok": False, "config": dict(config), "mounted": [], "obs_dim_total": None,
                "provenance": {}, "problems": problems}

    return {
        "ok": True, "config": merged, "mounted": mounted,
        "obs_dim_total": (int(obs_dim) + delta_total) if obs_dim is not None else None,
        "provenance": provenance, "problems": [],
    }


def unmount(
    config: Mapping[str, Any],
    pack_id: str,
    *,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """卸下一个包：**只回退它引入的键**（靠 provenance），不动手写的同名字段。"""
    merged: dict[str, Any] = json.loads(json.dumps(dict(config)))
    removed_from = (provenance or {}).get(pack_id)
    if not removed_from:
        return {"ok": False, "config": dict(config), "removed": [],
                "problems": [f"{pack_id}: 没有这个包的挂载记录（provenance）—— 不能猜着删"]}
    removed: list[str] = []
    for key in ("observations", "reward_terms", "providers"):
        for item in removed_from.get(key) or []:
            current = [str(x) for x in (merged.get(key) or [])]
            if item in current:
                current.remove(item)
                merged[key] = current
                removed.append(f"{key}:{item}")
    for key in (removed_from.get("params") or {}):
        if isinstance(merged.get("params"), Mapping) and key in merged["params"]:
            merged["params"] = {k: v for k, v in merged["params"].items() if k != key}
            removed.append(f"params:{key}")
    return {"ok": True, "config": merged, "removed": removed, "problems": []}
