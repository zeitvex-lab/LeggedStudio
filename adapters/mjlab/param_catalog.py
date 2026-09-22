"""参数目录：语义段名标签词典 + 自动分组/渐进披露规则。

设计原则（对齐 robot_lab / langflow / n8n 的"结构即参数树"思想）：
- 不做人工"精选"：全部配置叶子由内省树结构自动组织
- 中文标签来自段名词典：命中即译，未命中保留原名——永不隐藏、永不猜错
- 渐进披露是客观规则：树深度、叶子类型，而非人工清单
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# 段名 → 中文标签词典（可随使用增长；未命中保留英文段名）
# ---------------------------------------------------------------------------
SEGMENT_LABELS: dict[str, str] = {
    # 仿真器 / 物理
    "timestep": "物理步长",
    "iterations": "求解器迭代",
    "ls_iterations": "线搜索迭代",
    "ls_tolerance": "线搜索容差",
    "tolerance": "求解容差",
    "impratio": "摩擦 impratio",
    "cone": "摩擦锥",
    "jacobian": "雅可比模式",
    "solver": "求解器",
    "ccd_iterations": "CCD 迭代",
    "gravity": "重力",
    "nconmax": "最大接触数",
    "njmax": "最大约束数",
    "contact_sensor_maxmatch": "接触传感器匹配上限",
    "broadphase": "宽相位算法",
    "ls_parallel": "并行线搜索",
    "nan_guard": "NaN 保护",
    # 场景
    "num_envs": "并行环境数",
    "env_spacing": "环境间距",
    "episode_length_s": "回合长度 (s)",
    "extent": "场景范围",
    "spec_fn": "场景构造函数",
    # 地形
    "terrain_type": "地形类型",
    "terrain_generator": "地形生成器",
    "max_init_terrain_level": "初始地形难度上限",
    "curriculum": "课程学习",
    # 指令
    "resampling_time_range": "指令重采样间隔 (s)",
    "rel_standing_envs": "站立环境比例",
    "rel_heading_envs": "朝向指令比例",
    "rel_forward_envs": "前进指令比例",
    "rel_lateral_envs": "侧移指令比例",
    "rel_yaw_envs": "原地转向比例",
    "rel_world_envs": "世界系指令比例",
    "heading_command": "朝向指令",
    "heading_control_stiffness": "朝向控制刚度",
    "ranges": "速度指令范围",
    "lin_vel_x": "前进速度",
    "lin_vel_y": "侧移速度",
    "ang_vel_z": "转向角速度",
    "heading": "朝向范围",
    "init_velocity_prob": "初始速度指令概率",
    # **观测/动作同名段**：本表是**扁平**字典，同名段只能有一个标签，否则**后写的静默覆盖**
    # 前面的（2026-09-22 实测踩到——这里曾同时写「观测裁剪/缩放」与「动作裁剪/缩放」，
    # 前一组是死条目）。消费点 `segment_label()` 只按段名查、拿不到段所在分区，
    # 所以文案必须**上下文无关**。
    "clip": "裁剪（观测/动作）",
    "scale": "缩放（观测/动作）",
    # 观测
    "noise": "观测噪声",
    "enable_corruption": "启用观测噪声",
    "concatenate_terms": "拼接观测项",
    "history_length": "历史帧数",
    # 动作
    "offset": "动作偏移",
    "use_default_offset": "基于默认姿态偏移",
    "preserve_order": "保持关节顺序",
    "control_frequency": "控制频率 (Hz)",
    "cut_off_frequency": "低通截止频率 (Hz)",
    "min_delay": "最小动作延迟",
    "max_delay": "最大动作延迟",
    "actuator_names": "执行器关节",
    # 事件 / DR
    "interval_range_s": "触发间隔 (s)",
    "min_step_count_between_reset": "重置间最小步数",
    "is_global_time": "全局计时",
    "pose_range": "初始姿态范围",
    "velocity_range": "速度扰动范围",
    "x": "X", "y": "Y", "z": "Z", "yaw": "偏航", "roll": "横滚", "pitch": "俯仰",
    "weight_distribution": "质量分布",
    "friction_range": "摩擦系数范围",
    "friction": "摩擦系数",
    "mass_distribution": "质量扰动",
    "mass_range": "质量扰动范围",
    # 奖励
    "weight": "权重",
    "only_positive_rewards": "仅保留正奖励",
    "stand_still_scale": "站立惩罚缩放",
    # 终止
    "limit_angle": "摔倒判定角度 (rad)",
    "time_out": "超时终止",
    # Runner / PPO
    "learning_rate": "学习率",
    "schedule": "学习率调度",
    "desired_kl": "目标 KL",
    "gamma": "折扣因子 γ",
    "lam": "GAE λ",
    "clip_param": "裁剪范围 ε",
    "entropy_coef": "熵系数",
    "num_learning_epochs": "每批学习轮数",
    "num_mini_batches": "小批量数",
    "max_grad_norm": "梯度裁剪上限",
    "value_loss_coef": "价值损失系数",
    "use_clipped_value_loss": "截断价值损失",
    "obs_normalization": "观测归一化",
    "init_std": "初始策略标准差",
    "std_type": "标准差类型",
    "hidden_dims": "网络隐层结构",
    "activation": "激活函数",
    "num_steps_per_env": "每环境采样步数",
    "max_iterations": "最大迭代数",
    "save_interval": "检查点保存间隔",
    "seed": "随机种子",
    "clip_actions": "动作裁剪范围",
    "resume": "从检查点恢复",
    "experiment_name": "实验名称",
    "run_name": "运行名称",
    "logger": "日志后端",
    "upload_model": "上传模型",
}

# 特定路径的精确定义（覆盖末段映射）
PATH_LABELS: dict[str, str] = {
    "runner.clip_actions": "动作裁剪范围",
    "runner.obs_groups": "观测组映射",
    "runner.experiment_name": "实验名称",
    "environment.rewards.only_positive_rewards": "仅保留正奖励",
}

# ---------------------------------------------------------------------------
# 自动分组与渐进披露规则（客观，非人工挑选）
# ---------------------------------------------------------------------------

# 一级路径前缀 → 五分类面板映射
CATEGORY_BY_PREFIX = [
    ("environment.sim", "simulator"),
    ("environment.scene", "simulator"),
    ("environment.episode_length_s", "simulator"),
    ("environment.seed", "simulator"),
    ("environment.terrain", "environment"),
    ("environment.commands", "environment"),
    ("environment.curriculum", "environment"),
    ("environment.observations", "embodiment"),
    ("environment.actions", "embodiment"),
    ("environment.events", "robustness"),
    ("environment.rewards", "rewards"),
    ("environment.terminations", "robustness"),
    ("runner.", "learning"),
]

# 结构性字段：叶子但不适合作为参数行（函数引用、类型标记、实体引用）
STRUCTURAL_SEGMENTS = {"func", "class_type", "spec_fn", "__type__", "entity_name",
                       "sensor_name", "debug_vis", "obs_groups", "viz"}

# 分类标题（与五分类面板一致）
CATEGORY_TITLES = {
    "simulator": "仿真器与运行时",
    "environment": "环境与地形",
    "embodiment": "机器人与观测",
    "learning": "算法与超参数",
    "rewards": "奖励",
    "robustness": "终止与域随机化",
    "other": "其他",
}


def category_for(path: str) -> str:
    for prefix, cat in CATEGORY_BY_PREFIX:
        if path == prefix or path.startswith(prefix):
            return cat
    return "other"


def label_for(path: str) -> str:
    if path in PATH_LABELS:
        return PATH_LABELS[path]
    segment = path.split(".")[-1].split("[")[0]
    return SEGMENT_LABELS.get(segment, segment)


def is_structural(path: str) -> bool:
    return path.split(".")[-1] in STRUCTURAL_SEGMENTS


def node_title(path: str) -> str:
    """分组节点标题：末段语义化。"""
    segment = path.split(".")[-1]
    return SEGMENT_LABELS.get(segment, segment)
