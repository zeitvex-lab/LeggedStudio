"""Synchronous training application service, independent of HTTP frameworks."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from adapters.mjlab.algorithms.registry import list_algorithms, resolve_algorithm
from adapters.mjlab.recipe_registry import resolve_recipe
from backend.robot_packages import package_for_contract
from backend.training.models import CreateTrainingRequest
from backend.training.config_cache import cached_param_catalog
from contracts.contract_legacy_v2 import ContractLegacyV2


class TrainingServiceError(Exception):
    """Application rejection with transport-independent kind and original detail."""

    def __init__(self, kind: str, detail: Any):
        self.kind = kind
        self.detail = detail
        super().__init__(str(detail))


def get_training_manager():
    from backend.training_manager import get_training_manager as get_manager
    return get_manager()


def _algorithm(request: CreateTrainingRequest) -> str:
    try:
        entry = resolve_algorithm(request.algorithm)
    except ValueError as exc:
        raise TrainingServiceError('invalid_request', str(exc)) from exc
    algorithm = str(entry['id'])
    if not entry['product_open']:
        raise TrainingServiceError('unsupported', {
            'message': f'算法 {algorithm} 已登记，但产品内未开放训练',
            'kind': entry['kind'],
            'native_supported': entry['native_supported'],
            'reason': (
                '插件路径：协议与 class_name 绑定已就绪（profile 里 algorithm_plugin 可启用），'
                '但尚未经真训练验证，产品内不开放'
                if entry['kind'] == 'plugin'
                else '内置路径：off-policy（SAC/TD3）尚未接入 runner'
            ),
            'open_algorithms': [item['id'] for item in list_algorithms() if item.get('product_open')],
        })
    return algorithm


def build_training_config(request: CreateTrainingRequest) -> dict:
    """Build detached launch inputs; profile hyperparameters override only if explicit.

    Recipe resolution remains a separate launch step, as before. Preview callers
    can use this function without validating a contract or probing a runtime.
    """
    config = request.model_dump(include=set(CreateTrainingRequest.model_fields) - {'contract', 'smoke'})
    config['algorithm'] = _algorithm(request)
    config['smoke_preset'] = request.smoke
    if request.profile_id:
        for key in ('learning_rate', 'num_steps', 'num_minibatches', 'gamma', 'gae_lambda', 'clip_param', 'entropy_coef'):
            if key not in request.model_fields_set:
                config.pop(key, None)
    if request.smoke:
        from backend.training import smoke_gate
        config['num_envs'] = min(request.num_envs, smoke_gate.SMOKE_MAX_ENVS)
        config['max_iterations'] = min(request.max_iterations, smoke_gate.SMOKE_MAX_ITERS)
    return config


def prepare_training_config(
    request: CreateTrainingRequest, *, catalog_loader: Callable | None = None,
) -> tuple[ContractLegacyV2, dict]:
    config = build_training_config(request)
    contract = ContractLegacyV2(**deepcopy(request.contract))
    from contracts.validator import validate_contract
    validation = validate_contract(contract)
    if not validation.valid:
        errors = [e.message for e in validation.errors]
        raise TrainingServiceError('invalid_request', f"Invalid contract: {', '.join(errors)}")
    if request.backend != 'native_mjlab':
        raise TrainingServiceError('unsupported', {'message': f"backend '{request.backend}' is reserved for a future framework and is not wired yet"})
    try:
        config['resolved_recipe'] = resolve_recipe(config).model_dump(mode='json')
    except ValueError as exc:
        raise TrainingServiceError('invalid_request', str(exc)) from exc
    config['mode'] = 'train'
    config['robot_package'] = package_for_contract(contract.model_dump(mode='json'))
    config['generic_task'] = True
    if request.overrides:
        from backend.training.dot_path import validate_edits, validate_override_policy
        catalog = (catalog_loader or cached_param_catalog)(str(request.profile_id)) if request.profile_id else None
        report = (validate_edits(config['overrides'], catalog=catalog) if catalog is not None
                  else validate_override_policy(config['overrides']))
        if not report['ok']:
            raise TrainingServiceError('invalid_overrides', {
                'message': '点路径覆盖未通过校验（整批拒绝，一个都不会写入）',
                'problems': report['problems'],
                'catalog': 'full' if catalog else 'static_only',
            })
        config['overrides'] = report['applied']
    return contract, config


def create_training_run(
    request: CreateTrainingRequest, *, idempotency_key: str | None = None,
    manager: Any = None, runtime_probe: Callable | None = None,
    catalog_loader: Callable | None = None,
) -> dict:
    """Validate and launch a run. Injectable boundaries never change launch policy."""
    if idempotency_key:
        if manager is None:
            manager = get_training_manager()
        replayed = manager.resolve_idempotency(idempotency_key)
        if replayed and manager.get_task(replayed):
            return {'success': True, 'task_id': replayed, 'idempotent_replay': True,
                    'message': 'Idempotent replay: returning existing task'}

    contract, config = prepare_training_config(request, catalog_loader=catalog_loader)
    from adapters.mjlab.native_adapter import DEFAULT_SOURCE, package_runtime_diagnostics, preflight
    native = deepcopy((runtime_probe or preflight)(DEFAULT_SOURCE, True))
    if not native.get("execution_ready"):
        raise TrainingServiceError('unsupported', {
            'message': native.get("not_ready_reason") or 'native MJLab adapter is not ready',
            'preflight': native,
        })
    compatibility = package_runtime_diagnostics(config['robot_package'], native)
    native['package_compatibility'] = compatibility
    if compatibility['status'] == 'incompatible':
        raise TrainingServiceError('unsupported', {'message': 'selected robot package is incompatible with the active MJLab runtime', 'compatibility': compatibility, 'preflight': native})
    if compatibility['status'] == 'unknown':
        raise TrainingServiceError('unsupported', {'message': 'active MJLab runtime version could not be verified for the selected robot package', 'compatibility': compatibility, 'preflight': native})

    from backend.training import smoke_gate
    from backend.training.runs import run_inputs_from_task
    if manager is None:
        manager = get_training_manager()
    contract_hash = contract.compute_hash() if hasattr(contract, 'compute_hash') else str(contract)
    run_inputs = run_inputs_from_task(contract_hash=contract_hash, config=config)
    smoke = smoke_gate.check(
        inputs=run_inputs, config=config,
        candidates=[(task.get_status_info().get('status') or task.status, task.task_dir)
                    for task in manager.tasks.values()],
    )
    if smoke['required'] and not smoke['ok']:
        raise TrainingServiceError('smoke_required', {'message': smoke['reason'], 'smoke_gate': smoke})
    task_id = manager.create_task(contract=contract, config=config, idempotency_key=idempotency_key)
    return {'success': True, 'task_id': task_id, 'smoke_gate': smoke,
            'message': 'Training task created successfully'}
