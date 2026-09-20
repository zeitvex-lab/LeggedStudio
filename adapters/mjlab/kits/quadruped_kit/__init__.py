"""四足形态 Kit（quadruped）—— 框架层唯一真值。

## 这份代码从哪来

原先叫 ``adapters/mjlab/velocity_task_kit``（B8 训练去包化试点），当时它同时服务两组包：

* **四足组**（``unitree_b2`` / ``deeprobotics_lite3``）：用本模块的装配骨架 ——
  包内 MJCF 真值解析 / ``XmlActuatorCfg`` 执行器包装 / velocity env 装配 /
  高度扫描重指 / viewer 与 play 收尾 / ``ppo_runner_cfg``；
* **轮足组**（``deeprobotics_m20`` / ``unitree_b2w`` / ``unitree_go2w``）：用
  ``mdp/`` 框架族 + ``velocity_env_cfg.py`` + ``ppo_runner_cfg_ex``。

2026-09-19 按形态拆成两个 Kit（决策依据与三条否决理由见
``00_know/90_归档/07_形态Kit设计草案.md``）——**两组用的符号完全不重叠**，
所以这是纯归属划分：没有共享代码、没有双份、没有行为变更。
包侧 stub 的调用点只改模块名（``from adapters.mjlab.kits import quadruped_kit as kit``）。

## 边界

* **管**：装配骨架 / 执行器包装机制 / 运行器配置 —— 即"与任务无关的框架层"；
* **不管**：任何物理数值（契约真值 → MJCF 是执行真值）、半自主参数**取值**（Kit 只给方法）、
  状态与进度（在 `05`）；
* 任务特有部分（奖励表 / 传感器 / 终止 / 常量）与入口 stub **留在包内**
  （entrypoint 符号仍在 ``<pkg>_velocity.env_cfg`` 模块内，
  ``tools/audit_training_entrypoints.py`` 的静态解析不受影响）。

对照手册：``00_resources/mjlab-skillkit/``（dict-based manager、迁移配方、
preserve-layout 模式）——只对照写法，不引入其 adapters/agents 目录；本模块归属
仓库既有的 mjlab 适配边界 ``adapters/mjlab/``。

语义保持承诺：每个函数都标注来源（哪一包的哪一段原样上移），默认参数即各包
出现过的字面常量；调用方按原顺序调用即可复现原构建序列。任何 mjlab 1.6 API
适配（B22/B26/B28/B31/B35 的裁决语义）原样保留，注释随任务特有部分留在包内。

供包内 stub 导入的健壮性：worker / schema-dump / 冒烟三处运行环境都只把
``training/source``（或包根）放进 ``sys.path``，不保证仓库根在场。包侧 stub
先用「沿目录向上找 adapters/mjlab」自举仓库根再导入本模块（assets 源树与
workspace 镜像副本的深度不同，按文件位置探测对两处都成立）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

import mujoco
from mjlab.actuator import XmlActuatorCfg
from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.entity import EntityArticulationInfoCfg
from mjlab.managers.event_manager import EventTermCfg
from mjlab.sensor import (
    ObjRef,
    RayCastSensorCfg,
    RingPatternCfg,
    TerrainHeightSensorCfg,
)
from mjlab.tasks.velocity.velocity_env_cfg import make_velocity_env_cfg
from mjlab.utils.spec_config import CollisionCfg


# -----------------------------------------------------------------------------
# 包内 MJCF 真值解析（B28 同族：训练模型 = model/robot.xml，与仿真同源）。
# 来源：lite3 robot_constants.py L18-24 / b2 robot_constants.py L18-24（仅常量名差）。
# -----------------------------------------------------------------------------


def package_mjcf(
    robot_constants_file: str | Path, *, parents: int = 3
) -> tuple[Path, Callable[[], mujoco.MjSpec]]:
    """解析包根下的 ``model/robot.xml``，返回 ``(xml_path, get_spec)``。

    ``parents`` 是 robot_constants 文件到包根的层数（training/source/<task>/ 下
    恒为 3）。``assert`` 保留原语义：模型缺失在导入期即崩，而非训练中期。
    """
    package_root = Path(robot_constants_file).resolve().parents[parents]
    xml_path = package_root / "model" / "robot.xml"
    assert xml_path.exists()

    def get_spec() -> mujoco.MjSpec:
        return mujoco.MjSpec.from_file(str(xml_path))

    return xml_path, get_spec


# -----------------------------------------------------------------------------
# 执行器包装机制（B28/B35 裁决：MJCF 为执行真值，XmlActuatorCfg 只包装不重设）。
# 来源：lite3 robot_constants.py L54-65 / b2 robot_constants.py L55-66（仅正则差）。
# 包内的裁决注释（kp/kv/forcerange 对账、repeated-name 崩溃机理）留在各包常量文件。
# -----------------------------------------------------------------------------


def position_actuator_trio(
    expressions: Sequence[str],
) -> tuple[XmlActuatorCfg, ...]:
    """按给定顺序构造 ``command_field="position"`` 的 XmlActuatorCfg 组。

    gains/limits/armature 全部沿用 MJCF 定义（Xml 沿用不重设）；包装保持
    ``entity._actuators`` 非空供动作/观测/随机化侧解析 —— 语义与两包原实现一致。
    """
    return tuple(
        XmlActuatorCfg(target_names_expr=(expression,), command_field="position")
        for expression in expressions
    )


def quadruped_foot_collision() -> CollisionCfg:
    """全身碰撞 + 足端 condim/priority/friction 的碰撞配置。

    两包逐字相同（lite3 L88-95 == b2 L89-96），上移为唯一真值。
    """
    return CollisionCfg(
        geom_names_expr=(".*",),
        contype=1,
        conaffinity=0,
        condim={".*foot.*": 3, ".*": 1},
        priority={".*foot.*": 1, ".*": 0},
        friction={".*foot.*": (0.6,)},
    )


def action_scale_from_actuators(
    articulation: EntityArticulationInfoCfg, value: float = 0.25
) -> dict[str, float]:
    """按执行器 target 正则推导动作缩放表（lite3 L117-121 / b2 L118-122）。"""
    scales: dict[str, float] = {}
    for actuator in articulation.actuators:
        assert isinstance(actuator, XmlActuatorCfg)
        for expression in actuator.target_names_expr:
            scales[expression] = value
    return scales


# -----------------------------------------------------------------------------
# velocity env 装配骨架。
# -----------------------------------------------------------------------------


def new_velocity_env_cfg(
    robot_cfg,
    *,
    ccd_iterations: int = 500,
    contact_sensor_maxmatch: int = 500,
) -> ManagerBasedRlEnvCfg:
    """velocity 基座 + sim 上限 + 实体挂载（rough 前奏）。

    来源：lite3 env_cfg.py L110-114 / b2 env_cfg.py L90-94（逐字相同，
    仅 robot_cfg 来源不同）。
    """
    cfg = make_velocity_env_cfg()
    cfg.sim.mujoco.ccd_iterations = ccd_iterations
    cfg.sim.contact_sensor_maxmatch = contact_sensor_maxmatch
    cfg.sim.nconmax = None  # full-body contact sensors need headroom
    cfg.scene.entities = {"robot": robot_cfg}
    return cfg


def repoint_height_scan_sensors(
    cfg: ManagerBasedRlEnvCfg,
    *,
    root_body: str,
    foot_frames: Sequence[str] = (),
    frame_type: str = "site",
) -> None:
    """把基座高度扫描重指到本机型：terrain_scan 挂根 body，足端扫描挂足端帧。

    来源：lite3 env_cfg.py L61-74 / b2 env_cfg.py L37-48（同一逻辑；lite3 用
    body 帧 + ``<LR>_FOOT``（B31 裁决：MJCF 无足端 site），b2 用 site 帧）。
    ``frame_type`` ∈ {"site", "body"}；ring 参数两包一致（0.04 m × 4 samples）。

    ``foot_frames`` 默认空列表：**go1 没有足端 site**（其 site 级 `foot_height_scan`
    恒被丢弃），只需要重指根 body。**不重指的后果**见 go1 env_cfg 的序 15 注释 ——
    mjlab 基座给 `terrain_scan` 的默认 frame 是 ``ObjRef(entity="robot", name="")``，
    会解析成 ``robot/``（空 body 名）并在 Scene 初始化时 `mj_model.body("robot/")` KeyError。
    """
    for sensor in cfg.scene.sensors or ():
        if sensor.name == "terrain_scan":
            assert isinstance(sensor, RayCastSensorCfg)
            assert isinstance(sensor.frame, ObjRef)
            sensor.frame.name = root_body
        elif sensor.name == "foot_height_scan":
            assert isinstance(sensor, TerrainHeightSensorCfg)
            sensor.frame = tuple(
                ObjRef(type=frame_type, name=name, entity="robot")
                for name in foot_frames
            )
            sensor.pattern = RingPatternCfg.single_ring(radius=0.04, num_samples=4)


def set_viewer(
    cfg: ManagerBasedRlEnvCfg,
    *,
    body_name: str,
    distance: float = 1.5,
    elevation: float = -10.0,
) -> None:
    """viewer 三元组（lite3 L367-369 / b2 L111-113，distance/elevation 两包同值）。"""
    cfg.viewer.body_name = body_name
    cfg.viewer.distance = distance
    cfg.viewer.elevation = elevation


def apply_play_postlude(
    cfg: ManagerBasedRlEnvCfg,
    *,
    drop_push_event: bool = False,
    add_randomize_terrain: bool = False,
) -> None:
    """play 变体收尾（评估态：无限长 episode、关噪声、平地形展厅）。

    来源：lite3 env_cfg.py L374-383 / b2 env_cfg.py L131-147。共同部分：episode
    拉满、actor 噪声关闭、curriculum 清空、地形 5×5 + 10 m 边界并关 curriculum。
    差异参数化：b2 的 play 还会撤 push 事件并补 ``randomize_terrain``（展厅重建
    地形），lite3 不做 —— 用两个开关表达，默认（False/False）即 lite3 行为。
    """
    cfg.episode_length_s = int(1e9)
    cfg.observations["actor"].enable_corruption = False
    if drop_push_event:
        cfg.events.pop("push_robot", None)
    if add_randomize_terrain:
        cfg.events["randomize_terrain"] = EventTermCfg(
            func=envs_mdp.randomize_terrain,
            mode="reset",
            params={},
        )
    cfg.curriculum = {}
    if cfg.scene.terrain is not None and cfg.scene.terrain.terrain_generator is not None:
        terrain = cfg.scene.terrain.terrain_generator
        terrain.curriculum = False
        terrain.num_cols = 5
        terrain.num_rows = 5
        terrain.border_width = 10.0


def apply_flat_postlude(
    cfg: ManagerBasedRlEnvCfg,
    *,
    drop_terrain_scan_sensor: bool = False,
    drop_height_scan_obs: bool = False,
) -> None:
    """flat 变体收尾（平地 + 轻 sim 上限 + 撤地形课程）。

    来源：lite3 env_cfg.py L390-398 / b2 env_cfg.py L154-167（共同八项逐字相同）。
    差异参数化：b2 还要从场景撤 ``terrain_scan`` 传感器并从 actor/critic 观测撤
    ``height_scan``（其基座观测含高度扫描；lite3 的 45 维 rl_sdk 观测本就无此项、
    传感器保留），默认 False 即 lite3 行为。
    """
    cfg.sim.njmax = 300
    cfg.sim.mujoco.ccd_iterations = 50
    cfg.sim.contact_sensor_maxmatch = 64
    cfg.sim.nconmax = None
    assert cfg.scene.terrain is not None
    cfg.scene.terrain.terrain_type = "plane"
    cfg.scene.terrain.terrain_generator = None
    if drop_terrain_scan_sensor:
        cfg.scene.sensors = tuple(
            sensor for sensor in (cfg.scene.sensors or ()) if sensor.name != "terrain_scan"
        )
    if drop_height_scan_obs:
        cfg.observations["actor"].terms.pop("height_scan", None)
        cfg.observations["critic"].terms.pop("height_scan", None)
    cfg.terminations.pop("out_of_terrain_bounds", None)
    cfg.curriculum.pop("terrain_levels", None)


def ppo_runner_cfg(experiment_name: str, *, save_interval: int = 100):
    """四足组逐字共享的 PPO runner 配置（lite3 L402-444 / b2 L185-226）。

    原先唯一差异是 ``experiment_name``（lite3_velocity / b2_velocity），故成为参数；
    2026-09-20 接入 go2 时发现**第二个差异**：go2 的 ``save_interval`` 是 50，其余 20 余个
    字段与 lite3/b2 逐字相同（隐藏层 512/256/128、全部 PPO 超参、num_steps 24、
    max_iterations 10_000）。按 zex-w 同一先例（``wheel_leg_kit.ppo_runner_cfg_ex`` 为它补
    ``obs_normalization`` / ``std_type`` 两维、默认值即原语义），这里补 ``save_interval``：
    **默认 100 = lite3 / b2 / go1 的既有行为**，go2 显式传 50 保持自己的语义。
    ``mjlab.rl`` 沿用包内原样的函数内导入（保持 schema-dump 路径的导入面不变）。
    """
    from mjlab.rl import (
        RslRlModelCfg,
        RslRlOnPolicyRunnerCfg,
        RslRlPpoAlgorithmCfg,
    )

    return RslRlOnPolicyRunnerCfg(
        actor=RslRlModelCfg(
            hidden_dims=(512, 256, 128),
            activation="elu",
            obs_normalization=True,
            distribution_cfg={
                "class_name": "GaussianDistribution",
                "init_std": 1.0,
                "std_type": "scalar",
            },
        ),
        critic=RslRlModelCfg(
            hidden_dims=(512, 256, 128),
            activation="elu",
            obs_normalization=True,
        ),
        algorithm=RslRlPpoAlgorithmCfg(
            value_loss_coef=1.0,
            use_clipped_value_loss=True,
            clip_param=0.2,
            entropy_coef=0.01,
            num_learning_epochs=5,
            num_mini_batches=4,
            learning_rate=1.0e-3,
            schedule="adaptive",
            gamma=0.99,
            lam=0.95,
            desired_kl=0.01,
            max_grad_norm=1.0,
        ),
        experiment_name=experiment_name,
        save_interval=save_interval,
        num_steps_per_env=24,
        max_iterations=10_000,
    )
