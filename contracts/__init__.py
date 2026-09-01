"""Stable data contracts shared by Legged Studio services.

The contracts package intentionally contains no simulator or web imports.  It can
be used by inventory tooling, adapters, and the API layer independently.
"""

from .models import (
    AssetRecord,
    AssetRole,
    ContractEvidence,
    InventoryDocument,
    Locomotion,
    Readiness,
    RobotContract,
    SizeClass,
    SizeClassLike,
    load_inventory,
    load_robot_contract,
    load_asset_records,
    filter_assets,
    size_class_for_mass,
)

__all__ = [
    "AssetRecord",
    "AssetRole",
    "ContractEvidence",
    "InventoryDocument",
    "Locomotion",
    "Readiness",
    "RobotContract",
    "SizeClass",
    "SizeClassLike",
    "load_inventory",
    "load_robot_contract",
    "load_asset_records",
    "filter_assets",
    "size_class_for_mass",
]
