# Go2 and ZEX-W training assets

The current product line contains two Robot Packages: Unitree Go2 and ZEX-W.
The filename is retained for compatibility with existing documentation links;
this document describes both supported packages.

| Preset | Contract | Format | Class | Actions | Package root |
| --- | --- | --- | --- | ---: | --- |
| Unitree Go2 | `unitree_go2_mvp_v1` | MJCF | M-P | 12 | `assets/robots/unitree_go2` (persisted copies supported) |
| ZEX-W | `zex-w_contract_v1` | MJCF | M-W | 16 | `workspace/packages/zex-w` |

Each robot follows the same package layout:

```text
workspace/packages/<package-id>/
  robot_package.json
  contract.json
  model/robot.xml
  model/assets/
  training/config.json
  training/profiles/
  training/source/
  simulation/config.json
```

Every source-backed training profile uses the same robot-neutral fields:

| Field | Purpose |
| --- | --- |
| `source_root` | Import root inside the persisted package |
| `entrypoints.env` | MJLab environment factory (`module:callable`) |
| `entrypoints.runner` | Algorithm runner-config factory |
| `entrypoints.runner_class` | Optional custom runner class |
| `entrypoints.configure` | Optional package hook for robot-specific field mapping |
| `runner` | UI-editable algorithm defaults |
| `command_ranges` | UI-editable unified `lin_vel_x`, `lin_vel_y`, `ang_vel_z` ranges |

The Web UI and native worker never branch on a robot id. A package that needs
special joint mappings, sensors, rewards, terrain, or command semantics keeps
that implementation below `training/source/` and exposes it through these
entrypoints. Project ZIP import/export copies the complete package tree, so
profiles and their source modules remain available after persistence.

The Web training form reads `/api/robots/presets` and submits the selected
Contract. Action dimensions and joint order therefore come from package data,
not from UI or worker conditionals. Go2 has 12 position actions. ZEX-W has 16
actions covering twelve leg joints and four wheel joints; its maintained
training profiles live under `training/profiles/`.

Go2's LLoco implementation uses the package extension contract shared by all
robots: `extension_entrypoint` registers the package asset factory under
MJLab's canonical asset-zoo path. The backend does not import or depend on
`unitree_rl_mjlab`; robot-specific XML, actuators, observations, rewards, and
terrain logic remain inside the Go2 package profile.

Training options are exposed by `/api/training/options`. PPO is currently the
available native MJLab algorithm. Each reward term has an editable weight and
enable toggle. The resolved recipe and selected package profile are stored with
the task so runs remain reproducible and auditable.

## Adapter environment

The control plane remains on Python 3.12. The unified MJLab adapter and its
isolated environment live in `adapters/mjlab`:

```powershell
uv sync --project adapters/mjlab --extra cu128
python adapters/mjlab/preflight.py
```

The native worker builds manager-based MJLab tasks from Robot Package metadata
and selected training profiles. It writes RSL-RL checkpoints and a
`PolicyArtifact`; MuJoCo is retained for interactive simulation sessions, not
as a training backend.
