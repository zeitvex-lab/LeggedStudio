import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace

from adapters.mjlab.native_worker import _load_profile_bundle, apply_training_recipe


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
            env_cfg, play_env_cfg, rl_cfg = _load_profile_bundle(
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
