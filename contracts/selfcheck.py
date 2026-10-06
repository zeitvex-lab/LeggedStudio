"""Dependency-light smoke checks for the contracts package.

Run from the workspace root:
    python -m legged_studio.contracts.selfcheck
"""

from pathlib import Path

from .models import (
    InventoryDocument,
    SizeClass,
    filter_assets,
    load_robot_contract,
    size_class_for_mass,
)


def _scan_inventory_payload(root: Path) -> dict:
    """活扫描 ``assets/robots`` 构造最小清单 payload（与 backend.inventory 回退同源思想）。

    清单快照已退役（2026-10-06）：contracts 包零依赖，不能 import backend，
    故就地做同一件事的最小版本——只取本 selfcheck 断言需要的字段。
    """
    import json

    records = []
    for package_dir in sorted((root / "assets" / "robots").iterdir()):
        contract_path = package_dir / "contract.json"
        if not contract_path.is_file():
            continue
        contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
        joints = contract.get("joints") or {}
        mass = (contract.get("urdf") or {}).get("total_mass_kg")
        loco_raw = contract.get("locomotion_type")
        records.append({
            "path": f"assets/robots/{package_dir.name}/model/robot.xml",
            "format": "mjcf",
            "family": package_dir.name,
            "role": "robot",
            "joint_count": len(joints.get("actuated_joints") or []),
            "classification_mass_kg": mass,
            # v3 契约顶层自带 size_class（与 backend.inventory 活扫描同口径）
            "size_class_by_mass": contract.get("size_class")
            or (size_class_for_mass(mass).value if mass else None),
            "locomotion": "point_foot" if loco_raw in ("P", "B") else ("wheeled_leg" if loco_raw == "W" else None),
            "readiness": "direct_mujoco_candidate",
        })
    return {"schema_version": "1.0", "document_role": "scanned", "records": records}


def main() -> None:
    # 仓库布局：contracts/ 的上一级即仓库根（旧代码 parents[2] 是另一种安装布局的残留，
    # 在当前布局下指向文件系统根——随清单快照退役一并修正）。
    root = Path(__file__).resolve().parents[1]
    inventory = InventoryDocument.model_validate(_scan_inventory_payload(root))
    assert len(inventory.records) > 0
    assert size_class_for_mass(14.999) == SizeClass.S
    assert size_class_for_mass(15) == SizeClass.M
    assert size_class_for_mass(34.999) == SizeClass.M
    assert size_class_for_mass(35) == SizeClass.L
    go2 = filter_assets(inventory.records, family="unitree_go2")
    assert go2 and all(record.is_robot for record in go2)
    point_medium = filter_assets(
        inventory.records, size_class=SizeClass.M, locomotion="point_foot", usable_only=True
    )
    assert point_medium
    go2_contract = load_robot_contract(Path(__file__).parent / "fixtures" / "go2.v1.json")
    assert len(go2_contract.joints.canonical_order) == 12
    assert go2_contract.physics_hz is None
    assert go2_contract.joints.direction_multipliers is None
    print(
        f"contracts selfcheck passed: {len(inventory.records)} records, "
        f"{len(go2)} Go2 records, {len(point_medium)} usable M point-foot records, "
        f"{go2_contract.model_revision} fixture"
    )


if __name__ == "__main__":
    main()
