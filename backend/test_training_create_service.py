import subprocess
import sys
from unittest.mock import Mock

import pytest

from backend.training.models import CreateTrainingRequest


HYPERS = {'learning_rate', 'num_steps', 'num_minibatches', 'gamma', 'gae_lambda', 'clip_param', 'entropy_coef'}


def test_service_without_http_framework():
    result = subprocess.run([sys.executable, '-c', '''
import sys
sys.modules['fastapi'] = None
sys.modules['starlette'] = None
from backend.training.service import build_training_config, create_training_run
from backend.training.models import CreateTrainingRequest
assert build_training_config(CreateTrainingRequest(contract={}))['num_envs'] == 4096
class Manager:
    def resolve_idempotency(self, key): return 'existing'
    def get_task(self, key): return True
assert create_training_run(CreateTrainingRequest(contract={}), idempotency_key='key', manager=Manager())['idempotent_replay']
'''], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_profile_omitted_hyperparameters():
    from backend.training.service import build_training_config
    config = build_training_config(CreateTrainingRequest(contract={}, profile_id='profile'))
    assert not HYPERS.intersection(config)
    assert [config[k] for k in ('num_envs', 'max_iterations', 'save_interval', 'seed')] == [4096, 1000, 100, 0]


def test_explicit_defaults_and_generic_defaults():
    from backend.training.service import build_training_config
    defaults = CreateTrainingRequest(contract={})
    values = {key: getattr(defaults, key) for key in HYPERS}
    for request in (defaults, CreateTrainingRequest(contract={}, profile_id='profile', **values)):
        assert {key: build_training_config(request)[key] for key in HYPERS} == values


def test_config_does_not_alias_request():
    from backend.training.service import build_training_config
    request = CreateTrainingRequest(contract={}, smoke=True, overrides={'a': [1]})
    before = request.model_dump()
    fields = request.model_fields_set.copy()
    config = build_training_config(request)
    config['overrides']['a'].append(2)
    assert config['num_envs'] == 64
    assert config['max_iterations'] == 5
    assert request.model_dump() == before
    assert request.model_fields_set == fields


@pytest.mark.parametrize('kind,status', [('invalid_request', 400), ('smoke_required', 409), ('invalid_overrides', 422), ('unsupported', 501)])
def test_http_maps_service_errors(monkeypatch, kind, status):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.training import create, service
    app = FastAPI()
    app.include_router(create.router)
    monkeypatch.setattr(create, 'create_training_run', Mock(side_effect=service.TrainingServiceError(kind, {'reason': 'test'})))
    response = TestClient(app).post('/api/training/create', json={'contract': {}})
    assert response.status_code == status
    assert response.json() == {'detail': {'reason': 'test'}}


@pytest.fixture
def contract():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    return json.loads((root / 'assets/robots/unitree_go2/contract_legacy_v2.json').read_text(encoding='utf-8-sig'))


@pytest.fixture
def launch_runtime(monkeypatch):
    from adapters.mjlab import native_adapter
    monkeypatch.setattr(native_adapter, 'preflight', lambda *args: {'execution_ready': True})
    monkeypatch.setattr(native_adapter, 'package_runtime_diagnostics', lambda *args: {'status': 'compatible'})


@pytest.fixture
def evidence_dir():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as directory:
        yield Path(directory)


def test_real_smoke_gate_and_idempotency(monkeypatch, evidence_dir, contract, launch_runtime):
    import json
    from types import SimpleNamespace
    from backend.training import service, smoke_gate
    from backend.training.runs import run_inputs_from_task
    monkeypatch.delenv(smoke_gate.BYPASS_ENV, raising=False)
    manager = Mock(tasks={})
    manager.create_task.return_value = 'new'
    manager.resolve_idempotency.return_value = None
    request = CreateTrainingRequest(contract=contract, smoke=True)
    original = request.model_dump()
    result = service.create_training_run(request, manager=manager, idempotency_key='key')
    assert result['task_id'] == 'new'
    assert not result['smoke_gate']['required']
    assert request.model_dump() == original
    created = manager.create_task.call_args.kwargs
    assert created['idempotency_key'] == 'key'
    inputs = run_inputs_from_task(contract_hash=created['contract'].compute_hash(), config=created['config'])
    (evidence_dir / 'resolved-config.json').write_text(json.dumps({'schema': 'training-run-1.0', 'inputs': inputs}), encoding='utf-8')
    long_request = request.model_copy(update={'smoke': False})
    with pytest.raises(service.TrainingServiceError) as error:
        service.create_training_run(long_request, manager=manager)
    assert error.value.kind == 'smoke_required'
    manager.tasks = {'smoke': SimpleNamespace(status='running', task_dir=evidence_dir, get_status_info=lambda: {'status': 'train_completed'})}
    assert service.create_training_run(long_request, manager=manager)['smoke_gate']['ok']
    manager.resolve_idempotency.return_value = 'new'
    manager.get_task.return_value = True
    manager.create_task.reset_mock()
    assert service.create_training_run(CreateTrainingRequest(contract={}), manager=manager, idempotency_key='key')['idempotent_replay']
    manager.create_task.assert_not_called()


def test_preparation_is_shared_without_starting_runtime(contract, monkeypatch):
    from backend.training import service
    from adapters.mjlab import native_adapter
    monkeypatch.setattr(native_adapter, 'preflight', Mock(side_effect=AssertionError('must not probe')))
    request = CreateTrainingRequest(contract=contract, smoke=True)
    parsed, config = service.prepare_training_config(request)
    assert parsed.robot_id == contract['robot_id']
    assert config['resolved_recipe']['task_name'] == request.task_name
    assert config['mode'] == 'train'
    assert config['robot_package']['package_root']
    assert config['num_envs'] == 64


def test_cold_catalog_defers_leaf_validation_to_assembly(contract):
    from backend.training import service
    request = CreateTrainingRequest(contract=contract, overrides={'runner.num_steps_per_env': 8})
    _, config = service.prepare_training_config(request, catalog_loader=lambda _: None)
    assert config['overrides'] == request.overrides
    request.overrides = {'environment.sim.mujoco.timestep': 0.002}
    with pytest.raises(service.TrainingServiceError) as error:
        service.prepare_training_config(request, catalog_loader=lambda _: None)
    assert error.value.kind == 'invalid_overrides'


def test_runtime_not_ready(contract):
    from backend.training import service
    probe = Mock(return_value={'execution_ready': False, 'not_ready_reason': 'missing runtime'})
    with pytest.raises(service.TrainingServiceError) as error:
        service.create_training_run(CreateTrainingRequest(contract=contract), runtime_probe=probe)
    assert error.value.kind == 'unsupported'
    assert error.value.detail['message'] == 'missing runtime'
    assert probe.call_args.args[1] is True


def test_overrides_are_batch_rejected(contract, launch_runtime):
    from backend.training import service
    manager = Mock(tasks={})
    request = CreateTrainingRequest(contract=contract, smoke=True,
                                    overrides={'environment.sim.mujoco.timestep': 0.002})
    with pytest.raises(service.TrainingServiceError) as error:
        service.create_training_run(request, manager=manager)
    assert error.value.kind == 'invalid_overrides'
    manager.create_task.assert_not_called()


def test_http_forwards_key_in_worker_thread(monkeypatch):
    import threading
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.training import create
    app = FastAPI()
    app.include_router(create.router)
    result = {'success': True, 'task_id': 'existing', 'idempotent_replay': True,
              'message': 'Idempotent replay: returning existing task'}
    def launch(request, *, idempotency_key):
        assert idempotency_key == 'key'
        assert 'worker' in threading.current_thread().name.lower()
        return result
    monkeypatch.setattr(create, 'create_training_run', launch)
    response = TestClient(app).post('/api/training/create', json={'contract': {}}, headers={'Idempotency-Key': 'key'})
    assert response.status_code == 200
    assert response.json() == result
