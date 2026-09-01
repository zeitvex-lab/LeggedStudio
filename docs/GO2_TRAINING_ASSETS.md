# Go2 and Go2W training assets

Legged Studio now carries two self-contained canonical MuJoCo assets sourced from the local UniLab snapshot:

| Preset | Contract | Format | Class | Actuators | Compiled mass |
|---|---|---|---|---:|---:|
| Unitree Go2 | `unitree_go2_mvp_v1` | `go2.xml` | M-P | 12 | 15.206408 kg |
| Unitree Go2W | `unitree_go2w_mvp_v1` | `go2w.xml` | M-W | 16 | 19.126408 kg |

Assets live under `assets/robots/` with their mesh files in a sibling `assets/` directory. Contracts and default forward-walk recipes are checked in at:

```text
contracts/fixtures/unitree_go2.v2.json
contracts/fixtures/unitree_go2w.v2.json
presets/training/unitree_go2_forward_walk.json
presets/training/unitree_go2w_forward_walk.json
```

The Web training form reads `/api/robots/presets` and submits the selected Contract, so action dimensions and joint order are no longer hard-coded. Go2 uses 12 actions and Go2W uses 16 actions including the four wheel joints.

Training options are exposed by `/api/training/options`. PPO is currently the available algorithm. Each listed reward term has an editable weight and an enable toggle; the resulting map is stored in the task configuration and applied by the MuJoCo environment. Disabling a term writes a zero weight, which keeps runs reproducible and auditable.

## Adapter environment

The control plane remains on Python 3.12. The MJLab adapter is isolated in `adapters/mjlab/.venv` (or `adapters/mjlab_new/.venv` when present). The training launcher checks both locations and uses the first available environment. Install/update the adapter from its project file:

```powershell
uv sync --project adapters/mjlab --extra cu128
```

Run the dependency and GPU preflight before a long run:

```powershell
python adapters/mjlab/preflight.py
```

The `mjlab_new` worker now performs real MuJoCo rollouts against the canonical MJCF and PPO updates against those observations, then writes PyTorch checkpoints and a `PolicyArtifact`. The saved `env_config.json` records the canonical MJCF path, mesh directory, robot family, M-P/M-W class, action/observation dimensions, control rates, terrain, and command ranges. Native MJLab registry task integration remains optional because the local MJLab release only ships Go1/G1 task modules; the Contract-driven environment is the stable product adapter boundary.
