"""B3 物理事实绑定：把三端消费的物理参数收敛到契约 v3 的单一真值。

背景（重构方案 §5.7-1、任务清单 B3）
------------------------------------
各包的 ``simulation/config.json`` 与契约 v3 的 ``actuator_profile`` / ``control``
长期**双写**，且 config 侧的键风格在包之间并不统一（实测）：

* ``deeprobotics_lite3`` / ``deeprobotics_m20``：``stiffness`` 等是**逐关节**键；
* ``unitree_go2`` / ``zex-w``：**角色键控** + ``joint`` 兜底；
* ``wuji_hand``：只有 ``joint`` 一个兜底键；``torque_limits`` 在 zex-w/wuji_hand **缺失**。

契约 v3 侧则是角色化的 ``actuator_profile.by_role``（default < by_role < by_joint
三级展开），且既有测试已证明其展开值与 config 逐关节相等。因此本模块提供**唯一读取
API**，让消费者不再各自解释 config 的键风格：

    facts = physics_facts(package_dir)
    facts["by_role"]["stiffness"]      # 角色键控（浏览器 control 载荷用）
    facts["by_joint"]["armature"]      # 逐关节展开（mjlab 装配用）
    facts["control_hz"]                # 控制频率三件套

真值优先级：``contract_v3.json`` → ``simulation/config.json``（未迁移包的兼容回落，
以 ``source="legacy_config"`` 标记，使迁移进度可观测，而不是静默双真值）。

本模块只依赖标准库与 ``contracts.role_resolver``。
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from contracts.role_resolver import RoleResolver

__all__ = [
    "PARAM_KEYS",
    "CONTROL_KEYS",
    "PAYLOAD_MAP_KEYS",
    "PAYLOAD_CONST_KEYS",
    "LEG_GROUP_ROLES",
    "LEGACY_CONFIG_PHYSICS_KEYS",
    "GAIN_TO_V3",
    "apply_actuator_gains",
    "TN_CURVE_KEY",
    "RPM_TO_RAD_S",
    "ACTUATOR_MODEL_IDEAL_PD",
    "ACTUATOR_MODEL_DC_MOTOR",
    "ACTUATOR_MODELS",
    "parse_tn_curve_text",
    "format_tn_curve_text",
    "dc_params_from_t_n_curve",
    "t_n_curve_facts",
    "payload_t_n_curve_view",
    "dc_actuator_settings",
    "apply_t_n_curves",
    "facts_from_contract",
    "facts_from_legacy_config",
    "physics_facts",
    "joint_constant_tables",
    "physics_scalars",
    "payload_physics_view",
    "action_scale_facts",
    "payload_action_scale_view",
]

# 非轮角色在浏览器载荷里的**分组键**：旧 simulation/config.json 用的是
# {"leg": 0.5, "wheel": 5.0} 这种"腿/轮"两分组，而不是契约的角色名。前端可能按
# 该分组键查找，故载荷视图在"所有非轮角色同值"时补一个 leg 组键（同 joint 兜底思路）。
LEG_GROUP_ROLES = ("leg",)
WHEEL_ROLE = "wheel"

# 物理事实的规范字段：契约侧参数名 -> 对外统一名
PARAM_KEYS = (
    ("stiffness", "stiffness"),
    ("damping", "damping"),
    ("effort", "torque_limits"),
    # 速度限幅（D9）：契约 v3 键为单数 `velocity_limit`，对外统一名沿用前端既有的
    # 复数 `velocity_limits`（与 `effort -> torque_limits` 同一处理）。
    # 此前该字段**只有 schema 声明、没有任何包填值、也没有消费者**：浏览器侧的
    # `applyVelocityLimits` 读的是 sim config 的 `velocity_limits`（14 包实测都没有
    # 这个键，等于永远走缺省），训练/验收侧从不读它 → 同一个"电机参数"三端口径不一。
    ("velocity_limit", "velocity_limits"),
    ("armature", "armature"),
    ("friction_loss", "friction_loss"),
)
CONTROL_KEYS = ("control_hz", "physics_hz", "decimation")

# 浏览器载荷里的角色/关节键控映射与常量表（键名沿用前端既有命名）
PAYLOAD_MAP_KEYS = ("stiffness", "damping", "torque_limits", "velocity_limits")
PAYLOAD_CONST_KEYS = (("armature", "armature"), ("friction_loss", "frictionloss"))

#: ``simulation/config.json`` 上**已废弃**的物理键（B3 收尾）。
#: 物理事实现在只剩契约 v3 一处：这组键既造成"两处并存"，又让训练/验收侧用
#: 小写关节名查混合大小写键而静默失效。保存链落盘前必须剔除，防止又被写回来。
LEGACY_CONFIG_PHYSICS_KEYS = (
    "stiffness",
    "damping",
    "torque_limits",
    # D9：速度限幅的唯一真值是契约 v3 `actuator_profile[].velocity_limit`。
    # sim config 里的 `velocity_limits` 是历史第二个家（UI 曾写这里、浏览器曾读这里），
    # 一并剔除——否则"改一处不生效"的问题会再演一次。
    "velocity_limits",
    "armature",
    "frictionloss",
    "control_hz",
    "physics_hz",
    "decimation",
    # 执行器"运行时重建"开关已退役：包内 MJCF 由 tools/bake_mjcf_physics.py 按契约固化，
    # 运行时只加载不改写。留着它就会有人再把"资产是坏的"这件事藏回运行时。
    "browser_actuator_rebuild",
)


def _expand(contract_v3: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return RoleResolver(contract_v3).expand_actuator_profile()


def facts_from_contract(contract_v3: dict[str, Any]) -> dict[str, Any]:
    """从契约 v3 抽出物理事实（单一真值路径）。

    同时给出角色键控与逐关节两种视图，避免各消费者自行改口径。
    """

    profile = contract_v3.get("actuator_profile") or {}
    by_role = profile.get("by_role") or {}
    default = profile.get("default") or {}
    by_joint_raw = profile.get("by_joint") or {}
    expanded = _expand(contract_v3)

    role_view: dict[str, dict[str, Any]] = {}
    joint_view: dict[str, dict[str, Any]] = {}
    for contract_key, name in PARAM_KEYS:
        role_view[name] = {
            role: params[contract_key]
            for role, params in by_role.items()
            if isinstance(params, dict) and contract_key in params
        }
        joint_view[name] = {
            joint: params[contract_key]
            for joint, params in expanded.items()
            if isinstance(params, dict) and contract_key in params
        }

    control = contract_v3.get("control") or {}
    facts: dict[str, Any] = {
        "source": "contract_v3",
        "by_role": role_view,
        "by_joint": joint_view,
        "default": {
            name: default[contract_key]
            for contract_key, name in PARAM_KEYS
            if contract_key in default
        },
        # 逐关节覆盖表（异例），迁移/对账时需要知道"哪些关节是特例"
        "by_joint_override": {
            name: {
                joint: params[contract_key]
                for joint, params in by_joint_raw.items()
                if isinstance(params, dict) and contract_key in params
            }
            for contract_key, name in PARAM_KEYS
        },
    }
    for key in CONTROL_KEYS:
        facts[key] = control.get(key)
    facts["actuator_type"] = (contract_v3.get("morphology") or {}).get("actuator_type")
    # P1：执行器模型开关（缺省 ideal_pd = 现役行为**不变**；dc_motor 才消费 t_n_curve）
    model = control.get("actuator_model") or ACTUATOR_MODEL_IDEAL_PD
    if model not in ACTUATOR_MODELS:
        raise ValueError(f"control.actuator_model 取值非法：{model!r}（允许 {ACTUATOR_MODELS}）")
    facts["actuator_model"] = model
    return facts


def facts_from_legacy_config(sim_cfg: dict[str, Any]) -> dict[str, Any]:
    """兼容回落：未迁移包仍从 ``simulation/config.json`` 取，但输出同一形状。

    config 侧键风格不统一（逐关节 / 角色键控 / ``joint`` 兜底），此处不做猜测式改写：
    ``by_joint`` 直接采用 config 原值（其键可能是关节名或角色名），并明确标记
    ``source="legacy_config"`` 与 ``needs_migration=True``。
    """

    def pick(name: str) -> dict[str, Any]:
        raw = sim_cfg.get(name)
        return dict(raw) if isinstance(raw, dict) else {}

    facts: dict[str, Any] = {
        "source": "legacy_config",
        "needs_migration": True,
        "by_role": {
            "stiffness": pick("stiffness"),
            "damping": pick("damping"),
            "torque_limits": pick("torque_limits"),
        },
        "by_joint": {
            "stiffness": pick("stiffness"),
            "damping": pick("damping"),
            "torque_limits": pick("torque_limits"),
            "armature": pick("armature"),
            "friction_loss": pick("frictionloss"),
        },
        "default": {},
        "by_joint_override": {},
        "actuator_type": sim_cfg.get("actuator_interface"),
    }
    for key in CONTROL_KEYS:
        facts[key] = sim_cfg.get(key)
    return facts


def payload_physics_view(facts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """浏览器 control 载荷视图（B3/2）。

    前端解析顺序（``web/sim2sim/app.js`` 的 ``controlValue``）：
        精确关节名 → jointSegment(名)（去腿前缀与 joint 后缀）→ 分组/角色 → ``joint`` 兜底

    历史 ``simulation/config.json`` 的键风格跨包不同（lite3/m20 逐关节、go2/zex-w
    角色键控 + ``joint`` 兜底、wuji_hand 仅 ``joint``），因此换源时若只给角色键，
    "精确关节名"这条路会失配并**静默回退到默认值**（表现为浏览器里策略抽搐，而非报错）。

    本视图刻意同时提供：
      * **角色键**（覆盖 分组/角色 查找路径）
      * **逐关节键**（覆盖 精确关节名 查找路径，取契约 by_joint 展开，优先级最高）
      * 角色内取值一致时补 ``joint``（延续旧 config 的兜底语义）

    这样两条查找路径命中同一数值，从而在**键形态改变**的同时保证**逐关节解析结果不变**。
    ``armature`` / ``frictionloss`` 额外保留 ``__default__``（模型 default 层兜底，
    覆盖非驱动 dof）。
    """

    view: dict[str, dict[str, Any]] = {}
    for name in PAYLOAD_MAP_KEYS:
        merged: dict[str, Any] = {}
        merged.update(facts["by_role"].get(name) or {})
        # by_joint 优先级最高（契约三级展开优先级 default < by_role < by_joint）
        merged.update(facts["by_joint"].get(name) or {})
        if merged and len(set(merged.values())) == 1:
            merged["joint"] = next(iter(merged.values()))
        view[name] = merged

    for fact_key, payload_key in PAYLOAD_CONST_KEYS:
        merged = dict(facts["by_joint"].get(fact_key) or {})
        default = (facts.get("default") or {}).get(fact_key)
        if default is not None:
            merged["__default__"] = default
        view[payload_key] = merged

    return view


def action_scale_facts(contract_v3: dict[str, Any]) -> dict[str, Any]:
    """action_scale 的事实（B5/2）：``{scalar, by_role, by_joint}``。

    真值归**契约**：`action.action_scale` 是标量缺省，`actuator_profile.by_role[]`
    是角色级权威，`by_joint` 是三级展开后的逐关节结果。

    为什么消费方不该再读 ``simulation/config.json``：轮足类机型的轮档位在训练契约
    内部就是**任务相关**的（实测 go2w：UniLab 类默认 10.0、rough 任务 5.0、官方部署
    yaml 35.0），仿真侧那份 config 只是其中一个快照，再读它就会与契约漂移。
    """

    profile = contract_v3.get("actuator_profile") or {}
    by_role = {
        role: params["action_scale"]
        for role, params in (profile.get("by_role") or {}).items()
        if isinstance(params, dict) and params.get("action_scale") is not None
    }
    return {
        "source": "contract_v3",
        "scalar": (contract_v3.get("action") or {}).get("action_scale"),
        "by_role": by_role,
        "by_joint": RoleResolver(contract_v3).action_scale_by_joint(),
    }


def payload_action_scale_view(facts: dict[str, Any]) -> dict[str, Any]:
    """浏览器 control 载荷的 action_scale 视图（B5/2）。

    前端已有**比标量更细**的两条查找路径（按角色 / 按关节），这比单一标量功能更多，
    因此保留该形态，只把来源换成契约。视图刻意同时提供：

      * ``action_scale_by_role``：角色键控；非轮角色同值时补 ``leg`` 组键，
        并在全部同值时补 ``joint`` 兜底（延续旧 config 的查找语义）；
      * ``action_scale_by_joint``：逐关节（优先级最高）；
      * ``action_scale``：标量缺省。

    这样"键形态改变"不会让前端**静默回退到默认值**（表现为策略抽搐而非报错）。
    """

    by_role = dict(facts.get("by_role") or {})
    by_joint = {name: float(value) for name, value in (facts.get("by_joint") or {}).items()}

    role_view = dict(by_role)
    wheel_values = {value for role, value in by_role.items() if role == WHEEL_ROLE}
    leg_values = {value for role, value in by_role.items() if role != WHEEL_ROLE}
    if leg_values and len(leg_values) == 1:
        for group in LEG_GROUP_ROLES:
            role_view.setdefault(group, next(iter(leg_values)))
    merged = {**role_view, **by_joint}
    if merged and len(set(merged.values())) == 1:
        merged["joint"] = next(iter(merged.values()))

    scalar = facts.get("scalar")
    if scalar is None:
        scalar = merged.get("joint") if merged else None
    return {
        "action_scale": float(scalar) if scalar is not None else 0.25,
        "action_scale_by_role": merged or {"joint": 0.25},
        "action_scale_by_joint": by_joint,
        "wheel_scale_declared": bool(wheel_values),
    }


def physics_facts(package_dir: str | Path) -> dict[str, Any]:
    """读取某机器人包的物理事实（契约 v3 优先，缺失则回落 config）。"""

    root = Path(package_dir)
    contract_path = root / "contract_v3.json"
    if contract_path.exists():
        contract_v3 = json.loads(contract_path.read_text(encoding="utf-8-sig"))
        return facts_from_contract(contract_v3)

    config_path = root / "simulation" / "config.json"
    if config_path.exists():
        sim_cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
        return facts_from_legacy_config(sim_cfg)

    return {
        "source": "missing",
        "needs_migration": True,
        "by_role": {},
        "by_joint": {},
        "default": {},
        "by_joint_override": {},
        **{key: None for key in CONTROL_KEYS},
    }


# --- P1：T-N 曲线（转矩-转速曲线；高级参数，声明 ≠ 生效） -------------------------------
#
# 形态与语义
#   * 契约里以**折线点列**声明：``actuator_profile[].t_n_curve = [{rpm, torque_nm}, ...]``，
#     采样点取**关节输出侧**（不折算减速比），rpm 升序、扭矩非增（schema + 模型双校验）。
#   * ``control.actuator_model`` 决定**是否消费**：缺省 ``ideal_pd`` = 现役理想 PD，
#     **一律忽略 t_n_curve**（"不修改就不起作用"）；``dc_motor`` 才把折线折算成
#     mjlab ``DcMotorActuatorCfg`` 需要的两个标量。
#   * 折算只在这一处实现（:func:`dc_params_from_t_n_curve`），避免"曲线在契约、
#     参数在别处"再次漂移。
TN_CURVE_KEY = "t_n_curve"
RPM_TO_RAD_S = 2.0 * math.pi / 60.0
ACTUATOR_MODEL_IDEAL_PD = "ideal_pd"
ACTUATOR_MODEL_DC_MOTOR = "dc_motor"
ACTUATOR_MODELS = (ACTUATOR_MODEL_IDEAL_PD, ACTUATOR_MODEL_DC_MOTOR)


def parse_tn_curve_text(text: str) -> list[dict[str, float]]:
    """解析面板口径的 T-N 曲线文本：``"0:60, 120:60, 188:0"``（``rpm:扭矩``，逗号/分号分隔）。

    面板用紧凑文本便于人工粘贴 datasheet，这里与 :func:`format_tn_curve_text` 配对，
    作为该文本的唯一解析实现（后端也接受，避免"只有前端会解析"的隐性契约）。
    空串 → 空列表（= 清除声明）。
    """
    points: list[dict[str, float]] = []
    for chunk in str(text).replace(";", ",").split(","):
        item = chunk.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"T-N 曲线采样点格式应为 rpm:扭矩，收到 {item!r}")
        rpm_text, torque_text = item.split(":", 1)
        try:
            points.append({"rpm": float(rpm_text), "torque_nm": float(torque_text)})
        except ValueError as exc:
            raise ValueError(f"T-N 曲线点数值无法解析：{item!r}") from exc
    return points


def format_tn_curve_text(points: Any) -> str:
    """点列 → 面板紧凑文本（与 :func:`parse_tn_curve_text` 往返一致）。"""
    out = []
    for point in _normalize_tn_curve_points(points):
        rpm = point["rpm"]
        torque = point["torque_nm"]
        out.append(f"{rpm:g}:{torque:g}")
    return ", ".join(out)


def _normalize_tn_curve_points(raw: Any) -> list[dict[str, float]]:
    """把三种可接受写法规整成 ``[{"rpm": float, "torque_nm": float}, ...]``。

    接受：``[{rpm, torque_nm}]``（契约口径）、``[[rpm, torque], ...]``、``"0:60, 120:60"``
    （面板口径）。其余一律抛错——T-N 曲线是"要么可解析、要么不声明"的字段。
    """
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return parse_tn_curve_text(raw)
    points: list[dict[str, float]] = []
    for item in raw:
        if isinstance(item, dict):
            rpm, torque = item.get("rpm"), item.get("torque_nm")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            rpm, torque = item
        else:
            raise ValueError(f"T-N 曲线采样点须为 {{rpm, torque_nm}} 或 [rpm, torque]：{item!r}")
        if rpm is None or torque is None:
            raise ValueError(f"T-N 曲线采样点缺 rpm/torque_nm：{item!r}")
        points.append({"rpm": float(rpm), "torque_nm": float(torque)})
    return points


def dc_params_from_t_n_curve(points: Any) -> dict[str, float]:
    """T-N 曲线折线 → DC 电机模型标量（mjlab ``DcMotorActuatorCfg`` 口径）。

    推导规则：

    * ``saturation_effort`` = 折线上的**最大扭矩**（通常出现在 rpm=0，即堵转扭矩）。
      取 max 而非首点，是为了不因上传顺序不规范而低估；
    * ``no_load_rpm`` = 扭矩降到 0 的转速。**末点扭矩 > 0 时用最后两点斜率外推**
      （真机 datasheet 常只给到额定点），而不是硬把末点当空载点；
    * ``velocity_limit_rad_s`` = ``no_load_rpm × 2π/60``（mjlab 的 ``cmd.vel`` 是 rad/s）。

    单调性在此再校验一次（rpm 升序、扭矩非增），违反即抛错：T-N 曲线是 fail-closed 字段。
    """
    ordered = sorted(_normalize_tn_curve_points(points), key=lambda p: p["rpm"])
    if len(ordered) < 2:
        raise ValueError("t_n_curve 至少需要 2 个采样点（否则无法定义斜率）")
    for prev, cur in zip(ordered, ordered[1:]):
        if cur["rpm"] <= prev["rpm"]:
            raise ValueError(f"t_n_curve 的 rpm 必须严格升序：{cur['rpm']} 未大于 {prev['rpm']}")
        if cur["torque_nm"] > prev["torque_nm"]:
            raise ValueError(
                f"t_n_curve 的扭矩必须非增：rpm={cur['rpm']} 处 {cur['torque_nm']} 大于前一点 {prev['torque_nm']}"
            )
    saturation = max(point["torque_nm"] for point in ordered)
    if saturation <= 0:
        raise ValueError("T-N 曲线的最大扭矩为 0：这不是一条可用的电机曲线（无法定义峰值扭矩）")
    last, prev = ordered[-1], ordered[-2]
    if last["torque_nm"] <= 0:
        no_load_rpm = last["rpm"]
    else:
        slope = (last["torque_nm"] - prev["torque_nm"]) / (last["rpm"] - prev["rpm"])
        if slope == 0:
            raise ValueError(
                "末段是水平的（扭矩不随转速变化），无法推出空载转速——"
                "请在末尾补一个扭矩降到 0 的点，例如 `0:25, 95:25, 200:0`"
            )
        no_load_rpm = last["rpm"] - last["torque_nm"] / slope
    return {
        "saturation_effort": float(saturation),
        "no_load_rpm": float(no_load_rpm),
        "velocity_limit_rad_s": float(no_load_rpm * RPM_TO_RAD_S),
    }


def t_n_curve_facts(package_dir: str | Path) -> dict[str, Any]:
    """T-N 曲线事实（P1）：``{source, actuator_model, declared, by_role, by_joint, derived}``。

    ``declared`` 只表示"契约里写了曲线"，**不等于生效**——是否生效看 ``actuator_model``。
    ``derived`` 给出逐关节的 DC 标量（供 mjlab 装配），键为关节名（+ ``__default__``）。
    """
    root = Path(package_dir)
    contract_path = root / "contract_v3.json"
    empty = {
        "source": "missing",
        "actuator_model": ACTUATOR_MODEL_IDEAL_PD,
        "declared": False,
        "by_role": {},
        "by_joint": {},
        "derived": {},
    }
    if not contract_path.exists():
        return empty
    contract_v3 = json.loads(contract_path.read_text(encoding="utf-8-sig"))
    profile = contract_v3.get("actuator_profile") or {}
    default_points = _normalize_tn_curve_points((profile.get("default") or {}).get(TN_CURVE_KEY))
    by_role = {
        role: _normalize_tn_curve_points(params.get(TN_CURVE_KEY))
        for role, params in (profile.get("by_role") or {}).items()
        if isinstance(params, dict) and params.get(TN_CURVE_KEY)
    }
    by_joint = {
        joint: _normalize_tn_curve_points(params.get(TN_CURVE_KEY))
        for joint, params in _expand(contract_v3).items()
        if isinstance(params, dict) and params.get(TN_CURVE_KEY)
    }
    derived = {
        joint: dc_params_from_t_n_curve(points)
        for joint, points in by_joint.items()
        if points
    }
    if default_points:
        derived["__default__"] = dc_params_from_t_n_curve(default_points)
    model = str(((contract_v3.get("control") or {}).get("actuator_model")) or ACTUATOR_MODEL_IDEAL_PD)
    return {
        "source": "contract_v3",
        "actuator_model": model,
        "declared": bool(by_joint or by_role or default_points),
        "by_role": by_role,
        "by_joint": by_joint,
        "derived": derived,
    }


def payload_t_n_curve_view(facts: dict[str, Any]) -> dict[str, list[list[float]]]:
    """浏览器 ``control.motor_envelopes`` 视图：``{小写关节名|角色名: [[rpm, Nm], ...]}``。

    形态对齐 ``web/sim2sim/app.js::normalizeMotorEnvelope``（接受 ``[rpm, torque]`` 二元组，
    要求 ≥2 点、rpm 严格升序——本模块的校验更严，通过即必然通过浏览器侧）。

    键**同时给逐关节与角色两种**：浏览器先查精确关节名，查不到再查 ``jointGroup`` 角色名。
    未声明任何曲线时返回 ``{}`` —— 浏览器 ``applyMotorEnvelopes`` 会自行早退，行为不变。
    """
    view: dict[str, list[list[float]]] = {}
    for role, points in (facts.get("by_role") or {}).items():
        if points:
            view[str(role).lower()] = [[float(p["rpm"]), float(p["torque_nm"])] for p in points]
    for joint, points in (facts.get("by_joint") or {}).items():
        if points:
            view[str(joint).lower()] = [[float(p["rpm"]), float(p["torque_nm"])] for p in points]
    return view


def dc_actuator_settings(package_dir: str | Path) -> dict[str, dict[str, float]]:
    """mjlab DC 执行器的逐关节装配参数（P1）——键名与 ``DcMotorActuatorCfg`` 对齐。

    只在 ``control.actuator_model == "dc_motor"`` 时有意义，否则返回 ``{}``（= 让调用方
    保持现役理想 PD，**不做任何事**）。启用时：

    * 由 t_n_curve 折算 ``saturation_effort`` / ``velocity_limit``（rad/s）；
    * 其余（``stiffness`` / ``damping`` / ``effort_limit`` / ``armature`` / ``frictionloss``）
      取契约同一真值，参数不另开一处；
    * **任一驱动关节缺 t_n_curve → 抛错**。不静默退回理想 PD——那会让用户以为 T-N 曲线生效了。

    真实装配（构造 ``DcMotorActuatorCfg``）在 ``adapters/mjlab/generic_task_builder.py``，
    本函数只负责"契约 → 参数"，因此不需要 mjlab 即可被测试。
    """
    root = Path(package_dir)
    contract_path = root / "contract_v3.json"
    if not contract_path.exists():
        return {}
    contract_v3 = json.loads(contract_path.read_text(encoding="utf-8-sig"))
    control = contract_v3.get("control") or {}
    if str(control.get("actuator_model") or ACTUATOR_MODEL_IDEAL_PD) != ACTUATOR_MODEL_DC_MOTOR:
        return {}
    facts = facts_from_contract(contract_v3)
    expanded = _expand(contract_v3)
    derived = t_n_curve_facts(root).get("derived") or {}
    default_derived = derived.get("__default__")
    tables = joint_constant_tables(root)
    armature_table = tables["armature"]
    friction_table = tables["frictionloss"]

    def pick(table: dict[str, float], joint: str, fallback: float) -> float:
        value = table.get(joint.lower())
        if value is None:
            value = table.get("__default__")
        return float(value) if value is not None else float(fallback)

    settings: dict[str, dict[str, float]] = {}
    missing: list[str] = []
    for joint, params in expanded.items():
        entry = derived.get(joint) or default_derived
        if not entry:
            missing.append(joint)
            continue
        saturation = float(entry["saturation_effort"])
        effort = params.get("effort")
        settings[joint] = {
            "stiffness": float(params.get("stiffness") or 0.0),
            "damping": float(params.get("damping") or 0.0),
            # 无 effort 声明时以峰值扭矩为上限（mjlab 会就此告警，属预期可见行为）
            "effort_limit": float(effort) if effort is not None else saturation,
            "armature": pick(armature_table, joint, 0.0),
            "frictionloss": pick(friction_table, joint, 0.0),
            "saturation_effort": saturation,
            "velocity_limit": float(entry["velocity_limit_rad_s"]),
        }
    if missing:
        raise ValueError(
            f"actuator_model=dc_motor 但以下驱动关节没有 t_n_curve：{sorted(missing)}"
            "（先补 T-N 曲线，或把 actuator_model 改回 ideal_pd——不静默退回）"
        )
    return settings


def apply_t_n_curves(v3: dict[str, Any], t_n_curves: Any) -> list[str]:
    """把「逐关节 T-N 曲线点列」按角色归层写进契约 v3 ``actuator_profile``（就地修改）。

    归层规则与 :func:`apply_actuator_gains` 完全一致（角色内全同 → ``by_role``，否则
    ``by_joint``；写 ``by_role`` 时清掉同键的逐关节覆盖），只是值从标量换成点列。
    值为空（``None`` / ``""`` / ``[]``）表示**清除该键**——面板清空即回到"未声明"。

    Returns: 实际改动的角色名（``role:<name>``）与关节名（排序后）。
    """
    if not t_n_curves:
        return []
    if isinstance(t_n_curves, dict):
        items = list(t_n_curves.items())
    elif isinstance(t_n_curves, (list, tuple)):
        items = [(None, item) for item in t_n_curves]  # 无键形态：仅规整校验，不改结构
    else:
        raise ValueError("t_n_curve 载荷须为 {部位|关节: 点列} 或点列本身")
    actuated = ((v3.get("joints") or {}).get("actuated")) or []
    roles_of = {e.get("name"): e.get("role") for e in actuated if isinstance(e, dict)}
    profile = v3.setdefault("actuator_profile", {})
    by_role = profile.setdefault("by_role", {})
    by_joint = profile.setdefault("by_joint", {})
    role_groups: dict[str, list[str]] = {}
    for joint_name, role in roles_of.items():
        if role:
            role_groups.setdefault(str(role), []).append(str(joint_name))

    touched: set[str] = set()
    if items and items[0][0] is None:  # 无键：只做可解析性校验
        for _, value in items:
            dc_params_from_t_n_curve(value)
        return []

    def assign(joint: str, points: list[dict[str, float]] | None) -> None:
        if points:
            by_joint.setdefault(joint, {})[TN_CURVE_KEY] = points
        elif joint in by_joint:
            by_joint[joint].pop(TN_CURVE_KEY, None)

    for key, value in items:
        key = str(key)
        points = _normalize_tn_curve_points(value)
        if points:
            dc_params_from_t_n_curve(points)  # 校验（含单调性），不合法即抛
        if key in role_groups:
            names = role_groups[key]
            per_joint = {name: (points or None) for name in names}
            if points:
                by_role.setdefault(key, {})[TN_CURVE_KEY] = points
                for name in names:
                    if name in by_joint:
                        by_joint[name].pop(TN_CURVE_KEY, None)
                touched.add(f"role:{key}")
            else:
                if key in by_role:
                    by_role[key].pop(TN_CURVE_KEY, None)
                for name in names:
                    assign(name, None)
                touched.add(f"role:{key}")
            continue
        assign(key, points or None)
        touched.add(key)
    return sorted(touched)


def joint_constant_tables(package_dir: str | Path) -> dict[str, dict[str, float]]:
    """逐关节常量表 ``{"armature": {...}, "frictionloss": {...}, "velocity_limits": {...}}``（键统一小写）。

    **存在的理由（B3 收尾实测）**：训练/验收侧（`adapters/mjlab/scene_builder.py`、
    `adapters/mjlab/policy_acceptance.py`）此前直接读 `simulation/config.json` 顶层的
    ``armature`` / ``frictionloss``，再拿 ``joint.name.lower()`` 去查**混合大小写**的键
    （``FL_hip_joint``）——查不到就落到 ``__default__``（多数包没有）→ **armature 实际
    从未生效**；而浏览器侧（契约 v3 + 精确关节名查 ``mj_name2id``）是生效的。同一条
    数据、两条链路、两种结论，且失败方式是**静默**的。

    这里统一一处：来源 = :func:`physics_facts`（契约 v3 优先，legacy config 仅兜底），
    键统一小写，并显式带出 ``__default__``（模型 default 层兜底，覆盖非驱动 dof）。
    调用方只需 ``name.lower()`` 查表。
    """

    facts = physics_facts(package_dir)
    tables: dict[str, dict[str, float]] = {"armature": {}, "frictionloss": {}, "velocity_limits": {}}
    for fact_key, out_key in (
        ("armature", "armature"),
        ("friction_loss", "frictionloss"),
        # D9：速度限幅同表带出（验收侧用它给探针的峰值关节速度做判据）
        ("velocity_limits", "velocity_limits"),
    ):
        table: dict[str, float] = {}
        for source in ("by_joint", "by_joint_override"):
            for joint, value in (facts.get(source, {}).get(fact_key) or {}).items():
                if value is None:
                    continue
                try:
                    table[str(joint).lower()] = float(value)
                except (TypeError, ValueError):
                    continue
        default_value = (facts.get("default") or {}).get(fact_key)
        if default_value is not None:
            try:
                table["__default__"] = float(default_value)
            except (TypeError, ValueError):
                pass
        tables[out_key] = table
    return tables


def physics_scalars(package_dir: str | Path) -> dict[str, Any]:
    """控制层标量（``control_hz`` / ``physics_hz`` / ``decimation`` / 执行器类型）+ 来源标记。"""
    facts = physics_facts(package_dir)
    scalars: dict[str, Any] = {key: facts.get(key) for key in CONTROL_KEYS}
    scalars["actuator_type"] = facts.get("actuator_type")
    # P1：执行器模型开关（缺省 ideal_pd = 现役行为不变）
    scalars["actuator_model"] = str((facts.get("actuator_model") or ACTUATOR_MODEL_IDEAL_PD))
    scalars["source"] = facts.get("source")
    scalars["needs_migration"] = bool(facts.get("needs_migration"))
    return scalars


#: 可编辑的执行器参数（工作台/接口口径）→ 契约 v3 ``actuatorParams`` 键名。
#: D8：`armature` 与 `friction_loss` 与 stiffness/damping/effort 同为 v3 一等参数
#: （schema `actuatorParams` 已声明），因此统一走这一张表，避免"某些参数写 v3、
#: 某些写 sim config"的两处并存。
GAIN_TO_V3: dict[str, str] = {
    "stiffness": "stiffness",
    "damping": "damping",
    "torque_limits": "effort",
    "armature": "armature",
    "friction_loss": "friction_loss",
    # D9：速度限幅也走这张表（control 侧沿用前端复数键名 → 契约 v3 单数键名）
    "velocity_limits": "velocity_limit",
    # D10：动作缩放（工作台「动作缩放」卡片）。标量缺省走 v3 `action.action_scale`，
    # 逐关节/角色值走同一张 actuator_profile 分发表（schema actuatorParams 已含
    # action_scale；role_resolver 展开序 default < by_role < by_joint 同样适用）。
    "action_scale": "action_scale",
}


def apply_actuator_gains(v3: dict[str, Any], control: dict[str, Any]) -> list[str]:
    """把「逐关节参数表」按角色归层写进契约 v3 的 ``actuator_profile``（就地修改）。

    归层规则与 ``role_resolver`` 的 ``default < by_role < by_joint`` 合并序一致：

    * 某角色下**所有关节都有值且相同** → 写 ``by_role``，并把该键从 ``by_joint`` 移除
      （否则旧的逐关节覆盖会盖住新写入的角色值）；
    * 否则 → 逐关节写 ``by_joint``。

    这是唯一一处"面板编辑 → 契约 v3"的映射实现（原为接口内联代码，D8 抽出以便单测）。

    Args:
        v3: 契约 v3 文档（就地修改）。
        control: ``{参数名: {关节名: 值}}``，键取自 :data:`GAIN_TO_V3`。

    Returns:
        实际写入的 v3 参数键名（排序后），供接口回报"改了哪些"。
    """
    if not isinstance(control, dict) or not control:
        return []
    actuated = ((v3.get("joints") or {}).get("actuated")) or []
    roles_of = {entry.get("name"): entry.get("role") for entry in actuated if isinstance(entry, dict)}
    if not roles_of:
        return []
    profile = v3.setdefault("actuator_profile", {})
    by_role = profile.setdefault("by_role", {})
    by_joint = profile.setdefault("by_joint", {})
    role_groups: dict[str, list[str]] = {}
    for joint_name, role in roles_of.items():
        if role:
            role_groups.setdefault(str(role), []).append(str(joint_name))

    written: set[str] = set()
    for gain_key, v3_key in GAIN_TO_V3.items():
        per_joint = control.get(gain_key)
        if not isinstance(per_joint, dict):
            continue
        for role, names in role_groups.items():
            values = [per_joint.get(name) for name in names if per_joint.get(name) is not None]
            if not values:
                continue
            if len(values) == len(names) and len({float(v) for v in values}) == 1:
                by_role.setdefault(role, {})[v3_key] = values[0]
                for name in names:
                    if name in by_joint:
                        by_joint[name].pop(v3_key, None)
                written.add(v3_key)
            else:
                for name in names:
                    if per_joint.get(name) is not None:
                        by_joint.setdefault(name, {})[v3_key] = per_joint[name]
                        written.add(v3_key)
    return sorted(written)
