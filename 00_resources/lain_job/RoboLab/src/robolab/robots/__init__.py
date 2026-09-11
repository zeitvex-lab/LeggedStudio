"""Robot asset discovery and backend bindings."""

from .bindings import (
    backend_asset_matrix,
    build_mjlab_spec,
    isaacgym_asset,
    mjlab_asset,
)
from .registry import RobotAsset, discover_robot_assets, get_robot_asset
from .profiles import PROFILES, RobotTaskProfile, get_task_profile

__all__ = [
    "RobotAsset",
    "backend_asset_matrix",
    "build_mjlab_spec",
    "discover_robot_assets",
    "get_robot_asset",
    "isaacgym_asset",
    "mjlab_asset",
    "PROFILES",
    "RobotTaskProfile",
    "get_task_profile",
]
