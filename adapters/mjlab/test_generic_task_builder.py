import tempfile
import unittest
from pathlib import Path

from adapters.mjlab.generic_task_builder import build_generic_task


def _cartpole_contract(path: Path, joint: str = "slider") -> dict:
    return {
        "contract_id": "generic_fixture",
        "urdf": {"path": str(path)},
        "joints": {"actuated_joints": [joint], "default_pose": [0.0]},
        "action": {"joint_order": [joint], "action_scale": 0.5},
        "observation": {"components": ["joint_pos", "joint_vel", "last_action"]},
        "control": {"decimation": 5, "physics_hz": 100},
    }


# 真实机型（lite3 / m20 的 MJCF）里存在 **无 name 的 <gyro>/<accelerometer>**：
# MuJoCo 接受无名传感器，但 mjlab 的 scene 会把每个 spec 传感器按名包成
# BuiltinSensor（`mj_model.sensor('')` → KeyError: Invalid name ''），环境直接建不起来。
_NAMELESS_SENSOR_XML = """<mujoco model="unnamed_sensor_fixture">
  <worldbody>
    <body name="base" pos="0 0 0.2">
      <freejoint name="root"/>
      <geom name="base_geom" type="box" size="0.1 0.1 0.1"/>
      <site name="imu_site" pos="0 0 0.02"/>
    </body>
  </worldbody>
  <sensor>
    <velocimeter name="imu_lin_vel" site="imu_site"/>
    <gyro site="imu_site"/>
    <accelerometer site="imu_site"/>
    <framepos name="base_pos" objtype="site" objname="imu_site"/>
  </sensor>
</mujoco>
"""

# go2 的 robot.xml 在 default class 上写 margin="0.001"；与地形 BOX 成对时，
# mujoco_warp 的 _check_margin 会在 MULTICCD（默认开）下直接 NotImplementedError。
_MARGIN_XML = """<mujoco model="geom_margin_fixture">
  <default>
    <geom margin="0.001"/>
  </default>
  <worldbody>
    <body name="base" pos="0 0 0.2">
      <joint name="base_joint" type="hinge" axis="0 0 1"/>
      <geom name="base_geom" type="box" size="0.1 0.1 0.1"/>
    </body>
  </worldbody>
  <actuator>
    <motor name="base_motor" joint="base_joint"/>
  </actuator>
</mujoco>
"""


class GenericTaskBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import mjlab

        cls.xml = Path(mjlab.__file__).resolve().parent / "tasks" / "cartpole" / "cartpole.xml"
        if not cls.xml.exists():
            raise unittest.SkipTest("MJLab cartpole fixture is unavailable")

    def test_builds_from_contract_and_binds_xml_actuator(self):
        bundle = build_generic_task(
            _cartpole_contract(self.xml),
            {"environment": {"terrain_type": "plane", "num_envs": 3}, "reward_scales": {"joint_torques_l2": -0.01}},
        )
        self.assertTrue(bundle.task_id.startswith("LeggedStudio-Generic-"))
        self.assertEqual(bundle.env_cfg.scene.num_envs, 3)
        self.assertEqual(bundle.env_cfg.actions["joint_pos"].actuator_names, ("slider",))
        self.assertEqual(bundle.diagnostics["xml_actuated_joints"], ["slider"])

    def test_preset_reward_names_map_to_mjlab_terms(self):
        bundle = build_generic_task(
            _cartpole_contract(self.xml),
            {"environment": {"terrain_type": "plane"}, "reward_scales": {"body_orientation_l2": -2.0}},
        )
        self.assertIn("upright", bundle.env_cfg.rewards)
        self.assertEqual(bundle.env_cfg.rewards["upright"].weight, -2.0)
        self.assertNotIn("body_orientation_l2", bundle.diagnostics["skipped_rewards"])

    def test_command_cfg_mirrors_mjlab_velocity_defaults(self):
        contract = _cartpole_contract(self.xml)
        contract["observation"]["components"].append("command")
        bundle = build_generic_task(
            contract,
            {"environment": {"terrain_type": "plane", "command_ranges": {"vx": (-0.4, 0.4)}}},
        )
        twist = bundle.env_cfg.commands["twist"]
        self.assertTrue(twist.heading_command)
        self.assertEqual(twist.ranges.lin_vel_x, (-0.4, 0.4))
        self.assertFalse(twist.debug_vis)

    def test_rejects_robot_specific_unknown_observation(self):
        contract = _cartpole_contract(self.xml)
        contract["observation"]["components"].append("foot_contact")
        with self.assertRaisesRegex(ValueError, "unsupported generic observation"):
            build_generic_task(contract, {"environment": {"terrain_type": "plane"}})

    def test_generic_spec_keeps_consumed_sensors_only(self):
        """通用路径的传感器口径：只留被消费的（`imu_lin_vel` 等），其余连同无名的一起撤掉。

        于是 mjlab scene 永远不会去按名包装一个无名传感器（`Invalid name ''`），也不会为没人读的
        声明每步填 sensordata。留一个 keep 集里的传感器在夹具里，证明"保留"这条腿也在工作。
        """
        import mujoco

        with tempfile.TemporaryDirectory() as tmp:
            xml = Path(tmp) / "robot.xml"
            xml.write_text(_NAMELESS_SENSOR_XML, encoding="utf-8")
            bundle = build_generic_task(
                _cartpole_contract(xml, joint="base_joint"),
                {"environment": {"terrain_type": "plane"}},
            )
            spec = bundle.env_cfg.scene.entities["robot"].spec_fn()
            names = [sensor.name for sensor in spec.sensors]
            self.assertEqual(["imu_lin_vel"], names)
            compiled = spec.compile()
            self.assertNotEqual(
                -1, mujoco.mj_name2id(compiled, mujoco.mjtObj.mjOBJ_SENSOR, "imu_lin_vel"),
                "保留的传感器在编译模型里查不到",
            )

    def test_geom_margin_disables_warp_ccd_flags(self):
        """模型带非零 geom margin 时，通用路径须关掉 MULTICCD/NATIVECCD（warp 不支持该组合）。"""
        with tempfile.TemporaryDirectory() as tmp:
            xml = Path(tmp) / "robot.xml"
            xml.write_text(_MARGIN_XML, encoding="utf-8")
            bundle = build_generic_task(
                _cartpole_contract(xml, joint="base_joint"),
                {"environment": {"terrain_type": "plane"}},
            )
        self.assertEqual(("multiccd", "nativeccd"), tuple(bundle.env_cfg.sim.mujoco.disableflags))
        self.assertEqual(["multiccd", "nativeccd"], bundle.diagnostics["mujoco_disableflags"])

    def test_margin_free_model_keeps_ccd_flags_untouched(self):
        bundle = build_generic_task(
            _cartpole_contract(self.xml),
            {"environment": {"terrain_type": "plane"}},
        )
        self.assertEqual((), tuple(bundle.env_cfg.sim.mujoco.disableflags))
        self.assertEqual([], bundle.diagnostics["mujoco_disableflags"])

    def test_strip_actuators_removes_xml_actuators(self):
        """撤 XML 执行器的分支（mjlab 认不出的执行器会走它）必须真能撤掉。"""
        from adapters.mjlab.generic_task_builder import _make_spec_fn

        with tempfile.TemporaryDirectory() as tmp:
            xml = Path(tmp) / "robot.xml"
            xml.write_text(_MARGIN_XML, encoding="utf-8")
            spec = _make_spec_fn(xml, strip_actuators=True)()
            self.assertEqual([], [actuator.name for actuator in spec.actuators])
            self.assertEqual(0, spec.compile().nu)


if __name__ == "__main__":
    unittest.main()
