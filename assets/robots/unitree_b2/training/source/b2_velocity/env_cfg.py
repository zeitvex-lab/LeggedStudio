"""Unitree B2 velocity environment configurations.

Quadruped flat/rough velocity tasks built from the package-local robot
constants and mjlab's shared velocity base.  The wiring mirrors the A2
tuning documented in the package manifest (root body ``base_link``, four
leg feet, 0.5 m command z-offset) so the trained policy matches the
deployed sim2sim contract.

B8 训练去包化（试点轮）：与 deeprobotics_lite3 逐字重复的装配骨架（sim 上限 /
高度扫描重指 / viewer / play 与 flat 收尾 / PPO runner）上移到
``adapters/mjlab/velocity_task_kit``；本文件只留 B2 专属 wiring 与入口
stub（entrypoint 符号仍在原模块原符号名，静态解析与运行时加载不受影响）。
"""

from __future__ import annotations

import sys
from pathlib import Path

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs.mdp.actions import JointPositionActionCfg
from mjlab.managers import TerminationTermCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg
from mjlab.tasks.velocity import mdp
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg

# 仓库根自举（见 velocity_task_kit 模块注释）：worker / schema-dump / 冒烟三种
# 运行环境都只把 training/source 或包根放进 sys.path；沿目录向上找 adapters/mjlab
# 对 assets 源树与 workspace 镜像副本两种深度都成立。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab import velocity_task_kit as kit  # noqa: E402

from .robot_constants import B2_ACTION_SCALE, get_b2_robot_cfg

_QUAD_FEET = ("FR", "FL", "RR", "RL")
_QUAD_GEOMS = tuple(f"{name}_foot_collision" for name in _QUAD_FEET)
_ROOT_BODY = "base_link"


def _contact_sensors() -> tuple[ContactSensorCfg, ContactSensorCfg]:
    feet = ContactSensorCfg(
        name="feet_ground_contact",
        primary=ContactMatch(
            mode="geom", pattern=_QUAD_GEOMS, entity="robot"
        ),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
        track_air_time=True,
    )
    other = ContactSensorCfg(
        name="nonfoot_ground_touch",
        primary=ContactMatch(mode="geom", pattern=".*_collision", entity="robot"),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
        track_air_time=True,
    )
    return feet, other


def _configure_posture(cfg: ManagerBasedRlEnvCfg) -> None:
    cfg.rewards["pose"].params["std_standing"] = {
        r".*_(hip|thigh)_joint.*": 0.05,
        r".*_calf_joint.*": 0.1,
    }
    moving = {
        r".*_(hip|thigh)_joint.*": 0.3,
        r".*_calf_joint.*": 0.6,
    }
    cfg.rewards["pose"].params["std_walking"] = moving
    cfg.rewards["pose"].params["std_running"] = moving


def make_b2_rough_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Rough-terrain A2 velocity configuration."""
    cfg = kit.new_velocity_env_cfg(get_b2_robot_cfg())
    # 足端高度扫描沿用基座的 site 帧（B2 MJCF 四腿有命名 site，与 lite3 的
    # body 帧裁决 B31 不同源，见 kit.repoint_height_scan_sensors 注释）。
    kit.repoint_height_scan_sensors(
        cfg, root_body=_ROOT_BODY, foot_frames=_QUAD_FEET, frame_type="site"
    )
    feet_sensor, other_sensor = _contact_sensors()
    cfg.scene.sensors = (cfg.scene.sensors or ()) + (feet_sensor, other_sensor)

    if cfg.scene.terrain is not None and cfg.scene.terrain.terrain_generator is not None:
        cfg.scene.terrain.terrain_generator.curriculum = True

    action = cfg.actions["joint_pos"]
    assert isinstance(action, JointPositionActionCfg)
    action.scale = B2_ACTION_SCALE

    # The base foot_friction event references geom names that do not exist
    # on this robot (its MJCF geoms are unnamed); drop it.
    cfg.events.pop("foot_friction", None)

    kit.set_viewer(cfg, body_name=_ROOT_BODY)
    command = cfg.commands["twist"]
    assert isinstance(command, UniformVelocityCommandCfg)
    command.viz.z_offset = 0.5

    cfg.events["base_com"].params["asset_cfg"].body_names = (_ROOT_BODY,)
    _configure_posture(cfg)
    cfg.rewards["upright"].params["asset_cfg"].body_names = (_ROOT_BODY,)
    cfg.rewards["body_ang_vel"].params["asset_cfg"].body_names = (_ROOT_BODY,)
    for name in ("foot_clearance", "foot_slip"):
        cfg.rewards[name].params["asset_cfg"].site_names = _QUAD_FEET

    cfg.terminations.pop("fell_over", None)
    cfg.terminations["illegal_contact"] = TerminationTermCfg(
        func=mdp.illegal_contact,
        params={"sensor_name": other_sensor.name, "force_threshold": 10.0},
    )

    if play:
        kit.apply_play_postlude(cfg, drop_push_event=True, add_randomize_terrain=True)
        cfg.terminations.pop("out_of_terrain_bounds", None)
    return cfg


def make_b2_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Flat-ground A2 velocity configuration."""
    cfg = make_b2_rough_env_cfg(play=play)
    kit.apply_flat_postlude(cfg, drop_terrain_scan_sensor=True, drop_height_scan_obs=True)
    if play:
        command = cfg.commands["twist"]
        assert isinstance(command, UniformVelocityCommandCfg)
        command.ranges.lin_vel_x = (-1.0, 1.5)
        command.ranges.lin_vel_y = (-0.5, 0.5)
        command.ranges.ang_vel_z = (-0.7, 0.7)
    return cfg


def b2_flat_env_cfg(*, play: bool = False):
    return make_b2_flat_env_cfg(play=play)


def b2_rough_env_cfg(*, play: bool = False):
    return make_b2_rough_env_cfg(play=play)


def b2_runner_cfg():
    return kit.ppo_runner_cfg("b2_velocity")
