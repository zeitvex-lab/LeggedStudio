import json
import os
import sys
import tempfile
import types
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

from adapters.mjlab.config_introspect import build_profile_schema


@dataclass
class Scene:
    num_envs: int = 32
    entities: dict = field(default_factory=dict)
    terrain: object = None


@dataclass
class Environment:
    scene: Scene = field(default_factory=Scene)
    rewards: dict = field(default_factory=dict)
    commands: dict = field(default_factory=dict)
    episode_length_s: float = 7.0
    seed: int = 0


@dataclass
class Algorithm:
    learning_rate: float = 0.0008


@dataclass
class Runner:
    algorithm: Algorithm = field(default_factory=Algorithm)
    num_steps_per_env: int = 24
    max_iterations: int = 20
    save_interval: int = 10
    logger: str = "tensorboard"
    experiment_name: str = "fixture"


class ProfilePreviewAssemblyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name)
        cwd, search_path = Path.cwd(), list(sys.path)
        self.addCleanup(os.chdir, cwd)
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), search_path))
        module = types.ModuleType("preview_fixture")
        module.env = lambda play=False: Environment()
        module.runner = Runner

        def configure(*, env_cfg, play_env_cfg, rl_cfg, config):
            env_cfg.episode_length_s = 9.0
            rl_cfg.algorithm.learning_rate = 0.0009

        module.configure = configure
        self.modules = patch.dict(sys.modules, {module.__name__: module})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.entrypoints = {
            "env": "preview_fixture:env",
            "runner": "preview_fixture:runner",
            "configure": "preview_fixture:configure",
        }

    def test_schema_includes_profile_configure_hook(self):
        schema = build_profile_schema(self.source, self.entrypoints, "fixture")
        self.assertEqual(schema["environment"]["episode_length_s"], 9.0)
        self.assertEqual(schema["runner"]["algorithm"]["learning_rate"], 0.0009)

    def test_preview_matches_execution_assembly_and_roundtrips_json(self):
        config = {
            "mode": "train", "profile_id": "fixture", "num_envs": 4,
            "max_iterations": 2, "num_steps": 8,
            "overrides": {"runner.num_steps_per_env": 12},
        }
        schema = build_profile_schema(self.source, self.entrypoints, "fixture", config=config)
        from adapters.mjlab.task_config import assemble_training_config, load_profile_bundle

        profile = {"profile_id": "fixture", "source_root": str(self.source), "entrypoints": self.entrypoints}
        env_cfg, _, runner_cfg = load_profile_bundle(profile, {"package_root": str(self.source)}, config)
        assembled = assemble_training_config(env_cfg, runner_cfg, config, profile=profile)
        self.assertEqual(schema["environment"], assembled.snapshot["environment"])
        self.assertEqual(schema["runner"], assembled.snapshot["runner"])
        self.assertEqual(schema["runner"]["num_steps_per_env"], 12)
        self.assertEqual(json.loads(json.dumps(schema)), schema)
        self.assertEqual(config["num_steps"], 8)

    def test_worker_preview_uses_full_request_and_selected_profile(self):
        from adapters.mjlab.native_worker import _dump_profile_schema
        profiles = self.source / 'training' / 'profiles'
        profiles.mkdir(parents=True)
        profile = {'profile_id': 'fixture', 'source_root': str(self.source), 'entrypoints': self.entrypoints}
        (profiles / 'fixture.json').write_text(json.dumps(profile), encoding='utf-8')
        config = {'mode': 'train', 'profile_id': 'fixture',
                  'robot_package': {'package_root': str(self.source)},
                  'overrides': {'runner.num_steps_per_env': 12}}
        payload = _dump_profile_schema({'training_config': config, 'contract': {}})
        self.assertEqual(payload['runner']['num_steps_per_env'], 12)
        self.assertEqual(payload['environment']['episode_length_s'], 9.0)

    def test_preview_rejects_unknown_explicit_override(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            build_profile_schema(
                self.source, self.entrypoints, "fixture",
                config={"mode": "train", "overrides": {"runner.missing": 1}},
            )


class EffectivePreviewApiTest(unittest.TestCase):
    def test_post_preview_uses_creation_input_without_creating_a_run(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.training import schema
        root = Path(__file__).resolve().parents[1]
        contract = json.loads((root / 'assets/robots/unitree_b2/contract_legacy_v2.json').read_text(encoding='utf-8-sig'))
        app = FastAPI()
        app.include_router(schema.router)
        request = {'contract': contract, 'profile_id': 'b2-velocity', 'task_name': 'velocity', 'smoke': True}
        seen = {}

        def dump(robot_id, profile_id, profile, package_root, **kwargs):
            seen.update(kwargs)
            return {'schema': 'training-effective-config-1.0', 'runner': {'num_steps_per_env': 24}}

        with patch.object(schema, '_dump_schema_via_worker', side_effect=dump), \
             patch('backend.training.service.get_training_manager', side_effect=AssertionError('must not launch')):
            response = TestClient(app).post('/api/training/config-preview', json=request)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn('num_steps', seen['training_config'])
        self.assertEqual(seen['training_config']['num_envs'], 64)
        self.assertEqual(response.json()['request_config'], request)
        self.assertEqual(response.json()['effective_config']['runner']['num_steps_per_env'], 24)


class ProfileCacheVersionTest(unittest.TestCase):
    def test_legacy_schema_cache_is_not_an_effective_catalog(self):
        from backend.training.service import cached_param_catalog
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LEGGED_STUDIO_WORKSPACE': tmp}):
            cache = Path(tmp) / 'schema_cache'
            cache.mkdir()
            (cache / 'fixture.json').write_text(json.dumps({'schema': {'runner': {'num_steps_per_env': 24}}}), encoding='utf-8')
            self.assertIsNone(cached_param_catalog('fixture'))


class EffectiveRunArchiveTest(unittest.TestCase):
    def test_archive_exposes_effective_snapshot_without_rewriting_inputs(self):
        import asyncio
        from types import SimpleNamespace
        from backend.training.artifacts import get_training_run
        from backend.training.runs import create_run_for_task

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = SimpleNamespace(robot_id="fixture", compute_hash=lambda: "fixture-hash")
            create_run_for_task(root, contract=contract, config={"seed": 1}, task="fixture")
            requested = (root / "resolved-config.json").read_bytes()
            snapshot = {"schema": "training-effective-config-1.0", "runner": {"num_steps_per_env": 12}}
            (root / "effective-config.json").write_text(json.dumps(snapshot), encoding="utf-8")
            manager = SimpleNamespace(get_task=lambda task_id: SimpleNamespace(task_dir=root))
            with patch("backend.training.artifacts.get_training_manager", return_value=manager), \
                 patch("backend.policy_artifacts.produced_for_run", return_value=[]):
                payload = asyncio.run(get_training_run("fixture"))
                summary = asyncio.run(get_training_run("fixture", summary=True))
            self.assertEqual(payload["effective_config"], snapshot)
            self.assertNotIn("effective_config", summary)
            self.assertEqual((root / "resolved-config.json").read_bytes(), requested)


if __name__ == "__main__":
    unittest.main()
