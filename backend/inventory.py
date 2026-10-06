"""Read-only asset-inventory helpers shared by the control plane and tooling.

**默认行为 = 活扫描 ``assets/robots/``**（2026-10-06 起）：清单快照
（``QUADRUPED_ASSET_INVENTORY.json`` 且名带已删机型前缀）已退役——15 条陈旧记录
与 8 个真实包不一致，而 wheel/Electron 打包从未携带它（发行侧一直走扫描）
⇒ dev 与发行分叉。活扫描让两边同源、永不漂移；``LEGGED_STUDIO_INVENTORY``
仍可钉一份外部清单（测试/特殊部署用）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parent
# The repository root: one level above the ``backend`` package.
PROJECT_ROOT = BACKEND_DIR.parent
#: 外部清单钉入点（测试/特殊部署）：**只有设了** ``LEGGED_STUDIO_INVENTORY`` 才读文件；
#: 未设 = 活扫描 ``assets/robots/``（清单快照已退役，代码里不再挂陈旧文件名）。
INVENTORY_PATH: Path | None = (
    Path(os.environ["LEGGED_STUDIO_INVENTORY"]).expanduser().resolve()
    if os.environ.get("LEGGED_STUDIO_INVENTORY")
    else None
)


class InventoryError(RuntimeError):
    """Raised when the read-only inventory cannot be loaded."""


def _scan_default_inventory() -> dict[str, Any]:
    """Build a lightweight inventory by scanning ``assets/robots`` packages.

    Used as a fallback when the inventory file is absent on a fresh checkout.
    Fields requiring a full MuJoCo/URDF probe are left null.
    """
    import re as _re

    robots_root = PROJECT_ROOT / "assets" / "robots"
    records: list[dict[str, Any]] = []
    if robots_root.is_dir():
        for package_dir in sorted(robots_root.iterdir()):
            contract_path = package_dir / "contract.json"
            if not package_dir.is_dir() or not contract_path.exists():
                continue
            try:
                contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            package_id = package_dir.name
            mass = (contract.get("urdf") or {}).get("total_mass_kg")
            # v3 契约顶层自带 size_class（S/M/L）——质量真值在 MJCF 编译期才有（mass_source=
            # mjcf_compiled），扫描不编译模型，故优先读契约声明、缺失才按质量推（2026-10-06 修：
            # 此前只读 urdf.total_mass_kg，v3 契约该段为空 ⇒ size_class 恒 None）
            size = contract.get("size_class") or _mass_size(mass)
            joints = contract.get("joints") or {}
            actuated = (joints.get("actuated_joints") or [])
            loco_raw = contract.get("locomotion_type")
            records.append({
                "path": f"assets/robots/{package_id}/model/robot.xml",
                "format": "mjcf",
                "model_name": contract.get("family") or package_id,
                "family": package_id,
                "quadruped": loco_raw != "H",
                "role": "robot",
                "joint_count": len(actuated),
                "joint_names": list(actuated),
                "locomotion": "point_foot" if loco_raw in ("P", "B") else ("wheeled_leg" if loco_raw == "W" else None),
                "classification_mass_kg": mass,
                "size_class_by_mass": size,
                "quality": "ok",
                "readiness": "direct_mujoco_candidate",
                "missing_mesh_ref_count": 0,
                "missing_include_ref_count": 0,
            })
    return {"schema_version": "1.0", "document_role": "scanned fallback", "summary": {"total": len(records)}, "records": records}


def _mass_size(mass: float | None) -> str | None:
    if mass is None or mass <= 0:
        return None
    if mass < 15:
        return "S"
    if mass < 35:
        return "M"
    return "L"


def load_inventory(path: Path | None = None) -> dict[str, Any]:
    """读资产清单：显式 path > 环境变量钉入 > **活扫描**（默认）。"""
    # JSON 读取走单一来源（``utf-8-sig`` 吃 BOM）：旧实现是 ``path.open(encoding="utf-8")``，
    # 带 BOM 的清单会在第一个字节就抛（报错只说 Expecting value，不指向编码）。
    from contracts.jsonio import load_json

    if path is None:
        path = INVENTORY_PATH
    if path is None:
        return _scan_default_inventory()
    try:
        value = load_json(path)
    except FileNotFoundError:
        return _scan_default_inventory()
    except json.JSONDecodeError as exc:
        raise InventoryError(f"Inventory is not valid JSON: {path}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("records"), list):
        raise InventoryError("Inventory must be an object containing a records array")
    return value


def dict_records(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    """Drop non-object entries so filters and summaries can index safely."""
    return [record for record in inventory["records"] if isinstance(record, dict)]


def filter_records(
    records: list[dict[str, Any]],
    *,
    readiness: str | None = None,
    size: str | None = None,
    locomotion: str | None = None,
    family: str | None = None,
) -> list[dict[str, Any]]:
    """Apply exact, case-insensitive filters shared by every inventory consumer."""

    def matches(record: dict[str, Any], key: str, expected: str | None) -> bool:
        return expected is None or str(record.get(key, "")).lower() == expected.lower()

    return [
        record
        for record in records
        if matches(record, "readiness", readiness)
        and matches(record, "size_class_by_mass", size)
        and matches(record, "locomotion", locomotion)
        and matches(record, "family", family)
    ]
