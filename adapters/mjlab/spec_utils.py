"""MJCF spec 小修（两处消费：通用任务路径 + 包内档案）。

只做"让 MJLab 能建环境"的补丁，**不动类型/挂载点/物理量**——改物理量是越界。

* :func:`name_unnamed_sensors`：MuJoCo 允许无 ``name`` 的传感器，但 mjlab 的 scene 会把
  每个 spec 传感器按名包成 ``BuiltinSensor``（``mj_model.sensor('')`` →
  ``KeyError: Invalid name ''``），环境直接建不起来。真实机型里就有这种 MJCF：
  `deeprobotics_lite3` / `deeprobotics_m20` 的 ``model/robot.xml`` 带无名
  ``<gyro>``/``<accelerometer>``（lite3 包内曾自行补名绕过，2026-09-24 收敛到这里）。
"""

from __future__ import annotations

from typing import Any

#: 常见 IMU 传感器的补充名（按 MuJoCo 传感器类型编号）。
_IMU_SENSOR_NAMES = {
    "mjSENS_ACCELEROMETER": "imu_accelerometer",
    "mjSENS_GYRO": "imu_gyro",
}


def name_unnamed_sensors(spec: Any) -> list[str]:
    """给无 name 的传感器补稳定名，返回补出来的名字列表（按类型：`imu_accelerometer` /
    `imu_gyro`，其它类型 `sensor_type<N>`；重名加序号）。类型/挂载点/语义都不动。"""

    import mujoco

    fallback = {
        int(getattr(mujoco.mjtSensor, attr)): name
        for attr, name in _IMU_SENSOR_NAMES.items()
        if hasattr(mujoco.mjtSensor, attr)
    }
    taken = {sensor.name for sensor in spec.sensors if sensor.name}
    named: list[str] = []
    for sensor in spec.sensors:
        if sensor.name:
            continue
        base = fallback.get(int(sensor.type), f"sensor_type{int(sensor.type)}")
        name = base
        suffix = 0
        while name in taken:
            suffix += 1
            name = f"{base}_{suffix}"
        sensor.name = name
        taken.add(name)
        named.append(name)
    return named


__all__ = ["name_unnamed_sensors"]
