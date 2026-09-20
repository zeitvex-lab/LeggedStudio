"""Capability 导出物的 **Web 入口**（序 10「发得出去」）。

## 缺口的准确形状（2026-09-20 取证）

`backend/bundle_export.py` 里 `list_exports()` 的注释写着"供 **CLI/页面** 展示"，而实测：
**CLI 有（`export <kind>` / `verify bundle`）、页面没有、API 也没有**。也就是说"发得出去"
这条路上，能打包的是命令行用户；页面用户既看不到自己有什么导出物，也没法把一个包交出去。
本模块补的就是这层入口，判据/打包**一律委托 `bundle_export`**（不另写一套，避免"页面导出的
和 CLI 导出的不是一回事"）。

## 两条安全纪律（API 与 CLI 的差别就在这里）

1. **只按"名字"认目录**：所有读路径的操作（list / detail / import）都取 `<workspace>/exports/<名字>`
   并**拒绝**空名、`.`/`..`、含分隔符的名字 —— 页面来的是用户输入，不能当路径用。
2. **不凭空造新目录**：导入一个收到的场景包**只做校验并回载荷**（调用方拿它去跑/预填编辑器），
   不往磁盘写新位置。落盘只有一处：打包（导出）写到 `<workspace>/exports/`，且**默认不覆盖**
   已存在的同名导出物（要覆盖必须显式 `overwrite=true`）。
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.paths import api_path, workspace_root as _workspace_root

router = APIRouter(prefix="/api/exports", tags=["exports"])

#: 导出物的家（与 `bundle_export.default_out_dir` 同一处：`<workspace>/exports`）。
EXPORTS_DIR_NAME = "exports"


class ScenarioExportRequest(BaseModel):
    """打包一份场景：给**内联载荷**（页面主路径）或仓库内文件路径，二选一。"""

    scenario: dict[str, Any] | None = None
    scenario_path: str | None = None
    out_name: str | None = None
    overwrite: bool = False


class BundleExportRequest(BaseModel):
    """打包一个 Bundle（Pack 引用 + **被引用物离线副本** + 哈希）。"""

    pack: str
    scenario: dict[str, Any] | None = None
    artifact_id: str | None = None
    out_name: str | None = None
    overwrite: bool = False


class ImportScenarioRequest(BaseModel):
    name: str


def _exports_root() -> Path:
    return _workspace_root() / EXPORTS_DIR_NAME


def _safe_export_name(name: str | None) -> str:
    """导出名只许是**单段**目录名（页面输入不能当路径用）。"""

    value = str(name or "").strip()
    if not value or value in {".", ".."} or ".." in value or "/" in value or "\\" in value:
        raise HTTPException(status_code=400, detail=f"非法的导出名：{name!r}（只允许单段目录名，禁止分隔符与 ..）")
    return value


def _export_dir(name: str | None) -> Path:
    """名字 → `<workspace>/exports/<名字>`（必须已存在）。"""

    target = _exports_root() / _safe_export_name(name)
    if not target.is_dir():
        raise HTTPException(status_code=404, detail=f"没有这个导出物：{name!r}（在 {api_path(_exports_root())} 下）")
    return target


def _repo_relative_file(value: str) -> Path:
    """仓库相对文件（拒绝绝对路径与越界——与 `bundle_export._safe_relative` 同一取向）。"""

    raw = str(value or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or ".." in Path(raw).parts or (len(raw) > 1 and raw[1] == ":"):
        raise HTTPException(status_code=400, detail=f"只接受仓库相对路径（禁止绝对路径与 ..）：{value!r}")
    candidate = Path(__file__).resolve().parents[1] / raw
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在：{value!r}")
    return candidate


def _prepare_out_dir(name: str, *, overwrite: bool) -> Path:
    """打包落点：已存在且非空 ⇒ 默认拒绝（不覆盖别人的导出物）。"""

    out = _exports_root() / _safe_export_name(name)
    if out.exists() and any(out.iterdir()) and not overwrite:
        raise HTTPException(
            status_code=409,
            detail=f"{api_path(out)} 已存在且非空；要覆盖请显式 overwrite=true（或换个 out_name）",
        )
    out.mkdir(parents=True, exist_ok=True)
    return out


@router.get("")
async def list_capability_exports() -> dict[str, Any]:
    """列出工作区里已有的导出物（含逐项 `verify_export` 结论）。"""

    from backend.bundle_export import list_exports

    items = list_exports()
    return {
        "success": True,
        "count": len(items),
        "broken": sum(1 for item in items if not item.get("ok")),
        "root": api_path(_exports_root()),
        "exports": items,
    }


@router.get("/{name}")
async def capability_export_detail(name: str) -> dict[str, Any]:
    """单个导出物的完整校验报告（缺文件 / sha256 不符 / 幽灵文件 / 未解析项）。"""

    from backend.bundle_export import verify_export

    report = verify_export(_export_dir(name))
    return {"success": bool(report.get("ok")), "name": name, **report}


@router.post("/scenario")
async def create_scenario_export(request: ScenarioExportRequest) -> dict[str, Any]:
    """**打包场景**：内联载荷或仓库内文件 → `<workspace>/exports/scenario-<名字>`。"""

    from backend.bundle_export import default_out_dir, export_scenario, verify_export
    from contracts.scenario_contract import ScenarioContract

    if request.scenario is None and not request.scenario_path:
        raise HTTPException(status_code=400, detail="要么给 scenario（内联载荷）、要么给 scenario_path（仓库内文件）")

    temporary: Path | None = None
    try:
        if request.scenario is not None:
            try:
                contract = ScenarioContract(**request.scenario)  # 与导出口**同一道闸**
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"场景不合法：{exc}") from exc
            name = request.out_name or contract.scenario_id
            handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
            import json

            json.dump(contract.to_payload(), handle, ensure_ascii=False, indent=2)
            handle.close()
            temporary = Path(handle.name)
            source = temporary
        else:
            source = _repo_relative_file(str(request.scenario_path))
            name = request.out_name or source.stem

        out = default_out_dir("scenario", _safe_export_name(name))
        if request.out_name:
            out = _prepare_out_dir(request.out_name, overwrite=request.overwrite)
        elif out.exists() and any(out.iterdir()) and not request.overwrite:
            raise HTTPException(status_code=409, detail=f"{api_path(out)} 已存在且非空；要覆盖请显式 overwrite=true")
        manifest = export_scenario(source, out)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

    report = verify_export(out)
    return {
        "success": bool(report.get("ok")),
        "out_dir": api_path(out),
        "manifest": manifest,
        "verify": report,
    }


@router.post("/bundle")
async def create_bundle_export(request: BundleExportRequest) -> dict[str, Any]:
    """**打包 Bundle**（分发的主体形态：Pack 引用 + 被引用物离线副本 + 哈希）。"""

    from backend.bundle_export import default_out_dir, export_bundle, verify_export
    from contracts.scenario_contract import ScenarioContract

    pack = _repo_relative_file(request.pack)
    scenario_path: Path | None = None
    temporary: Path | None = None
    try:
        if request.scenario is not None:
            try:
                contract = ScenarioContract(**request.scenario)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"内嵌场景不合法：{exc}") from exc
            import json

            handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
            json.dump(contract.to_payload(), handle, ensure_ascii=False, indent=2)
            handle.close()
            temporary = Path(handle.name)
            scenario_path = temporary
        name = request.out_name or pack.name.replace(".pack.json", "")
        out = _prepare_out_dir(request.out_name or f"bundle-{name}", overwrite=request.overwrite) if request.out_name else default_out_dir("bundle", name)
        manifest = export_bundle(pack, out, artifact_id=request.artifact_id, scenario_path=scenario_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

    report = verify_export(out)
    return {
        "success": bool(report.get("ok")),
        "out_dir": api_path(out),
        "manifest": manifest,
        "verify": report,
    }


@router.post("/import-scenario")
async def import_scenario_export(request: ImportScenarioRequest) -> dict[str, Any]:
    """**收下别人给的场景包**：校验（完整性 + 契约）并回载荷，**不落盘**。

    调用方拿到 `scenario` 之后可以：预填 Scenario 编辑器、或直接送进
    `POST /api/simulation/sessions`。不落盘是刻意的——"导入到哪里"没有唯一答案，
    凭空造一个目录比不写更糟；要归档就把包放在 `<workspace>/exports/` 下（本接口正从这里读）。
    """

    from backend.bundle_export import import_scenario

    try:
        result = import_scenario(_export_dir(request.name))
    except FileExistsError as exc:  # pragma: no cover - 本接口不写盘，出现即说明语义变了
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "name": request.name, **result}
