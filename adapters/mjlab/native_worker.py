"""Isolated MJLab worker used for native preflight and environment smoke tests.

The control-plane never imports MJLab. This process owns the MJLab source path,
optional CUDA runtime, and manager-based environment lifecycle.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import traceback
from dataclasses import asdict
import time
import shutil
import copy
import importlib
import inspect
import importlib.metadata
from pathlib import Path



def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ensure_on_path(path) -> None:
    """Idempotently prepend *path* to ``sys.path`` if not already present.

    Centralises the scattered ``if ... not in sys.path: sys.path.insert(0, ...)``
    boilerplate in this worker.  *path* may be a ``str`` or ``Path``; it is
    resolved and deduplicated before insertion.
    """
    normalized = str(Path(path).resolve())
    if normalized not in sys.path:
        sys.path.insert(0, normalized)


def build_deploy_metadata(env, rl_cfg, joint_names: list[str]) -> dict:
    """从 mjlab env 提取部署契约元数据（键与 onnx_exporter/浏览器校验对齐）。"""
    import mujoco

    mj_model = env.sim.mj_model
    joint_to_ctrl = {}
    for aid in range(mj_model.nu):
        jid = int(mj_model.actuator_trnid[aid, 0])
        name = mujoco.mj_id2name(mj_model, mujoco.mjtObj.mjOBJ_JOINT, jid)
        joint_to_ctrl[name] = aid
    stiffness: list[float] = []
    damping: list[float] = []
    for name in joint_names:
        aid = joint_to_ctrl.get(name)
        stiffness.append(float(mj_model.actuator_gainprm[aid, 0]) if aid is not None else 0.0)
        damping.append(float(-mj_model.actuator_biasprm[aid, 2]) if aid is not None else 0.0)
    default_joint_pos = env.scene["robot"].data.default_joint_pos[0].detach().cpu().tolist()

    try:
        action_term = env.action_manager.get_term("joint_pos")
        scale = getattr(action_term, "_scale")
        action_scale = scale.flatten().tolist() if hasattr(scale, "flatten") else [float(x) for x in scale]
    except Exception:
        action_scale = []
    try:
        # B26 同族裁决：训练观测组名是 "actor"（读 "policy" 恒得空——B44 轮登记的
        # metadata 盲项）；有 "actor" 用 "actor"，历史环境无 "actor" 时回退 "policy"。
        active_terms = env.observation_manager.active_terms
        observation_names = list(active_terms.get("actor") or active_terms.get("policy") or [])
    except Exception:
        observation_names = []
    try:
        command_names = list(env.command_manager.active_terms)
    except Exception:
        command_names = []

    metadata: dict = {
        "joint_names": joint_names,
        "joint_stiffness": stiffness,
        "joint_damping": damping,
        "default_joint_pos": default_joint_pos,
        "observation_names": observation_names,
        "command_names": command_names,
        "action_scale": action_scale,
    }
    clip = getattr(rl_cfg, "clip_actions", None)
    if clip is not None:
        metadata["clip_actions"] = float(clip)
    return metadata


def stamp_contract_extras(metadata: dict, contract_entry: dict | None) -> dict:
    """把包契约的部署字段补进元数据（清单：joint_ids_map / history_lengths / clip）。"""
    if not isinstance(contract_entry, dict):
        return metadata
    extras = contract_entry.get("contract") or {}
    if extras.get("joint_ids_map"):
        metadata["joint_ids_map"] = [int(x) for x in extras["joint_ids_map"]]
    if extras.get("observation_history_lengths"):
        metadata["observation_history_lengths"] = json.dumps(extras["observation_history_lengths"], ensure_ascii=False)
    if extras.get("clip_actions") is not None and "clip_actions" not in metadata:
        metadata["clip_actions"] = str(extras["clip_actions"])
    return metadata


def export_runner_policy_onnx(report: dict, env, runner, wrapped, rl_cfg, output: Path,
                              device: str, contract=None, contract_path=None) -> None:
    """训练完成即导出（清单 ⑤）：actor -> exported/policy.onnx + 部署元数据盖章。

    元数据键与 adapters/mjlab/onnx_exporter.attach_metadata_to_onnx 及浏览器
    sim2sim 的 validatePolicyMetadata 对齐：joint_names / joint_stiffness /
    joint_damping / default_joint_pos / observation_names / command_names /
    action_scale / clip_actions。导出失败只记录，不影响训练结果。
    """
    import torch

    try:
        import onnx  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(f"适配器 venv 缺少 onnx 包: {exc}")

    if contract is None and contract_path:
        from contracts.contract_legacy_v2 import ContractLegacyV2
        contract = ContractLegacyV2.from_json_file(str(contract_path))

    robot = env.scene["robot"]
    joint_names = list(getattr(robot, "joint_names", []) or [])
    if not joint_names and contract is not None:
        joint_names = [joint.name for joint in contract.joints.actuated_joints]

    export_path = Path(output) / "exported" / "policy.onnx"
    export_path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(runner, "export_policy_to_onnx"):
        # mjlab runner 自带的导出器（与 checkpoint 包装器同一条已验证路径）：它自己提供
        # dummy inputs / input_names。直接拿 wrapped.reset() 的观测喂 torch.onnx.export
        # 会因 TensorDict 触发 bool 转换而失败（L7 首跑实测：
        # "Converting a tensordict to boolean value is not permitted"）。
        runner.export_policy_to_onnx(str(export_path.parent), export_path.name)
    else:
        with torch.no_grad():
            obs, _ = wrapped.reset()
            if isinstance(obs, tuple):
                obs = obs[0]
            sample = obs.reshape(obs.shape[0], -1)[:1].to(device)
            policy = runner.get_inference_policy(device=device)
            torch.onnx.export(
                policy,
                sample,
                str(export_path),
                input_names=["obs"],
                output_names=["action"],
                dynamic_axes={"obs": {0: "batch"}, "action": {0: "batch"}},
                opset_version=17,
            )

    metadata = build_deploy_metadata(env, rl_cfg, joint_names)

    try:
        from onnx_exporter import attach_metadata_to_onnx
    except ImportError:
        from adapters.mjlab.onnx_exporter import attach_metadata_to_onnx

    metadata["run_path"] = str(output)
    attach_metadata_to_onnx(str(export_path), metadata)
    report["onnx_path"] = str(export_path)
    report["onnx_metadata_keys"] = sorted(metadata.keys())
    print(f"[native_worker] policy exported: {export_path}")


def collect_curriculum_snapshot(env) -> dict:
    """课程阶段状态快照（清单 ⑰）：可序列化的 per-term 状态表。

    mjlab 的课程 term 在 _curriculum_state 里维护每步更新的状态（如命令范围
    缩放系数、阶段索引）。序列化为 {term: {key: float}} 供 monitor 渲染
    "当前课程阶段 + 各阶段指标"，而不是只有 reward 曲线。
    """
    import torch

    snapshot: dict = {}
    try:
        manager = env.unwrapped.curriculum_manager
    except AttributeError:
        try:
            manager = env.unwrapped.curriculum
        except AttributeError:
            return snapshot
    state = getattr(manager, "_curriculum_state", {}) or {}
    for term_name, term_state in state.items():
        if term_state is None:
            continue
        if isinstance(term_state, dict):
            entry = {}
            for key, value in term_state.items():
                entry[str(key)] = float(value.item()) if isinstance(value, torch.Tensor) else float(value)
            snapshot[str(term_name)] = entry
        elif isinstance(term_state, torch.Tensor):
            snapshot[str(term_name)] = {"value": float(term_state.item())}
        else:
            try:
                snapshot[str(term_name)] = {"value": float(term_state)}
            except (TypeError, ValueError):
                snapshot[str(term_name)] = {"repr": str(term_state)}
    return snapshot


def wrap_runner_with_checkpoint_export(runner_cls, metadata_builder):
    """包一层 runner：每次 save checkpoint 时同步导出 onnx 并盖章部署元数据。

    仅对 MjlabOnPolicyRunner 及其子类生效；其他 runner 原样返回。
    metadata_builder(runner) 返回元数据 dict；导出失败只打印，不中断训练。
    """
    try:
        from mjlab.rl import MjlabOnPolicyRunner
    except ImportError:
        return runner_cls
    if not (isinstance(runner_cls, type) and issubclass(runner_cls, MjlabOnPolicyRunner)):
        return runner_cls

    class ExportingRunner(runner_cls):  # type: ignore[misc,valid-type]
        _deploy_metadata_builder = staticmethod(metadata_builder)

        def save(self, path: str, infos=None) -> None:
            super().save(path, infos)
            try:
                export_dir, filename, export_path = self._get_export_paths(str(path))
                self.export_policy_to_onnx(str(export_dir), filename)
                metadata = type(self)._deploy_metadata_builder(self)
                if metadata:
                    metadata = {**metadata, "checkpoint_path": str(path)}
                    try:
                        from onnx_exporter import attach_metadata_to_onnx
                    except ImportError:
                        from adapters.mjlab.onnx_exporter import attach_metadata_to_onnx
                    attach_metadata_to_onnx(str(export_path), metadata)
            except Exception as exc:
                print(f"[native_worker] checkpoint onnx export failed: {exc}")

    return ExportingRunner


def apply_training_recipe(env_cfg, rl_cfg, config: dict, *, preserve_profile: bool = False) -> dict:
    """Apply the canonical Web/CLI recipe to real MJLab config objects."""
    recipe = config.get("resolved_recipe") or config.get("recipe") or {}
    environment = recipe.get("environment", {}) if isinstance(recipe, dict) else {}
    recipe_rewards = recipe.get("reward_scales", {}) if isinstance(recipe, dict) else {}
    # MECH-2 裁决 A「任务真值优先」（2026-09-18 三十轮塑形实验取证，见
    # tools/baselines/reward_shaping_experiments.json §mechanism_findings MECH-2）：
    # preserve_profile=True 意味着包声明了自己的任务（worker 按 profile_id 载入包内
    # profile bundle），此时 recipe.reward_scales 里由 resolve_recipe
    # （recipe_registry.py 通用任务分支 ``get_reward_preset`` + ``update``）并入的
    # 通用 preset（registry/rewards/presets.json）只是**通用任务的缺省**，不是包任务
    # 真值。reward_overrides=true 的语义据此收紧：只有**请求显式列出的** reward_scales
    # 才允许覆盖包任务（显式意图），preset 全表不得随之涌入 —— 此前把 recipe 全表
    # setattr 进 env_cfg，go2 任务真值 track_angular_velocity=2.0 / upright=+1.0 被
    # 通用值 0.5 / -2.0（经 body_orientation_l2→upright 别名）静默顶掉，任何带
    # reward_scales 的实验都在"测一个被偷换的任务"。
    # 与裁决 A 字面（"preset 只填充任务未定义的项"）的等价性：任务未定义的奖励项在
    # preserve_profile 下本就 unmatched 跳过（不报错也不生效），所以"只透传显式项"
    # 与"preset 填洞"可观测行为一致，且不依赖对任务词表的猜测，语义更干净。
    # 否决 B（显式钉住要求：请求方必须列全要动的项、未列项不进 preset）：把复杂度
    # 推给调用方/前端，漏列即踩坑；A 无技术障碍，故选 A。
    # 两条既有路径逐字节不漂移：通用任务（preserve_profile=False，generic_task_builder
    # 拿 recipe 建任务，preset 表就是任务自身定义）照旧全表应用；默认路径
    # （reward_overrides 缺省 false）照旧全表丢弃、保留任务真值。
    explicit_rewards = {
        str(key): float(value)
        for key, value in (config.get("reward_scales") or {}).items()
        if value is not None
    }
    if preserve_profile:
        rewards = explicit_rewards if config.get("reward_overrides", False) else {}
    else:
        rewards = recipe_rewards or explicit_rewards
    terrain_type = str(environment.get("terrain_type", config.get("terrain_type", "plane"))).lower()
    if not preserve_profile and terrain_type not in {"plane", "rough"}:
        raise ValueError(f"native MJLab training supports terrain_type plane or rough; got {terrain_type!r}")
    terrain = getattr(getattr(env_cfg, "scene", None), "terrain", None)
    if terrain is not None and not preserve_profile:
        if terrain_type == "plane":
            terrain.terrain_type = "plane"
            terrain.terrain_generator = None
        elif terrain.terrain_generator is None:
            raise ValueError("rough terrain recipe requires an MJLab terrain generator")

    aliases = {
        "tracking_lin_vel": "track_linear_velocity", "tracking_ang_vel": "track_angular_velocity",
        "track_lin_vel": "track_linear_velocity", "track_ang_vel": "track_angular_velocity",
        "joint_torques": "joint_torques_l2", "joint_acc": "joint_acc_l2",
        "body_ang_vel": "body_angular_velocity_penalty", "body_collision": "self_collision_cost",
        "feet_air_time": "feet_air_time", "wheel_roll_tracking": "wheel_roll_tracking",
        "orientation": "body_orientation_l2", "torques": "joint_torques_l2", "dof_vel": "joint_vel_l2",
        "dof_acc": "joint_acc_l2", "action_rate": "action_rate_l2", "collision": "illegal_contact",
        "feet_air_time": "air_time", "base_height": "upright", "stumble": "body_orientation_l2",
    }
    reward_terms = getattr(env_cfg, "rewards", {})
    unmatched = []
    term_candidates = {
        "track_linear_velocity": ("track_linear_velocity", "track_lin_vel"),
        "track_angular_velocity": ("track_angular_velocity", "track_ang_vel"),
        "body_orientation_l2": ("body_orientation_l2", "upright", "flat_orientation"),
        "joint_torques_l2": ("joint_torques_l2", "joint_torques"),
        "joint_acc_l2": ("joint_acc_l2", "joint_acc"),
        "action_rate_l2": ("action_rate_l2", "action_rate"),
        "air_time": ("air_time", "feet_air_time"),
        "base_height_l2": ("base_height_l2", "base_height"),
        "self_collision_cost": ("self_collision_cost", "body_collision"),
    }
    def resolve_term(name: str):
        for candidate in (name, aliases.get(name), *term_candidates.get(aliases.get(name, name), ())):
            if candidate in reward_terms:
                return candidate
        return None
    for name, weight in rewards.items():
        target = resolve_term(name)
        if target not in reward_terms:
            if float(weight) == 0.0:
                continue
            unmatched.append(name)
            continue
        reward_terms[target].weight = float(weight)
    if unmatched and not preserve_profile:
        raise ValueError(f"reward terms are not available in MJLab task {unmatched}")

    reward_params = (environment.get("reward_params") if isinstance(environment, dict) else None) or config.get("reward_params", {})
    if preserve_profile and not config.get("reward_overrides", False):
        reward_params = {}
    for name, params in reward_params.items():
        target = resolve_term(name)
        if target not in reward_terms or not isinstance(params, dict):
            if preserve_profile:
                continue
            raise ValueError(f"reward parameter target is not available in MJLab task: {name}")
        term_params = getattr(reward_terms[target], "params", None)
        if isinstance(term_params, dict):
            term_params.update(params)
        else:
            for key, value in params.items():
                if hasattr(term_params, key): setattr(term_params, key, value)

    command_ranges = (environment.get("command_ranges") if isinstance(environment, dict) else None) or config.get("command_ranges", {})
    if command_ranges:
        command = getattr(env_cfg, "commands", {}).get("twist")
        ranges = getattr(command, "ranges", None)
        if ranges is not None:
            for key, value in command_ranges.items():
                target = "ang_vel_z" if key in {"wz", "ang_vel_yaw"} else "lin_vel_x" if key in {"vx", "lin_vel_x"} else "lin_vel_y" if key in {"vy", "lin_vel_y"} else key
                if hasattr(ranges, target): setattr(ranges, target, tuple(value))
                elif value is not None: raise ValueError(f"command range is not supported by MJLab: {key}")

    if hasattr(env_cfg, "episode_length_s"):
        # B23：取值链改守卫式 —— environment / config 取到的值是 None（请求省略）时
        # **不动 env_cfg**，保留任务真值（profile/训练源码自带值，如 standup 6s）；
        # 只有显式提供的非 None 值才覆盖。
        _episode_length_s = environment.get("episode_length_s")
        if _episode_length_s is None:
            _episode_length_s = config.get("episode_length_s")
        if _episode_length_s is not None:
            env_cfg.episode_length_s = float(_episode_length_s)
    # num_envs 是运行层参数（吞吐规模，请求默认 4096 合法，见 models.py），保持硬默认覆盖不变。
    if hasattr(env_cfg.scene, "num_envs"):
        env_cfg.scene.num_envs = max(1, int(environment.get("num_envs", config.get("num_envs", env_cfg.scene.num_envs))))

    algorithm_config = recipe.get("algorithm_config", {}) if isinstance(recipe, dict) else {}
    algorithm_config = {**algorithm_config, **config}
    algorithm = getattr(rl_cfg, "algorithm", None)
    field_aliases = {"gae_lambda": "lam", "num_minibatches": "num_mini_batches"}
    for source, target in field_aliases.items():
        if source in algorithm_config and algorithm is not None and hasattr(algorithm, target):
            setattr(algorithm, target, type(getattr(algorithm, target))(algorithm_config[source]))
    for name in ("learning_rate", "gamma", "clip_param", "entropy_coef"):
        if name in algorithm_config and algorithm is not None and hasattr(algorithm, name):
            setattr(algorithm, name, type(getattr(algorithm, name))(algorithm_config[name]))
    if "num_steps" in algorithm_config and hasattr(rl_cfg, "num_steps_per_env"):
        rl_cfg.num_steps_per_env = max(4, int(algorithm_config["num_steps"]))
    if "max_iterations" in algorithm_config and hasattr(rl_cfg, "max_iterations"):
        rl_cfg.max_iterations = max(1, int(algorithm_config["max_iterations"]))
    if "save_interval" in algorithm_config and hasattr(rl_cfg, "save_interval"):
        rl_cfg.save_interval = max(1, int(algorithm_config["save_interval"]))
    return {"terrain_type": terrain_type, "reward_terms_applied": len(rewards) - len(unmatched), "reward_params_applied": len(reward_params), "command_ranges_applied": len(command_ranges), "algorithm": str(config.get("algorithm", recipe.get("algorithm", "PPO"))).upper()}


def _import_entrypoint(value: str):
    """Import a package-owned ``module:factory`` entrypoint."""
    module_name, separator, attr_name = str(value).partition(":")
    if not separator or not module_name or not attr_name:
        raise ValueError(f"invalid package entrypoint: {value!r}; expected module:callable")
    factory = getattr(importlib.import_module(module_name), attr_name, None)
    if not callable(factory):
        raise TypeError(f"package entrypoint is not callable: {value}")
    return factory


def _resolve_entrypoint(value: str):
    """Resolve a package entrypoint that may be a factory or config object."""
    module_name, separator, attr_name = str(value).partition(":")
    if not separator or not module_name or not attr_name:
        raise ValueError(f"invalid package entrypoint: {value!r}; expected module:callable")
    return getattr(importlib.import_module(module_name), attr_name, None)


def _call_factory(factory, *, play: bool = False):
    """Call factories with the optional MJLab play flag when supported."""
    try:
        signature = inspect.signature(factory)
        if "play" in signature.parameters:
            return factory(play=play)
    except (TypeError, ValueError):
        pass
    return factory()


def strip_visual_geoms(env_cfg) -> int:
    """headless 训练变体（清单 ⑧ A 的 get_headless_spec 同语义）：训练 env 剥离纯渲染
    geom（contype==0 且 conaffinity==0 且 density==0），只留碰撞体，Warp 训练提速。
    通过包装 entity 的 spec_fn 在 spec 阶段剔除；play/evaluate 不受影响。返回剥离数。
    """
    stripped_total = 0
    try:
        entities = env_cfg.scene.entities
    except AttributeError:
        return 0
    for name, entity_cfg in entities.items():
        spec_fn = getattr(entity_cfg, "spec_fn", None)
        if not callable(spec_fn):
            continue
        original = spec_fn

        def wrapped(_original=original):
            import mujoco
            spec = _original()
            stripped = 0
            for geom in list(spec.geoms):
                try:
                    if (int(geom.contype) == 0 and int(geom.conaffinity) == 0
                            and float(getattr(geom, "density", 0) or 0) == 0):
                        spec.delete_geom(geom)
                        stripped += 1
                except Exception:
                    continue
            nonlocal_stripped[0] += stripped
            return spec

        nonlocal_stripped = [0]
        try:
            entity_cfg.spec_fn = wrapped
            # 记录剥离数要等构建后才知道；这里只挂包装
        except Exception:
            entity_cfg.spec_fn = original
    return stripped_total


def _apply_profile_algorithm_plugin(profile: dict | None, rl_cfg) -> dict | None:
    """profile 显式声明 ``algorithm_plugin`` 时才绑定插件；否则**一行不碰**。

    为什么把开关放在 profile 上：算法插件层（``adapters/mjlab/algorithms/``）与
    "包内训练源自带 runner"是两条合法路径，只有 profile 作者知道这次要用哪条——
    平台不替它猜（猜错就是把原生 PPO 的 runner 换成插件类，训练照跑但结论不可比）。

    绑定本身只读注册表（纯 JSON）+ 写 class_name 字符串，**不需要 torch**；
    真正的插件类 import 由训练栈解析 class_name 时发生——所以这段能进控制面测试。
    阈值与口径见 ``adapters/mjlab/algorithms/registry.py`` 模块头。
    """

    if not isinstance(profile, dict):
        return None
    name = str(profile.get("algorithm_plugin") or "").strip()
    if not name:
        return None
    from adapters.mjlab.algorithms.plugin_registry import apply_algorithm_plugin

    variant = profile.get("algorithm_variant")
    return apply_algorithm_plugin(rl_cfg, algorithm_plugin=name, variant=str(variant) if variant else None)


def _load_profile_bundle(profile: dict, package: dict, config: dict):
    """Load an isolated package profile without robot-id-specific branches."""
    package_root = Path(str(package.get("package_root", ""))).resolve()
    source_root = package_root / str(profile.get("source_root", "training/source"))
    if not source_root.exists():
        raise FileNotFoundError(f"profile source root not found: {source_root}")
    _ensure_on_path(source_root)
    entrypoints = profile.get("entrypoints") or {}
    env_entrypoint = entrypoints.get("env")
    runner_entrypoint = entrypoints.get("runner")
    if not env_entrypoint or not runner_entrypoint:
        raise ValueError(f"profile {profile.get('profile_id')} must declare entrypoints.env and entrypoints.runner")
    env_factory = _import_entrypoint(env_entrypoint)
    runner_factory = _resolve_entrypoint(runner_entrypoint)
    if runner_factory is None:
        raise AttributeError(f"package entrypoint attribute not found: {runner_entrypoint}")
    env_cfg = _call_factory(env_factory, play=False)
    play_env_cfg = _call_factory(env_factory, play=True)
    if bool(config.get("headless_visual", False)) is False and str(config.get("mode", "train")) == "train":
        strip_visual_geoms(env_cfg)
    # MJLab profiles commonly export a runner config instance (for example
    # ``MicroduckRlCfg = RslRlOnPolicyRunnerCfg(...)``) rather than a factory.
    # Accept both forms so package authors do not need a platform-specific
    # wrapper.
    rl_cfg = _call_factory(runner_factory) if callable(runner_factory) else copy.deepcopy(runner_factory)
    configure_entrypoint = entrypoints.get("configure")
    if configure_entrypoint:
        configure = _import_entrypoint(configure_entrypoint)
        configured = configure(
            env_cfg=env_cfg,
            play_env_cfg=play_env_cfg,
            rl_cfg=rl_cfg,
            config=copy.deepcopy(config),
        )
        if isinstance(configured, dict):
            env_cfg = configured.get("env_cfg", env_cfg)
            play_env_cfg = configured.get("play_env_cfg", play_env_cfg)
            rl_cfg = configured.get("rl_cfg", rl_cfg)
    return env_cfg, play_env_cfg, rl_cfg


def _load_package_extension(package: dict) -> dict:
    """Load a package-owned MJLab extension declared by its manifest.

    Extensions are deliberately data-driven: a package may expose an
    ``extension_entrypoint`` (``module:register``) and optional
    ``extension_root``.  The worker never branches on robot identity and the
    shared MJLab source tree remains untouched.
    """
    entrypoint = package.get("extension_entrypoint") or package.get("extension_module")
    if not entrypoint:
        return {}
    package_root = Path(str(package.get("package_root", ""))).resolve()
    extension_root = package.get("extension_root")
    if extension_root:
        root = Path(str(extension_root))
        if not root.is_absolute():
            root = package_root / root
        if root.exists():
            _ensure_on_path(root)
    # Package source is always available for its extension module, even when
    # the selected profile has a different source_root.
    _ensure_on_path(package_root)
    register = _import_entrypoint(str(entrypoint))
    result = _call_factory(register)
    return result if isinstance(result, dict) else {"result": result}


def _apply_config_overrides(env_cfg, rl_cfg, config: dict) -> list[str]:
    """Apply generic dot-path overrides from the create request to live configs.

    Keys are full schema paths as displayed in the Web console, e.g.
    ``environment.sim.mujoco.timestep`` or ``runner.max_iterations``. Applied
    after the recipe so user edits always win. Unknown paths are logged and
    skipped — an override must never crash a launch.
    """
    overrides = config.get("overrides")
    if not isinstance(overrides, dict) or not overrides:
        return []
    from adapters.mjlab.config_introspect import set_by_path

    applied: list[str] = []
    for dot_path, value in overrides.items():
        path = str(dot_path).strip()
        targets: list[tuple[str, object]] = []
        if path.startswith("environment."):
            targets = [("env", env_cfg)] if env_cfg is not None else []
            stripped = path.removeprefix("environment.")
        elif path.startswith("runner."):
            targets = [("runner", rl_cfg)] if rl_cfg is not None else []
            stripped = path.removeprefix("runner.")
        else:
            targets = ([("env", env_cfg)] if env_cfg is not None else []) + ([("runner", rl_cfg)] if rl_cfg is not None else [])
            stripped = path
        for label, target in targets:
            try:
                set_by_path(target, stripped, value)
            except KeyError:
                continue
            except (TypeError, ValueError) as exc:
                print(f"[native-worker] override {dot_path}={value!r} rejected: {exc}", file=sys.stderr)
                break
            applied.append(path)
            break
        else:
            print(f"[native-worker] override path not found, ignored: {dot_path}", file=sys.stderr)
    return applied


def _dump_profile_schema(config: dict) -> dict:
    """Build the full config-tree schema for a resolved profile bundle."""
    package_root = Path(str(config.get("package_root", ""))).resolve()
    source_root = Path(str(config.get("source_root", "training/source")))
    if not source_root.is_absolute():
        source_root = package_root / source_root
    from adapters.mjlab.config_introspect import build_profile_schema

    return build_profile_schema(source_root, config.get("entrypoints") or {}, config.get("profile_id"))


def run(config: dict, source: Path, output: Path, extension_root: Path | None = None) -> int:
    _write(output / "status.json", {"status": "running", "backend": "native_mjlab"})
    project_root = Path(__file__).resolve().parents[2]
    _ensure_on_path(project_root)
    from adapters.mjlab.runtime_compat import evaluate_package_runtime
    _ensure_on_path(source / "src")
    package = config.get("robot_package") or {}
    generic_bundle = None
    profile = None
    profile_id = config.get("profile_id")
    if profile_id:
        profile_root = Path(str(package.get("package_root", ""))) / "training" / "profiles"
        for profile_path in profile_root.glob("*.json") if profile_root.exists() else []:
            try:
                candidate = json.loads(profile_path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            if candidate.get("profile_id") == profile_id:
                profile = candidate
                break
        if profile is None:
            raise ValueError(f"training profile not found in robot package: {profile_id}")
        config["package_profile"] = profile
    extension_report = _load_package_extension(package)
    import torch
    import mjlab
    import mjlab.tasks  # noqa: F401
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.tasks.registry import list_tasks, load_env_cfg, load_rl_cfg, load_runner_cls, register_mjlab_task

    # Generic tasks are registered dynamically from the imported Robot Contract.
    # This path is opt-in so historical extension tasks remain untouched while
    # Web/CLI callers can train any valid MJCF asset without a robot-id branch.
    # contract_path 在两条分支都要用：generic 分支必填，profile 分支的 checkpoint
    # 元数据兜底也读它（_checkpoint_metadata 的默认参数）。此前只在 generic 分支赋值，
    # profile 训练一到 wrap_runner_with_checkpoint_export 就 UnboundLocalError —— L7 首跑抓到。
    contract_path = config.get("contract_path")
    profile_bundle = None
    if profile:
        profile_bundle = _load_profile_bundle(profile, package, config)
        from mjlab.tasks.registry import register_mjlab_task
        profile_task_id = str(config.get("native_task_id") or f"LeggedStudio-{profile.get('profile_id')}")
        runner_cls = None
        runner_entrypoint = (profile.get("entrypoints") or {}).get("runner_class")
        if runner_entrypoint:
            runner_cls = _import_entrypoint(runner_entrypoint)
        register_mjlab_task(profile_task_id, profile_bundle[0], profile_bundle[1], profile_bundle[2], runner_cls=runner_cls)
        config["native_task_id"] = profile_task_id
        config["profile_task"] = True
    if config.get("generic_task", True) and profile_bundle is None:
        if not contract_path:
            raise ValueError("generic MJLab task requires contract_path")
        from contracts.contract_legacy_v2 import ContractLegacyV2
        from adapters.mjlab.generic_task_builder import build_generic_task

        contract = ContractLegacyV2.from_json_file(str(contract_path))
        bundle = build_generic_task(
            contract,
            config.get("resolved_recipe") or config.get("recipe") or config,
            asset_root=package.get("package_root") or Path(__file__).resolve().parents[2],
            task_id=str(config.get("native_task_id") or "") or None,
        )
        register_mjlab_task(bundle.task_id, bundle.env_cfg, bundle.play_env_cfg, bundle.rl_cfg)
        config["native_task_id"] = bundle.task_id
        config["generic_task_diagnostics"] = bundle.diagnostics

    task_id = config.get("native_task_id") or config.get("task_name")
    tasks = list_tasks()
    report = {
        "backend": "native_mjlab",
        "task_id": task_id,
        "registered_tasks": tasks,
        "torch_version": torch.__version__,
        "cuda_available": bool(torch.cuda.is_available()),
        "package": {"package_id": package.get("package_id"), "task_kind": "generic", "capabilities": package.get("capabilities", [])},
        "profile": {"profile_id": profile.get("profile_id"), "source": profile.get("source")} if profile else None,
        "package_extension": extension_report or None,
        # 训练前可达性预检（清单 ⑧）：包模型开环恒定动作扫描（纯 mujoco，无策略）。
        # 默认姿态不稳或动作包络即刻发散时在这里暴露，而不是训练几小时后。
    }
    try:
        package_root = Path(str(package.get("package_root", ""))) if package else None
        if package_root and (package_root / "model" / "robot.xml").is_file():
            import mujoco
            _ensure_on_path(Path(__file__).resolve().parent)
            from policy_acceptance import ObsBuilder, PackageContract, load_package_model, run_probe

            package_contract = PackageContract(package_root, _probe_policy_entry(package_root, config))
            probe_model = load_package_model(package_root, package_contract.sim)
            probe_model.opt.timestep = 1.0 / package_contract.physics_hz
            probe_data = mujoco.MjData(probe_model)
            probe_obs = ObsBuilder(package_contract, probe_model, probe_data)
            probe_report = run_probe(
                package_contract, probe_model, probe_data, probe_obs,
                seconds=float(config.get("probe_seconds", 2.0)),
            )
            # 如实记录探针用的是哪条声明（对照训练工程，也证明条目解析生效）
            probe_report["policy_entry"] = package_contract.entry.get("id")
            report["acceptance_probe"] = probe_report
    except Exception as exc:
        # 只留 message 曾让 B25 只剩一句裸 IndexError 无从定位；补最内层出错位置。
        frames = traceback.extract_tb(sys.exc_info()[2])
        origin = f" @ {Path(frames[-1].filename).name}:{frames[-1].lineno}" if frames else ""
        report["acceptance_probe_error"] = f"{type(exc).__name__}: {exc}{origin}"
    try:
        mjlab_version = str(importlib.metadata.version("mjlab"))
    except importlib.metadata.PackageNotFoundError:
        mjlab_version = str(getattr(mjlab, "__version__", "")) or None
    report["package_compatibility"] = evaluate_package_runtime(
        package,
        {
            "mjlab_version": mjlab_version,
            "python_version": ".".join(str(value) for value in sys.version_info[:3]),
            "torch_version": str(torch.__version__),
        },
    )
    if report["package_compatibility"]["status"] != "compatible":
        report.update({"status": "runtime_incompatible", "error": "robot package runtime requirements are not satisfied"})
        _write(output / "native_preflight.json", report)
        return 4
    if config.get("generic_task"):
        report["generic_task"] = True
        report["generic_task_diagnostics"] = config.get("generic_task_diagnostics", {})
    if task_id not in tasks:
        report.update({"status": "unsupported_task", "error": f"task {task_id!r} is not registered by MJLab"})
        _write(output / "native_preflight.json", report)
        return 2

    requested = str(config.get("device", "auto")).lower()
    if requested == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    elif requested.startswith("cuda"):
        if not torch.cuda.is_available():
            report.update({"status": "device_unavailable", "error": "CUDA requested but unavailable"})
            _write(output / "native_preflight.json", report)
            return 3
        device = requested
    else:
        device = "cpu"

    if profile_bundle is not None:
        env_cfg, _play_env_cfg, rl_cfg = profile_bundle
    else:
        env_cfg = load_env_cfg(task_id)
        rl_cfg = load_rl_cfg(task_id)
    recipe_report = apply_training_recipe(env_cfg, rl_cfg, config, preserve_profile=profile_bundle is not None)
    # 算法插件绑定：只在 profile 显式声明 ``algorithm_plugin`` 时生效（默认路径不变）。
    # 绑定的 class_name 进 ``recipe`` 报告——"这次用的是哪个算法的哪套接线"必须可查。
    plugin_report = _apply_profile_algorithm_plugin(profile if profile_bundle is not None else None, rl_cfg)
    if plugin_report:
        recipe_report = {**recipe_report, "algorithm_plugin": plugin_report}
    env_cfg.scene.num_envs = max(1, int(config.get("num_envs", env_cfg.scene.num_envs)))
    actor_terms = env_cfg.observations.get("actor")
    critic_terms = env_cfg.observations.get("critic")
    # MJLab 1.6 requires structural collision dictionaries to have a default;
    # Unitree's extension was authored against the previous sparse-dict API.
    for entity_cfg in env_cfg.scene.entities.values():
        for collision_cfg in entity_cfg.collisions or ():
            if isinstance(collision_cfg.priority, dict) and ".*" not in collision_cfg.priority:
                collision_cfg.priority[".*"] = 0
    if config.get("seed") is not None:
        env_cfg.seed = int(config["seed"])
    # Generic dot-path overrides run LAST so user edits win over every recipe
    # and request merge above (never crash: unknown paths are logged instead).
    report["overrides_applied"] = _apply_config_overrides(env_cfg, rl_cfg, config)
    env = None
    try:
        env = ManagerBasedRlEnv(cfg=env_cfg, device=device)
        obs, _ = env.reset()
        action_dim = env.action_manager.total_action_dim
        action = torch.zeros((env.num_envs, action_dim), device=device)
        _step = env.step(action)
        report.update({
            "status": "smoke_passed",
            "device": device,
            "num_envs": env.num_envs,
            "observation_groups": list(obs.keys()),
            "observation_dimensions": {name: list(value.shape[1:]) for name, value in obs.items()},
            "action_dim": action_dim,
            "recipe": recipe_report,
            "generic_task": config.get("generic_task_diagnostics"),
        })
        if config.get("mode") == "train":
            started = time.time()
            from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
            rl_cfg.max_iterations = max(1, int(config.get("max_iterations", 1)))
            rl_cfg.num_steps_per_env = max(4, int(config.get("num_steps", rl_cfg.num_steps_per_env)))
            rl_cfg.experiment_name = str(config.get("experiment_name", "legged_studio_native"))
            # Keep the isolated worker offline by default. Package extensions
            # may carry optional writers; the control plane uses TensorBoard.
            rl_cfg.logger = str(config.get("logger", "tensorboard"))
            wrapped = RslRlVecEnvWrapper(env, clip_actions=rl_cfg.clip_actions)
            runner_type = load_runner_cls(task_id) or MjlabOnPolicyRunner

            def _checkpoint_metadata(r, _rl_cfg=rl_cfg, _cp=contract_path):
                joint_names = list(getattr(r.env.unwrapped.scene["robot"], "joint_names", []) or [])
                if not joint_names and _cp:
                    from contracts.contract_legacy_v2 import ContractLegacyV2
                    loaded = ContractLegacyV2.from_json_file(str(_cp))
                    joint_names = [joint.name for joint in loaded.joints.actuated_joints]
                return build_deploy_metadata(r.env.unwrapped, _rl_cfg, joint_names)

            runner_type = wrap_runner_with_checkpoint_export(runner_type, _checkpoint_metadata)
            runner = runner_type(wrapped, asdict(rl_cfg), str(output), device)

            # Resume-from-checkpoint (Feature 13): when the config carries a
            # resume_from path, load the weights (and optimizer) from that .pt
            # so training continues instead of starting from scratch. The
            # starting iteration is inferred from the filename model_<iter>.pt
            # so the remaining budget is honoured.
            resume_from = config.get("resume_from")
            resume_iteration = 0
            if resume_from:
                resume_path = Path(str(resume_from)).resolve()
                if not resume_path.exists():
                    raise FileNotFoundError(f"resume checkpoint not found: {resume_path}")
                try:
                    runner.load(str(resume_path), load_cfg={"actor": True, "optimizer": True}, strict=True, map_location=device)
                    report["resume_from"] = str(resume_path)
                except Exception as exc:
                    raise RuntimeError(f"resume checkpoint load failed: {exc}") from exc
                import re as _re
                m = _re.search(r"model_(\d+)\.pt$", resume_path.name)
                if m:
                    resume_iteration = int(m.group(1))
                    report["resume_iteration"] = resume_iteration

            target_iters = max(1, int(config.get("max_iterations", 1)))
            remaining = max(1, target_iters - resume_iteration)
            rl_cfg.max_iterations = remaining
            runner.learn(num_learning_iterations=remaining, init_at_random_ep_len=True)
            report["status"] = "train_completed"
            report["resumed"] = bool(resume_from)
            report["total_iterations_effective"] = resume_iteration + remaining
            # 课程阶段快照（⑰）：训练结束时的 per-term 课程状态
            try:
                report["curriculum_final"] = collect_curriculum_snapshot(env)
            except Exception as exc:
                report["curriculum_final_error"] = f"{type(exc).__name__}: {exc}"
            report["max_iterations"] = rl_cfg.max_iterations
            report["checkpoint_dir"] = str(output)
            model_path = output / f"model_{rl_cfg.max_iterations - 1}.pt"
            if not model_path.exists():
                candidates = sorted(output.glob("model_*.pt"))
                model_path = candidates[-1] if candidates else model_path
            if model_path.exists() and not (output / "model_final.pt").exists():
                shutil.copy2(model_path, output / "model_final.pt")
            if model_path.exists() and contract_path:
                from contracts.policy_artifact import TrainingMetrics, create_artifact_from_training
                from contracts.contract_legacy_v2 import ContractLegacyV2
                contract = ContractLegacyV2.from_json_file(str(contract_path))
                logical_task = str(config.get("task_name", task_id)).lower().replace(" ", "_").replace("-", "_")
                artifact = create_artifact_from_training(
                    contract=contract,
                    task_name=logical_task,
                    algorithm=str(config.get("algorithm", "PPO")),
                    model_path=str(model_path.resolve()),
                    metrics=TrainingMetrics(
                        iterations=rl_cfg.max_iterations,
                        episodes=env.num_envs * rl_cfg.max_iterations,
                        success_rate=0.0,
                        avg_reward=0.0,
                        final_reward=0.0,
                        training_duration_seconds=time.time() - started,
                    ),
                    algorithm_config=asdict(rl_cfg),
                    obs_normalizer={"mean": [], "std": []},
                    mjlab_version="1.6.0-native",
                    tags=["native_mjlab", contract.robot_id],
                )
                artifact.to_json_file(str(output / "artifact.json"))
                report["artifact_id"] = artifact.artifact_id
            # 训练完成即导出（⑤）：ONNX + 部署元数据随 checkpoint 一起产出
            if model_path.exists():
                try:
                    export_runner_policy_onnx(
                        report=report,
                        env=env,
                        runner=runner,
                        wrapped=wrapped,
                        rl_cfg=rl_cfg,
                        output=output,
                        device=device,
                        contract=locals().get("contract"),
                        contract_path=contract_path,
                    )
                except Exception as exc:  # 导出失败不影响训练产物
                    report["onnx_export_error"] = f"{type(exc).__name__}: {exc}"
                    print(f"[native_worker] onnx export failed: {exc}")
        elif config.get("mode") == "evaluate":
            from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
            checkpoint = Path(str(config.get("checkpoint", ""))).resolve()
            if not checkpoint.exists():
                raise FileNotFoundError(f"native checkpoint not found: {checkpoint}")
            if profile_bundle is None:
                rl_cfg = load_rl_cfg(task_id)
            rl_cfg.logger = "tensorboard"
            wrapped = RslRlVecEnvWrapper(env, clip_actions=rl_cfg.clip_actions)
            runner_type = load_runner_cls(task_id) or MjlabOnPolicyRunner
            runner = runner_type(wrapped, asdict(rl_cfg), str(output), device)
            runner.load(str(checkpoint), load_cfg={"actor": True}, strict=True, map_location=device)
            policy = runner.get_inference_policy(device=device)
            episodes = max(1, int(config.get("episodes", 1)))
            max_steps = max(1, int(config.get("max_steps", 500)))
            episode_rewards = []
            with torch.no_grad():
                for _ in range(episodes):
                    obs, _ = wrapped.reset()
                    total = 0.0
                    for _step_index in range(max_steps):
                        action = policy(obs)
                        obs, reward, dones, _extras = wrapped.step(action)
                        total += float(reward.mean().item())
                        if bool(dones.any().item()):
                            break
                    episode_rewards.append(total)
            report.update({"status": "evaluate_completed", "episodes": episodes, "avg_reward": sum(episode_rewards) / len(episode_rewards), "evaluated_env": "native_mjlab"})
            _write(output / "evaluation.json", report)
        elif config.get("mode") == "navigation":
            from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
            checkpoint = Path(str(config.get("checkpoint", ""))).resolve()
            if not checkpoint.exists():
                raise FileNotFoundError(f"native checkpoint not found: {checkpoint}")
            if profile_bundle is None:
                rl_cfg = load_rl_cfg(task_id)
            rl_cfg.logger = "tensorboard"
            wrapped = RslRlVecEnvWrapper(env, clip_actions=rl_cfg.clip_actions)
            runner_type = load_runner_cls(task_id) or MjlabOnPolicyRunner
            runner = runner_type(wrapped, asdict(rl_cfg), str(output), device)
            runner.load(str(checkpoint), load_cfg={"actor": True}, strict=True, map_location=device)
            policy = runner.get_inference_policy(device=device)
            route = config.get("waypoints") or [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]]
            tolerance = float(config.get("waypoint_tolerance", 0.35))
            max_steps = max(1, int(config.get("max_steps", 500)))
            obstacles = config.get("obstacles") or []
            # 感知-决策闭环（Feature 1）：当提供了地图障碍时，启用反应式避障控制器，
            # 在 A* 规划路径的航点跟踪之上叠加势场斥力，使机器人实时对世界障碍做出反应，
            # 而不是开环地沿预设航点指令行走。控制器为纯 Python 实现，不含 torch/mjlab。
            use_avoidance = bool(obstacles) and bool(config.get("use_avoidance", True))
            if use_avoidance:
                from adapters.mjlab.nav_avoidance import AvoidanceConfig, compute_avoidance_command
            avoidance_cfg = AvoidanceConfig(**{
                key: value for key, value in (config.get("avoidance_config") or {}).items()
                if key in AvoidanceConfig.__annotations__
            }) if use_avoidance else None
            term = env.command_manager.get_term("twist")
            completions = []
            tracking_errors = []
            stability_flags = []
            collision_flags = []
            avoidance_active_flags = []
            nearest_distances = []
            with torch.no_grad():
                for _ in range(max(1, int(config.get("episodes", 1)))):
                    obs, _ = wrapped.reset()
                    waypoint_index = 0
                    episode_track_error = 0.0
                    episode_steps = 0
                    early_stop = False
                    episode_avoid_active = False
                    episode_min_nearest = float("inf")
                    for _step_index in range(max_steps):
                        position = env.scene["robot"].data.root_link_pos_w[0, :2]
                        while waypoint_index < len(route):
                            initial_target = torch.as_tensor(route[waypoint_index], device=device, dtype=position.dtype)
                            if float(torch.linalg.norm(position - initial_target).item()) > tolerance:
                                break
                            waypoint_index += 1
                        if waypoint_index >= len(route):
                            break
                        target = torch.as_tensor(route[min(waypoint_index, len(route) - 1)], device=device, dtype=position.dtype)
                        delta = target - position
                        episode_track_error += float(torch.linalg.norm(position - target).item())
                        episode_steps += 1
                        if use_avoidance:
                            avoidance = compute_avoidance_command(
                                (float(position[0]), float(position[1])),
                                (float(target[0]), float(target[1])),
                                [tuple(o[:4]) for o in obstacles],
                                avoidance_cfg,
                            )
                            cmd = avoidance["command"]
                            if avoidance["avoidance_active"]:
                                episode_avoid_active = True
                            nearest = avoidance["nearest_obstacle_distance"]
                            if nearest is not None and nearest < episode_min_nearest:
                                episode_min_nearest = nearest
                            move_x, move_y = cmd[0], cmd[1]
                        else:
                            move_x = float(torch.clamp(delta[0], -1.0, 1.0))
                            move_y = float(torch.clamp(delta[1], -1.0, 1.0))
                        term.command[:] = torch.tensor((move_x, move_y, 0.0), device=device)
                        action = policy(obs)
                        obs, _reward, dones, _extras = wrapped.step(action)
                        position = env.scene["robot"].data.root_link_pos_w[0, :2]
                        if waypoint_index < len(route) and float(torch.linalg.norm(position - target).item()) <= tolerance:
                            waypoint_index += 1
                        if bool(dones.any().item()):
                            early_stop = True
                            break
                        if waypoint_index >= len(route):
                            break
                    completions.append(waypoint_index / len(route))
                    tracking_errors.append(episode_track_error / max(1, episode_steps))
                    stability_flags.append(1.0 if (waypoint_index >= len(route) and not early_stop) else 0.0)
                    collision_flags.append(1.0 if early_stop else 0.0)
                    avoidance_active_flags.append(1.0 if episode_avoid_active else 0.0)
                    if math.isfinite(episode_min_nearest):
                        nearest_distances.append(episode_min_nearest)
            report.update({
                "status": "navigation_completed",
                "route_completion": sum(completions) / len(completions),
                "mean_tracking_error": sum(tracking_errors) / len(tracking_errors),
                "stability_score": sum(stability_flags) / len(stability_flags),
                "collision_count": sum(collision_flags),
                "waypoints": route,
                "obstacles": obstacles,
                "use_avoidance": use_avoidance,
                "evaluated_env": "native_mjlab_navigation",
            })
            if use_avoidance:
                report["avoidance_engagement"] = round(sum(avoidance_active_flags) / len(avoidance_active_flags), 4)
                report["min_obstacle_distance_m"] = round(min(nearest_distances), 4) if nearest_distances else None
                report["avoidance_config"] = avoidance_cfg.as_dict() if avoidance_cfg else None
            _write(output / "navigation.json", report)
        _write(output / "native_preflight.json", report)
        _write(output / "status.json", {"status": "completed", **report})
        return 0
    finally:
        if env is not None:
            env.close()


def _probe_policy_entry(package_root: Path, config: dict) -> dict:
    """开环探针用的策略声明条目（B25，2026-09-16）。

    config["policy"] 在训练链上从不写入（training_config.json 无此键，整个仓库只有
    探针这里消费）——此前恒传空 dict，而包级 policy_contract 只在 g1/go2w/zex-w/tron1
    声明了 obs_dim/action_dim；microduck/go1/go2 等包的维度只在 ``policies[]`` 各条目
    顶层，条目缺位让 action_dim 落 0 → ``run_probe`` 拿空动作数组按关节序取 ``raw[0]``
    → 裸 IndexError，监控页每次冒烟都带脏字段。条目缺位时改从包内声明解析：
    优先 ``training_ref.profile`` 对上当前训练 profile 的条目，否则第一条
    （与验收器 CLI ``--probe`` 同口径）。
    """
    policy_entry = config.get("policy")
    if isinstance(policy_entry, dict) and policy_entry:
        return policy_entry
    sim_cfg = json.loads((package_root / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
    _ensure_on_path(Path(__file__).resolve().parent)
    from policy_acceptance import resolve_probe_policy_entry

    return resolve_probe_policy_entry(sim_cfg, str(config.get("profile_id") or ""))


def main() -> int:
    parser = argparse.ArgumentParser(description="Legged Studio native MJLab worker")
    parser.add_argument("--source")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output")
    parser.add_argument("--extension-root")
    parser.add_argument("--contract")
    parser.add_argument(
        "--dump-schema",
        action="store_true",
        help="build the profile's full env/runner config tree and exit",
    )
    parser.add_argument("--schema-output", help="write the schema JSON to this file (bypasses stdout pipe limits)")
    args = parser.parse_args()
    try:
        # PowerShell's ``-Encoding utf8`` emits a BOM on Windows; accepting
        # utf-8-sig keeps CLI and desktop launches interoperable.
        config = json.loads(Path(args.config).read_text(encoding="utf-8-sig"))
        if args.contract:
            config["contract_path"] = str(Path(args.contract).resolve())
        if args.dump_schema:
            # Must stay ahead of any torch/mjlab import: the schema dump only
            # needs the package source tree. Large trees can hit Windows pipe
            # limits when printed (Errno 22 mid-write), so prefer writing to
            # --schema-output and keep stdout printing as a CLI fallback.
            try:
                schema = _dump_profile_schema(config)
            except Exception as exc:
                print(f"[native-worker] schema dump failed: {exc}", file=sys.stderr)
                traceback.print_exc()
                return 6
            if args.schema_output:
                Path(args.schema_output).write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
            else:
                sys.stdout.write(json.dumps(schema, ensure_ascii=False))
                sys.stdout.flush()
            return 0
        if not args.source or not args.output:
            parser.error("--source and --output are required unless --dump-schema is used")
        output = Path(args.output)
        extension = Path(args.extension_root).resolve() if args.extension_root else None
        return run(config, Path(args.source).resolve(), output, extension)
    except Exception as exc:
        output = Path(args.output) if args.output else Path.cwd() / "native_worker_output"
        _write(output / "status.json", {"status": "failed", "error": str(exc), "traceback": traceback.format_exc()})
        print(f"[native-worker] failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
