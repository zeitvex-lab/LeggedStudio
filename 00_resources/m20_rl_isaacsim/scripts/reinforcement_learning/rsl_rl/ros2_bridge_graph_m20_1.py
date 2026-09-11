from __future__ import annotations

import os
from dataclasses import dataclass, field

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

    # ---- 四环视相机 prim 路径 ----
    front_camera_prim: str = "/World/envs/env_0/Robot/base_link/front_camera_mount/front_camera"
    rear_camera_prim:  str = "/World/envs/env_0/Robot/base_link/rear_camera_mount/rear_camera"
    left_camera_prim:  str = "/World/envs/env_0/Robot/base_link/left_camera_mount/left_camera"
    right_camera_prim: str = "/World/envs/env_0/Robot/base_link/right_camera_mount/right_camera"

    # ---- 激光雷达 ----
    front_lidar_mount_prim: str = "/World/envs/env_0/Robot/base_link/front_lidar_mount"
    front_lidar_prim:       str = "/World/envs/env_0/Robot/base_link/front_lidar_mount/front_lidar"
    rear_lidar_mount_prim:  str = "/World/envs/env_0/Robot/base_link/rear_lidar_mount"
    rear_lidar_prim:        str = "/World/envs/env_0/Robot/base_link/rear_lidar_mount/rear_lidar"

    # ---- IMU ----
    imu_mount_prim:  str = "/World/envs/env_0/Robot/base_link/body_imu_mount"
    imu_sensor_prim: str = "/World/envs/env_0/Robot/base_link/body_imu_mount/Imu_Sensor"

    graph_path: str = "/World/ROS2_M20_Bridge"

    # ---- 通用话题 ----
    clock_topic: str = "clock"
    odom_topic:  str = "odom"
    odom_frame:  str = "odom"
    base_frame:  str = "base_link"

    # ---- 前相机 ----
    front_camera_ns:    str = "/m20/front_camera"
    front_camera_frame: str = "front_camera"

    # ---- 后相机 ----
    rear_camera_ns:     str = "/m20/rear_camera"
    rear_camera_frame:  str = "rear_camera"

    # ---- 左相机 ----
    left_camera_ns:     str = "/m20/left_camera"
    left_camera_frame:  str = "left_camera"

    # ---- 右相机 ----
    right_camera_ns:    str = "/m20/right_camera"
    right_camera_frame: str = "right_camera"

    # ---- 激光雷达话题 ----
    front_lidar_ns:    str = "/m20/front_lidar"
    front_lidar_frame: str = "front_lidar"
    rear_lidar_ns:     str = "/m20/rear_lidar"
    rear_lidar_frame:  str = "rear_lidar"

    # ---- IMU 话题 ----
    imu_ns:    str = "/m20/imu"
    imu_frame: str = "body_imu"

    # ---- 分辨率与跳帧 ----
    camera_resolution:       tuple[int, int] = (640, 480)
    camera_frame_skip_count: int = 0
    lidar_frame_skip_count:  int = 0


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


def set_xform_ops(prim, translate=None, rotate_xyz_deg=None, scale=None):
    xform = UsdGeom.Xformable(prim)
    xform.ClearXformOpOrder()
    if translate is not None:
        xform.AddTranslateOp().Set(Gf.Vec3d(*translate))
    if rotate_xyz_deg is not None:
        xform.AddRotateXYZOp().Set(Gf.Vec3f(*rotate_xyz_deg))
    if scale is not None:
        xform.AddScaleOp().Set(Gf.Vec3f(*scale))


def _ensure_rtx_lidar(sensor_prim: str, scan_rate_hz: float = 10.0):
    """创建 RTX lidar，使用完整路径 + parent=None 的方式。"""
    prim = get_prim_at_path(sensor_prim)
    if prim and prim.IsValid():
        return prim

    _, sensor = omni.kit.commands.execute(
        "IsaacSensorCreateRtxLidar",
        path=sensor_prim,
        parent=None,
        config="Example_Rotary",
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
        raise RuntimeError(
            f"[ROS2] IMU sensor NOT FOUND at {cfg.imu_sensor_prim}. "
            "Please open your robot's USD file and manually create an IMU Sensor at this path."
        )


def ensure_sensor_prims(cfg: Ros2M20BridgeCfg):
    _ensure_rtx_lidar(cfg.front_lidar_prim, scan_rate_hz=80.0)
    _ensure_rtx_lidar(cfg.rear_lidar_prim,  scan_rate_hz=80.0)
    _ensure_imu_sensor(cfg)


def build_ros2_bridge_graph(cfg: Ros2M20BridgeCfg):
    ensure_required_extensions()
    ensure_sensor_prims(cfg)

    stage = omni.usd.get_context().get_stage()
    old_graph = stage.GetPrimAtPath(cfg.graph_path)
    if old_graph.IsValid():
        stage.RemovePrim(cfg.graph_path)

    keys = og.Controller.Keys

    # -------------------------------------------------------------------------
    # 节点列表
    # -------------------------------------------------------------------------
    create_nodes = [
        # 基础
        ("OnPlaybackTick", "omni.graph.action.OnPlaybackTick"),
        ("ReadSimTime",    "isaacsim.core.nodes.IsaacReadSimulationTime"),
        ("ClockPub",       "isaacsim.ros2.bridge.ROS2PublishClock"),

        # 里程计
        ("OdomCompute",    "isaacsim.core.nodes.IsaacComputeOdometry"),
        ("OdomPub",        "isaacsim.ros2.bridge.ROS2PublishOdometry"),
        ("OdomTfPub",      "isaacsim.ros2.bridge.ROS2PublishRawTransformTree"),

        # TF 传感器树
        ("SensorTfPub",    "isaacsim.ros2.bridge.ROS2PublishTransformTree"),

        # ---- 前相机 ----
        ("FrontCameraRP",      "isaacsim.core.nodes.IsaacCreateRenderProduct"),
        ("FrontCameraRgbPub",  "isaacsim.ros2.bridge.ROS2CameraHelper"),
        ("FrontCameraInfoPub", "isaacsim.ros2.bridge.ROS2CameraInfoHelper"),

        # ---- 后相机 ----
        ("RearCameraRP",       "isaacsim.core.nodes.IsaacCreateRenderProduct"),
        ("RearCameraRgbPub",   "isaacsim.ros2.bridge.ROS2CameraHelper"),
        ("RearCameraInfoPub",  "isaacsim.ros2.bridge.ROS2CameraInfoHelper"),

        # ---- 左相机 ----
        ("LeftCameraRP",       "isaacsim.core.nodes.IsaacCreateRenderProduct"),
        ("LeftCameraRgbPub",   "isaacsim.ros2.bridge.ROS2CameraHelper"),
        ("LeftCameraInfoPub",  "isaacsim.ros2.bridge.ROS2CameraInfoHelper"),

        # ---- 右相机 ----
        ("RightCameraRP",      "isaacsim.core.nodes.IsaacCreateRenderProduct"),
        ("RightCameraRgbPub",  "isaacsim.ros2.bridge.ROS2CameraHelper"),
        ("RightCameraInfoPub", "isaacsim.ros2.bridge.ROS2CameraInfoHelper"),

        # ---- 激光雷达 ----
        ("FrontLidarRP",  "isaacsim.core.nodes.IsaacCreateRenderProduct"),
        ("FrontLidarPub", "isaacsim.ros2.bridge.ROS2RtxLidarHelper"),
        ("RearLidarRP",   "isaacsim.core.nodes.IsaacCreateRenderProduct"),
        ("RearLidarPub",  "isaacsim.ros2.bridge.ROS2RtxLidarHelper"),

        # ---- IMU ----
        ("ReadImu", "isaacsim.sensors.physics.IsaacReadIMU"),
        ("ImuPub",  "isaacsim.ros2.bridge.ROS2PublishImu"),
    ]

    # -------------------------------------------------------------------------
    # 连接列表
    # -------------------------------------------------------------------------
    connections = [
        # 时钟
        ("OnPlaybackTick.outputs:tick",            "ClockPub.inputs:execIn"),
        ("ReadSimTime.outputs:simulationTime",     "ClockPub.inputs:timeStamp"),

        # 里程计
        ("OnPlaybackTick.outputs:tick",            "OdomCompute.inputs:execIn"),
        ("OdomCompute.outputs:execOut",            "OdomPub.inputs:execIn"),
        ("ReadSimTime.outputs:simulationTime",     "OdomPub.inputs:timeStamp"),
        ("OdomCompute.outputs:position",           "OdomPub.inputs:position"),
        ("OdomCompute.outputs:orientation",        "OdomPub.inputs:orientation"),
        ("OdomCompute.outputs:linearVelocity",     "OdomPub.inputs:linearVelocity"),
        ("OdomCompute.outputs:angularVelocity",    "OdomPub.inputs:angularVelocity"),

        # Odom TF
        ("OdomCompute.outputs:execOut",            "OdomTfPub.inputs:execIn"),
        ("ReadSimTime.outputs:simulationTime",     "OdomTfPub.inputs:timeStamp"),
        ("OdomCompute.outputs:position",           "OdomTfPub.inputs:translation"),
        ("OdomCompute.outputs:orientation",        "OdomTfPub.inputs:rotation"),

        # 传感器 TF
        ("OnPlaybackTick.outputs:tick",            "SensorTfPub.inputs:execIn"),
        ("ReadSimTime.outputs:simulationTime",     "SensorTfPub.inputs:timeStamp"),

        # 前相机
        ("OnPlaybackTick.outputs:tick",            "FrontCameraRP.inputs:execIn"),
        ("FrontCameraRP.outputs:renderProductPath","FrontCameraRgbPub.inputs:renderProductPath"),
        ("FrontCameraRP.outputs:renderProductPath","FrontCameraInfoPub.inputs:renderProductPath"),
        ("OnPlaybackTick.outputs:tick",            "FrontCameraRgbPub.inputs:execIn"),
        ("OnPlaybackTick.outputs:tick",            "FrontCameraInfoPub.inputs:execIn"),

        # 后相机
        ("OnPlaybackTick.outputs:tick",            "RearCameraRP.inputs:execIn"),
        ("RearCameraRP.outputs:renderProductPath", "RearCameraRgbPub.inputs:renderProductPath"),
        ("RearCameraRP.outputs:renderProductPath", "RearCameraInfoPub.inputs:renderProductPath"),
        ("OnPlaybackTick.outputs:tick",            "RearCameraRgbPub.inputs:execIn"),
        ("OnPlaybackTick.outputs:tick",            "RearCameraInfoPub.inputs:execIn"),

        # 左相机
        ("OnPlaybackTick.outputs:tick",            "LeftCameraRP.inputs:execIn"),
        ("LeftCameraRP.outputs:renderProductPath", "LeftCameraRgbPub.inputs:renderProductPath"),
        ("LeftCameraRP.outputs:renderProductPath", "LeftCameraInfoPub.inputs:renderProductPath"),
        ("OnPlaybackTick.outputs:tick",            "LeftCameraRgbPub.inputs:execIn"),
        ("OnPlaybackTick.outputs:tick",            "LeftCameraInfoPub.inputs:execIn"),

        # 右相机
        ("OnPlaybackTick.outputs:tick",            "RightCameraRP.inputs:execIn"),
        ("RightCameraRP.outputs:renderProductPath","RightCameraRgbPub.inputs:renderProductPath"),
        ("RightCameraRP.outputs:renderProductPath","RightCameraInfoPub.inputs:renderProductPath"),
        ("OnPlaybackTick.outputs:tick",            "RightCameraRgbPub.inputs:execIn"),
        ("OnPlaybackTick.outputs:tick",            "RightCameraInfoPub.inputs:execIn"),

        # 前激光雷达
        ("OnPlaybackTick.outputs:tick",            "FrontLidarRP.inputs:execIn"),
        ("FrontLidarRP.outputs:renderProductPath", "FrontLidarPub.inputs:renderProductPath"),
        ("OnPlaybackTick.outputs:tick",            "FrontLidarPub.inputs:execIn"),

        # 后激光雷达
        ("OnPlaybackTick.outputs:tick",            "RearLidarRP.inputs:execIn"),
        ("RearLidarRP.outputs:renderProductPath",  "RearLidarPub.inputs:renderProductPath"),
        ("OnPlaybackTick.outputs:tick",            "RearLidarPub.inputs:execIn"),

        # IMU
        ("OnPlaybackTick.outputs:tick",            "ReadImu.inputs:execIn"),
        ("ReadImu.outputs:execOut",                "ImuPub.inputs:execIn"),
        ("ReadImu.outputs:orientation",            "ImuPub.inputs:orientation"),
        ("ReadImu.outputs:angVel",                 "ImuPub.inputs:angularVelocity"),
        ("ReadImu.outputs:linAcc",                 "ImuPub.inputs:linearAcceleration"),
        ("ReadSimTime.outputs:simulationTime",     "ImuPub.inputs:timeStamp"),
    ]

    # -------------------------------------------------------------------------
    # 参数设置
    # -------------------------------------------------------------------------
    set_values = [
        # 时钟
        ("ClockPub.inputs:topicName",          cfg.clock_topic),

        # 里程计
        ("OdomCompute.inputs:chassisPrim",     cfg.base_link_prim),
        ("OdomPub.inputs:topicName",           cfg.odom_topic),
        ("OdomPub.inputs:chassisFrameId",      cfg.base_frame),
        ("OdomPub.inputs:odomFrameId",         cfg.odom_frame),
        ("OdomTfPub.inputs:parentFrameId",     cfg.odom_frame),
        ("OdomTfPub.inputs:childFrameId",      cfg.base_frame),

        # 传感器 TF
        ("SensorTfPub.inputs:parentPrim",      cfg.base_link_prim),
        ("SensorTfPub.inputs:topicName",       "tf"),

        # ---- 前相机 ----
        ("FrontCameraRP.inputs:cameraPrim",    cfg.front_camera_prim),
        ("FrontCameraRP.inputs:width",         cfg.camera_resolution[0]),
        ("FrontCameraRP.inputs:height",        cfg.camera_resolution[1]),
        ("FrontCameraRgbPub.inputs:frameId",       cfg.front_camera_frame),
        ("FrontCameraRgbPub.inputs:nodeNamespace", cfg.front_camera_ns),
        ("FrontCameraRgbPub.inputs:topicName",     "rgb"),
        ("FrontCameraRgbPub.inputs:type",          "rgb"),
        ("FrontCameraRgbPub.inputs:frameSkipCount",cfg.camera_frame_skip_count),
        ("FrontCameraInfoPub.inputs:frameId",      cfg.front_camera_frame),
        ("FrontCameraInfoPub.inputs:nodeNamespace",cfg.front_camera_ns),
        ("FrontCameraInfoPub.inputs:topicName",    "camera_info"),
        ("FrontCameraInfoPub.inputs:frameSkipCount",cfg.camera_frame_skip_count),

        # ---- 后相机 ----
        ("RearCameraRP.inputs:cameraPrim",     cfg.rear_camera_prim),
        ("RearCameraRP.inputs:width",          cfg.camera_resolution[0]),
        ("RearCameraRP.inputs:height",         cfg.camera_resolution[1]),
        ("RearCameraRgbPub.inputs:frameId",        cfg.rear_camera_frame),
        ("RearCameraRgbPub.inputs:nodeNamespace",  cfg.rear_camera_ns),
        ("RearCameraRgbPub.inputs:topicName",      "rgb"),
        ("RearCameraRgbPub.inputs:type",           "rgb"),
        ("RearCameraRgbPub.inputs:frameSkipCount", cfg.camera_frame_skip_count),
        ("RearCameraInfoPub.inputs:frameId",       cfg.rear_camera_frame),
        ("RearCameraInfoPub.inputs:nodeNamespace", cfg.rear_camera_ns),
        ("RearCameraInfoPub.inputs:topicName",     "camera_info"),
        ("RearCameraInfoPub.inputs:frameSkipCount",cfg.camera_frame_skip_count),

        # ---- 左相机 ----
        ("LeftCameraRP.inputs:cameraPrim",     cfg.left_camera_prim),
        ("LeftCameraRP.inputs:width",          cfg.camera_resolution[0]),
        ("LeftCameraRP.inputs:height",         cfg.camera_resolution[1]),
        ("LeftCameraRgbPub.inputs:frameId",        cfg.left_camera_frame),
        ("LeftCameraRgbPub.inputs:nodeNamespace",  cfg.left_camera_ns),
        ("LeftCameraRgbPub.inputs:topicName",      "rgb"),
        ("LeftCameraRgbPub.inputs:type",           "rgb"),
        ("LeftCameraRgbPub.inputs:frameSkipCount", cfg.camera_frame_skip_count),
        ("LeftCameraInfoPub.inputs:frameId",       cfg.left_camera_frame),
        ("LeftCameraInfoPub.inputs:nodeNamespace", cfg.left_camera_ns),
        ("LeftCameraInfoPub.inputs:topicName",     "camera_info"),
        ("LeftCameraInfoPub.inputs:frameSkipCount",cfg.camera_frame_skip_count),

        # ---- 右相机 ----
        ("RightCameraRP.inputs:cameraPrim",    cfg.right_camera_prim),
        ("RightCameraRP.inputs:width",         cfg.camera_resolution[0]),
        ("RightCameraRP.inputs:height",        cfg.camera_resolution[1]),
        ("RightCameraRgbPub.inputs:frameId",        cfg.right_camera_frame),
        ("RightCameraRgbPub.inputs:nodeNamespace",  cfg.right_camera_ns),
        ("RightCameraRgbPub.inputs:topicName",      "rgb"),
        ("RightCameraRgbPub.inputs:type",           "rgb"),
        ("RightCameraRgbPub.inputs:frameSkipCount", cfg.camera_frame_skip_count),
        ("RightCameraInfoPub.inputs:frameId",       cfg.right_camera_frame),
        ("RightCameraInfoPub.inputs:nodeNamespace", cfg.right_camera_ns),
        ("RightCameraInfoPub.inputs:topicName",     "camera_info"),
        ("RightCameraInfoPub.inputs:frameSkipCount",cfg.camera_frame_skip_count),

        # ---- 前激光雷达 ----
        ("FrontLidarRP.inputs:cameraPrim",    cfg.front_lidar_prim),
        ("FrontLidarPub.inputs:frameId",      cfg.front_lidar_frame),
        ("FrontLidarPub.inputs:nodeNamespace",cfg.front_lidar_ns),
        ("FrontLidarPub.inputs:topicName",    "point_cloud"),
        ("FrontLidarPub.inputs:type",         "point_cloud"),
        ("FrontLidarPub.inputs:fullScan",     True),
        ("FrontLidarPub.inputs:showDebugView",False),
        ("FrontLidarPub.inputs:frameSkipCount",cfg.lidar_frame_skip_count),

        # ---- 后激光雷达 ----
        ("RearLidarRP.inputs:cameraPrim",    cfg.rear_lidar_prim),
        ("RearLidarPub.inputs:frameId",      cfg.rear_lidar_frame),
        ("RearLidarPub.inputs:nodeNamespace",cfg.rear_lidar_ns),
        ("RearLidarPub.inputs:topicName",    "point_cloud"),
        ("RearLidarPub.inputs:type",         "point_cloud"),
        ("RearLidarPub.inputs:fullScan",     True),
        ("RearLidarPub.inputs:showDebugView",False),
        ("RearLidarPub.inputs:frameSkipCount",cfg.lidar_frame_skip_count),

        # ---- IMU ----
        ("ReadImu.inputs:readGravity", True),
        ("ImuPub.inputs:frameId",      cfg.imu_frame),
        ("ImuPub.inputs:nodeNamespace",cfg.imu_ns),
        ("ImuPub.inputs:topicName",    "data"),
    ]

    og.Controller.edit(
        {"graph_path": cfg.graph_path, "evaluator_name": "execution"},
        {
            keys.CREATE_NODES: create_nodes,
            keys.CONNECT: connections,
            keys.SET_VALUES: set_values,
        },
    )

    # -------------------------------------------------------------------------
    # target inputs（不能通过 SET_VALUES 设置，需单独处理）
    # -------------------------------------------------------------------------
    # IMU prim
    try:
        imu_attr = og.Controller.attribute(f"{cfg.graph_path}/ReadImu.inputs:imuPrim")
        imu_attr.set(cfg.imu_sensor_prim)
        print(f"[ROS2] ReadImu.inputs:imuPrim set to: {cfg.imu_sensor_prim}")
    except Exception as e:
        print(f"[ROS2] Warning: could not set imuPrim via og.Controller: {e}")
        try:
            read_imu_prim = get_prim_at_path(f"{cfg.graph_path}/ReadImu")
            if read_imu_prim and read_imu_prim.IsValid():
                set_targets(read_imu_prim, "inputs:imuPrim", [cfg.imu_sensor_prim])
                print("[ROS2] ReadImu.inputs:imuPrim set via set_targets (fallback)")
        except Exception as e2:
            print(f"[ROS2] ERROR: imuPrim could not be set: {e2}")

    # 传感器 TF 目标（四相机 + 两雷达 + IMU 全部加入）
    sensor_tf_prim = get_prim_at_path(f"{cfg.graph_path}/SensorTfPub")
    if sensor_tf_prim and sensor_tf_prim.IsValid():
        set_targets(
            sensor_tf_prim,
            "inputs:targetPrims",
            [
                # 四相机的 prim（CameraCfg 里的实际相机 prim）
                cfg.front_camera_prim,
                cfg.rear_camera_prim,
                cfg.left_camera_prim,
                cfg.right_camera_prim,
                # 激光雷达（mount + sensor）
                cfg.front_lidar_mount_prim,
                cfg.front_lidar_prim,
                cfg.rear_lidar_mount_prim,
                cfg.rear_lidar_prim,
                # IMU
                cfg.imu_mount_prim,
                cfg.imu_sensor_prim,
            ],
        )

    print(f"[ROS2] Bridge graph created at {cfg.graph_path}")
    return cfg.graph_path