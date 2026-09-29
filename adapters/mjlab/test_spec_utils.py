"""MJCF 规范化的回归锁（族内"统一基准"的装配层半边）。

守两件事：
1. **无名传感器必须被补名**（mjlab scene 按名包装，无名 ⇒ 建环境时 `Invalid name ''`）；
2. **撤 XML 执行器时必须处理引用 ctrl 的 keyframe**——MuJoCo 要求 `key.ctrl` 长度 == `nu`，
   撤了执行器再编译就是 `invalid ctrl size, expected length 0`（go1 / b2 各有一个 keyframe，
   2026-09-24 探针实测踩到；通用路径的 strip 分支此前同样没处理）。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.mjlab.spec_utils import name_unnamed_sensors, normalize_spec  # noqa: E402

_NAMELESS_SENSORS = """<mujoco model="nameless_sensor_fixture">
  <worldbody>
    <body name="base" pos="0 0 0.2">
      <freejoint name="root"/>
      <geom name="base_geom" type="box" size="0.1 0.1 0.1"/>
      <site name="imu_site" pos="0 0 0.02"/>
    </body>
  </worldbody>
  <sensor>
    <gyro site="imu_site"/>
    <accelerometer site="imu_site"/>
    <framepos name="base_pos" objtype="site" objname="imu_site"/>
  </sensor>
</mujoco>
"""

# 带执行器 + 带 ctrl 的 keyframe（go1/b2 的结构）：撤执行器后 keyframe 必须一起处理。
_ACTUATORS_WITH_KEY = """<mujoco model="actuator_key_fixture">
  <worldbody>
    <body name="base" pos="0 0 0.3">
      <joint name="trunk_joint" type="hinge" axis="0 0 1"/>
      <geom name="base_geom" type="box" size="0.1 0.1 0.1"/>
    </body>
  </worldbody>
  <actuator>
    <position name="trunk_joint" joint="trunk_joint" kp="20" kv="1"/>
  </actuator>
  <keyframe>
    <key name="home" qpos="0" ctrl="0"/>
  </keyframe>
</mujoco>
"""


def _spec(text: str):
    import mujoco

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "robot.xml"
        path.write_text(text, encoding="utf-8")
        return mujoco.MjSpec.from_file(str(path))


class NameUnnamedSensorsTest(unittest.TestCase):
    def test_unnamed_sensors_get_stable_names(self):
        import mujoco

        spec = _spec(_NAMELESS_SENSORS)
        named = name_unnamed_sensors(spec)
        self.assertEqual(["imu_gyro", "imu_accelerometer"], named)
        self.assertTrue(all(sensor.name for sensor in spec.sensors))
        model = spec.compile()
        for name in named:
            self.assertNotEqual(-1, mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SENSOR, name))

    def test_existing_names_are_untouched(self):
        spec = _spec(_NAMELESS_SENSORS)
        name_unnamed_sensors(spec)
        self.assertIn("base_pos", [sensor.name for sensor in spec.sensors])


class NormalizeSpecTest(unittest.TestCase):
    def test_strip_actuators_also_repairs_ctrl_keyframes(self):
        spec = _spec(_ACTUATORS_WITH_KEY)
        report = normalize_spec(spec, strip_actuators=True)
        self.assertEqual(1, report.actuators_deleted)
        self.assertEqual(["home"], report.keys_removed)
        self.assertEqual([], list(spec.keys))
        self.assertEqual(0, spec.compile().nu)

    def test_keyframes_without_ctrl_survive_stripping(self):
        text = _ACTUATORS_WITH_KEY.replace(' qpos="0" ctrl="0"', ' qpos="0"')
        spec = _spec(text)
        report = normalize_spec(spec, strip_actuators=True)
        self.assertEqual([], report.keys_removed)
        self.assertEqual(1, len(list(spec.keys)))

    def test_report_is_json_shaped(self):
        report = normalize_spec(_spec(_NAMELESS_SENSORS))
        self.assertEqual(
            {"sensors_named": ["imu_gyro", "imu_accelerometer"], "sensors_deleted": [],
             "actuators_deleted": 0, "keys_removed": [], "collision_geoms_named": []},
            report.as_dict(),
        )


class SensorPolicyTest(unittest.TestCase):
    """传感器策略：`keep` 只补名；`training_only` 只留全仓按名消费的那几个。"""

    _MIXED = """<mujoco model="sensor_policy_fixture">
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
    <framequat name="base_quat" objtype="site" objname="imu_site"/>
    <jointpos name="leg_joint_pos" joint="root"/>
  </sensor>
</mujoco>
"""

    def test_training_only_keeps_only_consumed_names(self):
        spec = _spec(self._MIXED)
        report = normalize_spec(spec, sensor_policy="training_only")
        self.assertEqual(["imu_lin_vel"], [sensor.name for sensor in spec.sensors])
        self.assertEqual(["imu_gyro", "base_quat", "leg_joint_pos"], report.sensors_deleted)

    def test_keep_policy_deletes_nothing(self):
        spec = _spec(self._MIXED)
        report = normalize_spec(spec)
        self.assertEqual(4, len(list(spec.sensors)))
        self.assertEqual([], report.sensors_deleted)

    def test_unknown_policy_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "未知 sensor_policy"):
            normalize_spec(_spec(self._MIXED), sensor_policy="whatever")

    def test_default_keep_set_is_the_three_consumed_names(self):
        from adapters.mjlab.spec_utils import KEEP_SENSORS

        self.assertEqual(("imu_ang_vel", "imu_lin_vel", "root_angmom"), KEEP_SENSORS)


if __name__ == "__main__":
    unittest.main()
