"""资产清点路由（v3.0 Phase 2：自 ``api_complete`` 巨石下沉的域路由）。

桌面启动器只需要一个控制面进程，资产清点端点原先内联在 ``api_complete``；
按「api_complete 只做装配、业务路由归域文件」的拆解纪律移到本模块
（路径与行为零变化，测试经 ``app`` 全部照旧）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.inventory import InventoryError, dict_records, filter_records, load_inventory

router = APIRouter(tags=["assets"])


def _inventory_summary(inventory: dict[str, Any]) -> dict[str, Any]:
    records = dict_records(inventory)
    by_size: dict[str, int] = {}
    by_locomotion: dict[str, int] = {}
    families: set[str] = set()
    for record in records:
        size = str(record.get("size_class_by_mass") or "UNKNOWN")
        locomotion = str(record.get("locomotion") or "UNKNOWN")
        by_size[size] = by_size.get(size, 0) + 1
        by_locomotion[locomotion] = by_locomotion.get(locomotion, 0) + 1
        if record.get("family"):
            families.add(str(record["family"]))
    summary = dict(inventory.get("summary", {}))
    summary.update({
        "total": len(records),
        "count": len(records),
        "by_size": by_size,
        "by_locomotion": by_locomotion,
        "families": sorted(families),
        "schema_version": inventory.get("schema_version"),
        "document_role": inventory.get("document_role"),
        "size_taxonomy": inventory.get("size_taxonomy", {}),
    })
    return summary


@router.get("/api/assets/summary")
async def get_assets_summary() -> dict[str, Any]:
    try:
        return _inventory_summary(load_inventory())
    except InventoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/api/summary")
async def get_inventory_summary() -> dict[str, Any]:
    return await get_assets_summary()


@router.get("/api/assets")
async def get_assets(
    readiness: str | None = None,
    size: str | None = None,
    locomotion: str | None = None,
    family: str | None = None,
    offset: int = 0,
    limit: int = 500,
) -> dict[str, Any]:
    try:
        inventory = load_inventory()
    except InventoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    records = filter_records(
        dict_records(inventory), readiness=readiness, size=size,
        locomotion=locomotion, family=family,
    )
    offset = max(0, offset)
    limit = min(500, max(1, limit))
    return {"count": len(records), "offset": offset, "limit": limit, "records": records[offset:offset + limit]}


@router.get("/api/assets/{family_name}")
async def get_asset_family(family_name: str, readiness: str | None = None, size: str | None = None, locomotion: str | None = None) -> dict[str, Any]:
    try:
        inventory = load_inventory()
    except InventoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    records = filter_records(dict_records(inventory), readiness=readiness, size=size, locomotion=locomotion, family=family_name)
    if not records:
        raise HTTPException(status_code=404, detail=f"Unknown asset family: {family_name}")
    return {"family": family_name, "count": len(records), "records": records}
