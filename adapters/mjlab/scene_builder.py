"""MjSpec 场景组装工具：机器人 + 契约物理常量 + 平地/box 障碍的统一桌面场景来源。

背景：`<include file="../model/robot.xml"/>` + `<compiler meshdir=...>` 的场景 XML
在桌面 MuJoCo 3.11 下会因 include 的 mesh 路径自动改写产生双重前缀，无法直接编译。
浏览器（虚拟 FS）不受影响，但任何**桌面 Python 端**需要"机器人 + 地面/障碍"场景时，
统一走本模块的 MjSpec 组装（与 policy_acceptance.load_package_model 同代码路径）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_robot_spec(package_dir: Path, sim_cfg: dict[str, Any] | None = None):
    """编译包内 model/robot.xml，并应用契约的 armature/frictionloss（增量真值）。

    B3 收尾：常量改由 :func:`contracts.physics_binding.joint_constant_tables` 供给
    （契约 v3 优先，键统一小写）。**此前这里读 ``sim_cfg["armature"]`` 并用
    ``joint.name.lower()`` 去查混合大小写的键，永远查不中 → armature 静默不生效**，
    而浏览器侧同一份数据是生效的（同数据两结论）。``sim_cfg`` 参数保留仅为兼容调用方，
    不再作为物理常量来源。
    """
    import mujoco

    from contracts.physics_binding import joint_constant_tables

    model_xml = Path(package_dir) / "model" / "robot.xml"
    if not model_xml.is_file():
        raise FileNotFoundError(f"包内缺少模型: {model_xml}")
    spec = mujoco.MjSpec.from_file(str(model_xml))

    tables = joint_constant_tables(package_dir)
    armature = tables["armature"]
    frictionloss = tables["frictionloss"]
    default_arm = armature.get("__default__")
    default_fric = frictionloss.get("__default__")
    for joint in spec.joints:
        name = (joint.name or "").lower()
        if name in armature:
            joint.armature = float(armature[name])
        elif default_arm is not None:
            joint.armature = float(default_arm)
        if name in frictionloss:
            joint.frictionloss = float(frictionloss[name])
        elif default_fric is not None:
            joint.frictionloss = float(default_fric)
    return spec


def build_flat_scene(package_dir: Path, sim_cfg: dict[str, Any] | None = None,
                     floor_size: float = 10.0, light_z: float = 2.5):
    """机器人 + 平地 + 灯光的场景（验收/工具链通用）。"""
    import mujoco

    spec = load_robot_spec(package_dir, sim_cfg)
    spec.worldbody.add_geom(type=mujoco.mjtGeom.mjGEOM_PLANE, name="scene_floor",
                            size=[floor_size, floor_size, 0.05])
    return spec.compile()


def add_box_obstacles(spec, obstacles: list[dict[str, Any]]) -> None:
    """在已编译前的 spec 上追加 box 障碍（rough 场景的可再生产物路径）。

    每项：{name?, size: [x,y,z], pos: [x,y,z], euler?: [r,p,y]}
    """
    import mujoco

    for item in obstacles:
        geom = spec.worldbody.add_geom(
            type=mujoco.mjtGeom.mjGEOM_BOX,
            name=str(item.get("name") or f"obstacle_{len(list(spec.geoms))}"),
            size=[float(x) for x in item["size"]],
            pos=[float(x) for x in item["pos"]],
        )
        if item.get("euler"):
            import math
            r, p, y = (float(a) for a in item["euler"])
            quat = _euler_to_quat(r, p, y)
            geom.quat = quat


def _euler_to_quat(roll: float, pitch: float, yaw: float) -> list[float]:
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    return [
        cr * cp * cy + sr * sp * sy,
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
    ]
