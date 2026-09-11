from pathlib import Path

from robolab.robots import (
    backend_asset_matrix,
    discover_robot_assets,
    isaacgym_asset,
    mjlab_asset,
)


EXPECTED_ROBOTS = {
    "anymal_b",
    "anymal_c",
    "bipedal_walker",
    "booster_k1",
    "cassie",
    "limx_tron1pf",
    "limx_tron1sf",
    "unitree_a1",
    "unitree_g1",
    "unitree_go2",
}


def test_all_tracked_robots_have_dual_backend_asset_bindings():
    assets = discover_robot_assets()
    assert set(assets) == EXPECTED_ROBOTS
    for robot_id in assets:
        assert isaacgym_asset(robot_id).suffix == ".urdf"
        assert mjlab_asset(robot_id).suffix in {".urdf", ".xml"}
        assert isaacgym_asset(robot_id).is_file()
        assert mjlab_asset(robot_id).is_file()


def test_matrix_distinguishes_native_mjcf_from_urdf_fallback():
    matrix = {row["robot"]: row for row in backend_asset_matrix()}
    assert matrix["unitree_a1"]["native_mjcf"] is True
    assert matrix["cassie"]["native_mjcf"] is False
    assert all(row["isaacgym"] and row["mjlab"] for row in matrix.values())


def test_backend_paths_stay_in_canonical_resource_tree():
    resource_root = Path("resources/robots").resolve()
    for robot_id in EXPECTED_ROBOTS:
        assert isaacgym_asset(robot_id).resolve().is_relative_to(resource_root)
        assert mjlab_asset(robot_id).resolve().is_relative_to(resource_root)
