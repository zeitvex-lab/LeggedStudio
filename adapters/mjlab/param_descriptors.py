"""Curated parameter descriptors for the training-config UI.

每一个精选训练参数一条描述符：声明一次（中文 label / 类型 / 默认 /
取值约束 / 说明 / 条件可见性 / 分组），前端据此自动渲染控件，
CLI 与 JSON Schema 从同一份定义派生。参考 n8n INodeProperties /
ComfyUI INPUT_TYPES / langflow Input 的声明式模式。

描述符结构：
{
  "id": "environment.sim.mujoco.timestep",   # dot-path（配方树内寻址）
  "label": "物理步长",                        # 中文名
  "category": "simulator",                   # 所属五分类面板
  "type": "float",                           # float|int|bool|str|options|range
  "default": 0.005,
  "min": 0.0005, "max": 0.05, "step": 0.0005,# 数值约束（可选）
  "unit": "s",
  "hint": "物理仿真步长；越小越精确、越慢",
  "advanced": False,                          # True → 折叠进高级区
  "options": [...],                           # type=options 时的候选
  "displayOptions": {"show": {"<其他id>": [值, ...]}},  # 条件可见
  "readonly": False,                          # True → 只读展示
}

pattern 描述符（PATTERN_DESCRIPTORS）按实际配方树动态展开：
  例如 rewards.<term>.weight 对树里每个奖励项生成一条。
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# 固定描述符（对 mjlab ManagerBasedRlEnvCfg + RslRlOnPolicyRunnerCfg 实测路径）
# ---------------------------------------------------------------------------

DESCRIPTORS: list[dict[str, Any]] = [
    # ---- 仿真器与运行时 (simulator) ----
    {"id": "environment.scene.num_envs", "label": "并行环境数", "category": "simulator",
     "type": "int", "default": 2048, "min": 64, "max": 8192, "step": 64,
     "hint": "并行仿真环境数。越大采样越快、显存越高；GPU 推荐 2048-4096，CPU 调试 ≤256"},
    {"id": "environment.episode_length_s", "label": "回合长度", "category": "simulator",
     "type": "float", "default": 20.0, "min": 1.0, "max": 60.0, "step": 1.0, "unit": "s",
     "hint": "每个训练回合的最大时长"},
    {"id": "environment.sim.mujoco.timestep", "label": "物理步长", "category": "simulator",
     "type": "float", "default": 0.005, "min": 0.0005, "max": 0.02, "step": 0.0005, "unit": "s",
     "hint": "物理仿真步长；越小越精确、越慢"},
    {"id": "environment.sim.mujoco.solver", "label": "求解器", "category": "simulator",
     "type": "options", "default": "newton",
     "options": ["newton", "cg", "pgs"], "advanced": True,
     "hint": "MuJoCo 约束求解器类型"},
    {"id": "environment.sim.mujoco.iterations", "label": "求解器迭代", "category": "simulator",
     "type": "int", "default": 100, "min": 10, "max": 200, "advanced": True},
    {"id": "environment.sim.mujoco.ls_iterations", "label": "线搜索迭代", "category": "simulator",
     "type": "int", "default": 50, "min": 10, "max": 100, "advanced": True},
    {"id": "environment.sim.mujoco.impratio", "label": "摩擦 impratio", "category": "simulator",
     "type": "float", "default": 10.0, "min": 1.0, "max": 100.0, "advanced": True,
     "hint": "摩擦锥阻抗比；轮足等高摩擦场景常用 10-100"},
    {"id": "environment.sim.mujoco.cone", "label": "摩擦锥", "category": "simulator",
     "type": "options", "default": "elliptic",
     "options": ["elliptic", "pyramidal"], "advanced": True},

    # ---- 环境与地形 (environment) ----
    {"id": "environment.scene.terrain.terrain_type", "label": "地形类型", "category": "environment",
     "type": "options", "default": "plane",
     "options": ["plane", "generator"],
     "hint": "plane=平地；generator=崎岖地形生成器"},
    {"id": "environment.scene.terrain.max_init_terrain_level", "label": "初始地形难度上限",
     "category": "environment", "type": "int", "default": 5, "min": 0, "max": 19,
     "advanced": True,
     "displayOptions": {"show": {"environment.scene.terrain.terrain_type": ["generator"]}},
     "hint": "课程学习的初始难度等级"},
    {"id": "environment.commands.twist.ranges.lin_vel_x", "label": "前进速度范围",
     "category": "environment", "type": "range", "default": [-1.0, 1.0],
     "min": -5.0, "max": 8.0, "step": 0.1, "unit": "m/s",
     "hint": "指令采样范围 [最小, 最大]"},
    {"id": "environment.commands.twist.ranges.lin_vel_y", "label": "侧移速度范围",
     "category": "environment", "type": "range", "default": [-0.5, 0.5],
     "min": -3.0, "max": 3.0, "step": 0.1, "unit": "m/s"},
    {"id": "environment.commands.twist.ranges.ang_vel_z", "label": "转向角速度范围",
     "category": "environment", "type": "range", "default": [-1.0, 1.0],
     "min": -5.0, "max": 5.0, "step": 0.1, "unit": "rad/s"},
    {"id": "environment.commands.twist.rel_standing_envs", "label": "站立环境比例",
     "category": "environment", "type": "float", "default": 0.15, "min": 0.0, "max": 1.0,
     "step": 0.05, "hint": "指令为零（站立）的环境占比"},

    # ---- 机器人与观测 (embodiment) ----
    {"id": "environment.actions.leg_joint_pos.scale", "label": "腿部动作缩放",
     "category": "embodiment", "type": "float", "default": 0.25, "min": 0.05, "max": 1.0,
     "step": 0.05, "advanced": True,
     "hint": "策略输出到关节目标的缩放系数（按关节组可能不同）"},
    {"id": "environment.actions.leg_joint_pos.cut_off_frequency", "label": "动作低通截止频率",
     "category": "embodiment", "type": "float", "default": 5.0, "min": 1.0, "max": 30.0,
     "step": 0.5, "unit": "Hz", "advanced": True,
     "hint": "目标低通滤波截止频率；越低越平滑、延迟越大"},

    # ---- 算法与超参数 (learning) ----
    {"id": "runner.algorithm.learning_rate", "label": "学习率", "category": "learning",
     "type": "float", "default": 0.001, "min": 1e-6, "max": 0.01, "step": 1e-5,
     "hint": "自适应 KL 调度下的初始学习率"},
    {"id": "runner.algorithm.desired_kl", "label": "目标 KL", "category": "learning",
     "type": "float", "default": 0.01, "min": 0.002, "max": 0.05, "step": 0.002,
     "advanced": True,
     "hint": "自适应学习率的目标 KL 散度；越大学习越激进"},
    {"id": "runner.algorithm.gamma", "label": "折扣因子 γ", "category": "learning",
     "type": "float", "default": 0.99, "min": 0.9, "max": 0.999, "step": 0.001},
    {"id": "runner.algorithm.lam", "label": "GAE λ", "category": "learning",
     "type": "float", "default": 0.95, "min": 0.5, "max": 0.99, "step": 0.01},
    {"id": "runner.algorithm.clip_param", "label": "裁剪范围 ε", "category": "learning",
     "type": "float", "default": 0.2, "min": 0.05, "max": 0.5, "step": 0.05},
    {"id": "runner.algorithm.entropy_coef", "label": "熵系数", "category": "learning",
     "type": "float", "default": 0.005, "min": 0.0, "max": 0.05, "step": 0.001,
     "hint": "鼓励探索。奖励过早坍缩时可适当调大"},
    {"id": "runner.algorithm.num_learning_epochs", "label": "每批学习轮数", "category": "learning",
     "type": "int", "default": 5, "min": 1, "max": 20, "advanced": True},
    {"id": "runner.algorithm.num_mini_batches", "label": "小批量数", "category": "learning",
     "type": "int", "default": 4, "min": 1, "max": 64, "advanced": True},
    {"id": "runner.algorithm.max_grad_norm", "label": "梯度裁剪上限", "category": "learning",
     "type": "float", "default": 1.0, "min": 0.1, "max": 10.0, "advanced": True},
    {"id": "runner.num_steps_per_env", "label": "每环境采样步数", "category": "learning",
     "type": "int", "default": 24, "min": 4, "max": 128, "step": 4,
     "hint": "每次策略更新前每个环境采集的步数"},
    {"id": "runner.max_iterations", "label": "最大迭代数", "category": "learning",
     "type": "int", "default": 10000, "min": 10, "max": 100000, "step": 100,
     "hint": "训练迭代上限；中途可手动停止"},
    {"id": "runner.save_interval", "label": "检查点保存间隔", "category": "learning",
     "type": "int", "default": 100, "min": 10, "max": 5000, "step": 10,
     "hint": "每 N 次迭代保存一个检查点"},
    {"id": "runner.seed", "label": "随机种子", "category": "learning",
     "type": "int", "default": 42, "min": 0, "max": 2147483647,
     "hint": "相同种子 + 相同配置可复现实验"},

    # ---- 奖励与鲁棒性 (robustness) —— 固定项；配方奖励权重走 PATTERN ----
    {"id": "environment.terminations.bad_orientation.params.limit_angle", "label": "摔倒判定角度",
     "category": "robustness", "type": "float", "default": 1.0, "min": 0.2, "max": 1.8,
     "step": 0.1, "unit": "rad", "readonly": True,
     "hint": "机身倾斜超过该角度即终止（配方定义）"},
]

# ---------------------------------------------------------------------------
# 模式描述符：对配方树里每个匹配项生成一条描述符
# ---------------------------------------------------------------------------

PATTERN_DESCRIPTORS = [
    {
        # 奖励项权重：24 项全量生成
        "pattern": r"environment\.rewards\.([a-zA-Z_0-9]+)\.weight",
        "label": "奖励权重：{term}",
        "category": "rewards",
        "type": "float",
        "step": 0.01,
        "hint": "0 = 关闭该项；负值为惩罚。开启奖励覆盖后可修改",
        "requires_override": True,   # 档案模式下修改需 reward_overrides=true
    },
    {
        # 域随机化事件参数（数值型）：推力 / 质量 / 摩擦 / 质心
        "pattern": r"environment\.events\.([a-zA-Z_0-9]+)\.params\.([a-zA-Z_0-9.\[\]]+)",
        "label": "域随机化：{event}.{param}",
        "category": "robustness",
        "type": "auto",
        "advanced": True,
        "readonly": True,   # DR 事件结构复杂，先只读展示
    },
]

# 分类顺序与标题
CATEGORY_ORDER = [
    ("simulator", "仿真器与运行时", 1),
    ("environment", "环境与地形", 2),
    ("embodiment", "机器人与观测", 3),
    ("learning", "算法与超参数", 4),
    ("rewards", "奖励", 5),
    ("robustness", "鲁棒性与终止", 6),
]


def tree_get(tree: dict, path: str) -> Any:
    node: Any = tree
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def tree_has(tree: dict, path: str) -> bool:
    node: Any = tree
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def resolve_params(schema: dict) -> list[dict[str, Any]]:
    """Resolve all descriptors against a dumped config tree.

    固定描述符按 id 在树中取当前值；缺失即跳过。
    模式描述符对树做正则展开（奖励权重 / DR 事件参数）。
    """
    import re

    params: list[dict[str, Any]] = []
    for desc in DESCRIPTORS:
        if not tree_has(schema, desc["id"]):
            continue
        entry = {**desc, "value": tree_get(schema, desc["id"])}
        params.append(entry)

    for pattern_desc in PATTERN_DESCRIPTORS:
        pattern = re.compile(pattern_desc["pattern"])
        for path in _iter_paths(schema):
            match = pattern.match(path)
            if not match:
                continue
            value = tree_get(schema, path)
            if value is None or isinstance(value, (dict, list)):
                continue
            if not isinstance(value, (int, float, bool, str)):
                continue
            label = pattern_desc["label"]
            groups = match.groups()
            if pattern_desc["label"].count("{term}") == 1:
                label = label.replace("{term}", groups[0])
            if pattern_desc["label"].count("{event}") == 1:
                label = label.replace("{event}", groups[0])
            if "{param}" in label:
                label = label.replace("{param}", groups[1] if len(groups) > 1 else "")
            entry = {
                "id": path,
                "label": label,
                "category": pattern_desc["category"],
                "type": (pattern_desc["type"] if pattern_desc["type"] != "auto"
                         else ("bool" if isinstance(value, bool)
                               else "int" if isinstance(value, int) and not isinstance(value, bool)
                               else "float" if isinstance(value, float) else "str")),
                "value": value,
                "advanced": pattern_desc.get("advanced", False),
                "readonly": pattern_desc.get("readonly", False),
                "requires_override": pattern_desc.get("requires_override", False),
            }
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                entry["step"] = pattern_desc.get("step", 0.01)
            params.append(entry)

    return params


def _iter_paths(node: Any, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "__type__":
                continue
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                paths.extend(_iter_paths(value, path))
            else:
                paths.append(path)
    return paths
