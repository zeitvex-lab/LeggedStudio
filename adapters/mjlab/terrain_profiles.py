"""地形档：把"训练用什么地形"从散在包内/Kit 的字面量收敛为**按档位 id 装配**。

## 为什么要有这一层

"越障"不是某个叫 parkour 的技能——它是**训练时的地形**（台阶 / 沟壑 / 障碍释放 / 竞赛构件）。
此前地形散在三处：通用路径硬编码 `{"plane","rough"}`、轮足族的竞赛/释放课程在
`wheel_leg_kit` 里、四足的台阶族在 go2 的 parkour 里——于是"同族换个机型能不能训同一档"
这件事没有单一真值可查。本模块把地形变成**档位**：

* 真值表：`registry/terrains/{index,profiles}.json`（档位 id / 怎么造 / 哪些族可用 / 依据）；
* 装配：`build_terrain_entity(profile_id)` —— 档位 id → `TerrainEntityCfg`（未知档、未就绪档
  一律**报错退出**并列出可用档，绝不静默退回平地）；
* 可用性：`availability(profile_id, family)` —— 族维度的就绪状态（`ready` / `missing`），
  由门禁 `tools/audit_terrain_profiles.py` 逐条与"能不能真装配"对账。

技能 = 地形档 × 奖励档（× 动作先验档）：换机型不需要换地形代码，换地形也不需要动机型。
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_DIR = REPO_ROOT / "registry" / "terrains"

#: 已知的族名（与 registry/families 的 family_id 对齐）。
FAMILIES = ("quadruped", "wheel_leg")


class TerrainProfileError(ValueError):
    """档位不存在 / 未就绪 / 构造失败——一律 fail-closed。"""


def _read(name: str) -> dict[str, Any]:
    path = REGISTRY_DIR / name
    if not path.is_file():
        raise TerrainProfileError(f"地形档真值表缺失：{path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def profiles() -> dict[str, dict[str, Any]]:
    """档位 id → 档位声明（顺序同 index.json 的清单）。"""
    index = _read("index.json")
    table = {str(item["profile_id"]): dict(item) for item in _read("profiles.json")["profiles"]}
    ordered: dict[str, dict[str, Any]] = {}
    for entry in index.get("profiles") or []:
        pid = str(entry["profile_id"])
        if pid not in table:
            raise TerrainProfileError(f"index.json 登记了 {pid!r}，但 profiles.json 里没有该档")
        ordered[pid] = {**table[pid], **{k: v for k, v in entry.items() if k in ("class",)}}
    extra = sorted(set(table) - set(ordered))
    if extra:
        raise TerrainProfileError(f"profiles.json 里有未登记的档位：{extra}（未登记即未注册）")
    return ordered


def resolve(profile_id: str) -> dict[str, Any]:
    """按档位 id 取声明；未知档 fail-closed 并列出可用档。"""
    key = str(profile_id or "").strip()
    table = profiles()
    if key not in table:
        raise TerrainProfileError(
            f"未知地形档 {profile_id!r}；可用档：{', '.join(sorted(table))}"
            "（新增地形 = 在 registry/terrains/ 登记一行，不是在代码里加分支）"
        )
    return table[key]


def availability(profile_id: str, family: str) -> str:
    """某族在该档上的就绪状态（`ready` / `missing`）。"""
    if family not in FAMILIES:
        raise TerrainProfileError(f"未知族 {family!r}；已知：{', '.join(FAMILIES)}")
    entry = resolve(profile_id)
    status = (entry.get("availability") or {}).get(family)
    if status not in {"ready", "missing"}:
        raise TerrainProfileError(f"{profile_id} 未声明 {family} 的 availability（要么 ready 要么 missing）")
    return status


def build_terrain_entity(profile_id: str, *, family: str | None = None):
    """档位 id → `TerrainEntityCfg`（仅本模块能造出"地形实体"这一件事）。

    `kind` 分工：

    * ``flat``：平地（`terrain_type="plane"`）；
    * ``mjlab_generator``：用声明的 cfg，按 ``sub_terrains`` 过滤子地形（无 sub_terrains 则整族）；
    * ``family_kit``：地形由**族 Kit** 提供（竞赛构件 / 释放课程），本函数只做**就绪校验**
      并返回该族声明的 refs —— 真正的装配在对应族的 env cfg 里，避免把族专属构造搬到这里。
    """
    entry = resolve(profile_id)
    builder = entry.get("builder") or {}
    kind = str(builder.get("kind") or "")

    if kind == "family_kit":
        if family is None:
            raise TerrainProfileError(f"{profile_id} 是族 Kit 档，装配需指明 family")
        refs = builder.get(family)
        if not refs:
            raise TerrainProfileError(
                f"{profile_id} 在 {family} 族没有构造（availability={availability(profile_id, family)}）"
            )
        return {"kind": "family_kit", "profile_id": profile_id, "family": family, "refs": refs}

    if kind == "flat":
        from mjlab.terrains import TerrainEntityCfg  # 局部导入：控制面/门禁不为此拉 mjlab

        return TerrainEntityCfg(terrain_type="plane")

    if kind == "mjlab_generator":
        from mjlab.terrains import TerrainEntityCfg  # noqa: PLC0415

        cfg_path = str(builder.get("cfg") or "")
        module_name, _, attr = cfg_path.rpartition(".")
        if not module_name or not attr:
            raise TerrainProfileError(f"{profile_id} 的 builder.cfg 不是模块路径：{cfg_path!r}")
        import importlib

        generator = getattr(importlib.import_module(module_name), attr)
        wanted = tuple(builder.get("sub_terrains") or ())
        if wanted:
            available = dict(getattr(generator, "sub_terrains", {}) or {})
            missing = [name for name in wanted if name not in available]
            if missing:
                raise TerrainProfileError(
                    f"{profile_id}: 子地形 {missing} 不在 {cfg_path} 里（可用：{', '.join(sorted(available))}）"
                )
            generator = dataclasses.replace(generator, sub_terrains={name: available[name] for name in wanted})
        return TerrainEntityCfg(terrain_type="generator", terrain_generator=generator)

    raise TerrainProfileError(f"{profile_id}: 未知 builder.kind {kind!r}（可选：flat / mjlab_generator / family_kit）")


def family_for_morphology(morphology_id: str) -> str | None:
    """构型 id → 族名（真值在 `registry/families/*.json` 的 `morphology_ids`，不另立一套）。

    为什么要按注册表判族而不是字符串前缀猜：构型 id 是契约声明的，族归属是族声明的；
    两者一旦有人改口径，前缀猜会静默判错（例如把轮足判成四足）。
    """
    families_dir = REPO_ROOT / "registry" / "families"
    index_path = families_dir / "index.json"
    if not index_path.is_file():
        return None
    index = json.loads(index_path.read_text(encoding="utf-8-sig"))
    for entry in index.get("families") or []:
        path = families_dir / str(entry.get("path"))
        if not path.is_file():
            continue
        declared = json.loads(path.read_text(encoding="utf-8-sig"))
        if str(morphology_id) in [str(item) for item in declared.get("morphology_ids") or []]:
            return str(declared.get("family_id"))
    return None


def declared_ids() -> list[str]:
    return sorted(profiles())
