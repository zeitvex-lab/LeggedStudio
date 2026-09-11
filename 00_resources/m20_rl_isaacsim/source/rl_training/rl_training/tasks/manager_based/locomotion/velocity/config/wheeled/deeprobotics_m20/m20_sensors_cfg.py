import omni.usd
import isaaclab.sim as sim_utils
from isaaclab.assets import AssetBaseCfg
from isaaclab.sensors import CameraCfg
from isaaclab.sim.utils import clone, create_prim
from isaaclab.utils import configclass
from pxr import Gf, UsdGeom


def set_xform_ops_isaaclab(prim, translate=(0.0, 0.0, 0.0), orient_wxyz=(1.0, 0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)):
    xform = UsdGeom.Xformable(prim)
    xform.ClearXformOpOrder()
    
    # Translate 默认请求的是 double，传入 Vec3d
    xform.AddTranslateOp().Set(Gf.Vec3d(*translate))
    
    # Orient 显式指定 double 精度
    xform.AddOrientOp(UsdGeom.XformOp.PrecisionDouble).Set(   
        Gf.Quatd(orient_wxyz[0], orient_wxyz[1], orient_wxyz[2], orient_wxyz[3])
    )
    
    # 【修改这里】：显式指定 scale 为 double 精度，并使用 Gf.Vec3d
    xform.AddScaleOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*scale))


@clone
def spawn_sensor_mount(prim_path: str, cfg, translation=None, orientation=None, **kwargs):
    """Spawn or reuse a visible Xform mount.

    修复：无论 prim 是否已存在，都强制用 IsaacLab 标准顺序写入 transform，
    保证修改 FRONT_LIDAR_MOUNT_POS 等常量后仿真里位置实际变化。
    """
    translation = (0.0, 0.0, 0.0) if translation is None else translation
    orientation = (1.0, 0.0, 0.0, 0.0) if orientation is None else orientation  # wxyz

    stage = omni.usd.get_context().get_stage()
    prim = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        prim = create_prim(prim_path, "Xform")

    # 无论 prim 是新建还是已存在，都强制用 [translate, orient, scale] 覆写
    set_xform_ops_isaaclab(prim, translate=translation, orient_wxyz=orientation)

    visual_path = f"{prim_path}/visual"
    visual_prim = stage.GetPrimAtPath(visual_path)
    if not visual_prim.IsValid():
        create_prim(
            visual_path,
            "Cube",
            scale=cfg.visual_scale,
            translation=(0.0, 0.0, 0.0),
            attributes={
                "size": 1.0,
                "primvars:displayColor": [cfg.visual_color],
            },
        )

    return stage.GetPrimAtPath(prim_path)


@configclass
class SensorMountCfg(sim_utils.SpawnerCfg):
    func = spawn_sensor_mount
    visual_scale: tuple[float, float, float] = (0.03, 0.03, 0.03)
    visual_color: tuple[float, float, float] = (0.7, 0.7, 0.7)


# -----------------------------------------------------------------------------
# Sensor extrinsics relative to base_link (meters)
# 修改这里的值后，仿真里会立即生效（已修复 transform 覆写问题）
# -----------------------------------------------------------------------------
IMU_MOUNT_POS = (0.0632, -0.0268, -0.0435)
CAMERA_MOUNT_POS = (0.37646, 0.0, 0.03738)
FRONT_LIDAR_MOUNT_POS = (0.35028, 0.0, -0.013)
REAR_LIDAR_MOUNT_POS = (-0.35028, 0.0, -0.013)

IDENTITY_QUAT = (1.0, 0.0, 0.0, 0.0)
LIDAR_HORIZONTAL_QUAT = (1.0, 0.0, 0.0, 0.0)
REAR_LIDAR_REVERSE_QUAT = (0.0, 0.0, 0.0, 1.0)

CAMERA_RESOLUTION = (640, 480)


# Stage paths used later by ROS2 bridge graph
BASE_LINK_PATH = "{ENV_REGEX_NS}/Robot/base_link"
FRONT_CAMERA_MOUNT_PATH = f"{BASE_LINK_PATH}/front_camera_mount"
FRONT_CAMERA_PATH = f"{FRONT_CAMERA_MOUNT_PATH}/front_camera"
FRONT_LIDAR_MOUNT_PATH = f"{BASE_LINK_PATH}/front_lidar_mount"
FRONT_LIDAR_PATH = f"{FRONT_LIDAR_MOUNT_PATH}/front_lidar"
REAR_LIDAR_MOUNT_PATH = f"{BASE_LINK_PATH}/rear_lidar_mount"
REAR_LIDAR_PATH = f"{REAR_LIDAR_MOUNT_PATH}/rear_lidar"
IMU_MOUNT_PATH = f"{BASE_LINK_PATH}/body_imu_mount"
IMU_SENSOR_PATH = f"{IMU_MOUNT_PATH}/imu_sensor"


def create_front_camera_mount_cfg() -> AssetBaseCfg:
    return AssetBaseCfg(
        prim_path=FRONT_CAMERA_MOUNT_PATH,
        spawn=SensorMountCfg(
            visual_scale=(0.05, 0.025, 0.025),
            visual_color=(0.15, 0.45, 0.95),
        ),
        init_state=AssetBaseCfg.InitialStateCfg(
            pos=CAMERA_MOUNT_POS,
            rot=IDENTITY_QUAT,
        ),
    )


def create_front_lidar_mount_cfg() -> AssetBaseCfg:
    return AssetBaseCfg(
        prim_path=FRONT_LIDAR_MOUNT_PATH,
        spawn=SensorMountCfg(
            visual_scale=(0.06, 0.03, 0.06),
            visual_color=(0.95, 0.45, 0.10),
        ),
        init_state=AssetBaseCfg.InitialStateCfg(
            pos=FRONT_LIDAR_MOUNT_POS,
            rot=LIDAR_HORIZONTAL_QUAT,
        ),
    )


def create_rear_lidar_mount_cfg() -> AssetBaseCfg:
    return AssetBaseCfg(
        prim_path=REAR_LIDAR_MOUNT_PATH,
        spawn=SensorMountCfg(
            visual_scale=(0.06, 0.03, 0.06),
            visual_color=(0.95, 0.75, 0.10),
        ),
        init_state=AssetBaseCfg.InitialStateCfg(
            pos=REAR_LIDAR_MOUNT_POS,
            rot=REAR_LIDAR_REVERSE_QUAT,
        ),
    )


def create_body_imu_mount_cfg() -> AssetBaseCfg:
    return AssetBaseCfg(
        prim_path=IMU_MOUNT_PATH,
        spawn=SensorMountCfg(
            visual_scale=(0.035, 0.02, 0.02),
            visual_color=(0.15, 0.85, 0.35),
        ),
        init_state=AssetBaseCfg.InitialStateCfg(
            pos=IMU_MOUNT_POS,
            rot=IDENTITY_QUAT,
        ),
    )


def create_front_camera_cfg() -> CameraCfg:
    return CameraCfg(
        prim_path=FRONT_CAMERA_PATH,
        update_period=0.0,
        height=CAMERA_RESOLUTION[1],
        width=CAMERA_RESOLUTION[0],
        data_types=["rgb"],
        spawn=sim_utils.PinholeCameraCfg(
            focal_length=24.0,
            focus_distance=400.0,
            horizontal_aperture=20.955,
            clipping_range=(0.05, 1.0e5),
        ),
        offset=CameraCfg.OffsetCfg(
            pos=(0.0, 0.0, 0.0),
            rot=(0.5, -0.5, 0.5, -0.5),
            convention="ros",
        ),
    )