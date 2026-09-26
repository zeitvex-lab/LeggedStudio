"""族级技能的**通用装配**：给一份契约 + 标准 MJCF，直接建出族级技能的 env/runner。

## 它解决什么

族级技能此前是「一台机型 × 一个技能 = 一个包内客户文件」（绑定 + profile + 入口）。
那是为了**证明复用**必要的（逐档等价 + 真跑），但对"**新机型进来**"这件事是胶水：
标准 MJCF + 契约已经足够表达一台四足/四轮足，可技能还是要人再写一遍。

本模块把机型侧收敛成**数据**：技能目录声明在族注册表（`skill_catalog`，按 `task_name` 成键），
机器人事实全部从 `QuadrupedSkillBinding.from_contract(...)` 派生，实体/解析器复用
`generic_task_builder` 的**同一套原语**（不另立一条"新机型怎么建实体"的路）。

于是：**新机型 + 标准 MJCF ⇒ 族级技能可用**，无需任何机型专属 Python 文件。

## 口径（写死在代码里的只有"怎么装配"，不是"装配成什么"）

* `kit` / `profile` / `profile_kwargs` / `factory_kwargs` 全在族注册表里；
* 出生高：优先契约初始位姿（`joints.init_state.pos[2]` 之类），否则取 MJCF 根 body 的 `pos[2]`
  —— 那是"标准 MJCF"对站立高最直接的表达；
* 机型身份（`task_id` / `experiment_name`）由机器人 id + 任务名合成，可被 `profile_overrides` 覆盖
  （逐档档案就是这么来的：它们只是把身份与少量数值钉死）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

# 训练栈（mjlab/mujoco）**全部惰性 import**：控制面（backend / tools 的轻量路径）
# 也要能 import 本模块做诊断，不能因为缺 mjlab 就炸（与 generic_task_builder 同一条边界约定）。

#: 族 id → 该族的**绑定工厂**（形态各一套 Kit，装配流程一致；装配表指向谁就装配谁）。
_FAMILY_KITS = {
    "quadruped": {
        "kit": "adapters.mjlab.kits.quadruped_kit",
        "binding_from_contract": "adapters.mjlab.kits.quadruped_kit.skills:from_contract",
    },
    "wheel_leg": {
        "kit": "adapters.mjlab.kits.wheel_leg_kit",
        "binding_from_contract": "adapters.mjlab.kits.wheel_leg_kit.skills:from_contract",
    },
}


def _family_hooks(family_id: str) -> dict[str, str]:
    hooks = _FAMILY_KITS.get(family_id)
    if hooks is None:
        raise ValueError(
            f"族 {family_id!r} 还没有通用装配的分派（可用：{sorted(_FAMILY_KITS)}）—— "
            "新增形态时在这里登记绑定工厂即可，装配流程共用"
        )
    return hooks


@dataclass(frozen=True)
class FamilySkillRecipe:
    """一个任务的装配配方（**数据**：族注册表的 `skill_catalog[task_name]`）。"""

    task_name: str
    family_id: str
    env: str
    runner: str
    profile: str
    profile_kwargs: dict[str, Any]
    factory_kwargs: dict[str, Any]
    adaptive_switches: dict[str, str]
    requires: tuple[str, ...]
    derive: tuple[str, ...]
    note: str = ""


@dataclass(frozen=True)
class FamilySkillAssembly:
    """装配结果：三个 cfg + 一份"我派生自哪里"的诊断（排查用，不参与训练）。"""

    task_name: str
    family_id: str
    env_cfg: Any
    play_cfg: Any
    runner_cfg: Any
    diagnostics: dict[str, Any]


def _load_symbol(path: str) -> Any:
    module_name, _, attr = path.partition(":")
    if not module_name or not attr:
        raise ValueError(f"装配表里的符号必须是 `module:attr` 形式，得到 {path!r}")
    return getattr(__import__(module_name, fromlist=[attr]), attr)


def family_skill_catalog(family_id: str) -> dict[str, FamilySkillRecipe]:
    """读族注册表的 `skill_catalog`（唯一真值），缺项即报错、不静默给空。"""
    from .kits.quadruped_kit.skills import family as family_roles

    document = family_roles.load_family(family_id)
    catalog = document.get("skill_catalog")
    if not isinstance(catalog, dict) or not catalog:
        raise ValueError(
            f"族 {family_id!r} 的注册表没有 `skill_catalog` —— "
            "通用装配要求技能配方是**数据**（见 registry/families/*.json）"
        )
    recipes: dict[str, FamilySkillRecipe] = {}
    for task_name, item in catalog.items():
        if not isinstance(item, dict):
            raise ValueError(f"{family_id}/{task_name}: 装配表项必须是对象")
        missing = [key for key in ("env", "runner", "profile") if not item.get(key)]
        if missing:
            raise ValueError(f"{family_id}/{task_name}: 装配表项缺 {missing}")
        recipes[str(task_name)] = FamilySkillRecipe(
            task_name=str(task_name),
            family_id=family_id,
            env=str(item["env"]),
            runner=str(item["runner"]),
            profile=str(item["profile"]),
            profile_kwargs=dict(item.get("profile_kwargs") or {}),
            factory_kwargs=dict(item.get("factory_kwargs") or {}),
            adaptive_switches=dict(item.get("adaptive_switches") or {}),
            requires=tuple(str(name) for name in (item.get("requires") or ())),
            derive=tuple(str(name) for name in (item.get("derive") or ())),
            note=str(item.get("note") or ""),
        )
    return recipes


def _root_body_height(spec_fn: Callable[[], Any]) -> float:
    """MJCF 根 body 的 `pos[2]`（**建模基准**，不是站立高；只作最后的兜底并如实标注）。"""
    bodies = list(spec_fn().worldbody.bodies)
    if not bodies:
        raise RuntimeError("MJCF 的 worldbody 没有子 body —— 取不到站立高")
    return float(bodies[0].pos[2])


def _standing_height_by_fk(contract: Any, spec_fn: Callable[[], Any]) -> float | None:
    """**站立高 = 默认姿 FK 后把最低足端放到地面上所需的高度**。

    为什么用这个口径：标准 MJCF 的根 body `pos[2]` 只是建模基准（b2 是 0.8，而它真正的
    训练出生高是 0.54），契约里也没有出生高字段。把契约 `joints.default_pose` 灌进模型、
    做一次 FK、量足端最低点到地面的距离 —— 这才是"这台机器人站着多高"的可计算答案，
    且只用标准 MJCF + 契约（不需要任何机型 Python）。
    """
    import mujoco

    joint_order = [str(item) for item in ((contract.get("action") or {}).get("joint_order") or ())]
    pose = [float(x) for x in ((contract.get("joints") or {}).get("default_pose") or ())]
    if not joint_order or len(pose) != len(joint_order):
        return None
    model = spec_fn().compile()
    data = mujoco.MjData(model)
    for name, value in zip(joint_order, pose):
        address = next(
            (index for index in range(model.njnt) if model.joint(index).name == name), None
        )
        if address is None or model.jnt_type[address] == mujoco.mjtJoint.mjJNT_FREE:
            continue
        data.qpos[int(model.jnt_qposadr[address])] = value
    # 先把根放到 1 m 高处做 FK（保证不穿地），再量足端最低点
    free = next(
        (index for index in range(model.njnt) if model.jnt_type[index] == mujoco.mjtJoint.mjJNT_FREE),
        None,
    )
    if free is None:
        return None
    data.qpos[int(model.jnt_qposadr[free]) + 2] = 1.0
    mujoco.mj_forward(model, data)
    names = [model.geom(index).name for index in range(model.ngeom)]
    feet = [index for index, name in enumerate(names) if name and "foot" in name.lower()]
    candidates = feet or list(range(model.ngeom))
    lowest = min(float(data.geom_xpos[index][2]) for index in candidates)
    return round(1.0 - lowest, 4)


def _default_pose_fk(contract: Any, spec_fn: Callable[[], Any]):
    """把契约 `default_pose` 灌进模型做一次 FK（根先抬到 1 m，避免穿地）。

    返回 `(model, data)`；关节序/默认姿不齐时返回 `(None, None)`。
    """
    import mujoco

    joint_order = [str(item) for item in ((contract.get("action") or {}).get("joint_order") or ())]
    pose = [float(x) for x in ((contract.get("joints") or {}).get("default_pose") or ())]
    if not joint_order or len(pose) != len(joint_order):
        return None, None
    model = spec_fn().compile()
    data = mujoco.MjData(model)
    for name, value in zip(joint_order, pose):
        address = next((i for i in range(model.njnt) if model.joint(i).name == name), None)
        if address is None or model.jnt_type[address] == mujoco.mjtJoint.mjJNT_FREE:
            continue
        data.qpos[int(model.jnt_qposadr[address])] = value
    free = next((i for i in range(model.njnt) if model.jnt_type[i] == mujoco.mjtJoint.mjJNT_FREE), None)
    if free is None:
        return None, None
    data.qpos[int(model.jnt_qposadr[free]) + 2] = 1.0
    mujoco.mj_forward(model, data)
    return model, data


def derive_wheel_geometry(contract: Any, spec_fn: Callable[[], Any]) -> dict[str, float] | None:
    """轮半径 / 轮距：**从 MJCF 的轮 body 与其几何**派生（几何无名也算得出）。

    轮 body 的判据是名含 `wheel`（族内四台同词：`FL_wheel_link` / `fl_wheel`）；
    半径取挂在这些 body 上几何的最大"水平半宽"（圆柱/球给 size[0]，盒给 max(size[:2])），
    轮距取 FK 后左右轮世界 y 方向的跨度。取不到（没有轮 body）即返回 None。
    """
    model, data = _default_pose_fk(contract, spec_fn)
    if model is None:
        return None
    wheel_ids = [
        index for index in range(model.nbody) if "wheel" in (model.body(index).name or "").lower()
    ]
    if not wheel_ids:
        return None
    geoms = [index for index in range(model.ngeom) if int(model.geom_bodyid[index]) in wheel_ids]
    if not geoms:
        return None
    radii = []
    for index in geoms:
        size = [float(x) for x in model.geom_size[index]]
        radii.append(max(size[0], size[1] if len(size) > 1 else 0.0))
    ys = [float(data.xpos[index][1]) for index in wheel_ids]
    return {
        "wheel_radius": round(max(radii), 4),
        "wheel_track": round(max(ys) - min(ys), 4),
    }


def _initial_height(contract: Any, spec_fn: Callable[[], Any]) -> tuple[float, str]:
    """出生高（按可信度排序，各自如实标出处）。

    ① 契约显式声明 → ② **默认姿 FK 的站立高**（主口径）→ ③ MJCF 根 body `pos[2]`（建模基准，兜底）。
    """
    for path in ("initial_state.pos", "joints.init_state.pos", "init_state.pos"):
        node: Any = contract
        for part in path.split("."):
            node = node.get(part) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, (list, tuple)) and len(node) >= 3:
            return float(node[2]), f"契约 {path}[2]"
    try:
        standing = _standing_height_by_fk(contract, spec_fn)
    except Exception:  # noqa: BLE001 - FK 失败就落到兜底，不阻断装配
        standing = None
    if standing:
        return float(standing), "默认姿 FK：把最低足端放到地面（站立高）"
    return _root_body_height(spec_fn), "MJCF 根 body pos[2]（建模基准，**未标定**）"


def derive_profile_kwargs(
    contract: Any, spec_fn: Callable[[], Any], recipe: "FamilySkillRecipe", family_id: str
) -> dict[str, Any]:
    """按装配表 `derive` 声明，把 profile 需要的**机型事实**从契约 + MJCF 算出来。

    目前支持：`init_base_height`（默认姿 FK 站立高）、`wheel_radius` / `wheel_track`
    （轮几何，见 :func:`derive_wheel_geometry`）。声明了却算不出来 ⇒ 报错并说明缺什么，
    不静默漏参数（漏了会在 profile 构造时报"缺关键字参数"，信息量差得多）。
    """
    wanted = tuple(str(name) for name in (recipe.derive or ()))
    if not wanted:
        return {}
    derived: dict[str, Any] = {}
    if "init_base_height" in wanted:
        derived["init_base_height"] = _initial_height(contract, spec_fn)[0]
    if any(name in wanted for name in ("wheel_radius", "wheel_track")):
        geometry = derive_wheel_geometry(contract, spec_fn)
        if geometry is None:
            raise ValueError(
                f"{contract.get('robot_id')}: 装配表要求派生轮几何（{wanted}），"
                "但 MJCF 里找不到名含 `wheel` 的 body 或挂其上的几何 —— "
                "这是能力缺口：轮足的族级 velocity 需要轮半径/轮距，标准 MJCF 里轮 body 名带 `wheel` 即可"
            )
        derived.update({key: geometry[key] for key in ("wheel_radius", "wheel_track") if key in wanted})
    unresolved = [name for name in wanted if name not in derived]
    if unresolved:
        raise ValueError(f"{recipe.task_name}: 装配表声明了暂不支持的派生项 {unresolved}")
    return derived


def build_family_skill(
    contract: dict,
    model_path: str | Path,
    task_name: str,
    *,
    family_id: str = "quadruped",
    profile_overrides: dict[str, Any] | None = None,
    init_base_height: float | None = None,
    play: bool = False,
) -> FamilySkillAssembly:
    """用**契约 + MJCF**装配一个族级技能（不需要任何机型专属 Python 文件）。"""
    from . import generic_task_builder as generic

    from_contract = _load_symbol(_family_hooks(family_id)["binding_from_contract"])

    recipes = family_skill_catalog(family_id)
    recipe = recipes.get(str(task_name))
    if recipe is None:
        raise ValueError(
            f"族 {family_id!r} 的装配表里没有任务 {task_name!r}；可用：{sorted(recipes)}"
        )

    model = Path(model_path)
    if not model.is_file():
        raise FileNotFoundError(f"MJCF 资产不存在：{model}")

    # **依赖体检**：装配表声明了本任务依赖哪些资产能力时，先体检再装配 ——
    # 失败信息直接说"缺哪条能力、去族注册表哪一节看约定"，不让 mjlab 在中途抛看不懂的话。
    if recipe.requires:
        capabilities = robot_capabilities(contract, model, family_id=family_id)
        missing = [
            name for name in recipe.requires
            if not capabilities["items"].get(name, {}).get("ok", False)
        ]
        if missing:
            detail = "；".join(
                f"{name}: {capabilities['items'][name]['detail']}" for name in missing
            )
            raise ValueError(
                f"{contract.get('robot_id')}: 任务 {task_name!r} 依赖的资产能力缺失 —— {detail}"
                "（族约定见族注册表 `mjcf_conventions`；补齐资产即可通过）"
            )

    spec_fn = generic.make_spec_fn(model)
    entity_cfg, _joint_order, actuator_report = generic.build_entity_cfg(contract, model)
    # **前置条件：位置执行器**。族级技能的动作项是位置控制配方（`joint_pos` + 默认姿 offset），
    # 执行器是 effort 模式（MJCF 里写 `<motor>`）的资产在这里就明确拒绝 —— 说清"差什么、怎么补"，
    # 而不是让它跑到 DR 事件里再抛一句看不懂的话。
    fields = dict(actuator_report.get("xml_command_fields") or {})
    non_position = {joint: mode for joint, mode in fields.items() if mode != "position"}
    if non_position:
        raise ValueError(
            f"{contract.get('robot_id')}: 该资产的执行器不是位置模式"
            f"（{non_position}）—— 族级技能按**位置控制**装配（见族注册表 "
            f"`mjcf_conventions.actuator_binding`）。标准 MJCF 把执行器写成 "
            f"`<position joint=... kp=... kv=.../>` 即可通过；effort 模式的资产需要另立动作档。"
        )
    if init_base_height is not None:
        init_height, height_source = float(init_base_height), "调用方显式给定"
    else:
        init_height, height_source = _initial_height(contract, spec_fn)
    binding = from_contract(
        contract,
        spec_fn=spec_fn,
        base_entity_cfg=lambda: entity_cfg,
        init_base_height=init_height,
    )

    # **按资产事实自适应**（只在装配表声明了 `adaptive_switches` 时生效）：
    # 例：资产没有具名腿杆碰撞几何 ⇒ 族级"接触监看"（几何名口径）装不出来，
    # 自动置 False，而不是要求每个新资产写一行机型数据。判据是资产事实，不是机型名。
    adaptive: dict[str, Any] = {}
    if "contact_supervision" in recipe.adaptive_switches:
        missing_roles = []
        for role in binding.leg_pattern:
            if binding.family_role(role) == "hip_abduction":
                continue
            try:
                binding.collision_geoms_for_role(role)
            except RuntimeError:
                missing_roles.append(role)
        if missing_roles:
            adaptive["contact_supervision"] = False
    derivable = derive_profile_kwargs(contract, spec_fn, recipe, family_id)
    profile_class = _load_symbol(recipe.profile)
    robot_id = str(contract.get("robot_id") or "robot")
    # 身份字段**只在 profile 声明时注入**：有的 profile 是纯族级开关表（如 `VelocityProfile`），
    # 没有机型身份一说 —— 不硬塞关键字，也不因此判失败。
    import dataclasses

    accepted = (
        {field.name for field in dataclasses.fields(profile_class)}
        if dataclasses.is_dataclass(profile_class)
        else set()
    )
    identity = {
        key: value
        for key, value in {
            "task_id": str(task_name),
            "experiment_name": f"{robot_id.replace('.', '_')}_{task_name}",
        }.items()
        if not accepted or key in accepted
    }
    profile = profile_class(
        **{
            **identity,
            **recipe.profile_kwargs,
            **adaptive,
            **derivable,
            **(profile_overrides or {}),
        }
    )
    env_factory = _load_symbol(recipe.env)
    runner_factory = _load_symbol(recipe.runner)
    env_cfg = env_factory(binding, profile, **recipe.factory_kwargs, play=False)
    play_cfg = (
        env_factory(binding, profile, **recipe.factory_kwargs, play=True) if not play else env_cfg
    )
    # runner 的实验名：**按签名**决定传不传（profile 身份字段是可选口径，不强求每个族的
    # profile 数据类都有它 —— 轮足族的 profile 是几何/命令配方，不该为装配去改数据类）。
    import inspect

    experiment_name = f"{robot_id.replace('.', '_')}_{task_name}"
    if "experiment_name" in inspect.signature(runner_factory).parameters:
        runner_cfg = runner_factory(profile, experiment_name=experiment_name)
    else:
        runner_cfg = runner_factory(profile)
    return FamilySkillAssembly(
        task_name=str(task_name),
        family_id=family_id,
        env_cfg=env_cfg,
        play_cfg=play_cfg,
        runner_cfg=runner_cfg,
        diagnostics={
            "robot_id": robot_id,
            "model_path": str(model),
            "init_base_height": init_height,
            "init_height_source": height_source,
            "binding_root_body": binding.root_body,
            "binding_joint_order": list(binding.joint_order),
            "binding_foot_geoms": list(binding.foot_geoms),
            "binding_actuator_source": binding.actuator_source,
            "right_leg_indices": list(binding.right_leg_indices()),
            "profile_class": recipe.profile,
            "factory_kwargs": recipe.factory_kwargs,
            "recipe_note": recipe.note,
            "adaptive": adaptive,
            "derived_profile_kwargs": derivable,
            "capabilities": robot_capabilities(contract, model, family_id=family_id)["items"],
        },
    )



def robot_capabilities(contract: dict, model_path: str | Path, *, family_id: str = "quadruped") -> dict:
    """族级技能的**进场体检**：这台资产（契约 + 标准 MJCF）满足族约定的哪几条、缺哪条。

    体检项就是族级技能真正依赖的资产事实（都是族注册表 `mjcf_conventions` 的落点）：
    ① 位置执行器；② 族约定保留的传感器（`spec_utils.KEEP_SENSORS`）；
    ③ 可碰撞几何名以 `_collision` 结尾；④ 足端 site（站姿类 / spring_jump 需要）；
    ⑤ 腿杆 body / 具名腿杆几何（几何未具名时按 body 匹配）。
    结论是**如实清单**：缺项不判失败，但要写清缺哪个、影响哪一类技能 —— 新机型进场时
    一条命令就能看到"能用哪些技能、还差什么"。
    """
    from . import generic_task_builder as generic
    from .spec_utils import KEEP_SENSORS

    model = Path(model_path)
    spec_fn = generic.make_spec_fn(model)
    compiled = spec_fn().compile()
    entity_cfg, _joint_order, actuator_report = generic.build_entity_cfg(contract, model)
    from .kits.quadruped_kit.skills import from_contract

    spec = spec_fn()
    bodies = list(spec.worldbody.bodies)
    root_height = float(bodies[0].pos[2]) if bodies else 0.0
    binding = from_contract(
        contract, spec_fn=spec_fn, base_entity_cfg=lambda: entity_cfg, init_base_height=root_height
    )

    present_sensors = {compiled.sensor(index).name for index in range(compiled.nsensor)}
    named_geoms = [compiled.geom(index).name for index in range(compiled.ngeom) if compiled.geom(index).name]
    collision_named = [name for name in named_geoms if name.endswith("_collision")]
    fields = dict(actuator_report.get("xml_command_fields") or {})

    try:
        binding.foot_sites()
        foot_sites = True
        foot_detail = "齐全"
    except RuntimeError as exc:
        foot_sites = False
        foot_detail = str(exc)[:160]

    link_geom_roles = {}
    for role in binding.leg_pattern:
        if binding.family_role(role) == "hip_abduction":
            continue
        try:
            binding.collision_geoms_for_role(role)
            link_geom_roles[role] = True
        except RuntimeError:
            link_geom_roles[role] = False

    try:
        binding.penalized_contact_match()
        penalized = True
        penalized_detail = "可派生"
    except RuntimeError as exc:
        penalized = False
        penalized_detail = str(exc)[:160]

    return {
        "robot_id": contract.get("robot_id"),
        "family_id": family_id,
        "model_path": str(model),
        "items": {
            "position_actuators": {
                "ok": all(mode == "position" for mode in fields.values()) if fields else True,
                "detail": {joint: mode for joint, mode in fields.items() if mode != "position"} or "全部位置模式",
            },
            # 族级观测引用的两个 IMU 名（`base_ang_vel` / `base_lin_vel` 的载体；
            # 证据：b2 的编译产物有这两个名、parkour 与轮足 Kit 也按名引用）。
            "imu_sensors": {
                "ok": {"imu_lin_vel", "imu_ang_vel"}.issubset(present_sensors),
                "detail": {
                    "missing": sorted({"imu_lin_vel", "imu_ang_vel"} - present_sensors),
                    "present": sorted(name for name in present_sensors if name),
                },
            },
            # 规范化保留集（`spec_utils.KEEP_SENSORS`）：**仅告知**，不作 requires ——
            # 它是"训练时保留哪些传感器"的口径，比观测真正引用的那两个宽。
            "kept_sensors": {
                "ok": set(KEEP_SENSORS).issubset(present_sensors),
                "detail": {
                    "missing": sorted(set(KEEP_SENSORS) - present_sensors),
                    "note": "规范化保留集（训练只留这些）；缺它不必然影响装配，故不作为 requires",
                },
            },
            "named_collision_geoms": {
                "ok": bool(collision_named),
                "detail": f"{len(collision_named)} 个具名碰撞几何（族约定名尾 `_collision`）",
            },
            "foot_sites": {"ok": foot_sites, "detail": foot_detail},
            "link_collision_geoms_by_role": {"ok": all(link_geom_roles.values()), "detail": link_geom_roles},
            "penalized_contact_match": {"ok": penalized, "detail": penalized_detail},
        },
    }


def candidate_families(contract: dict) -> tuple[str, ...]:
    """这台机型的形态落在哪些族里（按契约 `morphology.id` 对族注册表的 `morphology_ids`）。

    与 `audit_families` 的成员判定同一条口径：**从契约派生**，不看机型名。
    """
    from .kits.quadruped_kit.skills import family as family_roles

    morphology = str((contract.get("morphology") or {}).get("id") or "")
    if not morphology:
        return ()
    root = family_roles.repo_root() / family_roles.FAMILY_DIR_NAME[0] / family_roles.FAMILY_DIR_NAME[1]
    index = json.loads((root / "index.json").read_text(encoding="utf-8-sig"))
    found: list[str] = []
    for entry in index.get("families") or ():
        path = root / str(entry.get("path"))
        if not path.is_file():
            continue
        document = json.loads(path.read_text(encoding="utf-8-sig"))
        family_id = str(document.get("family_id") or "")
        if morphology in {str(item) for item in (document.get("morphology_ids") or ())}:
            found.append(family_id)
    return tuple(found)


def resolve_package_assets(package_root: str | Path, contract_path: str | Path | None = None) -> tuple[dict, Path, str]:
    """从**包目录**解析 (契约, MJCF 路径, 用了哪份契约)。

    与 `tools/validate_family_skill_assembly.py` 同一口径：v3 契约优先、导入包常只有
    `contract_legacy_v2.json`；MJCF 依次看包清单 `model.path` → 契约 `urdf.path` →
    标准布局 `model/robot.xml` / `robot.xml`。
    """
    package = Path(package_root)
    contracts = [Path(contract_path)] if contract_path else []
    contracts += [package / "contract.json", package / "contract_legacy_v2.json"]
    for candidate in contracts:
        if candidate.is_file():
            contract = json.loads(candidate.read_text(encoding="utf-8-sig"))
            used = candidate.name
            break
    else:
        raise FileNotFoundError(f"{package} 里没有契约（contract.json / contract_legacy_v2.json）")

    manifest = package / "robot_package.json"
    if manifest.is_file():
        model = (json.loads(manifest.read_text(encoding="utf-8-sig")).get("model") or {}).get("path")
        if model and (package / model).is_file():
            return contract, (package / model).resolve(), used
    raw = str(((contract.get("urdf") or {}).get("path") or "")).strip()
    if raw:
        for candidate in (Path(raw), package / raw):
            if candidate.is_file():
                return contract, candidate.resolve(), used
    for candidate in (package / "model" / "robot.xml", package / "robot.xml"):
        if candidate.is_file():
            return contract, candidate.resolve(), used
    raise FileNotFoundError(f"{package} 里找不到 MJCF（清单/契约/标准布局都没命中）")


def try_build_family_skill_from_package(
    package_root: str | Path,
    task_name: str,
    *,
    contract_path: str | Path | None = None,
    profile_overrides: dict[str, Any] | None = None,
) -> FamilySkillAssembly | None:
    """**训练服务的入口**：无档案时按族装配表把任务建出来；不适用则返回 None（不干预既有流程）。

    "不适用"= 解析不出契约/MJCF、或该形态的族里没有这个任务 —— 这两种情况都**不抛错**，
    交给调用方走它原来的分支（generic 路径 / 报"任务不存在"）。**装配过程中的真错照抛**
    （缺能力/缺资产），因为它们正是要让人看见的结论。
    """
    try:
        contract, model, _used = resolve_package_assets(package_root, contract_path)
    except FileNotFoundError:
        return None
    for family_id in candidate_families(contract):
        try:
            recipes = family_skill_catalog(family_id)
        except ValueError:
            continue
        if task_name in recipes:
            return build_family_skill(
                contract, model, task_name,
                family_id=family_id, profile_overrides=profile_overrides,
            )
    return None

__all__ = [
    "FamilySkillAssembly",
    "FamilySkillRecipe",
    "build_family_skill",
    "family_skill_catalog",
    "candidate_families",
    "resolve_package_assets",
    "robot_capabilities",
    "try_build_family_skill_from_package",
]
