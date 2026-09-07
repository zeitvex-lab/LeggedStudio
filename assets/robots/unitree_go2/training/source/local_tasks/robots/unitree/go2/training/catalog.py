"""Go2 bindings to reusable learning profiles."""

from local_tasks.core import Catalog, TrainingSpec


def _profile(
  profile_id: str,
  algorithm: str = "rsl_rl.algorithms.ppo:PPO",
  actor: str = "rsl_rl.models.mlp_model:MLPModel",
  critic: str = "rsl_rl.models.mlp_model:MLPModel",
  storage: str = "rsl_rl.storage.rollout_storage:RolloutStorage",
  runner: str = "local_tasks.robots.unitree.go2.training.runner:VelocityOnPolicyRunner",
  auxiliary: tuple[str, ...] = (),
  groups: tuple[str, ...] = ("actor", "critic"),
) -> TrainingSpec:
  return TrainingSpec(
    profile_id=profile_id,
    algorithm=algorithm,
    actor_model=actor,
    critic_model=critic,
    storage=storage,
    runner=runner,
    optimizer="torch.optim:Adam",
    auxiliary_losses=auxiliary,
    required_observation_groups=groups,
    exporter="mjlab.rl.runner:MjlabOnPolicyRunner.export_policy_to_onnx",
  )


GO2_TRAINING_PROFILES = Catalog(
  (
    _profile("ppo"),
    _profile(
      "dreamwaq",
      algorithm=("local_tasks.learning.algorithms:DreamWaQPPO"),
      actor="local_tasks.learning.models:DreamWaQActorModel",
      storage="local_tasks.learning.storage:Go2RolloutStorage",
      auxiliary=("velocity-supervision", "vae-reconstruction", "vae-kl"),
      groups=("actor", "critic", "history"),
    ),
    _profile(
      "amp-dreamwaq",
      algorithm=("local_tasks.learning.algorithms:AmpDreamWaQPPO"),
      actor="local_tasks.learning.models:DreamWaQActorModel",
      storage="local_tasks.learning.storage:Go2RolloutStorage",
      auxiliary=("amp", "velocity-supervision", "vae-reconstruction", "vae-kl"),
      groups=("actor", "critic", "history", "amp"),
    ),
    _profile(
      "cts",
      algorithm="local_tasks.learning.algorithms:CtsPPO",
      actor="local_tasks.learning.models:CtsActorModel",
      critic="local_tasks.learning.models:CtsCriticModel",
      storage="local_tasks.learning.storage:Go2RolloutStorage",
      auxiliary=("teacher-student-latent",),
      groups=("actor", "critic", "history"),
    ),
    _profile(
      "amp-cts",
      algorithm="local_tasks.learning.algorithms:AmpCtsPPO",
      actor="local_tasks.learning.models:CtsActorModel",
      critic="local_tasks.learning.models:CtsCriticModel",
      storage="local_tasks.learning.storage:Go2RolloutStorage",
      auxiliary=("amp", "teacher-student-latent"),
      groups=("actor", "critic", "history", "amp"),
    ),
    _profile(
      "ts-teacher",
      algorithm=("local_tasks.learning.algorithms:Go2AuxiliaryPPO"),
      actor="local_tasks.learning.models:TeacherActorModel",
      storage="local_tasks.learning.storage:Go2RolloutStorage",
      auxiliary=("terrain-encoder", "privileged-encoder"),
      groups=("actor", "critic", "terrain", "privileged"),
    ),
    _profile(
      "amp-ts-teacher",
      algorithm="local_tasks.learning.algorithms:AmpPPO",
      actor="local_tasks.learning.models:TeacherActorModel",
      storage="local_tasks.learning.storage:Go2RolloutStorage",
      auxiliary=("amp", "terrain-encoder", "privileged-encoder"),
      groups=("actor", "critic", "terrain", "privileged", "amp"),
    ),
    _profile(
      "ts-student",
      algorithm=("local_tasks.learning.algorithms:TeacherStudentPPO"),
      actor="local_tasks.learning.models:StudentActorModel",
      storage="local_tasks.learning.storage:Go2RolloutStorage",
      runner=("local_tasks.robots.unitree.go2.training.runner:VelocityDistillationRunner"),
      auxiliary=("teacher-action-distillation",),
      groups=("actor", "critic", "history"),
    ),
  ),
  id_of=lambda profile: profile.profile_id,
)
