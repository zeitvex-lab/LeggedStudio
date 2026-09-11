from legged_gym.utils.helpers import class_to_dict

from .environment import register_task
from .runner import EERunner


class PPOEEPlugin:
    method_id = "ppo_ee"

    def register_task(self, task_registry, requested_task):
        if requested_task not in ("a1", "a1_ee"):
            raise ValueError("ppo_ee currently supports only the Unitree A1 task")
        return register_task(task_registry)

    def make_runner(self, task_registry, env, task, runtime_args, *, log_dir, checkpoint):
        _, train_cfg = task_registry.get_cfgs(task)
        runner = EERunner(env, class_to_dict(train_cfg), log_dir=log_dir, device=env.device)
        if checkpoint is not None:
            runner.load(str(checkpoint))
        return runner, train_cfg


PLUGIN = PPOEEPlugin()
