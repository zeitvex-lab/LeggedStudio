"""Generic backend asset bindings for ``resources/robots``."""

from __future__ import annotations

from pathlib import Path

from .registry import RobotAsset, discover_robot_assets, get_robot_asset


def isaacgym_asset(robot_id: str, root: Path | None = None) -> Path:
    asset = get_robot_asset(robot_id, root)
    if not asset.urdf:
        raise FileNotFoundError(f"{robot_id} has no URDF for Isaac Gym")
    return asset.urdf[0]


def mjlab_asset(robot_id: str, root: Path | None = None) -> Path:
    asset = get_robot_asset(robot_id, root)
    if asset.mjcf:
        return asset.mjcf[0]
    if asset.urdf:
        return asset.urdf[0]
    raise FileNotFoundError(f"{robot_id} has neither MJCF nor URDF for MJLab")


def build_mjlab_spec(robot_id: str, root: Path | None = None):
    """Load a fresh MuJoCo spec without importing MuJoCo in the host process."""

    import mujoco

    return mujoco.MjSpec.from_file(str(mjlab_asset(robot_id, root)))


def backend_asset_matrix(root: Path | None = None) -> list[dict[str, object]]:
    return [
        {
            "robot": asset.robot_id,
            "isaacgym": asset.isaacgym_ready,
            "mjlab": asset.mjlab_ready,
            "native_mjcf": bool(asset.mjcf),
            "urdf": [str(p) for p in asset.urdf],
            "mjcf": [str(p) for p in asset.mjcf],
        }
        for asset in discover_robot_assets(root).values()
    ]


__all__ = [
    "RobotAsset",
    "backend_asset_matrix",
    "build_mjlab_spec",
    "discover_robot_assets",
    "isaacgym_asset",
    "mjlab_asset",
]
