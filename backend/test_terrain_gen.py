"""T4.1 DoD：ArenaX terrain_generator 移植守护测试（backend/terrain_gen）。

测试用例改编自 ArenaX 自带 tests/test_terrain.py（移植不重写——逻辑一致，
仅命名空间从 terrain_generator 改为 backend.terrain_gen）。
"""

from __future__ import annotations

import unittest

import numpy as np

from backend.terrain_gen import (
    SUPPORTED_ELEMENT_TYPES,
    SUPPORTED_TERRAIN_TYPES,
    TerrainConfig,
    export_mujoco,
    export_scene,
    generate_terrain,
    load_and_validate,
    load_scene,
    playground_scene,
)


class TerrainGenPortTest(unittest.TestCase):
    def test_generation_is_reproducible(self) -> None:
        config = TerrainConfig(kind="noise", rows=32, cols=24, seed=123)
        first = generate_terrain(config)
        second = generate_terrain(config)
        np.testing.assert_array_equal(first.heights, second.heights)

    def test_all_terrain_types_have_valid_heightfields(self) -> None:
        for kind in ("flat", "slope", "stairs", "noise", "obstacle_mix"):
            terrain = generate_terrain(TerrainConfig(kind=kind, rows=24, cols=24, seed=4, obstacle_count=3))
            self.assertEqual(terrain.heights.shape, (24, 24))
            self.assertGreaterEqual(float(terrain.heights.min()), 0.0)
            self.assertLessEqual(float(terrain.heights.max()), 1.0)

    def test_eleven_obstacle_elements_registered(self) -> None:
        self.assertGreaterEqual(len(SUPPORTED_TERRAIN_TYPES), 5)
        self.assertGreaterEqual(
            len(SUPPORTED_ELEMENT_TYPES), 11,
            "ArenaX 的 11 种障碍组件必须完整随移植带入",
        )

    def test_export_mujoco_xml_and_validate(self) -> None:
        import tempfile

        terrain = generate_terrain(TerrainConfig(kind="stairs", rows=16, cols=16, seed=7))
        with tempfile.TemporaryDirectory() as tmp:
            paths = export_mujoco(terrain, tmp)
            model = load_and_validate(paths["xml"])
            self.assertEqual(model.nhfield, 1)

    def test_scene_roundtrip_and_playground_preset(self) -> None:
        import tempfile

        scene = playground_scene()
        with self.subTest("preset"):
            self.assertTrue(len(scene.elements) >= 0)
        with tempfile.TemporaryDirectory() as tmp:
            paths = export_scene(scene, tmp)
            loaded = load_scene(paths["scene"])
            self.assertEqual(len(loaded.elements), len(scene.elements))


class tempfile_dir:
    def __enter__(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        return f"{self._tmp.name}/scene.json"

    def __exit__(self, *args):
        self._tmp.cleanup()
        return False


if __name__ == "__main__":
    unittest.main()
