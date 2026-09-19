"""Unitree B2-W constants."""

from pathlib import Path

import mujoco

from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
from mjlab.actuator import XmlActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.utils.spec_config import CollisionCfg

##
# MJCF and assets.
##

GO2W_XML: Path = (
  _PACKAGE_DIR.parents[2] / "model" / "robot.xml"
)

# Requested action/joint order (matches Unitree SDK command order).
GO2W_LEG_JOINT_NAMES: tuple[str, ...] = (
  "FR_hip_joint",
  "FR_thigh_joint",
  "FR_calf_joint",
  "FL_hip_joint",
  "FL_thigh_joint",
  "FL_calf_joint",
  "RR_hip_joint",
  "RR_thigh_joint",
  "RR_calf_joint",
  "RL_hip_joint",
  "RL_thigh_joint",
  "RL_calf_joint",
)
GO2W_WHEEL_JOINT_NAMES: tuple[str, ...] = (
  r"FR_(foot|wheel)_joint",
  r"FL_(foot|wheel)_joint",
  r"RR_(foot|wheel)_joint",
  r"RL_(foot|wheel)_joint",
)
GO2W_ALL_JOINT_NAMES: tuple[str, ...] = GO2W_LEG_JOINT_NAMES + GO2W_WHEEL_JOINT_NAMES

GO2W_HIP_JOINT_NAMES: tuple[str, ...] = (
  "FR_hip_joint",
  "FL_hip_joint",
  "RR_hip_joint",
  "RL_hip_joint",
)
GO2W_THIGH_JOINT_NAMES: tuple[str, ...] = (
  "FR_thigh_joint",
  "FL_thigh_joint",
  "RR_thigh_joint",
  "RL_thigh_joint",
)
GO2W_CALF_JOINT_NAMES: tuple[str, ...] = (
  "FR_calf_joint",
  "FL_calf_joint",
  "RR_calf_joint",
  "RL_calf_joint",
)

GO2W_LEG_JOINT_REGEX: str = r"^(FR|FL|RR|RL)_(hip|thigh|calf)_joint$"
GO2W_WHEEL_JOINT_REGEX: str = r"^(FR|FL|RR|RL)_(foot|wheel)_joint$"


def get_spec() -> mujoco.MjSpec:
  if not GO2W_XML.exists():
    raise FileNotFoundError(
      f"Go2-W MJCF not found at {GO2W_XML}. "
      "Place your converted go2w.xml and meshes under this package."
    )
  return mujoco.MjSpec.from_file(str(GO2W_XML))


##
# Actuator config.
#
# B28 裁决:MJCF 为执行真值。model/robot.xml 的 <actuator> 段已内建全部 16 个
# 执行器(12 个 <position>:kp=160 kv=5,forcerange hip/thigh ±200、calf ±320;
# 4 个 <velocity>:kv=1,forcerange ±20;名字与目标关节同名),且所有关节
# armature=0.1、frictionloss=0 已写在 <joint> 上。训练源不得对这些关节重复
# 注册执行器(再 spec.add_actuator 同名即抛 repeated name → env 构建即崩)。
#
# 因此这里不再用 BuiltinPosition/VelocityActuatorCfg 重新生成执行器,而是用
# XmlActuatorCfg 显式「以 MJCF 为准」包装既有执行器:gains/limits/armature
# 全部沿用 MJCF 定义,本模块不提供任何覆盖参数。包装同时保持
# entity._actuators 非空——动作侧(JointPositionAction/JointVelocityAction 经
# Entity.find_joints_by_actuator_names 解析被驱动关节)与观测/随机化侧
# (actuator_ids → ctrl_ids)依赖该列表,故「整体跳过注册(空 actuators)」
# 不可行,只能包装。XmlActuator.compute 按 command_field 转发:position 组
# 出 position_target、velocity 组出 velocity_target,与原 Builtin 语义一致。
#
# 参数差异(训练 cfg 曾写 vs MJCF 真值,按裁决以 MJCF 为准,参数对齐另行裁决):
#   calf effort_limit:训练 cfg 曾写 300.0(go2w 移植残留);MJCF 与
#   contract_truth(actuator_profile.by_role.calf.effort)均为 320 → 运行时 320。
#   其余(hip/thigh 200、wheel 20、160/5/1 增益、armature 0.1)与 MJCF 一致。
##

GO2W_ACTUATOR_HIP = XmlActuatorCfg(
  target_names_expr=GO2W_HIP_JOINT_NAMES,
  command_field="position",
)
GO2W_ACTUATOR_THIGH = XmlActuatorCfg(
  target_names_expr=GO2W_THIGH_JOINT_NAMES,
  command_field="position",
)
GO2W_ACTUATOR_CALF = XmlActuatorCfg(
  target_names_expr=GO2W_CALF_JOINT_NAMES,
  command_field="position",
)
GO2W_ACTUATOR_WHEEL = XmlActuatorCfg(
  target_names_expr=GO2W_WHEEL_JOINT_NAMES,
  command_field="velocity",
)

##
# Keyframes.
##


INIT_STATE = EntityCfg.InitialStateCfg(
  pos=(0.0, 0.0, 0.4),
  joint_pos={
    "FR_hip_joint": 0.1,
    "FR_thigh_joint": 0.8,
    "FR_calf_joint": -1.5,
    "FL_hip_joint": -0.1,
    "FL_thigh_joint": 0.8,
    "FL_calf_joint": -1.5,
    "RR_hip_joint": 0.1,
    "RR_thigh_joint": 0.8,
    "RR_calf_joint": -1.5,
    "RL_hip_joint": -0.1,
    "RL_thigh_joint": 0.8,
    "RL_calf_joint": -1.5,
    r"FR_(foot|wheel)_joint": 0.0,
    r"FL_(foot|wheel)_joint": 0.0,
    r"RR_(foot|wheel)_joint": 0.0,
    r"RL_(foot|wheel)_joint": 0.0,
  },
  joint_vel={".*": 0.0},
)

##
# Collision config.
##

FULL_COLLISION = CollisionCfg(
  geom_names_expr=(".*_collision",),
  contype=1,
  conaffinity=0,
  condim={r".*(wheel|foot)_collision$": 3, ".*_collision": 1},
  priority={r".*(wheel|foot)_collision$": 1, ".*": 0},
  friction={r".*(wheel|foot)_collision$": (0.6,)},
)

##
# Final config.
##

GO2W_ARTICULATION = EntityArticulationInfoCfg(
  actuators=(
    GO2W_ACTUATOR_HIP,
    GO2W_ACTUATOR_THIGH,
    GO2W_ACTUATOR_CALF,
    GO2W_ACTUATOR_WHEEL,
  ),
  soft_joint_pos_limit_factor=0.9,
)


def get_go2w_robot_cfg() -> EntityCfg:
  """Get a fresh Go2-W robot configuration instance."""
  return EntityCfg(
    init_state=INIT_STATE,
    collisions=(FULL_COLLISION,),
    spec_fn=get_spec,
    articulation=GO2W_ARTICULATION,
  )
