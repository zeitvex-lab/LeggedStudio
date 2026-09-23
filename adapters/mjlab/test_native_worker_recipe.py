import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace

from adapters.mjlab.task_config import load_profile_bundle, apply_training_recipe, assemble_training_config


def test_smoke_final_override_bounds():
    from dataclasses import make_dataclass
    import pytest
    from backend.training.smoke_gate import SMOKE_MAX_ENVS, SMOKE_MAX_ITERS

    Scene = make_dataclass("SmokeScene", [("num_envs", int)])
    Env = make_dataclass("SmokeEnv", [("scene", Scene)])
    Runner = make_dataclass("SmokeRunner", [("max_iterations", int), ("save_interval", int)])
    env, runner = Env(Scene(1)), Runner(1, 1)
    config = {"smoke_preset": True, "num_envs": 1, "max_iterations": 1, "save_interval": 1}
    for path, value in (("runner.max_iterations", 100000),
                        ("runner.max_iterations", SMOKE_MAX_ITERS + 1),
                        ("environment.scene.num_envs", SMOKE_MAX_ENVS + 1)):
        with pytest.raises(ValueError, match="smoke_preset.*" + path):
            assemble_training_config(env, runner, {**config, "overrides": {path: value}})
    overrides = {"environment.scene.num_envs": SMOKE_MAX_ENVS,
                 "runner.max_iterations": SMOKE_MAX_ITERS, "runner.save_interval": 2}
    result = assemble_training_config(env, runner, {**config, "overrides": overrides})
    assert result.environment.scene.num_envs == SMOKE_MAX_ENVS
    assert result.runner.max_iterations == SMOKE_MAX_ITERS
    assert result.runner.save_interval == 2
    assert result.snapshot["runner"]["max_iterations"] == SMOKE_MAX_ITERS
    assert env.scene.num_envs == runner.max_iterations == 1
    assert config["num_envs"] == config["max_iterations"] == config["save_interval"] == 1


def test_reward_optional_signature_parameters_allowed():
    def reward(context, scale=1.0, *, threshold=0.5, **kwargs):
        return scale

    env = SimpleNamespace(scene=SimpleNamespace(num_envs=1), commands={},
                          rewards={"known": SimpleNamespace(weight=1, func=reward, params={"legacy": 1})})
    result = assemble_training_config(env, SimpleNamespace(), {
        "reward_params": {"known": {"legacy": 2, "scale": 3.0, "threshold": 0.2}}
    })
    assert result.environment.rewards["known"].params == {"legacy": 2, "scale": 3.0, "threshold": 0.2}
    assert env.rewards["known"].params == {"legacy": 1}


def test_reward_signature_rejects_unknown_context_and_dict_methods():
    import pytest

    def reward(context, positional=1, /, *, threshold=0.5, **kwargs):
        return threshold

    env = SimpleNamespace(scene=SimpleNamespace(num_envs=1), commands={},
                          rewards={"known": SimpleNamespace(weight=1, func=reward, params={})})
    for key in ("missing", "context", "positional", "kwargs", "items", "update"):
        with pytest.raises(ValueError, match="known." + key):
            assemble_training_config(env, SimpleNamespace(), {"reward_params": {"known": {key: 2}}})
    assert env.rewards["known"].params == {}


def test_explicit_unknown_profile_reward_rejected():
    import pytest
    env = SimpleNamespace(scene=SimpleNamespace(num_envs=1), rewards={}, commands={})
    with pytest.raises(ValueError):
        assemble_training_config(env, SimpleNamespace(), {
            "reward_overrides": True, "reward_scales": {"unknown": 0.0}
        }, profile={"profile_id": "test"})


def test_missing_command_ranges_rejected_without_mutation():
    import pytest
    env = SimpleNamespace(scene=SimpleNamespace(num_envs=1), rewards={}, commands={})
    with pytest.raises(ValueError):
        assemble_training_config(env, SimpleNamespace(), {"command_ranges": {"vx": [0, 1]}})
    assert env.scene.num_envs == 1


def test_final_overrides_snapshot_and_copy():
    from dataclasses import make_dataclass
    import pytest
    Scene = make_dataclass("Scene", [("num_envs", int)])
    Env = make_dataclass("Env", [("scene", Scene), ("rewards", dict), ("commands", dict)])
    Runner = make_dataclass("Runner", [("max_iterations", int), ("num_steps_per_env", int), ("logger", str), ("experiment_name", str)])
    env, runner = Env(Scene(1), {}, {}), Runner(100, 24, "old", "old")
    config = {"mode": "train", "max_iterations": 2, "overrides": {"runner.max_iterations": 9, "runner.logger": "custom"}}
    result = assemble_training_config(env, runner, config)
    assert result.runner.max_iterations == 9
    assert result.runner.logger == "custom"
    assert result.snapshot["runner"]["max_iterations"] == 9
    assert runner.max_iterations == 100
    config["overrides"]["runner.missing"] = 1
    with pytest.raises(ValueError):
        assemble_training_config(env, runner, config)
    assert runner.max_iterations == 100
    assert env.scene.num_envs == 1



def test_module_import_does_not_load_torch():
    import subprocess
    import sys
    result = subprocess.run([sys.executable, "-c", "import sys; import adapters.mjlab.task_config; assert 'torch' not in sys.modules; assert 'mjlab' not in sys.modules"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_unknown_reward_parameter_rejected():
    import pytest
    env = SimpleNamespace(scene=SimpleNamespace(num_envs=1), rewards={"known": SimpleNamespace(weight=1, params={"std": 0.5})}, commands={})
    with pytest.raises(ValueError, match="known.missing"):
        assemble_training_config(env, SimpleNamespace(), {"reward_overrides": True, "reward_params": {"known": {"missing": 2}}}, profile={})
    assert env.rewards["known"].params == {"std": 0.5}


def test_dot_readonly_and_bad_type_are_rejected():
    import pytest
    from dataclasses import make_dataclass
    Scene = make_dataclass("Scene", [("num_envs", int)])
    Env = make_dataclass("Env", [("scene", Scene), ("rewards", dict), ("commands", dict), ("decimation", int)])
    Runner = make_dataclass("Runner", [("max_iterations", int), ("sizes", list)])
    env, runner = Env(Scene(1), {}, {}, 4), Runner(100, [1, 2])
    for edits in ({"environment.decimation": 8}, {"runner.max_iterations": "bad"}, {"runner.sizes": 7}):
        with pytest.raises(ValueError):
            assemble_training_config(env, runner, {"overrides": edits})
    assert env.decimation == 4
    assert runner.max_iterations == 100


def test_worker_uses_final_runner_and_writes_snapshot_before_env(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="worker-assembly-") as directory:
        _check_worker_assembly(monkeypatch, Path(directory))


def _check_worker_assembly(monkeypatch, tmp_path):
    import json
    import sys
    from dataclasses import make_dataclass
    from types import ModuleType
    from adapters.mjlab import native_worker, runtime_compat

    Scene = make_dataclass("Scene", [("num_envs", int)])
    EnvCfg = make_dataclass("EnvCfg", [("scene", Scene), ("rewards", dict), ("commands", dict)])
    RunnerCfg = make_dataclass("RunnerCfg", [("max_iterations", int), ("num_steps_per_env", int), ("logger", str), ("experiment_name", str), ("clip_actions", float)])
    env_cfg = EnvCfg(Scene(1), {}, {})
    runner_cfg = RunnerCfg(100, 24, "old", "old", 1.0)
    observed = {}
    output = tmp_path / "output"

    class Env:
        def __init__(self, cfg, device):
            observed["snapshot"] = json.loads((output / "effective-config.json").read_text())
            self.num_envs = cfg.scene.num_envs
            self.action_manager = SimpleNamespace(total_action_dim=1)
        def reset(self):
            return {"actor": SimpleNamespace(shape=(1, 2))}, {}
        def step(self, action):
            return None
        def close(self):
            observed["closed"] = True

    class Runner:
        def __init__(self, env, cfg, output, device):
            observed["runner"] = cfg
        def load(self, *args, **kwargs):
            pass
        def learn(self, **kwargs):
            observed["learn"] = kwargs

    modules = {name: ModuleType(name) for name in ("torch", "mjlab", "mjlab.tasks", "mjlab.tasks.registry", "mjlab.envs", "mjlab.rl")}
    modules["torch"].__version__ = "test"
    modules["torch"].cuda = SimpleNamespace(is_available=lambda: False)
    modules["torch"].zeros = lambda *a, **kw: None
    modules["mjlab"].tasks = modules["mjlab.tasks"]
    registry = modules["mjlab.tasks.registry"]
    registry.list_tasks = lambda: ["test"]
    registry.load_env_cfg = lambda task: env_cfg
    registry.load_rl_cfg = lambda task: runner_cfg
    registry.load_runner_cls = lambda task: Runner
    registry.register_mjlab_task = lambda *args, **kwargs: None
    modules["mjlab.envs"].ManagerBasedRlEnv = Env
    modules["mjlab.rl"].MjlabOnPolicyRunner = Runner
    modules["mjlab.rl"].RslRlVecEnvWrapper = lambda env, **kwargs: env
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(runtime_compat, "evaluate_package_runtime", lambda *args: {"status": "compatible"})
    monkeypatch.setattr(native_worker, "wrap_runner_with_checkpoint_export", lambda cls, builder: cls)
    monkeypatch.setattr(native_worker, "collect_curriculum_snapshot", lambda env: {})
    checkpoint = tmp_path / "model_3.pt"
    checkpoint.touch()
    config = {"generic_task": False, "native_task_id": "test", "mode": "train", "max_iterations": 2,
              "resume_from": str(checkpoint), "overrides": {"runner.max_iterations": 9, "runner.num_steps_per_env": 32, "runner.logger": "custom", "runner.experiment_name": "final"}}
    assert native_worker.run(config, tmp_path, output) == 0
    assert observed["runner"]["max_iterations"] == 9
    assert observed["runner"]["num_steps_per_env"] == 32
    assert observed["runner"]["logger"] == "custom"
    assert observed["runner"]["experiment_name"] == "final"
    assert observed["learn"]["num_learning_iterations"] == 6
    assert observed["snapshot"]["runner"]["max_iterations"] == 9
    assert runner_cfg.max_iterations == 100
    assert observed["closed"]


class RecipeApplicationTests(unittest.TestCase):
    def test_package_profile_loader_is_robot_neutral(self):
        with tempfile.TemporaryDirectory(prefix="profile-protocol-") as value:
            package = Path(value)
            source = package / "training" / "source" / "acme_profile"
            source.mkdir(parents=True)
            (source / "__init__.py").write_text(
                "from types import SimpleNamespace\n"
                "def env(play=False): return SimpleNamespace(play=play, marker='env')\n"
                "def runner(): return SimpleNamespace(marker='runner')\n"
                "def configure(env_cfg, play_env_cfg, rl_cfg, config):\n"
                "    env_cfg.marker = config['marker']\n"
                "    return {'env_cfg': env_cfg, 'play_env_cfg': play_env_cfg, 'rl_cfg': rl_cfg}\n",
                encoding="utf-8",
            )
            profile = {
                "profile_id": "acme-profile",
                "source_root": "training/source",
                "entrypoints": {
                    "env": "acme_profile:env",
                    "runner": "acme_profile:runner",
                    "configure": "acme_profile:configure",
                },
            }
            env_cfg, play_env_cfg, rl_cfg = load_profile_bundle(
                profile, {"package_root": str(package)}, {"marker": "configured"}
            )
            self.assertEqual(env_cfg.marker, "configured")
            self.assertFalse(env_cfg.play)
            self.assertTrue(play_env_cfg.play)
            self.assertEqual(rl_cfg.marker, "runner")

    def test_recipe_applies_rewards_terrain_commands_and_ppo_fields(self):
        class Ranges:
            lin_vel_x = (-1.0, 1.0)
            lin_vel_y = (-1.0, 1.0)
            ang_vel_z = (-1.0, 1.0)

        rewards = {"track_linear_velocity": SimpleNamespace(weight=1.0, params={})}
        env = SimpleNamespace(
            scene=SimpleNamespace(num_envs=1, terrain=SimpleNamespace(terrain_type="generator", terrain_generator=object())),
            rewards=rewards,
            commands={"twist": SimpleNamespace(ranges=Ranges())},
            episode_length_s=20.0,
        )
        algorithm = SimpleNamespace(learning_rate=0.001, gamma=0.99, lam=0.95, clip_param=0.2, entropy_coef=0.01, num_mini_batches=4)
        runner = SimpleNamespace(algorithm=algorithm, num_steps_per_env=24, max_iterations=100, save_interval=10)
        report = apply_training_recipe(env, runner, {"terrain_type": "rough", "num_envs": 64, "reward_scales": {"track_linear_velocity": 2.0}, "command_ranges": {"lin_vel_x": [0.0, 2.0]}, "learning_rate": 0.0003, "gae_lambda": 0.9, "num_steps": 32})
        self.assertEqual(env.scene.num_envs, 64)
        self.assertEqual(env.rewards["track_linear_velocity"].weight, 2.0)
        self.assertEqual(env.commands["twist"].ranges.lin_vel_x, (0.0, 2.0))
        self.assertEqual(runner.algorithm.lam, 0.9)
        self.assertEqual(runner.num_steps_per_env, 32)
        self.assertEqual(report["terrain_type"], "rough")


if __name__ == "__main__":
    unittest.main()
