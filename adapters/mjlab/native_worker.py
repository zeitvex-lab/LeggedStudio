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
import importlib
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


def action_joint_order(env, contract=None) -> list[str]:
    """**动作接口序**（策略输入/输出的关节顺序），按动作项顺序拼接解析后的目标名。

    为什么不能用实体序：`scene["robot"].joint_names` 是 MJCF 的关节序，而策略的动作向量是
    **动作项**拼出来的（如轮足 = `joint_pos` 腿 + `wheel_vel` 轮，腿先轮后）。两者在轮足上不一致
    （m20 的 MJCF 是逐腿混排），拿实体序盖章会让产物元数据与策略实际动作序互相错标
    （2026-09-24 移植核对 F2 的根因）。顺序取不到时回退契约 `action.joint_order`，再回退实体序。
    """

    names: list[str] = []
    manager = getattr(env, "action_manager", None)
    for term_name in (getattr(manager, "active_terms", None) or []):
        try:
            term = manager.get_term(term_name)
        except Exception:  # noqa: BLE001
            continue
        for item in getattr(term, "target_names", None) or []:
            if isinstance(item, str) and item not in names:
                names.append(item)
    if names:
        return names
    if contract is not None:
        return [joint.name for joint in contract.joints.actuated_joints]
    return list(getattr(env.scene["robot"], "joint_names", []) or [])

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
        # _scale 形状是 (num_envs, num_joints)——整只 flatten 会把 12 关节 × N 环境
        # 串成 N 倍长（64 envs ⇒ 768 值），metadata 的 action_scale 就废了
        # （2026-09-20 实测 64×800 产物盖了 768 个值）。逐关节 scale 对所有环境
        # 相同，取第一行（一维/标量形状原样回落）。
        if getattr(scale, "ndim", 1) == 2:
            scale = scale[0]
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

    # 动作接口序（不是实体序）——见 action_joint_order 的说明
    joint_names = action_joint_order(env, contract)

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


def wrap_runner_with_checkpoint_export(runner_cls, metadata_builder, hooks=None):
    """包一层 runner：每次 save checkpoint 时同步导出 onnx 并盖章部署元数据。

    仅对 MjlabOnPolicyRunner 及其子类生效；其他 runner 原样返回。
    metadata_builder(runner) 返回元数据 dict；导出失败只打印，不中断训练。
    hooks（Phase 3 插件化，2026-10-03）：``on_checkpoint`` 切点位——每次 save 后
    同步执行（adapters/mjlab/training_hooks.py::run_hooks，fail-soft 带超时预算）；
    档案/config 的 ``hooks.on_checkpoint`` 声明消费者（首个 = tools.trend_probe_hook）。
    """
    try:
        from mjlab.rl import MjlabOnPolicyRunner
    except ImportError:
        return runner_cls
    if not (isinstance(runner_cls, type) and issubclass(runner_cls, MjlabOnPolicyRunner)):
        return runner_cls

    class ExportingRunner(runner_cls):  # type: ignore[misc,valid-type]
        _deploy_metadata_builder = staticmethod(metadata_builder)
        _hooks = list(hooks or [])

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
            if self._hooks:
                try:
                    from adapters.mjlab.training_hooks import run_hooks

                    run_hooks("on_checkpoint", self._hooks, {
                        "run_dir": str(Path(path).parent.parent),
                        "checkpoint_path": str(path),
                        "iteration": getattr(self, "current_learning_iteration", 0),
                        "report": {k: self.report.get(k) for k in self.report} if hasattr(self, "report") else {},
                    })
                except Exception as exc:
                    print(f"[native_worker] hooks dispatch failed: {exc}")

    return ExportingRunner


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
    from adapters.mjlab import task_config
    register = task_config._import_entrypoint(str(entrypoint))
    result = task_config._call_factory(register)
    return result if isinstance(result, dict) else {"result": result}


def _dump_profile_schema(config: dict) -> dict:
    """Build the full config-tree schema for a resolved profile bundle."""
    if "training_config" in config:
        from adapters.mjlab.config_introspect import build_training_preview
        _load_package_extension(config["training_config"].get("robot_package") or {})
        return build_training_preview(config["training_config"], config["contract"])
    package_root = Path(str(config.get("package_root", ""))).resolve()
    source_root = Path(str(config.get("source_root", "training/source")))
    if not source_root.is_absolute():
        source_root = package_root / source_root
    from adapters.mjlab.config_introspect import build_profile_schema

    return build_profile_schema(
        source_root, config.get("entrypoints") or {}, config.get("profile_id"),
        profile=config.get("profile"), package={"package_root": str(package_root)},
    )


def run(config: dict, source: Path, output: Path, extension_root: Path | None = None) -> int:
    _write(output / "status.json", {"status": "running", "backend": "native_mjlab"})
    project_root = Path(__file__).resolve().parents[2]
    _ensure_on_path(project_root)
    from adapters.mjlab import task_config
    from adapters.mjlab.runtime_compat import evaluate_package_runtime
    _ensure_on_path(source / "src")
    package = config.get("robot_package") or {}
    profile = task_config.find_training_profile(package, config.get("profile_id"))
    if profile:
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
        profile_bundle = task_config.load_profile_bundle(profile, package, config)
        from mjlab.tasks.registry import register_mjlab_task
        profile_task_id = str(config.get("native_task_id") or f"LeggedStudio-{profile.get('profile_id')}")
        runner_cls = None
        runner_entrypoint = (profile.get("entrypoints") or {}).get("runner_class")
        if runner_entrypoint:
            runner_cls = task_config._import_entrypoint(runner_entrypoint)
        register_mjlab_task(profile_task_id, profile_bundle[0], profile_bundle[1], profile_bundle[2], runner_cls=runner_cls)
        config["native_task_id"] = profile_task_id
        config["profile_task"] = True
    # **族级技能通用装配**（无档案时的第三支路）：这台机型的形态属于某个族、请求的任务又在
    # 该族的装配表（`skill_catalog`）里 ⇒ 从契约 + 标准 MJCF 直接装配 —— 新机型（含导入）
    # 不必写任何机型专属 Python 就能训族级技能。装配**不适用**时返回 None，流程原样往下走。
    if profile_bundle is None:
        from adapters.mjlab.family_skill_builder import try_build_family_skill_from_package

        assembly = try_build_family_skill_from_package(
            package.get("package_root") or Path(config.get("source_root", ".")).parent,
            str(config.get("task_name") or ""),
            contract_path=contract_path,
        )
        if assembly is not None:
            from mjlab.tasks.registry import register_mjlab_task

            family_task_id = str(
                config.get("native_task_id") or f"LeggedStudio-{assembly.family_id}-{assembly.task_name}"
            )
            register_mjlab_task(
                family_task_id, assembly.env_cfg, assembly.play_cfg, assembly.runner_cfg
            )
            config["native_task_id"] = family_task_id
            config["family_skill_task"] = True
            config["family_skill_diagnostics"] = assembly.diagnostics
            # 平台下发的迭代数对族级技能也要生效（配置里给了就以它为准；没给就用族级 runner 的预算）。
            # 档案路径的 runner 预算由档案自己声明，故这条只作用于通用装配出来的任务。
            if config.get("max_iterations"):
                assembly.runner_cfg.max_iterations = int(config["max_iterations"])
    if config.get("generic_task", True) and profile_bundle is None and not config.get("family_skill_task"):
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
    assembled = task_config.assemble_training_config(env_cfg, rl_cfg, config, profile=profile)
    env_cfg, rl_cfg = assembled.environment, assembled.runner
    report.update(assembled.report)
    recipe_report = assembled.report["recipe"]
    _write(output / "effective-config.json", assembled.snapshot)
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
            wrapped = RslRlVecEnvWrapper(env, clip_actions=rl_cfg.clip_actions)
            runner_type = load_runner_cls(task_id) or MjlabOnPolicyRunner

            def _checkpoint_metadata(r, _rl_cfg=rl_cfg, _cp=contract_path):
                _contract = None
                if _cp:
                    from contracts.contract_legacy_v2 import ContractLegacyV2
                    _contract = ContractLegacyV2.from_json_file(str(_cp))
                joint_names = action_joint_order(r.env.unwrapped, _contract)
                return build_deploy_metadata(r.env.unwrapped, _rl_cfg, joint_names)

            from adapters.mjlab.training_hooks import load_hooks

            _hooks = load_hooks(config, "on_checkpoint")
            runner_type = wrap_runner_with_checkpoint_export(runner_type, _checkpoint_metadata, hooks=_hooks)
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

            target_iters = int(rl_cfg.max_iterations)
            remaining = max(1, target_iters - resume_iteration)
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
