"""Backend-neutral discovery of tracked robot assets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RobotAsset:
    robot_id: str
    root: Path
    urdf: tuple[Path, ...]
    mjcf: tuple[Path, ...]
    mesh_root: Path

    @property
    def isaacgym_ready(self) -> bool:
        return bool(self.urdf)

    @property
    def mjlab_ready(self) -> bool:
        # MuJoCo accepts both MJCF and URDF.  Native MJCF remains preferable
        # because it can express actuators, sensors and contact tuning.
        return bool(self.mjcf or self.urdf)

    @property
    def dual_format(self) -> bool:
        return bool(self.urdf and self.mjcf)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def discover_robot_assets(root: Path | None = None) -> dict[str, RobotAsset]:
    assets_root = (root or repository_root()) / "resources" / "robots"
    result: dict[str, RobotAsset] = {}
    for path in sorted(p for p in assets_root.iterdir() if p.is_dir()):
        urdf = tuple(sorted(path.rglob("*.urdf")))
        mjcf = tuple(sorted(p for p in path.rglob("*.xml") if p.name != "scene.xml"))
        result[path.name] = RobotAsset(path.name, path, urdf, mjcf, path / "meshes")
    return result


def get_robot_asset(robot_id: str, root: Path | None = None) -> RobotAsset:
    try:
        return discover_robot_assets(root)[robot_id]
    except KeyError as exc:
        raise KeyError(f"unknown robot asset: {robot_id}") from exc


__all__ = ["RobotAsset", "discover_robot_assets", "get_robot_asset", "repository_root"]
