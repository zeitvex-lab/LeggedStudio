import isaaclab.sim as sim_utils
from isaaclab.assets import AssetBaseCfg
from isaaclab.sensors import CameraCfg
from isaaclab.utils import configclass
from isaaclab.terrains import TerrainImporterCfg
from .m20_sensors_cfg import (
    create_body_imu_mount_cfg,
    create_front_camera_cfg,
    create_front_camera_mount_cfg,
    #zheli
    # create_rear_camera_mount_cfg,
    # create_rear_camera_cfg,
    # create_left_camera_mount_cfg,
    # create_left_camera_cfg,
    # create_right_camera_mount_cfg,
    # create_right_camera_cfg,
    create_front_lidar_mount_cfg,
    create_rear_lidar_mount_cfg,
    # create_front_lidar_cfg,    # <== 新增导入
    # create_rear_lidar_cfg,

)
from .rough_fixed_obstacle_env_cfg import (
    DeeproboticsM20FixedObstacleEnvCfg,
    DeeproboticsM20FixedObstacleSceneCfg,
)

# -----------------------------------------------------------------------
# 3DGS USDZ 资产路径
# -----------------------------------------------------------------------
_3DGS_USDZ = "/home/user/3dgs/20260408/3dgs_k1/ply/yq/iteration_100/yq_1_mesh_vis.usdz"
# 修复 ValueError：使用以 "/" 开头的正则路径，绕过 Isaac Lab 的全局路径检查
_3DGS_PRIM_PATH = "/World/envs/env_0/gauss"
_3DGS_MESH_PATH = "/World/envs/env_0/gauss/gauss/mesh"

_RAY_CASTER_ATTRS = ("height_scanner", "height_scanner_base")


@configclass
class DeeproboticsM20PerceptionSceneCfg(DeeproboticsM20FixedObstacleSceneCfg):
    """Fixed-obstacle scene 替换为 3DGS USDZ 环境 + ROS2 传感器挂载点。"""

    # ------------------------------------------------------------------
    # 移除父类里的台阶和平台
    # ------------------------------------------------------------------
    platform: AssetBaseCfg = None        # type: ignore[assignment]
    stair_step_1: AssetBaseCfg = None    # type: ignore[assignment]
    stair_step_2: AssetBaseCfg = None    # type: ignore[assignment]
    stair_step_3: AssetBaseCfg = None    # type: ignore[assignment]

    # ------------------------------------------------------------------
    # 3DGS USDZ 场景
    # ------------------------------------------------------------------
    gaussian_scene: AssetBaseCfg = AssetBaseCfg(    
        prim_path=_3DGS_PRIM_PATH,      
        spawn=sim_utils.UsdFileCfg(
            usd_path=_3DGS_USDZ,
            collision_props=sim_utils.CollisionPropertiesCfg(
                collision_enabled=True,
                # 【关键点】：指定碰撞近似方式
                # "mesh" 表示直接使用网格面片，最精确但最吃性能
                # "convexDecomposition" 会生成凹凸包，性能较好

            ),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(
                rigid_body_enabled=True,
                kinematic_enabled=True, # 保持动力学开启，防止受重力掉落
                disable_gravity=True,
            ),
        ),
    )

    # ------------------------------------------------------------------
    # 传感器挂载点（保持不变）
    # ------------------------------------------------------------------
    front_camera_mount: AssetBaseCfg = create_front_camera_mount_cfg()
    #zheli
    # rear_camera_mount: AssetBaseCfg  = create_rear_camera_mount_cfg()
    # left_camera_mount : AssetBaseCfg = create_left_camera_mount_cfg()
    # right_camera_mount: AssetBaseCfg = create_right_camera_mount_cfg()

    front_lidar_mount: AssetBaseCfg = create_front_lidar_mount_cfg()
    rear_lidar_mount: AssetBaseCfg = create_rear_lidar_mount_cfg()
    # front_lidar: AssetBaseCfg = create_front_lidar_cfg()
    # rear_lidar: AssetBaseCfg = create_rear_lidar_cfg()
    body_imu_mount: AssetBaseCfg = create_body_imu_mount_cfg()
    
    front_camera: CameraCfg = create_front_camera_cfg()
    # zheli
    # rear_camera: CameraCfg = create_rear_camera_cfg()
    # left_camera: CameraCfg  = create_left_camera_cfg()
    # right_camera: CameraCfg  = create_right_camera_cfg()

@configclass
class DeeproboticsM20PerceptionEnvCfg(DeeproboticsM20FixedObstacleEnvCfg):
    scene: DeeproboticsM20PerceptionSceneCfg = DeeproboticsM20PerceptionSceneCfg(
        num_envs=1,
        env_spacing=5.0,
    )

    def __post_init__(self):
        super().__post_init__()
        self.scene.terrain = None
        
        # ------------------------------------------------------------------
        # 保持你原始代码中的防御性清理逻辑
        # ------------------------------------------------------------------
        for attr_name in (
            "obstacle",
            "obstacles",
            "fixed_obstacle",
            "fixed_obstacles",
            "boxes",
            "props",
        ):
            if hasattr(self.scene, attr_name):
                setattr(self.scene, attr_name, None)

        # 把 ray caster 的 mesh_prim_paths 改指向 3DGS 资产
        for attr_name in _RAY_CASTER_ATTRS:
            sensor_cfg = getattr(self.scene, attr_name, None)
            if sensor_cfg is not None and hasattr(sensor_cfg, "mesh_prim_paths"):
                sensor_cfg.mesh_prim_paths = [_3DGS_MESH_PATH]

        # ------------------------------------------------------------------
        # 保持你原始代码中的观察值与随机化禁用逻辑
        # ------------------------------------------------------------------
        if hasattr(self, "observations"):
            if hasattr(self.observations, "critic"):
                self.observations.critic = None

            if hasattr(self.observations, "policy"):
                for term_name in ("height_scan", "height_scan_raw"):
                    if hasattr(self.observations.policy, term_name):
                        setattr(self.observations.policy, term_name, None)

        self.disable_zero_weight_rewards()

        # 确定性启动（关闭所有随机化）
        self.events.randomize_rigid_body_material = None
        self.events.randomize_rigid_body_mass = None
        self.events.randomize_rigid_body_mass_base = None
        self.events.randomize_rigid_body_inertia = None
        self.events.randomize_com_positions = None
        self.events.randomize_apply_external_force_torque = None
        self.events.randomize_actuator_gains = None
        self.events.randomize_push_robot = None

        self.curriculum.terrain_levels = None
        self.curriculum.command_levels = None

        # 保持你原始定义的 reset_base.params
        self.events.randomize_reset_base.params = {
            "pose_range": {
                "x": (0.0, 0.0), "y": (0.0, 0.0), "z": (0.0, 0.0),
                "roll": (0.0, 0.0), "pitch": (0.0, 0.0), "yaw": (0.0, 0.0),
            },
            "velocity_range": {
                "x": (0.0, 0.0), "y": (0.0, 0.0), "z": (0.0, 0.0),
                "roll": (0.0, 0.0), "pitch": (0.0, 0.0), "yaw": (0.0, 0.0),
            },
        }

        self.sim.physics_material = sim_utils.RigidBodyMaterialCfg(
            friction_combine_mode="multiply",
            restitution_combine_mode="multiply",
            static_friction=1.0,
            dynamic_friction=1.0,
            restitution=0.0,
        )