"""Tests for the curated parameter descriptor registry (profile-schema params).

The resolver runs on the control plane, so these tests exercise it against a
fixture dump without importing mjlab/torch. A live end-to-end test spawns the
real adapter worker for zex-w-rough when the adapter venv is present.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_ADAPTER_VENV = _ROOT / "adapters" / "mjlab" / ".venv" / "Scripts" / "python.exe"


def _fixture_tree() -> dict:
    """Miniature dump matching the real mjlab config structure."""
    return {
        "profile_id": "fixture-rough",
        "environment": {
            "decimation": 4,
            "episode_length_s": 20.0,
            "sim": {
                "nconmax": None,  # None-valued paths must be skipped
                "mujoco": {
                    "timestep": 0.005,
                    "iterations": 100,
                    "ls_iterations": 50,
                    "impratio": 100,
                    "cone": "elliptic",
                    "gravity": [0.0, 0.0, -9.81],  # 3-vector → expert tree only
                },
            },
            "scene": {
                "num_envs": 2048,
                "terrain": {
                    "terrain_type": "generator",
                    "max_init_terrain_level": 5,
                    "terrain_generator": {"curriculum": True, "num_rows": 10},
                },
            },
            "commands": {
                "twist": {
                    "ranges": {"lin_vel_x": [-1.0, 1.0], "heading": [-3.14, 3.14]},
                    "resampling_time_range": [10.0, 10.0],
                    "rel_standing_envs": 0.02,
                },
            },
            "curriculum": {"terrain_levels": {"func": "fn:terrain_levels"}, "command_x_levels": {}},
            "actions": {
                "leg_joint_pos": {"scale": {".*_hip_abduction_joint": 0.125, "^(?!.*_hip).*": 0.25}},
                "wheel_joint_vel": {"scale": 5.0, "cut_off_frequency": 15.0},
            },
            "observations": {
                "actor": {"terms": {"command": {"noise": None}, "joint_pos": {"noise": 0.01}}},
            },
            "events": {
                "push_robot": {
                    "params": {
                        "velocity_range": {"x": [-0.5, 0.5], "y": [-0.5, 0.5]},
                        "asset_cfg": {"name": "robot"},  # must be excluded
                    },
                },
                "body_mass_base": {"params": {"ranges": [-1.0, 3.0], "operation": "add"}},
            },
            "rewards": {
                "track_lin_vel_x_exp": {"weight": 1.0, "func": "fn:track_linear_velocity_x"},
                "action_rate": {"weight": -0.01, "func": "fn:action_rate_l2"},
                "joint_torques": {"weight": -2.5e-05},
            },
            "terminations": {
                "bad_orientation": {"params": {"limit_angle": 1.0}},
            },
        },
        "runner": {
            "seed": 42,
            "max_iterations": 20000,
            "save_interval": 100,
            "num_steps_per_env": 24,
            "actor": {"hidden_dims": [512, 256, 128], "activation": "elu", "obs_normalization": False},
            "algorithm": {
                "learning_rate": 0.0008,
                "desired_kl": 0.01,
                "gamma": 0.99,
                "lam": 0.95,
                "clip_param": 0.2,
                "entropy_coef": 0.003,
                "num_learning_epochs": 5,
                "num_mini_batches": 4,
                "max_grad_norm": 1.0,
                "value_loss_coef": 1.0,
            },
        },
    }


class GetByPathTests(unittest.TestCase):
    def test_get_by_path_reads_dataclasses_and_dicts_with_default(self):
        from adapters.mjlab.config_introspect import get_by_path

        fixture = _fixture_tree()
        self.assertEqual(get_by_path(fixture, "environment.sim.mujoco.timestep"), 0.005)
        self.assertEqual(get_by_path(fixture, "runner.algorithm.lam"), 0.95)
        self.assertEqual(get_by_path(fixture, "environment.rewards.action_rate.weight"), -0.01)
        self.assertIsNone(get_by_path(fixture, "environment.missing.path"))
        self.assertEqual(get_by_path(fixture, "environment.missing.path", "fallback"), "fallback")
        # Traversal through a scalar is safe, not an exception.
        self.assertIsNone(get_by_path(fixture, "environment.decimation.deep"))


class ResolveParamsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from adapters.mjlab.param_registry import resolve_params

        cls.resolve_params = staticmethod(resolve_params)
        cls.params = resolve_params(_fixture_tree())
        cls.by_path = {param["path"]: param for param in cls.params}

    def test_registry_is_import_safe_and_curated(self):
        # Importing the registry must not pull mjlab/torch (stdlib-only module).
        import adapters.mjlab.param_registry as registry

        self.assertGreaterEqual(len(registry.FIXED_DESCRIPTORS), 30)
        categories = {descriptor["category"] for descriptor in registry.FIXED_DESCRIPTORS}
        self.assertEqual(categories, {"simulator", "environment", "learning"})

    def test_fixed_simulator_environment_learning_entries_resolved(self):
        for path in (
            "environment.sim.mujoco.timestep",
            "environment.sim.mujoco.iterations",
            "environment.scene.num_envs",
            "environment.episode_length_s",
            "runner.seed",
            "runner.max_iterations",
        ):
            self.assertIn(path, self.by_path, path)
        self.assertEqual(self.by_path["environment.sim.mujoco.timestep"]["type"], "float")
        self.assertEqual(self.by_path["environment.sim.mujoco.timestep"]["value"], 0.005)
        # None-valued / 3-vector paths stay out of the curated list.
        self.assertNotIn("environment.sim.nconmax", self.by_path)
        self.assertNotIn("environment.sim.mujoco.gravity", self.by_path)

    def test_command_ranges_resolved_as_editable_pairs(self):
        param = self.by_path["environment.commands.twist.ranges.lin_vel_x"]
        self.assertEqual(param["type"], "list")
        self.assertEqual(param["value"], [-1.0, 1.0])
        self.assertEqual(param["category"], "environment")
        self.assertFalse(param["readonly"])
        # Non-pair lists are not exposed (heading has 2 numeric entries → OK,
        # but the descriptor list does not include it).
        self.assertNotIn("environment.commands.twist.ranges.heading", self.by_path)

    def test_curriculum_dict_resolved_as_readonly_summary(self):
        param = self.by_path["environment.curriculum"]
        self.assertTrue(param["readonly"])
        self.assertIn("terrain_levels", param["value"])

    def test_action_scale_pattern_handles_dict_and_scalar(self):
        # Both fixture regex keys contain dots → not addressable via dot-path
        # overrides, so the leg scale collapses into a readonly summary.
        leg = self.by_path["environment.actions.leg_joint_pos.scale"]
        self.assertTrue(leg["readonly"])
        self.assertIn("hip_abduction_joint", leg["value"])
        self.assertEqual(leg["category"], "embodiment")
        wheel = self.by_path["environment.actions.wheel_joint_vel.scale"]
        self.assertEqual(wheel["value"], 5.0)
        self.assertFalse(wheel["readonly"])
        cutoff = self.by_path["environment.actions.wheel_joint_vel.cut_off_frequency"]
        self.assertEqual(cutoff["unit"], "Hz")

    def test_observation_noise_pattern_skips_none(self):
        self.assertIn("environment.observations.actor.terms.joint_pos.noise", self.by_path)
        self.assertNotIn("environment.observations.actor.terms.command.noise", self.by_path)

    def test_reward_weight_pattern_expands_with_labels(self):
        weights = [param for param in self.params if param["path"].startswith("environment.rewards.")]
        self.assertEqual(len(weights), 3)
        track = self.by_path["environment.rewards.track_lin_vel_x_exp.weight"]
        self.assertEqual(track["category"], "robustness")
        self.assertEqual(track["value"], 1.0)
        self.assertIn("track_linear_velocity_x", track["hint"])
        self.assertIn("奖励权重", track["label"])

    def test_event_params_skip_asset_cfg_and_strings(self):
        self.assertIn("environment.events.push_robot.params.velocity_range.x", self.by_path)
        self.assertEqual(self.by_path["environment.events.push_robot.params.velocity_range.x"]["value"], [-0.5, 0.5])
        self.assertIn("推力扰动", self.by_path["environment.events.push_robot.params.velocity_range.x"]["label"])
        self.assertIn("environment.events.body_mass_base.params.ranges", self.by_path)
        # asset_cfg subtrees and plain string params stay in the expert tree.
        self.assertFalse(any("asset_cfg" in param["path"] for param in self.params))
        self.assertNotIn("environment.events.body_mass_base.params.operation", self.by_path)

    def test_termination_thresholds_are_readonly(self):
        param = self.by_path["environment.terminations.bad_orientation.params.limit_angle"]
        self.assertEqual(param["value"], 1.0)
        self.assertTrue(param["readonly"])

    def test_every_param_carries_console_fields(self):
        for param in self.params:
            self.assertIn(param["category"], {"simulator", "environment", "embodiment", "learning", "robustness"})
            for field in ("path", "label", "type", "value", "default", "unit", "hint", "advanced", "readonly"):
                self.assertIn(field, param)
            self.assertEqual(param["default"], param["value"])


@unittest.skipUnless(_ADAPTER_VENV.exists(), "adapter venv not installed")
class ZexWRoughLiveSchemaTests(unittest.TestCase):
    """End-to-end: dump the real zex-w-rough tree and resolve the catalog."""

    @classmethod
    def setUpClass(cls):
        dump_config = {
            "profile_id": "zex-w-rough",
            "package_root": str(_ROOT / "workspace" / "packages" / "zex-w"),
            "source_root": "training/source",
            "entrypoints": {
                "env": "robot.config.env_cfgs:rough_env_cfg",
                "runner": "robot.config.rl_cfg:rough_ppo_runner_cfg",
            },
        }
        env = os.environ.copy()
        source_abs = Path(dump_config["package_root"]) / dump_config["source_root"]
        env["PYTHONPATH"] = os.pathsep.join([str(source_abs), env.get("PYTHONPATH", "")]).strip(os.pathsep)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump(dump_config, handle, ensure_ascii=False)
            config_path = handle.name
        try:
            completed = subprocess.run(
                [str(_ADAPTER_VENV), "-m", "adapters.mjlab.native_worker", "--dump-schema", "--config", config_path],
                cwd=str(_ROOT),
                env=env,
                capture_output=True,
                text=True,
                # worker 输出是 UTF-8；不显式指定时 Windows 会按系统 ANSI 码页（GBK）解码，
                # 遇到非 GBK 字节就抛 UnicodeDecodeError ⇒ 用例在本机必红（CI 是 UTF-8 环境所以看不到）。
                encoding="utf-8",
                timeout=180,
            )
        finally:
            try:
                os.unlink(config_path)
            except OSError:
                pass
        if completed.returncode != 0:
            raise AssertionError(f"schema dump failed: {(completed.stderr or '')[-500:]}")
        stdout = completed.stdout or ""
        start = stdout.find("{")
        cls.schema = json.JSONDecoder().raw_decode(stdout[start:])[0]

    @classmethod
    def tearDownClass(cls):
        # The worker chdir()s into the package source; not our process, nothing to undo.
        pass

    def test_params_cover_curated_categories_for_zex_w(self):
        from adapters.mjlab.param_registry import resolve_params

        params = resolve_params(self.schema)
        by_path = {param["path"]: param for param in params}
        for category in ("simulator", "environment", "embodiment", "learning", "robustness"):
            self.assertTrue(any(param["category"] == category for param in params), category)
        self.assertEqual(by_path["environment.sim.mujoco.timestep"]["value"], 0.005)
        self.assertEqual(by_path["runner.algorithm.lam"]["value"], 0.95)
        self.assertEqual(by_path["runner.actor.hidden_dims"]["value"], [512, 256, 128])
        self.assertTrue(by_path["runner.actor.hidden_dims"]["readonly"])

    def test_zex_w_rough_resolves_all_reward_weights_and_sim_defaults(self):
        from adapters.mjlab.param_registry import resolve_params

        params = resolve_params(self.schema)
        weights = [param for param in params if param["path"].startswith("environment.rewards.")]
        self.assertEqual(len(weights), 24)
        by_path = {param["path"]: param for param in params}
        self.assertEqual(by_path["environment.rewards.action_rate.weight"]["value"], -0.01)
        self.assertEqual(by_path["environment.scene.terrain.max_init_terrain_level"]["value"], 5)
        self.assertEqual(by_path["environment.commands.twist.rel_standing_envs"]["value"], 0.02)
        self.assertTrue(any(param["path"] == "environment.events.push_robot.params.velocity_range.x" for param in params))
        # All resolved paths must really exist in the dump; readonly summaries
        # (curriculum terms, per-joint scale regexes) synthesize display strings.
        from adapters.mjlab.config_introspect import get_by_path

        for param in params:
            value = get_by_path(self.schema, param["path"], "<<missing>>")
            self.assertNotEqual(value, "<<missing>>", param["path"])
            if param["readonly"] and isinstance(value, dict):
                self.assertIsInstance(param["value"], str)
                continue
            self.assertEqual(value, param["value"], param["path"])


if __name__ == "__main__":
    unittest.main()
