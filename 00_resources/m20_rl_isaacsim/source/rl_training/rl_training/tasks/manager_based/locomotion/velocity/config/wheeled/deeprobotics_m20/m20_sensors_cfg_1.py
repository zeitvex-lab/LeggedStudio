import omni.usd
import isaaclab.sim as sim_utils
from isaaclab.assets import AssetBaseCfg
from isaaclab.sensors import CameraCfg
from isaaclab.sim.utils import clone, create_prim
from isaaclab.utils import configclass
from pxr import Gf, UsdGeom
import omni.kit.commands


def set_xform_ops_isaaclab(prim, translate=(0.0, 0.0, 0.0), orient_wxyz=(1.0, 0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)):
    xform = UsdGeom.Xformable(prim)
    xform.ClearXformOpOrder()
    
    # Translate 默认请求的是 double，传入 Vec3d
    xform.AddTranslateOp().Set(Gf.Vec3d(*translate))
    
    # Orient 显式指定 double 精度
    xform.AddOrientOp(UsdGeom.XformOp.PrecisionDouble).Set(   
        Gf.Quatd(orient_wxyz[0], orient_wxyz[1], orient_wxyz[2], orient_wxyz[3])
    )
    
    # 显式指定 scale 为 double 精度，并使用 Gf.Vec3d
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
IMU_MOUNT_POS          = (0.0632,   -0.0268,  -0.0435)
FRONT_LIDAR_MOUNT_POS  = (0.35028,   0.0,     -0.013)
REAR_LIDAR_MOUNT_POS   = (-0.35028,  0.0,     -0.013)

# ---- 四环视相机安装位置 ----
# X 轴向前，Y 轴向左，Z 轴向上（ROS 坐标系）
# 根据实际机器人尺寸调整这四个值
FRONT_CAMERA_MOUNT_POS = ( 0.37646,  0.0,    0.03738)
REAR_CAMERA_MOUNT_POS  = (-0.37646,  0.0,    0.03738)
LEFT_CAMERA_MOUNT_POS  = ( 0.0,      0.20,   0.03738)   # ← 按实际侧边距修改
RIGHT_CAMERA_MOUNT_POS = ( 0.0,     -0.20,   0.03738)   # ← 按实际侧边距修改

# ---- 安装架朝向（wxyz 四元数，绕 Z 轴旋转）----
# 前：不旋转
IDENTITY_QUAT               = (1.0,      0.0, 0.0,  0.0)
# 后：绕 Z 旋转 180°  → (cos90°, 0, 0, sin90°) = (0, 0, 0, 1)
REAR_CAMERA_QUAT            = (0.0,      0.0, 0.0,  1.0)
# 左：绕 Z 旋转 +90°  → (cos45°, 0, 0, sin45°)
LEFT_CAMERA_QUAT            = (0.7071068, 0.0, 0.0,  0.7071068)
# 右：绕 Z 旋转 -90°  → (cos45°, 0, 0, -sin45°)
RIGHT_CAMERA_QUAT           = (0.7071068, 0.0, 0.0, -0.7071068)

LIDAR_HORIZONTAL_QUAT       = (1.0,      0.0, 0.0,  0.0)
REAR_LIDAR_REVERSE_QUAT     = (0.0,      0.0, 0.0,  1.0)

CAMERA_RESOLUTION = (640, 480)


# -----------------------------------------------------------------------------
# Stage prim paths（供 ROS2 bridge graph 引用）
# -----------------------------------------------------------------------------
BASE_LINK_PATH = "{ENV_REGEX_NS}/Robot/base_link"

# 相机
FRONT_CAMERA_MOUNT_PATH = f"{BASE_LINK_PATH}/front_camera_mount"
FRONT_CAMERA_PATH       = f"{FRONT_CAMERA_MOUNT_PATH}/front_camera"

REAR_CAMERA_MOUNT_PATH  = f"{BASE_LINK_PATH}/rear_camera_mount"
REAR_CAMERA_PATH        = f"{REAR_CAMERA_MOUNT_PATH}/rear_camera"

LEFT_CAMERA_MOUNT_PATH  = f"{BASE_LINK_PATH}/left_camera_mount"
LEFT_CAMERA_PATH        = f"{LEFT_CAMERA_MOUNT_PATH}/left_camera"

RIGHT_CAMERA_MOUNT_PATH = f"{BASE_LINK_PATH}/right_camera_mount"
RIGHT_CAMERA_PATH       = f"{RIGHT_CAMERA_MOUNT_PATH}/right_camera"

# 激光雷达
FRONT_LIDAR_MOUNT_PATH  = f"{BASE_LINK_PATH}/front_lidar_mount"
FRONT_LIDAR_PATH        = f"{FRONT_LIDAR_MOUNT_PATH}/front_lidar"
REAR_LIDAR_MOUNT_PATH   = f"{BASE_LINK_PATH}/rear_lidar_mount"
REAR_LIDAR_PATH         = f"{REAR_LIDAR_MOUNT_PATH}/rear_lidar"

# IMU
IMU_MOUNT_PATH          = f"{BASE_LINK_PATH}/body_imu_mount"
IMU_SENSOR_PATH         = f"{IMU_MOUNT_PATH}/imu_sensor"


# -----------------------------------------------------------------------------
# 相机安装架 cfg
# -----------------------------------------------------------------------------
def _make_camera_mount_cfg(prim_path: str, pos: tuple, rot: tuple) -> AssetBaseCfg:
    """通用相机安装架工厂，蓝色方块可视标记。"""
    return AssetBaseCfg(
        prim_path=prim_path,
        spawn=SensorMountCfg(
            visual_scale=(0.05, 0.025, 0.025),
            visual_color=(0.15, 0.45, 0.95),
        ),
        init_state=AssetBaseCfg.InitialStateCfg(pos=pos, rot=rot),
    )


def create_front_camera_mount_cfg() -> AssetBaseCfg:
    return _make_camera_mount_cfg(FRONT_CAMERA_MOUNT_PATH, FRONT_CAMERA_MOUNT_POS, IDENTITY_QUAT)

def create_rear_camera_mount_cfg() -> AssetBaseCfg:
    return _make_camera_mount_cfg(REAR_CAMERA_MOUNT_PATH,  REAR_CAMERA_MOUNT_POS,  REAR_CAMERA_QUAT)

def create_left_camera_mount_cfg() -> AssetBaseCfg:
    return _make_camera_mount_cfg(LEFT_CAMERA_MOUNT_PATH,  LEFT_CAMERA_MOUNT_POS,  LEFT_CAMERA_QUAT)

def create_right_camera_mount_cfg() -> AssetBaseCfg:
    return _make_camera_mount_cfg(RIGHT_CAMERA_MOUNT_PATH, RIGHT_CAMERA_MOUNT_POS, RIGHT_CAMERA_QUAT)


# -----------------------------------------------------------------------------
# 激光雷达安装架 cfg（保持不变）
# -----------------------------------------------------------------------------
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


# -----------------------------------------------------------------------------
# 相机传感器 cfg
# 四个相机共享相同的内参，offset.rot=(0.5,-0.5,0.5,-0.5) 是 Isaac→ROS 坐标系转换，
# 方向差异完全由各自的安装架旋转（mount rot）决定，不需要在这里改。
# -----------------------------------------------------------------------------
def _make_camera_cfg(prim_path: str) -> CameraCfg:
    """通用相机传感器工厂。"""
    return CameraCfg(
        prim_path=prim_path,
        update_period=0.01,
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
            rot=(0.5, -0.5, 0.5, -0.5),  # Isaac camera → ROS camera frame
            convention="ros",
        ),
    )


def create_front_camera_cfg() -> CameraCfg:
    return _make_camera_cfg(FRONT_CAMERA_PATH)

def create_rear_camera_cfg() -> CameraCfg:
    return _make_camera_cfg(REAR_CAMERA_PATH)

def create_left_camera_cfg() -> CameraCfg:
    return _make_camera_cfg(LEFT_CAMERA_PATH)

def create_right_camera_cfg() -> CameraCfg:
    return _make_camera_cfg(RIGHT_CAMERA_PATH)

@clone
def spawn_rtx_lidar(prim_path: str, cfg, translation=None, orientation=None, **kwargs):
    """自定义的 RTX Lidar 实例化器，修复类型匹配和导入问题"""
    
    # 1. 显式转换为 USD 期待的双精度类型 (Gf.Vec3d 和 Gf.Quatd)
    if translation is not None:
        translation_gf = Gf.Vec3d(*(float(v) for v in translation))
    else:
        translation_gf = Gf.Vec3d(0.0, 0.0, 0.0)

    if orientation is not None:
        # orientation 为 wxyz 格式
        orientation_gf = Gf.Quatd(
            float(orientation[0]), 
            float(orientation[1]), 
            float(orientation[2]), 
            float(orientation[3])
        )
    else:
        orientation_gf = Gf.Quatd(1.0, 0.0, 0.0, 0.0)

    # 2. 使用 omni.kit.commands 执行创建任务
    # 确保此处调用的 omni 已经在文件顶部 import
    success, prim = omni.kit.commands.execute(
        "IsaacSensorCreateRtxLidar",
        path=prim_path,
        parent=None,
        config="Example_Rotary",
        translation=translation_gf,
        orientation=orientation_gf,
    )
    
    # 3. 容错处理：如果命令没有直接返回 prim，则手动从 stage 获取
    if prim is None:
        stage = omni.usd.get_context().get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        
    return prim

@configclass
class RtxLidarSpawnerCfg(sim_utils.SpawnerCfg):
    func = spawn_rtx_lidar

# 创建真正的雷达传感器 CFG
def create_front_lidar_cfg() -> AssetBaseCfg:
    return AssetBaseCfg(
        prim_path=FRONT_LIDAR_PATH,
        spawn=RtxLidarSpawnerCfg(),
        # 位姿已由 mount 决定，传感器自身保持局部原点即可
        init_state=AssetBaseCfg.InitialStateCfg(pos=(0.0, 0.0, 0.0), rot=(1.0, 0.0, 0.0, 0.0)),
    )

def create_rear_lidar_cfg() -> AssetBaseCfg:
    return AssetBaseCfg(
        prim_path=REAR_LIDAR_PATH,
        spawn=RtxLidarSpawnerCfg(),
        init_state=AssetBaseCfg.InitialStateCfg(pos=(0.0, 0.0, 0.0), rot=(1.0, 0.0, 0.0, 0.0)),
    )