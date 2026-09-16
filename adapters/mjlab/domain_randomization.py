"""L3：域随机化（E1–E8）—— 注册表驱动的 term + 四种算子，作用在 MuJoCo 模型/数据上。

## 为什么是"注册表驱动 + 可复算"

真机迁移最大的缺口是"训练/验收环境与真机差异"（L3）。上游三处写法已取证到文件级：

1. `00_resources/mjlab_new/mjlab/src/mjlab/tasks/velocity/velocity_env_cfg.py` 的 `events` 字典
   （`EventTermCfg(mode="startup"/"reset"/"interval", func=dr.geom_friction / encoder_bias /
   body_com_offset / push_by_setting_velocity)`）；
2. **数据层** `00_resources/unitree_rl_mjlab_go2w/mjlab/envs/mdp/events.py` 的
   `FieldSpec` + `FIELD_SPECS` + `randomize_field()`（`dof_armature`/`dof_frictionloss` 正是
   `FieldSpec("dof", use_address=True)` —— 与本仓契约里的 armature / friction_loss 同字段）；
3. 参数清单 `00_resources/Dreamwaq/legged_gym/envs/M20/m20_config.py::domain_rand` 与
   `00_resources/m20_rl_isaacsim/.../velocity/mdp/events.py::_randomize_prop_by_op`
   （**uniform / log_uniform / gaussian × add / scale / abs**）。

本模块把这三处的**口径**合成一层：term 表（名字 / 目标字段 / 算子 / 范围 / 生效模式）+ 一个
`apply()`。**不新造语义**：算子名与上游 `by_op` 一致，字段名与本仓契约一致（armature /
friction_loss 已是契约一等物理量）。

## 验收判据（同 Seed 同 DR）

`tools/replay_gate.py --produce --seed-probe <另一个 seed>`：**DR 关**时两次跑结果必须相同
（确定性），**DR 开**时换 seed 必须**不同** —— 这条探测就是 L3 的验收线，不需要谁口头宣布
"DR 接进来了"。frame log 的 `head.randomization` 里如实写"这次到底有没有随机化"。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

#: 允许的算子（与上游 `_randomize_prop_by_op` 同名同义）
OPS = ("add", "scale", "abs")
#: 允许的分布
DISTRIBUTIONS = ("uniform", "log_uniform", "gaussian")
#: 生效模式（与上游 `EventTermCfg.mode` 同名）
MODES = ("startup", "reset", "interval")


@dataclass(frozen=True)
class RandomizeTerm:
    """一个随机化项：**声明**（名字/字段/算子/范围/模式）——范围必须写死，不许代码里散落。"""

    name: str
    target: str
    field: str
    op: str = "scale"
    distribution: str = "uniform"
    low: float = 1.0
    high: float = 1.0
    mode: str = "startup"
    interval_s: float | None = None
    bodies: tuple[str, ...] = ()
    geoms: tuple[str, ...] = ()
    note: str = ""

    def sample(self, rng: np.random.Generator, size: int | None = None) -> np.ndarray | float:
        if self.distribution == "log_uniform":
            value = np.exp(rng.uniform(math.log(self.low), math.log(self.high), size))
        elif self.distribution == "gaussian":
            value = rng.normal(self.low, self.high, size)
        else:
            value = rng.uniform(self.low, self.high, size)
        return float(value) if size is None else value


#: E1–E8：**本仓当前实现的 8 项**（字段名与本仓契约一致；范围口径见各项 note）
DEFAULT_TERMS: tuple[RandomizeTerm, ...] = (
    RandomizeTerm("E1-geom-friction", "geom", "friction", "scale", "uniform", 0.6, 1.4,
                  note="地面/足端摩擦系数倍率（上游 dr.geom_friction 同义；本仓 geom 多有命名，按 geoms 过滤）"),
    RandomizeTerm("E2-dof-armature", "dof", "armature", "scale", "uniform", 0.8, 1.2,
                  note="关节 armature 倍率 —— 本仓 armature 已是契约一等物理量（B22 的物理标量）"),
    RandomizeTerm("E3-dof-frictionloss", "dof", "frictionloss", "scale", "uniform", 0.7, 1.3,
                  note="关节摩擦损失倍率（与 armature 同族，影响能耗与跟随）"),
    RandomizeTerm("E4-dof-damping", "dof", "damping", "scale", "uniform", 0.8, 1.25,
                  note="关节阻尼倍率（执行器层，真机伺服差异的主要来源之一）"),
    RandomizeTerm("E5-body-mass", "body", "mass", "scale", "uniform", 0.9, 1.1,
                  note="刚体质量倍率（负载/电池/线束差异）"),
    RandomizeTerm("E6-body-ipos", "body", "ipos", "add", "uniform", -0.01, 0.01,
                  note="质心偏移（米，每轴独立采样；上游 body_com_offset 同义）"),
    RandomizeTerm("E7-push-velocity", "state", "push_velocity", "add", "uniform", -0.3, 0.3,
                  mode="interval", interval_s=1.0,
                  note="间歇推力（m/s，施加到基座线速度；上游 push_by_setting_velocity 同义）"),
    RandomizeTerm("E8-base-height", "state", "base_height", "add", "uniform", -0.02, 0.02,
                  mode="reset",
                  note="初始高度扰动（米）——启动姿态差异，影响第一次落地接触"),
)


def terms_from_config(config: Mapping[str, Any] | None) -> tuple[RandomizeTerm, ...]:
    """从声明（如包内 `simulation/config.json` 的 `domain_randomization`）构造 term 表。

    声明里只认**已实现的字段名与算子**：认不出的项**如实报错**（不静默忽略 —— 静默忽略会
    让"我开了 DR"变成"我以为开了"）。
    """

    if not config:
        return DEFAULT_TERMS
    entries = config.get("terms") if isinstance(config, Mapping) else None
    if not entries:
        return DEFAULT_TERMS
    built: list[RandomizeTerm] = []
    for item in entries:
        if not isinstance(item, Mapping):
            raise ValueError(f"域随机化项必须是对象：{item!r}")
        field = str(item.get("field") or "")
        target = str(item.get("target") or "")
        op = str(item.get("op") or "scale")
        distribution = str(item.get("distribution") or "uniform")
        mode = str(item.get("mode") or "startup")
        if op not in OPS:
            raise ValueError(f"{item.get('name')!r}: 未知算子 {op!r}（可选 {OPS}）")
        if distribution not in DISTRIBUTIONS:
            raise ValueError(f"{item.get('name')!r}: 未知分布 {distribution!r}（可选 {DISTRIBUTIONS}）")
        if mode not in MODES:
            raise ValueError(f"{item.get('name')!r}: 未知模式 {mode!r}（可选 {MODES}）")
        if target not in ("geom", "dof", "body", "state"):
            raise ValueError(f"{item.get('name')!r}: 未知目标 {target!r}（可选 geom/dof/body/state）")
        built.append(RandomizeTerm(
            name=str(item.get("name") or f"{target}-{field}"),
            target=target, field=field, op=op, distribution=distribution,
            low=float(item.get("low", 1.0)), high=float(item.get("high", 1.0)),
            mode=mode, interval_s=(float(item["interval_s"]) if item.get("interval_s") else None),
            bodies=tuple(str(v) for v in (item.get("bodies") or ())),
            geoms=tuple(str(v) for v in (item.get("geoms") or ())),
            note=str(item.get("note") or "包内声明"),
        ))
    return tuple(built)


def _indices(model: Any, term: RandomizeTerm) -> np.ndarray:
    """按名字过滤作用对象；**没给名字就是全体**（并在调用方如实记下作用范围）。"""

    import mujoco

    if term.target == "geom":
        count = model.ngeom
        if not term.geoms:
            return np.arange(count)
        ids = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name) for name in term.geoms]
        return np.asarray([i for i in ids if i >= 0], dtype=int)
    if term.target == "dof":
        if not term.bodies:
            return np.arange(model.nv)
        ids = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name) for name in term.bodies]
        return np.asarray([int(model.jnt_dofadr[i]) for i in ids if i >= 0], dtype=int)
    if term.target == "body":
        count = model.nbody
        if not term.bodies:
            return np.arange(1, count)
        ids = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name) for name in term.bodies]
        return np.asarray([i for i in ids if i >= 0], dtype=int)
    return np.arange(0)


def field_array(model: Any, target: str, field: str) -> Any:
    """字段 → MuJoCo 数组的**唯一映射**（备份与写入共用它）。

    早先把"备份取哪个数组"写成了按 **target** 分派（body 一律取 `body_mass`），于是
    `body/ipos` 的备份拿到 1 维 mass、写 2 维 ipos 时直接 IndexError（2026-09-16 实测踩到）。
    映射只能有一处，且必须按 **target + field** 查。
    """

    table = {
        ("geom", "friction"): "geom_friction",
        ("dof", "armature"): "dof_armature",
        ("dof", "frictionloss"): "dof_frictionloss",
        ("dof", "damping"): "dof_damping",
        ("body", "mass"): "body_mass",
        ("body", "ipos"): "body_ipos",
    }
    name = table.get((target, field))
    return getattr(model, name) if name else None


def _apply_operator(base: np.ndarray, sample: np.ndarray, op: str) -> np.ndarray:
    if op == "add":
        return base + sample
    if op == "scale":
        return base * sample
    if op == "abs":
        return np.abs(sample)
    raise ValueError(f"未知算子 {op!r}")


def apply(
    model: Any,
    data: Any,
    rng: np.random.Generator,
    *,
    terms: tuple[RandomizeTerm, ...] = DEFAULT_TERMS,
    mode: str = "startup",
    now_s: float | None = None,
    last_interval: dict[str, float] | None = None,
    backup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """按模式施加随机化，返回**这次到底改了什么**（逐项记下来，供 frame log/报告如实登记）。

    * ``startup`` / ``reset`` —— 只在重置时改模型/初始状态；
    * ``interval`` —— 每 ``interval_s`` 秒再来一次（推力那类），用 ``last_interval`` 记上次时刻。

    ``backup`` / ``last_interval`` 都由**调用方**持有并在多次调用间复用（见上面的说明）。
    """

    applied: list[dict[str, Any]] = []
    # 出厂值备份：scale 类算子必须基于**原始值**反复采样，否则多次 reset 会连乘漂走。
    # **由调用方持有**（`backup` 参数）：
    #   * 不能挂在 `model` 上 —— MuJoCo 的 `MjModel` 是 C 扩展类型，禁止自定义属性
    #     （实测 `model._dr_backup = …` 直接 AttributeError）；
    #   * 也不能按 `id(model)` 存在模块级缓存里 —— 模型被回收后 id 会被复用，
    #     新模型读到旧模型的备份数组 ⇒ 数值污染（实测跑出 nan，"连乘漂走"检出）。
    values = backup if backup is not None else {}

    for term in terms:
        eligible = term.mode == mode or (term.mode == "interval" and mode == "interval")
        if not eligible:
            continue
        if term.mode == "interval" and last_interval is not None:
            key = term.name
            previous = last_interval.get(key)
            interval = float(term.interval_s or 1.0)
            if previous is not None and now_s is not None and (float(now_s) - previous) < interval:
                continue
            last_interval[key] = float(now_s if now_s is not None else 0.0)

        indices = _indices(model, term)
        if term.target == "state":
            if term.field != "push_velocity":
                applied.append({"term": term.name, "skipped": f"未实现的状态量 {term.field}"})
                continue
            if term.field == "push_velocity":
                sample = float(term.sample(rng))
                data.qvel[0:2] = _apply_operator(np.asarray(data.qvel[0:2], dtype=np.float64), sample, term.op)
                applied.append({"term": term.name, "field": "qvel[0:2]", "op": term.op, "sample": round(sample, 5)})
            elif term.field == "base_height":
                sample = float(term.sample(rng))
                # 初始高度扰动：加在 qpos[2]（z）上 —— 用 add 语义（"抬高/压低几厘米"）
                data.qpos[2] = float(data.qpos[2]) + sample
                applied.append({"term": term.name, "field": "qpos[2]", "op": "add", "sample": round(sample, 5)})
            else:
                applied.append({"term": term.name, "skipped": f"未实现的状态量 {term.field}"})
            continue
        if indices.size == 0:
            applied.append({"term": term.name, "skipped": "没有匹配的对象"})
            continue

        section = field_array(model, term.target, term.field)
        if section is None:
            applied.append({"term": term.name, "skipped": f"未实现的字段 {term.target}/{term.field}"})
            continue
        backup_key = term.name
        if backup_key not in values:
            values[backup_key] = np.array(section, dtype=np.float64, copy=True)
        base = values[backup_key]

        # 字段可能是 **1 维**（body_mass / dof_armature / dof_damping / dof_frictionloss）
        # 也可能是 **2 维**（geom_friction(3) / body_ipos(3)）—— 两种都要写对，
        # 用 `section[indices, :]` 下标一维数组会直接 IndexError（2026-09-16 实测踩到）。
        current = np.asarray(section)[indices]
        base_values = np.asarray(base)[indices]
        if current.ndim == 1:
            sample = np.asarray(term.sample(rng, size=indices.size), dtype=np.float64)
            section[indices] = _apply_operator(base_values, sample, term.op)
        else:
            width = current.shape[1]
            sample = np.asarray(term.sample(rng, size=indices.size * width), dtype=np.float64).reshape(indices.size, width)
            section[indices, :] = _apply_operator(base_values, sample, term.op)
        applied.append({
            "term": term.name, "target": term.target, "field": term.field, "op": term.op,
            "objects": int(indices.size), "low": term.low, "high": term.high,
        })

    import mujoco

    mujoco.mj_forward(model, data) if mode in ("startup", "reset") else None
    return {"mode": mode, "applied": applied, "count": sum(1 for item in applied if "term" in item and "skipped" not in item)}


def summarise(report: Mapping[str, Any]) -> str:
    """一行摘要（frame log 的 head 与报告里用）。"""

    items = report.get("applied") or []
    effective = [item for item in items if item.get("term") and not item.get("skipped")]
    return f"DR[{report.get('mode')}] 生效 {len(effective)}/{len(items)} 项"
