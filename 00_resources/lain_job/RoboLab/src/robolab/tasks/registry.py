"""Backend-neutral task discovery and recipe resolution.

TaskSpec is the single public task contract.  Backend task names remain an
implementation detail and are selected only after framework and method have
been validated.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from robolab.methods.registry import get_method
from robolab.robots import PROFILES, discover_robot_assets


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    display_name: str
    robot_id: str
    backend_tasks: Mapping[str, Mapping[str, str]]
    observation_dim: int | None
    action_dim: int
    models: Mapping[str, str]
    preview_models: Mapping[str, str] = field(default_factory=dict)
    visualization_models: Mapping[str, str] = field(default_factory=dict)
    defaults: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    control_fields: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    aliases: tuple[str, ...] = ()

    @property
    def frameworks(self) -> tuple[str, ...]:
        return tuple(sorted(self.backend_tasks))

    @property
    def methods(self) -> tuple[str, ...]:
        return tuple(sorted({method for methods in self.backend_tasks.values() for method in methods}))

    def backend_task(self, framework: str, method: str) -> str:
        try:
            return self.backend_tasks[framework][method]
        except KeyError as exc:
            raise ValueError(
                f"task {self.task_id!r} does not support {framework}/{method}"
            ) from exc

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["frameworks"] = list(self.frameworks)
        value["methods"] = list(self.methods)
        return value


def _relative(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def _semantic_specs(root: Path) -> list[TaskSpec]:
    assets = discover_robot_assets(root)
    result = []
    for robot_id, profile in PROFILES.items():
        asset = assets.get(robot_id)
        if asset is None:
            continue
        backend_tasks: dict[str, dict[str, str]] = {}
        models: dict[str, str] = {}
        viewers: dict[str, str] = {}
        previews: dict[str, str] = {}
        defaults: dict[str, dict[str, Any]] = {}
        if asset.urdf:
            backend_tasks["isaacgym"] = {"ppo": f"robolab_{robot_id}"}
            models["isaacgym"] = _relative(asset.urdf[0], root)
            defaults["isaacgym"] = {"num_envs": 1024, "max_iterations": 1500, "checkpoint_interval": 300}
        if asset.mjcf or asset.urdf:
            backend_tasks["mjlab"] = {"ppo": f"RoboLab-Velocity-Flat-{robot_id}"}
            models["mjlab"] = _relative((asset.mjcf or asset.urdf)[0], root)
            defaults["mjlab"] = {"num_envs": 1024, "max_iterations": 1500, "checkpoint_interval": 300}
        if asset.mjcf:
            viewer = _relative(asset.mjcf[0], root)
            viewers = {framework: viewer for framework in backend_tasks}
        preview = _relative((asset.urdf or asset.mjcf)[0], root)
        previews = {framework: preview for framework in backend_tasks}
        if not backend_tasks:
            continue
        default_kp = min(80.0, max(20.0, profile.effort_limit))
        result.append(TaskSpec(
            task_id=f"velocity_flat.{robot_id}",
            display_name=f"Flat velocity · {robot_id}",
            robot_id=robot_id,
            backend_tasks=backend_tasks,
            observation_dim=9 + 3 * profile.action_dim,
            action_dim=profile.action_dim,
            models=models,
            preview_models=previews,
            visualization_models=viewers,
            defaults={
                framework: {
                    **values,
                    "seed": 0,
                    "control": {
                        "kp": default_kp,
                        "kd": 1.0,
                        "action_scale": profile.action_scale,
                        "decimation": 4,
                        "target_height": profile.base_height * 0.85,
                    },
                    "joint_order": list(profile.joint_order),
                    "joint_defaults": dict(profile.default_joint_pos),
                }
                for framework, values in defaults.items()
            },
            control_fields={
                framework: ("kp", "kd", "action_scale", "decimation", "target_height")
                for framework in backend_tasks
            },
            aliases=(f"robolab_{robot_id}", f"RoboLab-Velocity-Flat-{robot_id}"),
        ))
    return result


def _legacy_a1_spec(root: Path) -> TaskSpec | None:
    asset = discover_robot_assets(root).get("unitree_a1")
    if asset is None or not asset.urdf:
        return None
    viewer = _relative(asset.mjcf[0], root) if asset.mjcf else ""
    profile = PROFILES["unitree_a1"]
    return TaskSpec(
        task_id="legacy_velocity.unitree_a1",
        display_name="Legacy A1 locomotion (method-specific)",
        robot_id="unitree_a1",
        backend_tasks={"isaacgym": {
            "ppo": "a1",
            "cts": "a1_cts",
            "teacher_student": "a1_teacher_student",
            "dreamwaq": "a1_dreamwaq",
            "ppo_ee": "a1_ee",
        }},
        observation_dim=45,
        action_dim=12,
        models={"isaacgym": _relative(asset.urdf[0], root)},
        preview_models={"isaacgym": _relative(asset.urdf[0], root)},
        visualization_models={"isaacgym": viewer} if viewer else {},
        defaults={"isaacgym": {
            "num_envs": 1024,
            "max_iterations": 1500,
            "checkpoint_interval": 300,
            "seed": 0,
            "control": {"kp": 80.0, "kd": 2.0, "action_scale": 0.25, "decimation": 4, "target_height": 0.32},
            "joint_order": list(profile.joint_order),
            "joint_defaults": dict(profile.default_joint_pos),
        }},
        control_fields={"isaacgym": ("kp", "kd", "action_scale", "decimation", "target_height")},
        aliases=("a1", "a1_cts", "a1_teacher_student", "a1_dreamwaq", "a1_ee"),
    )


def list_task_specs(root: Path | None = None) -> tuple[TaskSpec, ...]:
    repository = (root or Path(__file__).resolve().parents[3]).resolve()
    specs = _semantic_specs(repository)
    legacy = _legacy_a1_spec(repository)
    if legacy is not None:
        specs.append(legacy)
    return tuple(sorted(specs, key=lambda item: item.task_id))


def get_task_spec(task_id: str, *, framework: str | None = None, method: str | None = None, root: Path | None = None) -> TaskSpec:
    candidates = []
    for spec in list_task_specs(root):
        if task_id == spec.task_id or task_id in spec.aliases:
            if framework is not None and framework not in spec.frameworks:
                continue
            if method is not None and method not in spec.methods:
                continue
            candidates.append(spec)
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        available = ", ".join(spec.task_id for spec in list_task_specs(root))
        raise KeyError(f"unknown or incompatible task {task_id!r}; available: {available}")
    raise KeyError(f"ambiguous task alias {task_id!r}; use a canonical task ID")


def resolve_training_recipe(data: Mapping[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    repository = (root or Path(__file__).resolve().parents[3]).resolve()
    framework = str(data.get("framework") or "")
    method = str(data.get("method") or "")
    if framework not in {"isaacgym", "mjlab"}:
        raise ValueError("framework must be isaacgym or mjlab")
    method_spec = get_method(method)
    if framework not in method_spec.frameworks:
        raise ValueError(f"method {method!r} does not support framework {framework!r}")
    spec = get_task_spec(str(data.get("task") or ""), framework=framework, method=method, root=repository)
    backend_task = spec.backend_task(framework, method)
    robot = str(data.get("robot") or spec.robot_id)
    if robot != spec.robot_id:
        raise ValueError(f"task {spec.task_id!r} requires robot {spec.robot_id!r}, got {robot!r}")
    expected_model = spec.models[framework]
    model = str(data.get("model") or expected_model)
    model_path = Path(model).expanduser()
    if not model_path.is_absolute():
        model_path = repository / model_path
    expected_path = repository / expected_model
    if model_path.resolve() != expected_path.resolve():
        raise ValueError(
            f"task {spec.task_id!r} trains the registered model {expected_model!r}; "
            f"the selected/uploaded model {model!r} is inspection-only until it is registered as a robot task"
        )
    defaults = dict(spec.defaults[framework])
    control_defaults = dict(defaults.get("control", {}))
    requested_control = dict(data.get("control") or {})
    allowed_control = set(spec.control_fields.get(framework, ()))
    unknown_control = sorted(set(requested_control) - allowed_control)
    if unknown_control:
        raise ValueError(f"unsupported control fields for {spec.task_id}: {', '.join(unknown_control)}")
    control = {name: control_defaults[name] for name in allowed_control if name in control_defaults}
    control.update(requested_control)
    for name in ("kp", "kd", "action_scale", "target_height"):
        if name in control and float(control[name]) <= 0:
            raise ValueError(f"control.{name} must be positive")
    control["decimation"] = int(control["decimation"])
    if control["decimation"] < 1:
        raise ValueError("control.decimation must be positive")
    num_envs = int(data.get("num_envs", defaults["num_envs"]))
    max_iterations = int(data.get("max_iterations", data.get("iterations", defaults["max_iterations"])))
    checkpoint_interval = int(data.get("checkpoint_interval", defaults.get("checkpoint_interval", 300)))
    seed = int(data.get("seed", defaults["seed"]))
    if num_envs < 1 or max_iterations < 1 or checkpoint_interval < 1:
        raise ValueError("num_envs, max_iterations and checkpoint_interval must be positive")
    if checkpoint_interval > max_iterations:
        raise ValueError("checkpoint_interval cannot exceed max_iterations")
    joint_order = tuple(defaults.get("joint_order", ()))
    mapping = dict(data.get("mapping") or {name: name for name in joint_order})
    if mapping and any(mapping.get(name) != name for name in joint_order):
        raise ValueError("training joint remapping is not implemented; the selected task requires identity mapping")
    joints = dict(data.get("joints") or {})
    unknown_joints = sorted(set(joints) - set(joint_order))
    if unknown_joints:
        raise ValueError(f"recipe contains joints outside the task contract: {', '.join(unknown_joints[:8])}")
    joint_defaults = dict(defaults.get("joint_defaults", {}))
    use_standing_pose = bool(data.get("use_standing_pose", False))
    if not use_standing_pose:
        joint_defaults = {}
    joint_kp: dict[str, float] = {}
    joint_kd: dict[str, float] = {}
    joint_scales: set[float] = set()
    for name, values in joints.items():
        values = dict(values)
        if use_standing_pose and "default" in values:
            joint_defaults[name] = float(values["default"])
        if "kp" in values:
            joint_kp[name] = float(values["kp"])
        if "kd" in values:
            joint_kd[name] = float(values["kd"])
        if "action_scale" in values:
            joint_scales.add(float(values["action_scale"]))
    if len(joint_scales) > 1:
        raise ValueError("per-joint action_scale is not supported; use one uniform action scale")
    if joint_scales:
        control["action_scale"] = joint_scales.pop()
    if framework == "mjlab" and (len(set(joint_kp.values())) > 1 or len(set(joint_kd.values())) > 1):
        raise ValueError("MJLab currently requires uniform per-joint KP/KD values")
    if framework == "mjlab" and joint_kp:
        control["kp"] = next(iter(joint_kp.values()))
    if framework == "mjlab" and joint_kd:
        control["kd"] = next(iter(joint_kd.values()))
    run_dir = data.get("run_dir")
    if not run_dir:
        raise ValueError("run_dir must be explicit after run allocation")
    # A checkpoint shown by the UI is informational.  Resuming must be an
    # explicit recipe field so a fresh run can never accidentally continue the
    # latest run in a shared directory.
    resume_from = data.get("resume_from") or None
    if resume_from:
        checkpoint = Path(str(resume_from)).expanduser()
        if not checkpoint.is_absolute():
            checkpoint = repository / checkpoint
        if not checkpoint.is_file():
            raise FileNotFoundError(f"resume checkpoint does not exist: {checkpoint}")
    return {
        "schema_version": 2,
        "task": spec.task_id,
        "backend_task": backend_task,
        "framework": framework,
        "method": method,
        "robot": robot,
        "model": expected_model,
        "visualization_model": spec.visualization_models.get(framework),
        "observation_dim": spec.observation_dim,
        "action_dim": spec.action_dim,
        "num_envs": num_envs,
        "max_iterations": max_iterations,
        "checkpoint_interval": checkpoint_interval,
        "device": str(data.get("device") or "cuda:0"),
        "seed": seed,
        "run_dir": str(run_dir),
        "resume_from": str(resume_from) if resume_from else None,
        "control": control,
        "joint_order": list(joint_order),
        "joint_defaults": joint_defaults,
        "use_standing_pose": use_standing_pose,
        "joint_kp": joint_kp,
        "joint_kd": joint_kd,
        "joints": joints,
        "mapping": mapping,
        "robot_profile": data.get("robot_profile"),
        "applied_fields": ["model", "control", "joint_defaults", "joint_kp", "joint_kd", "mapping"],
    }


__all__ = ["TaskSpec", "get_task_spec", "list_task_specs", "resolve_training_recipe"]
