"""MJCF spec 的**规范化唯一入口**（族内统一基准的装配层半边）。

训练栈的两条路径（通用任务路径 / 包内档案）都必须经过 :func:`normalize_spec`——"同族同构"
不靠约束上游 XML 长什么样，而靠**同一套规范化**把差异收口。改的只有语义中性的东西
（传感器名字、执行器声明归属），物理量一律不碰。

规范化做两件事（都能单独关）：

1. **补传感器名**——MuJoCo 允许无 ``name`` 的传感器，但 mjlab 的 scene 会把每个 spec 传感器按名
   包成 ``BuiltinSensor``（``mj_model.sensor('')`` → ``KeyError: Invalid name ''``），环境建不起来。
   真实机型里就有：`deeprobotics_lite3` / `deeprobotics_m20` 的 ``model/robot.xml``。
2. **撤 XML 执行器**（`strip_actuators=True`）——执行器声明归属必须**一族一个口径**：包内 cfg/Kit
   声明的族（轮足 m20/go2w/zex-w、四足 go2/go1）读包级 MJCF 时会与 XML 里同名执行器撞名
   （``repeated name 'fl_hipx_joint' in actuator``）。撤的时候**连引用 ctrl 的 keyframe 一起处理**：
   MuJoCo 要求 ``key.ctrl`` 长度等于 ``nu``，撤了执行器再编译就是
   ``invalid ctrl size, expected length 0``（go1 / b2 各有一个 keyframe，2026-09-24 实测）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: 常见 IMU 传感器的补充名（按 MuJoCo 传感器类型编号）。
_IMU_SENSOR_NAMES = {
    "mjSENS_ACCELEROMETER": "imu_accelerometer",
    "mjSENS_GYRO": "imu_gyro",
}


@dataclass
class NormalizeReport:
    """规范化动了什么（进诊断/取证，不猜）。"""

    sensors_named: list[str] = field(default_factory=list)
    actuators_deleted: int = 0
    keys_removed: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sensors_named": list(self.sensors_named),
            "actuators_deleted": self.actuators_deleted,
            "keys_removed": list(self.keys_removed),
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


def _drop_ctrl_keys(spec: Any, report: NormalizeReport) -> None:
    """撤掉**带 ctrl** 的 keyframe：执行器撤走后 ``nu`` 变了，keyframe 里的 ctrl 长度对不上。

    mjlab 自己会加一个 ``init_state`` key（qpos/ctrl 与当前实体一致），所以包内旧 keyframe 撤掉
    不改变训练语义——它只是"手动 reset 到某个姿态"的便利项。空 ctrl 的 keyframe 原样保留。
    """

    for key in list(spec.keys):
        ctrl = getattr(key, "ctrl", None)
        if ctrl is None or len(ctrl) == 0:
            continue
        report.keys_removed.append(str(getattr(key, "name", "")))
        spec.delete(key)


def normalize_spec(spec: Any, *, strip_actuators: bool = False) -> NormalizeReport:
    """就地规范化一个 ``mujoco.MjSpec``；返回 :class:`NormalizeReport`。"""

    report = NormalizeReport()
    if strip_actuators:
        for actuator in list(spec.actuators):
            spec.delete(actuator)
            report.actuators_deleted += 1
        if report.actuators_deleted:
            _drop_ctrl_keys(spec, report)
    report.sensors_named = name_unnamed_sensors(spec)
    return report


__all__ = ["NormalizeReport", "name_unnamed_sensors", "normalize_spec"]
