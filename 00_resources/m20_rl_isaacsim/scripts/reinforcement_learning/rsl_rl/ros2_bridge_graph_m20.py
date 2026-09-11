from __future__ import annotations

import os
from dataclasses import dataclass

import carb
import omni.graph.core as og
import omni.kit.commands
import omni.usd
from pxr import Gf, Sdf, UsdGeom
from isaacsim.core.utils.extensions import enable_extension
from isaacsim.core.utils.prims import get_prim_at_path, set_targets


@dataclass
class Ros2M20BridgeCfg:
    env_prim: str = "/World/envs/env_0"
    robot_prim: str = "/World/envs/env_0/Robot"
    base_link_prim: str = "/World/envs/env_0/Robot/base_link"

    camera_prim: str = "/World/envs/env_0/Robot/base_link/front_camera_mount/front_camera"
    front_lidar_mount_prim: str = "/World/envs/env_0/Robot/base_link/front_lidar_mount"
    front_lidar_prim: str = "/World/envs/env_0/Robot/base_link/front_lidar_mount/front_lidar"
    rear_lidar_mount_prim: str = "/World/envs/env_0/Robot/base_link/rear_lidar_mount"
    rear_lidar_prim: str = "/World/envs/env_0/Robot/base_link/rear_lidar_mount/rear_lidar"
    imu_mount_prim: str = "/World/envs/env_0/Robot/base_link/body_imu_mount"
    imu_sensor_prim: str = "/World/envs/env_0/Robot/base_link/body_imu_mount/Imu_Sensor"

    graph_path: str = "/World/ROS2_M20_Bridge"

    clock_topic: str = "clock"
    odom_topic: str = "odom"
    odom_frame: str = "odom"
    base_frame: str = "base_link"

    camera_ns: str = "/m20/front_camera"
    camera_frame: str = "front_camera"

    front_lidar_ns: str = "/m20/front_lidar"
    front_lidar_frame: str = "front_lidar"
    
    rear_lidar_ns: str = "/m20/rear_lidar"
    rear_lidar_frame: str = "rear_lidar"

    imu_ns: str = "/m20/imu"
    imu_frame: str = "body_imu"

    camera_resolution: tuple[int, int] = (360, 360)
    camera_frame_skip_count: int = 0
    lidar_frame_skip_count: int = 0


def ensure_extension_safe(ext_name: str):
    try:
        enable_extension(ext_name)
    except Exception as exc:
        print(f"[ROS2] Warning: could not enable extension {ext_name}: {exc}")


def ensure_required_extensions():
    for ext in (
        "isaacsim.ros2.bridge",
        "isaacsim.sensors.rtx",
        "isaacsim.sensors.physics",
    ):
        ensure_extension_safe(ext)


# ---------------------------------------------------------------------------
# 与 slam_nav.py 完全一致的 xform 工具函数
# 关键：每次都 ClearXformOpOrder() 再重写，保证位置修改即时生效
# ---------------------------------------------------------------------------
def set_xform_ops(prim, translate=None, rotate_xyz_deg=None, scale=None):
    xform = UsdGeom.Xformable(prim)
    xform.ClearXformOpOrder()
    if translate is not None:
        xform.AddTranslateOp().Set(Gf.Vec3d(*translate))
    if rotate_xyz_deg is not None:
        xform.AddRotateXYZOp().Set(Gf.Vec3f(*rotate_xyz_deg))
    if scale is not None:
        xform.AddScaleOp().Set(Gf.Vec3f(*scale))


# ---------------------------------------------------------------------------
# 与 slam_nav.py 完全一致的 lidar 创建函数
# 关键：path=完整绝对路径, parent=None
# 这样 render product 绑定稳定，fullScan=True 能正常触发
# ---------------------------------------------------------------------------
def _ensure_rtx_lidar(sensor_prim: str, scan_rate_hz: float = 10.0):
    """创建 RTX lidar，使用完整路径 + parent=None 的方式（与 slam_nav.py 一致）。"""
    prim = get_prim_at_path(sensor_prim)
    if prim and prim.IsValid():
        return prim

    _, sensor = omni.kit.commands.execute(
        "IsaacSensorCreateRtxLidar",
        path=sensor_prim,          # 完整绝对路径
        parent=None,               # 不再拆分 name + parent
        config="Example_Rotary",   # 纯 Example_Rotary，不覆盖任何参数
        translation=Gf.Vec3d(0.0, 0.0, 0.0),
        orientation=Gf.Quatd(1.0, 0.0, 0.0, 0.0),
    )

    created = get_prim_at_path(sensor_prim)
    if not created or not created.IsValid():
        raise RuntimeError(f"Failed to create RTX lidar at {sensor_prim}")
    created.GetAttribute("omni:sensor:Core:scanRateBaseHz").Set(float(scan_rate_hz))
    print(f"[ROS2] RTX lidar ready (Example_Rotary): {sensor_prim}")
    return created


def _ensure_imu_sensor(cfg: Ros2M20BridgeCfg):
    stage = omni.usd.get_context().get_stage()
    existing = stage.GetPrimAtPath(cfg.imu_sensor_prim)
    
    if existing.IsValid():
        print(f"[ROS2] Found baked IMU sensor in USD: {cfg.imu_sensor_prim}")
        return existing
    else:
        # 如果找不到，不要尝试强行创建，而是抛出明确错误提醒你修改 USD
        raise RuntimeError(
            f"[ROS2] IMU sensor NOT FOUND at {cfg.imu_sensor_prim}. "
            "Please open your robot's USD file and manually create an IMU Sensor at this path."
        )


def ensure_sensor_prims(cfg: Ros2M20BridgeCfg):
    _ensure_rtx_lidar(cfg.front_lidar_prim, scan_rate_hz=40.0)   # 改这里，单位 Hz
    _ensure_rtx_lidar(cfg.rear_lidar_prim,  scan_rate_hz=40.0)
    _ensure_imu_sensor(cfg)


def build_ros2_bridge_graph(cfg: Ros2M20BridgeCfg):
    ensure_required_extensions()
    ensure_sensor_prims(cfg)

    stage = omni.usd.get_context().get_stage()
    old_graph = stage.GetPrimAtPath(cfg.graph_path)
    if old_graph.IsValid():
        stage.RemovePrim(cfg.graph_path)

    keys = og.Controller.Keys

    create_nodes = [
        ("OnPlaybackTick", "omni.graph.action.OnPlaybackTick"),
        ("ReadSimTime", "isaacsim.core.nodes.IsaacReadSimulationTime"),
        ("ClockPub", "isaacsim.ros2.bridge.ROS2PublishClock"),
        ("OdomCompute", "isaacsim.core.nodes.IsaacComputeOdometry"),
        ("OdomPub", "isaacsim.ros2.bridge.ROS2PublishOdometry"),
        ("OdomTfPub", "isaacsim.ros2.bridge.ROS2PublishRawTransformTree"),
        ("SensorTfPub", "isaacsim.ros2.bridge.ROS2PublishTransformTree"),
        ("CameraRP", "isaacsim.core.nodes.IsaacCreateRenderProduct"),
        ("CameraRgbPub", "isaacsim.ros2.bridge.ROS2CameraHelper"),
        ("CameraInfoPub", "isaacsim.ros2.bridge.ROS2CameraInfoHelper"),
        ("FrontLidarRP", "isaacsim.core.nodes.IsaacCreateRenderProduct"),
        ("FrontLidarPub", "isaacsim.ros2.bridge.ROS2RtxLidarHelper"),
        ("RearLidarRP", "isaacsim.core.nodes.IsaacCreateRenderProduct"),
        ("RearLidarPub", "isaacsim.ros2.bridge.ROS2RtxLidarHelper"),
        ("ReadImu", "isaacsim.sensors.physics.IsaacReadIMU"),
        ("ImuPub", "isaacsim.ros2.bridge.ROS2PublishImu"),
    ]

    connections = [
        ("OnPlaybackTick.outputs:tick", "ClockPub.inputs:execIn"),
        ("ReadSimTime.outputs:simulationTime", "ClockPub.inputs:timeStamp"),

        ("OnPlaybackTick.outputs:tick", "OdomCompute.inputs:execIn"),
        ("OdomCompute.outputs:execOut", "OdomPub.inputs:execIn"),
        ("ReadSimTime.outputs:simulationTime", "OdomPub.inputs:timeStamp"),
        ("OdomCompute.outputs:position", "OdomPub.inputs:position"),
        ("OdomCompute.outputs:orientation", "OdomPub.inputs:orientation"),
        ("OdomCompute.outputs:linearVelocity", "OdomPub.inputs:linearVelocity"),
        ("OdomCompute.outputs:angularVelocity", "OdomPub.inputs:angularVelocity"),

        ("OdomCompute.outputs:execOut", "OdomTfPub.inputs:execIn"),
        ("ReadSimTime.outputs:simulationTime", "OdomTfPub.inputs:timeStamp"),
        ("OdomCompute.outputs:position", "OdomTfPub.inputs:translation"),
        ("OdomCompute.outputs:orientation", "OdomTfPub.inputs:rotation"),

        ("OnPlaybackTick.outputs:tick", "SensorTfPub.inputs:execIn"),
        ("ReadSimTime.outputs:simulationTime", "SensorTfPub.inputs:timeStamp"),

        ("OnPlaybackTick.outputs:tick", "CameraRP.inputs:execIn"),
        ("CameraRP.outputs:renderProductPath", "CameraRgbPub.inputs:renderProductPath"),
        ("CameraRP.outputs:renderProductPath", "CameraInfoPub.inputs:renderProductPath"),
        ("OnPlaybackTick.outputs:tick", "CameraRgbPub.inputs:execIn"),
        ("OnPlaybackTick.outputs:tick", "CameraInfoPub.inputs:execIn"),

        ("OnPlaybackTick.outputs:tick", "FrontLidarRP.inputs:execIn"),
        ("FrontLidarRP.outputs:renderProductPath", "FrontLidarPub.inputs:renderProductPath"),
        ("OnPlaybackTick.outputs:tick", "FrontLidarPub.inputs:execIn"),

        ("OnPlaybackTick.outputs:tick", "RearLidarRP.inputs:execIn"),
        ("RearLidarRP.outputs:renderProductPath", "RearLidarPub.inputs:renderProductPath"),
        ("OnPlaybackTick.outputs:tick", "RearLidarPub.inputs:execIn"),

        ("OnPlaybackTick.outputs:tick", "ReadImu.inputs:execIn"),
        ("ReadImu.outputs:execOut", "ImuPub.inputs:execIn"),
        ("ReadImu.outputs:orientation", "ImuPub.inputs:orientation"),
        ("ReadImu.outputs:angVel", "ImuPub.inputs:angularVelocity"),
        ("ReadImu.outputs:linAcc", "ImuPub.inputs:linearAcceleration"),
        ("ReadSimTime.outputs:simulationTime", "ImuPub.inputs:timeStamp"),
    ]

    set_values = [
        ("ClockPub.inputs:topicName", cfg.clock_topic),

        ("OdomCompute.inputs:chassisPrim", cfg.base_link_prim),
        ("OdomPub.inputs:topicName", cfg.odom_topic),
        ("OdomPub.inputs:chassisFrameId", cfg.base_frame),
        ("OdomPub.inputs:odomFrameId", cfg.odom_frame),
        ("OdomTfPub.inputs:parentFrameId", cfg.odom_frame),
        ("OdomTfPub.inputs:childFrameId", cfg.base_frame),

        ("SensorTfPub.inputs:parentPrim", cfg.base_link_prim),
        ("SensorTfPub.inputs:topicName", "tf"),

        ("CameraRP.inputs:cameraPrim", cfg.camera_prim),
        ("CameraRP.inputs:width", cfg.camera_resolution[0]),
        ("CameraRP.inputs:height", cfg.camera_resolution[1]),
        ("CameraRgbPub.inputs:frameId", cfg.camera_frame),
        ("CameraRgbPub.inputs:nodeNamespace", cfg.camera_ns),
        ("CameraRgbPub.inputs:topicName", "rgb"),
        ("CameraRgbPub.inputs:type", "rgb"),
        ("CameraRgbPub.inputs:frameSkipCount", cfg.camera_frame_skip_count),
        ("CameraInfoPub.inputs:frameId", cfg.camera_frame),
        ("CameraInfoPub.inputs:nodeNamespace", cfg.camera_ns),
        ("CameraInfoPub.inputs:topicName", "camera_info"),
        ("CameraInfoPub.inputs:frameSkipCount", cfg.camera_frame_skip_count),

        ("FrontLidarRP.inputs:cameraPrim", cfg.front_lidar_prim),
        ("FrontLidarPub.inputs:frameId", cfg.front_lidar_frame),
        ("FrontLidarPub.inputs:nodeNamespace", cfg.front_lidar_ns),
        ("FrontLidarPub.inputs:topicName", "point_cloud"),
        ("FrontLidarPub.inputs:type", "point_cloud"),
        ("FrontLidarPub.inputs:fullScan", True),   # Example_Rotary 原生支持，无需改参数
        ("FrontLidarPub.inputs:showDebugView", False),
        ("FrontLidarPub.inputs:frameSkipCount", cfg.lidar_frame_skip_count),

        ("RearLidarRP.inputs:cameraPrim", cfg.rear_lidar_prim),
        ("RearLidarPub.inputs:frameId", cfg.rear_lidar_frame),
        ("RearLidarPub.inputs:nodeNamespace", cfg.rear_lidar_ns),
        ("RearLidarPub.inputs:topicName", "point_cloud"),
        ("RearLidarPub.inputs:type", "point_cloud"),
        ("RearLidarPub.inputs:fullScan", True),
        ("RearLidarPub.inputs:showDebugView", False),
        ("RearLidarPub.inputs:frameSkipCount", cfg.lidar_frame_skip_count),

        ("ReadImu.inputs:readGravity", True),
        ("ImuPub.inputs:frameId", cfg.imu_frame),
        ("ImuPub.inputs:nodeNamespace", cfg.imu_ns),
        ("ImuPub.inputs:topicName", "data"),
    ]

    og.Controller.edit(
        {"graph_path": cfg.graph_path, "evaluator_name": "execution"},
        {
            keys.CREATE_NODES: create_nodes,
            keys.CONNECT: connections,
            keys.SET_VALUES: set_values,
        },
    )

    # target inputs
    try:
        imu_attr = og.Controller.attribute(f"{cfg.graph_path}/ReadImu.inputs:imuPrim")
        imu_attr.set(cfg.imu_sensor_prim)
        print(f"[ROS2] ReadImu.inputs:imuPrim set to: {cfg.imu_sensor_prim}")
    except Exception as e:
        print(f"[ROS2] Warning: could not set imuPrim via og.Controller: {e}")
        # 备选方式
        try:
            read_imu_prim = get_prim_at_path(f"{cfg.graph_path}/ReadImu")
            if read_imu_prim and read_imu_prim.IsValid():
                set_targets(read_imu_prim, "inputs:imuPrim", [cfg.imu_sensor_prim])
                print(f"[ROS2] ReadImu.inputs:imuPrim set via set_targets (fallback)")
        except Exception as e2:
            print(f"[ROS2] ERROR: imuPrim could not be set: {e2}")

    sensor_tf_prim = get_prim_at_path(f"{cfg.graph_path}/SensorTfPub")
    if sensor_tf_prim and sensor_tf_prim.IsValid():
        set_targets(
            sensor_tf_prim,
            "inputs:targetPrims",
            [
                cfg.camera_prim,
                cfg.front_lidar_mount_prim,
                cfg.front_lidar_prim,
                cfg.rear_lidar_mount_prim,
                cfg.rear_lidar_prim,
                cfg.imu_mount_prim,
                cfg.imu_sensor_prim,
            ],
        )

    print(f"[ROS2] Bridge graph created at {cfg.graph_path}")
    return cfg.graph_path