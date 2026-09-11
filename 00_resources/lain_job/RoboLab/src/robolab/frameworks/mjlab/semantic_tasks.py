"""Generic MJLab velocity task adapters driven by RoboLab profiles."""

from __future__ import annotations

from robolab.robots import PROFILES, mjlab_asset


def make_semantic_env_cfg(robot_id: str, *, play: bool = False):
    """Build a conservative flat-ground MJLab config for a robot profile."""
    import mujoco
    from mjlab.actuator import BuiltinPositionActuatorCfg
    from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
    from mjlab.sensor import ContactMatch, ContactSensorCfg, ObjRef
    from mjlab.sensor.builtin_sensor import BuiltinSensorCfg
    from mjlab.tasks.velocity.velocity_env_cfg import make_velocity_env_cfg

    profile = PROFILES[robot_id]
    source = mjlab_asset(robot_id)

    def spec_fn():
        spec = mujoco.MjSpec.from_file(str(source))
        if source.suffix == ".urdf":
            # MuJoCo's documented importer repairs for vendor URDFs containing
            # zero dummy-link masses or non-physical inertia tensors.
            spec.compiler.balanceinertia = True
            spec.compiler.boundmass = 1e-4
            spec.compiler.boundinertia = 1e-6
            root_body = spec.worldbody.first_body()
            if root_body is not None and not any(
                joint.type == mujoco.mjtJoint.mjJNT_FREE for joint in spec.joints
            ):
                root_body.add_freejoint(name="floating_base")
        for index, actuator in enumerate(spec.actuators):
            actuator.name = f"legacy_{actuator.name or index}"
        return spec

    cfg = make_velocity_env_cfg()
    cfg.scene.entities = {"robot": EntityCfg(
        init_state=EntityCfg.InitialStateCfg(
            pos=(0.0, 0.0, profile.base_height),
            joint_pos=dict(profile.default_joint_pos),
            joint_vel={".*": 0.0},
        ),
        spec_fn=spec_fn,
        articulation=EntityArticulationInfoCfg(actuators=(BuiltinPositionActuatorCfg(
            target_names_expr=profile.joint_order,
            stiffness=min(80.0, max(20.0, profile.effort_limit)),
            damping=1.0,
            effort_limit=profile.effort_limit,
        ),), soft_joint_pos_limit_factor=0.9),
    )}
    cfg.scene.terrain.terrain_type = "plane"
    cfg.scene.terrain.terrain_generator = None
    import re
    feet_pattern = "^(" + "|".join(re.escape(name) for name in profile.resolved_mjlab_contact_bodies) + ")$"
    cfg.scene.sensors = (
        BuiltinSensorCfg(name="semantic_lin_vel", sensor_type="framelinvel", obj=ObjRef(type="body", name=profile.resolved_mjlab_base_body, entity="robot")),
        BuiltinSensorCfg(name="semantic_ang_vel", sensor_type="frameangvel", obj=ObjRef(type="body", name=profile.resolved_mjlab_base_body, entity="robot")),
        ContactSensorCfg(name="feet_ground_contact", primary=ContactMatch(mode="subtree", pattern=feet_pattern, entity="robot"), secondary=ContactMatch(mode="body", pattern="terrain"), fields=("found", "force"), reduce="netforce", num_slots=1, track_air_time=True),
    )
    cfg.curriculum = {}
    # MuJoCo Warp does not support non-zero geom margins with MULTICCD for
    # several vendor XMLs (notably Tron1SF and Go2).  Disabling only this
    # optional flag preserves ordinary contact handling and makes the generic
    # adapter portable; robot-specific tuning may re-enable it after cleanup.
    cfg.sim.mujoco.disableflags = ("multiccd", "nativeccd")
    cfg.sim.nconmax = None
    cfg.viewer.body_name = profile.resolved_mjlab_base_body
    # Native MuJoCo URDF/MJCF imports expose these standard sensor names.
    # Keep the observation contract independent of the source file's optional
    # sensor aliases.
    for group in (cfg.observations["actor"], cfg.observations["critic"]):
        if "base_ang_vel" in group.terms:
            group.terms["base_ang_vel"].params["sensor_name"] = "robot/semantic_ang_vel"
        if "base_lin_vel" in group.terms:
            group.terms["base_lin_vel"].params["sensor_name"] = "robot/semantic_lin_vel"
        for name in ("height_scan", "foot_height", "foot_height_scan", "foot_contact", "foot_contact_forces", "foot_air_time"):
            group.terms.pop(name, None)
    for name in ("air_time", "foot_height", "foot_air_time", "foot_contact", "foot_contact_forces", "foot_slip", "foot_clearance", "foot_swing_height", "soft_landing"):
        cfg.rewards.pop(name, None)
    cfg.rewards.pop("pose", None)
    if play:
        cfg.episode_length_s = int(1e9)
        cfg.observations["actor"].enable_corruption = False
    action = cfg.actions.get("joint_pos")
    if action is not None:
        action.actuator_names = profile.joint_order
        action.preserve_order = True
        action.scale = profile.action_scale
    return cfg


def register_semantic_tasks():
    """Register native-MJCF profiles and report URDF-only profiles."""
    from mjlab.tasks.registry import register_mjlab_task
    from mjlab.tasks.velocity.config.go1.rl_cfg import unitree_go1_ppo_runner_cfg
    from mjlab.tasks.velocity.rl import VelocityOnPolicyRunner

    registered, unavailable = [], []
    for robot_id in PROFILES:
        try:
            env_id = f"RoboLab-Velocity-Flat-{robot_id}"
            rl_cfg = unitree_go1_ppo_runner_cfg()
            rl_cfg.experiment_name = f"{robot_id}_velocity"
            env_cfg = make_semantic_env_cfg(robot_id)
            # Fail registration early when vendor URDF inertias cannot be
            # compiled by MuJoCo; the task list must never advertise a broken
            # training task.
            env_cfg.scene.entities["robot"].spec_fn().compile()
            register_mjlab_task(
                task_id=env_id,
                env_cfg=env_cfg,
                play_env_cfg=make_semantic_env_cfg(robot_id, play=True),
                rl_cfg=rl_cfg,
                runner_cls=VelocityOnPolicyRunner,
            )
            registered.append(env_id)
        except (FileNotFoundError, ValueError, RuntimeError, OSError):
            unavailable.append(robot_id)
    return tuple(registered), tuple(unavailable)


__all__ = ["make_semantic_env_cfg", "register_semantic_tasks"]
