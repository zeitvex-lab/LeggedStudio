"""**形态 Kit 的家**（2026-09-19 拍板落点）。

一个形态一份框架层真值，包内只留任务特有部分 + 入口 stub。

**Kit 归属表（数据驱动，Phase 3b 收口 2026-10-07 起）**：下表由 `registry/families/*.json`
的 `kit` 块（`kit_module` / `provides`）与各族成员生成，**不再手写** —— 新族 = 族 JSON 声明
+ 写 Kit，本表自动跟随；漂移由 `backend/test_kits_registry.py` 判红（旧手写表里那些
过期的「迁移中」字样就是这么积出来的）。

{kit_table}

**为什么不放仓库顶层 `kits/`**：包侧 stub 靠"沿目录向上找 `adapters/mjlab`"自举仓库根
（worker / schema-dump / 冒烟三处只把 `training/source` 放进 `sys.path`），位置一变，
全部 stub 与自举逻辑都要改；且既有裁决已把 Kit 划在 `adapters/mjlab/` 边界内。
决策依据与否决理由见 `00_know/90_归档/07_形态Kit设计草案.md`。

**不做什么**：不建人形 Kit（`g1` 只登记不迁）；冻结包（`limx_tron1_pf/sf/wf` /
`microduck` / `wuji_hand`）不参与任何 Kit 动作；Kit 里不放任何物理数值。

**共享件**（跨族，非某族专属）：本目录下的 `joint_actions.py` / `obstacle_course.py` /
`obstacle_terrains.py` / `terrain_curriculums.py` —— 各族 Kit 与通用装配器共用；
族专属部分在 `<族>_kit/`（含 `skills/` 族级技能层）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: 族注册表目录（本文件 = adapters/mjlab/kits/__init__.py，上溯三层即仓库根）。
_FAMILIES_DIR = Path(__file__).resolve().parents[3] / "registry" / "families"


def kit_ownership() -> list[dict[str, Any]]:
    """族注册表 → Kit 归属表的**数据形态**（唯一实现；表格与门禁都从这里派生）。

    返回按 `kit_module` 排序的条目：``{family_id, display_name, kit_module, morphology,
    members, binding_from_contract, provides}``。族文件缺失/损坏即抛（这不是可降级的事）。

    未声明 `kit` 块的族（例如只有数据、没有 Kit 实现的族）**跳过**——完整性由
    `backend/test_kits_registry.py` 按族逐个判（那里才是门禁）。
    """
    entries: list[dict[str, Any]] = []
    for path in sorted(_FAMILIES_DIR.glob("*.json")):
        if path.stem == "index":
            continue
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
        kit = doc.get("kit") or {}
        kit_module = kit.get("kit_module")
        if not kit_module:
            continue
        morphologies = list(doc.get("morphology_ids") or [])
        entries.append(
            {
                "family_id": doc.get("family_id") or path.stem,
                "display_name": doc.get("display_name") or doc.get("family_id") or path.stem,
                "kit_module": kit_module,
                "morphology": morphologies[0] if morphologies else None,
                "members": list(doc.get("members") or []),
                "binding_from_contract": kit.get("binding_from_contract"),
                "provides": list(kit.get("provides") or []),
            }
        )
    entries.sort(key=lambda item: str(item["kit_module"]))
    return entries


def _short(entry: str) -> str:
    """``module:attr`` → ``attr``；裸模块 → 末段。"""
    return entry.rsplit(":", 1)[1] if ":" in entry else entry.rsplit(".", 1)[-1]


def render_ownership_table(entries: list[dict[str, Any]]) -> str:
    """归属表数据 → markdown 表（供文件头 docstring 使用）。"""
    lines = ["| Kit | 形态 | 成员机型 | 提供（入口点） |", "|---|---|---|---|"]
    for item in entries:
        provides = " · ".join(f"`{_short(entry)}`" for entry in item["provides"]) or "—"
        members = " · ".join(item["members"]) or "—"
        kit_name = str(item["kit_module"]).rsplit(".", 1)[-1]
        lines.append(f"| `{kit_name}` | {item['display_name']} | {members} | {provides} |")
    return "\n".join(lines)


def _kit_table() -> str:
    """生成归属表；失败**如实降级为一行说明**（文档坏了要看得见，但不该让 import 崩）。"""
    try:
        return render_ownership_table(kit_ownership())
    except Exception as exc:  # noqa: BLE001 - 这里刻意兜底，失败信息随表打印
        return f"（归属表生成失败：{type(exc).__name__}: {exc}）"


__doc__ = (__doc__ or "").replace("{kit_table}", _kit_table())
__all__ = ["kit_ownership", "render_ownership_table"]
