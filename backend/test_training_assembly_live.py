import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.environ.get('LEGGED_STUDIO_TEST_TRAINING') == '1', 'explicit real training opt-in')
class LiveTrainingAssemblyTest(unittest.TestCase):
    def test_preview_matches_profile_and_generic_training(self):
        from backend.training.models import CreateTrainingRequest
        from backend.training.service import prepare_training_config
        from backend.training_config_helpers import dump_schema_via_worker
        from contracts.path_bootstrap import adapter_python
        from adapters.mjlab.native_adapter import DEFAULT_SOURCE

        root = Path(__file__).resolve().parents[1]
        contract_data = json.loads((root / 'assets/robots/unitree_b2/contract_legacy_v2.json').read_text(encoding='utf-8-sig'))
        for profile_id, task_name in [('b2-velocity', 'velocity'), (None, 'forward_walk')]:
            with self.subTest(profile=profile_id), tempfile.TemporaryDirectory(prefix='ls-training-assembly-') as tmp:
                out = Path(tmp)
                request = CreateTrainingRequest(
                    contract=contract_data, profile_id=profile_id, task_name=task_name,
                    smoke=True, num_envs=2, max_iterations=1, num_steps=4,
                    num_minibatches=1, device='auto',
                    overrides={'runner.num_steps_per_env': 8},
                )
                contract, config = prepare_training_config(request)
                package = config['robot_package']
                preview = dump_schema_via_worker(
                    contract.robot_id, profile_id or '', {}, package['package_root'],
                    training_config=config, contract=contract.model_dump(mode='json'),
                )
                (out / 'request.json').write_text(json.dumps(config), encoding='utf-8')
                contract.to_json_file(str(out / 'contract.json'))
                env = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'}
                result = subprocess.run([
                    str(adapter_python()), '-m', 'adapters.mjlab.native_worker',
                    '--source', str(DEFAULT_SOURCE), '--config', str(out / 'request.json'),
                    '--contract', str(out / 'contract.json'), '--output', str(out),
                ], cwd=root, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=540)
                self.assertEqual(result.returncode, 0, (result.stdout + result.stderr)[-6000:])
                actual = json.loads((out / 'effective-config.json').read_text(encoding='utf-8'))
                self.assertEqual(actual['environment'], preview['environment'])
                self.assertEqual(actual['runner'], preview['runner'])
                self.assertEqual(actual['runner']['num_steps_per_env'], 8)
                self.assertTrue((out / 'model_final.pt').is_file())
                self.assertTrue((out / 'exported/policy.onnx').is_file(), result.stdout[-3000:])


if __name__ == '__main__':
    unittest.main()
