"""Dependency-light smoke checks for the contracts package.

Run from the workspace root:
    python -m legged_studio.contracts.selfcheck
"""

from pathlib import Path

from .models import (
    SizeClass,
    filter_assets,
    load_inventory,
    load_robot_contract,
    size_class_for_mass,
)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    inventory = load_inventory(root / "QUADRUPED_ASSET_INVENTORY.json")
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
