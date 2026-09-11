from legged_gym.utils.helpers import class_to_dict

from .environment import register_task
from .runner import CTSRunner


class CTSPlugin:
    method_id = "cts"

    def register_task(self, task_registry, requested_task):
        if requested_task not in ("a1", "a1_cts"):
            raise ValueError("cts currently supports only the Unitree A1 task")
        return register_task(task_registry)

    def make_runner(self, task_registry, env, task, runtime_args, *, log_dir, checkpoint):
        del runtime_args
        _, cfg = task_registry.get_cfgs(task)
        runner = CTSRunner(env, class_to_dict(cfg), log_dir=log_dir, device=env.device)
        if checkpoint is not None:
            runner.load(str(checkpoint))
        return runner, cfg


PLUGIN = CTSPlugin()
