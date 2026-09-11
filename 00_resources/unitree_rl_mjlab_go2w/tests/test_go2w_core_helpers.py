from __future__ import annotations

import sys
import unittest
from pathlib import Path

import mujoco

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(_REPO_ROOT))

from mjlab.asset_zoo.robots.unitree_go2w.go2w_constants import (
  get_go2w_robot_cfg,
  get_spec,
)
from mjlab.entity import Entity, EntityCfg
from mjlab.utils.spec import is_joint_limited


class Go2WCoreHelpersTest(unittest.TestCase):
  def test_go2w_mjcf_compiles_with_expected_joint_structure(self) -> None:
    spec = get_spec()
    model = spec.compile()

    joint_names = [model.joint(i).name for i in range(model.njnt)]
    named_joint_names = [name for name in joint_names if name]
    wheel_joint_names = {name for name in named_joint_names if name.endswith("_wheel_joint")}

    self.assertEqual(len(named_joint_names), 16)
    self.assertEqual(
      wheel_joint_names,
      {
        "FR_wheel_joint",
        "FL_wheel_joint",
        "RR_wheel_joint",
        "RL_wheel_joint",
      },
    )

    entity = Entity(get_go2w_robot_cfg())
    self.assertEqual(entity.num_actuators, 16)

  def test_find_joints_by_actuator_names_preserves_requested_order(self) -> None:
    entity = Entity(get_go2w_robot_cfg())
    requested = ["RL_wheel_joint", "FR_wheel_joint", "RR_wheel_joint"]
    expected_natural = [name for name in entity.joint_names if name in requested]

    natural_ids, natural_names = entity.find_joints_by_actuator_names(requested)
    ordered_ids, ordered_names = entity.find_joints_by_actuator_names(
      requested,
      preserve_order=True,
    )

    self.assertEqual(natural_names, expected_natural)
    self.assertEqual(ordered_names, requested)
    self.assertNotEqual(natural_ids, ordered_ids)

  def test_compute_indexing_supports_unnamed_joints(self) -> None:
    xml = """
    <mujoco model="unnamed-joints">
      <worldbody>
        <body name="base">
          <joint type="hinge" axis="0 0 1"/>
          <geom type="box" size="0.1 0.1 0.1" mass="1.0"/>
          <body name="link" pos="0 0 0.2">
            <joint type="hinge" axis="0 1 0"/>
            <geom type="capsule" fromto="0 0 0 0 0 0.2" size="0.03" mass="0.1"/>
          </body>
        </body>
      </worldbody>
    </mujoco>
    """
    entity = Entity(EntityCfg(spec_fn=lambda: mujoco.MjSpec.from_string(xml)))
    model = entity.compile()

    indexing = entity._compute_indexing(model, device="cpu")

    self.assertEqual(indexing.joint_ids.tolist(), [0, 1])
    self.assertEqual(len(indexing.joint_q_adr), 2)
    self.assertEqual(len(indexing.joint_v_adr), 2)

  def test_go2w_wheel_velocity_actuators_disable_inherited_ctrl_ranges(self) -> None:
    entity = Entity(get_go2w_robot_cfg())
    wheel_joint = entity.spec.joint("FR_wheel_joint")
    wheel_actuator = next(
      actuator for actuator in entity.spec.actuators if actuator.name == "FR_wheel_joint"
    )

    self.assertFalse(is_joint_limited(wheel_joint))
    self.assertFalse(wheel_actuator.ctrllimited)
    self.assertEqual(float(wheel_actuator.inheritrange), 0.0)


if __name__ == "__main__":
  unittest.main()
