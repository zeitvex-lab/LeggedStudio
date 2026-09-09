"""observation_convergence 测试：PolicyContract 字段级表述 ←→ v3 observation 收敛。"""

from __future__ import annotations

import unittest

from contracts.observation_convergence import (
    FieldSpec,
    ObservationConvergenceError,
    align_observation_fields,
    normalize_source,
    validate_v3_observation,
)


class AlignObservationFieldsTest(unittest.TestCase):
    def test_basic_align(self) -> None:
        conv = align_observation_fields(
            [
                FieldSpec("actor", 45, source="actuated"),
                FieldSpec("cmd", 3, source="cmd"),
            ],
            dimension=48,
            history_length=10,
        )
        self.assertEqual(conv.dimension, 48)
        self.assertEqual(conv.summary_width, 48)
        self.assertEqual(conv.history_length, 10)
        self.assertEqual(conv.history_order, "oldest_to_newest")
        self.assertEqual(len(conv.components), 2)

    def test_dimension_inferred(self) -> None:
        conv = align_observation_fields([FieldSpec("a", 4), FieldSpec("b", 6)])
        self.assertEqual(conv.dimension, 10)

    def test_dimension_mismatch_raises(self) -> None:
        with self.assertRaises(ObservationConvergenceError):
            align_observation_fields([FieldSpec("a", 4)], dimension=8)

    def test_duplicate_name_raises(self) -> None:
        with self.assertRaises(ObservationConvergenceError):
            align_observation_fields([FieldSpec("a", 1), FieldSpec("a", 2)])

    def test_bad_history_metadata_raises(self) -> None:
        with self.assertRaises(ObservationConvergenceError):
            align_observation_fields([FieldSpec("a", 1)], history_length=-1)
        with self.assertRaises(ObservationConvergenceError):
            align_observation_fields([FieldSpec("a", 1)], history_order="bad")
        with self.assertRaises(ObservationConvergenceError):
            align_observation_fields([FieldSpec("a", 1)], history_reset="bad")

    def test_dict_input(self) -> None:
        conv = align_observation_fields(
            [
                {"name": "base_ang_vel", "width": 3, "source": "imu", "scale": 0.25},
                {"name": "actions", "width": 12, "source": "action"},
            ],
            dimension=15,
        )
        self.assertEqual(conv.summary_width, 15)
        self.assertEqual(conv.components[0].source, "imu")
        self.assertEqual(conv.components[0].scale, 0.25)


class NormalizeSourceTest(unittest.TestCase):
    def test_known(self) -> None:
        self.assertEqual(normalize_source("imu"), "imu")
        self.assertEqual(normalize_source("external"), "external")

    def test_unknown_falls_back(self) -> None:
        self.assertEqual(normalize_source("heightfield"), "external")
        self.assertEqual(normalize_source(None), "external")


class ValidateV3ObservationTest(unittest.TestCase):
    def test_valid(self) -> None:
        obs = {
            "dimension": 48,
            "components": [
                {"name": "actor", "width": 45, "source": "actuated"},
                {"name": "cmd", "width": 3, "source": "cmd"},
            ],
            "history_length": 10,
            "history_order": "oldest_to_newest",
            "history_reset": "zero",
        }
        self.assertEqual(validate_v3_observation(obs), [])

    def test_dim_mismatch(self) -> None:
        obs = {
            "dimension": 48,
            "components": [{"name": "a", "width": 40, "source": "actuated"}],
        }
        self.assertIn("!= Σcomponents.width", validate_v3_observation(obs)[0])

    def test_dup_name(self) -> None:
        obs = {
            "dimension": 2,
            "components": [
                {"name": "a", "width": 1, "source": "imu"},
                {"name": "a", "width": 1, "source": "imu"},
            ],
        }
        self.assertIn("名称重复", validate_v3_observation(obs)[0])

    def test_invalid_history(self) -> None:
        obs = {"dimension": 0, "components": [], "history_order": "bad"}
        self.assertTrue(any("history_order" in e for e in validate_v3_observation(obs)))


if __name__ == "__main__":
    unittest.main()
