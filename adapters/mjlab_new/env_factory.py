"""
Environment Factory
基于 Contract 创建 MJLab 训练环境
参考 mjlab_new 和 microduck_all
"""

from typing import Dict, Any, Optional
from pathlib import Path
import numpy as np

from contracts.robot_contract_v2 import RobotContractV2
from contracts.asset_paths import resolve_asset_path


class EnvFactory:
    """环境工厂 - 基于 Contract 创建环境"""

    @staticmethod
    def create_from_contract(
        contract: RobotContractV2,
        task_config: Optional[Dict[str, Any]] = None
    ):
        """
        从 Contract 创建训练环境

        Args:
            contract: Robot Contract V2
            task_config: 任务配置（奖励权重、地形等）

        Returns:
            env: 训练环境实例
        """
        if task_config is None:
            task_config = {}

        # 环境配置
        env_config = {
            # 基础配置
            "num_envs": task_config.get("num_envs", 4096),
            "episode_length_s": task_config.get("episode_length_s", 20.0),

            # 控制频率（从 Contract）
            "control_hz": contract.control.control_hz,
            "physics_hz": contract.control.physics_hz,
            "decimation": contract.control.decimation,

            # 观测/动作维度（从 Contract）
            "num_observations": contract.observation.dimension,
            "num_actions": contract.action.dimension,

            # URDF 路径
            "urdf_path": contract.urdf.path,
            "asset_format": Path(contract.urdf.path).suffix.lower().lstrip(".") or "mjcf",
            "asset_path_resolved": str(resolve_asset_path(contract.urdf.path)),
            "asset_dir": str(resolve_asset_path(contract.urdf.path).parent / "assets"),
            "robot_id": contract.robot_id,
            "family": contract.family,
            "size_class": contract.size_class,
            "locomotion_type": contract.locomotion_type,

            # 关节配置
            "actuated_joints": contract.joints.actuated_joints,
            "joint_order": contract.action.joint_order,
            "default_joint_angles": contract.joints.default_pose,

            # 动作缩放
            "action_scale": contract.action.action_scale,

            # 任务配置
            "reward_scales": task_config.get("reward_scales", {
                "tracking_lin_vel": 1.0,
                "tracking_ang_vel": 0.5,
                "lin_vel_z": -2.0,
                "ang_vel_xy": -0.05,
                "orientation": -1.0,
                "torques": -0.0002,
                "dof_vel": -0.0001,
                "dof_acc": -2.5e-7,
                "base_height": -1.0,
                "feet_air_time": 1.0,
                "collision": -1.0,
                "action_rate": -0.01,
                "stand_still": -0.5,
            }),

            # 命令范围
            "command_ranges": task_config.get("command_ranges", {
                "lin_vel_x": [-1.0, 1.0],
                "lin_vel_y": [-1.0, 1.0],
                "ang_vel_yaw": [-1.0, 1.0]
            }),

            # 噪声配置
            "noise": task_config.get("noise", {
                "add_noise": True,
                "noise_level": 1.0,
                "noise_scales": {
                    "dof_pos": 0.01,
                    "dof_vel": 1.5,
                    "lin_vel": 0.1,
                    "ang_vel": 0.2,
                    "gravity": 0.05,
                    "height_measurements": 0.1
                }
            }),

            # 地形配置
            "terrain": task_config.get("terrain", {
                "terrain_type": "plane",  # "plane" / "rough" / "stairs"
                "measure_heights": True,
                "terrain_length": 8.0,
                "terrain_width": 8.0
            }),

            # 初始化配置
            "init_state": {
                "pos": [0.0, 0.0, 0.3],
                "default_joint_angles": contract.joints.default_pose,
                "lin_vel": [0.0, 0.0, 0.0],
                "ang_vel": [0.0, 0.0, 0.0]
            }
        }

        # TODO: 实际创建环境
        # 这里需要根据实际的 mjlab_new API 创建
        # from mjlab import VecEnv
        # env = VecEnv(env_config)

        print("[EnvFactory] Environment configuration created:")
        print(f"  Robot: {contract.family}")
        print(f"  Num envs: {env_config['num_envs']}")
        print(f"  Control Hz: {env_config['control_hz']}")
        print(f"  Obs dim: {env_config['num_observations']}")
        print(f"  Act dim: {env_config['num_actions']}")

        # 临时：返回配置字典
        # 实际应该返回环境实例
        return env_config

    @staticmethod
    def validate_env_config(env_config: Dict[str, Any]) -> bool:
        """验证环境配置"""
        required_keys = [
            "num_envs",
            "num_observations",
            "num_actions",
            "urdf_path",
            "control_hz",
            "physics_hz"
        ]

        for key in required_keys:
            if key not in env_config:
                print(f"[EnvFactory] Missing required key: {key}")
                return False

        # 检查 URDF 存在
        from pathlib import Path
        if not resolve_asset_path(env_config["urdf_path"]).exists():
            print(f"[EnvFactory] URDF not found: {env_config['urdf_path']}")
            return False

        return True


# ========== 奖励配置预设 ==========

REWARD_PRESETS = {
    "forward_walk": {
        "tracking_lin_vel": 1.5,
        "tracking_ang_vel": 0.5,
        "orientation": -2.0,
        "base_height": -1.0,
        "torques": -0.0002,
        "action_rate": -0.01
    },

    "trot": {
        "tracking_lin_vel": 2.0,
        "feet_air_time": 1.5,
        "orientation": -1.5,
        "torques": -0.0001,
        "action_rate": -0.02
    },

    "rough_terrain": {
        "tracking_lin_vel": 1.0,
        "orientation": -3.0,
        "base_height": -2.0,
        "collision": -2.0,
        "stumble": -1.0,
        "torques": -0.0003
    }
}

REWARD_TERMS = {
    "tracking_lin_vel": {"label": "线速度跟踪", "default": 1.5, "description": "鼓励沿 X 轴稳定前进"},
    "tracking_ang_vel": {"label": "角速度稳定", "default": 0.5, "description": "抑制偏航角速度误差"},
    "orientation": {"label": "姿态稳定", "default": -2.0, "description": "惩罚机身倾倒"},
    "upright": {"label": "机身直立", "default": 0.1, "description": "惩罚跌倒和过低机身高度"},
    "base_height": {"label": "目标高度", "default": -1.0, "description": "保持机身在站立高度附近"},
    "torques": {"label": "执行器能耗", "default": -0.0002, "description": "降低控制输出平方和"},
    "action_rate": {"label": "动作平滑", "default": -0.01, "description": "抑制相邻动作突变"},
}


def get_reward_preset(task_name: str) -> Dict[str, float]:
    """获取奖励配置预设"""
    return REWARD_PRESETS.get(task_name, REWARD_PRESETS["forward_walk"])


def get_reward_terms() -> Dict[str, dict]:
    return REWARD_TERMS.copy()


if __name__ == "__main__":
    # 测试
    from contracts.robot_contract_v2 import create_go2_contract

    contract = create_go2_contract()

    # 创建环境配置
    env_config = EnvFactory.create_from_contract(
        contract=contract,
        task_config={
            "num_envs": 4096,
            "episode_length_s": 20.0,
            "reward_scales": get_reward_preset("forward_walk")
        }
    )

    print("\nEnvironment config created successfully!")
    print(f"Valid: {EnvFactory.validate_env_config(env_config)}")
