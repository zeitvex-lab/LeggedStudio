# Legged Studio workflow

This document records the implemented MVP slice derived from the project vision, the local reference inventory, and the public 1000framesAI workflow.

## Implemented path

```text
desktop launcher
    -> control plane health check
    -> robot asset inventory / preset selection
    -> Contract-backed training task
    -> MuJoCo rollout + PPO update
    -> checkpoint + PolicyArtifact
    -> local evaluation result
    -> optional ONNX export
```

The control plane remains responsible for orchestration. Training code runs in a worker process, and adapter environments stay separate from FastAPI dependencies.

## API entry points

| Purpose | Endpoint | Notes |
|---|---|---|
| Robot inventory | `GET /api/assets` | Filters: `family`, `size`, `locomotion`, `readiness` |
| Robot presets | `GET /api/robots/presets` | Returns Go2/Go2W Contract and forward-walk recipe |
| Training options | `GET /api/training/options` | Reports available algorithms and reward terms |
| Create training | `POST /api/training/create` | Validates Contract before spawning worker |
| Task status | `GET /api/training/{task_id}/status` | Progress and current reward |
| Stop task | `POST /api/training/{task_id}/stop` | Terminates worker and records stopped state |
| Artifacts | `GET /api/export/list` | Lists completed ONNX exports |
| Evaluate | `POST /api/evaluation/run` | Deterministic local Contract-MuJoCo replay |

## Web workbenches

- `web/assets.html`: inventory browsing and asset detail, following the 1000framesAI robot configuration step.
- `web/training_create.html`: preset selection, PPO parameters, terrain selection, and editable reward weights.
- `web/training_list.html`: task filtering, status, progress, and stop action.
- `web/training_monitor.html`: live progress and worker logs.
- `web/artifacts.html`: ONNX export and download entry points.
- `web/evaluation.html`: local policy replay and metric summary.

## Reproduce a minimal run

```powershell
cd C:\Users\31560\Documents\00_open\legged_studio
python scripts\generate_robot_presets.py
python adapters\mjlab\train_worker.py `
  --contract contracts\fixtures\unitree_go2.v2.json `
  --config presets\training\unitree_go2_forward_walk.json `
  --output workspace\go2_smoke `
  --task-id go2_smoke
```

For an API-managed run, start `python -m uvicorn backend.api_complete:app --host 127.0.0.1 --port 8765`, select a preset from `GET /api/robots/presets`, and submit the returned Contract to `/api/training/create`. After the worker reaches `completed`, call `/api/evaluation/run` with the task ID.

## Capability boundary

Go2 and Go2W are real Contract-MuJoCo/PPO training presets. The isolated native MJLab worker registers the Unitree Go2 and Go2W manager-based tasks, writes RSL-RL checkpoints/artifacts, and exposes native evaluation/navigation through the same control-plane APIs. SAC and TD3 remain local-adapter options until their complete native checkpoint path is implemented. GPU readiness is reported by adapter preflight and must be verified on the target machine.
