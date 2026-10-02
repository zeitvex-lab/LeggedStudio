"""mjcf_parity 纯函数回归锁：本体保真门的 diff 核（误报/漏报都会误导本体裁决）。"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("mjcf_parity", ROOT / "tools" / "mjcf_parity.py")
mp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mp)

import mujoco

_TPL = """
<mujoco model="t">
  <worldbody>
    <body name="b1" pos="0 0 1">
      <inertial pos="0 0 0" mass="{mass}" diaginertia="0.01 0.01 0.01"/>
      <joint name="j1" type="hinge" axis="0 0 1" damping="0.1" armature="0.01"/>
      <geom name="g1" type="box" size="0.1 0.1 0.1" mass="0.5"/>
    </body>
  </worldbody>
</mujoco>
"""


def _spec(mass: float) -> mujoco.MjSpec:
    return mujoco.MjSpec.from_string(_TPL.format(mass=mass))


class MjcfParityDiffTest(unittest.TestCase):
    def test_identical_specs_are_clean(self):
        report = mp.diff_mjcf(_spec(1.0), _spec(1.0))
        self.assertTrue(report["ok"], report["categories"])
        self.assertEqual([], report["categories"]["bodies"]["fields"])
        self.assertEqual([], report["categories"]["joints"]["fields"])

    def test_mass_delta_is_caught_by_name_and_field(self):
        report = mp.diff_mjcf(_spec(1.0), _spec(2.0))
        self.assertFalse(report["ok"])
        field = next(f for f in report["categories"]["bodies"]["fields"] if f["name"] == "b1")
        self.assertEqual("mass", field["field"])
        self.assertEqual(1.0, field["ours"])
        self.assertEqual(2.0, field["theirs"])

    def test_armature_delta_is_caught(self):
        s1 = _spec(1.0)
        s2 = _spec(1.0)
        next(j for j in s2.joints if j.name == "j1").armature = 0.02
        report = mp.diff_mjcf(s1, s2)
        field = next(f for f in report["categories"]["joints"]["fields"] if f["name"] == "j1")
        self.assertEqual("armature", field["field"])

    def test_world_body_nan_never_counts_as_delta(self):
        # world 体无惯量声明（ipos=nan）：nan≠nan 曾制造伪 delta 挡住真结论（2026-10-02 实测）
        report = mp.diff_mjcf(_spec(1.0), _spec(1.0))
        self.assertEqual([], [f for f in report["categories"]["bodies"]["fields"] if f["name"] == "world"])


if __name__ == "__main__":
    unittest.main()
