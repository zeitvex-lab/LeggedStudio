# Backend API

The production control plane entry point is `backend/api_complete.py`.

## Run locally

```powershell
python -m uvicorn backend.api_complete:app --host 127.0.0.1 --port 8765
```

Useful endpoints:

| Purpose | Endpoint |
| --- | --- |
| Health and identity | `GET /health` |
| Runtime capabilities | `GET /api/system/capabilities` |
| Adapter readiness | `GET /api/adapters/status` |
| Environment status | `GET /api/system/environment` |
| Asset inventory | `GET /api/assets/summary` |
| Robot presets | `GET /api/robots/presets` |
| Import model assets | `POST /api/models/import` |
| Validate model/report | `POST /api/models/validate` |
| Render model preview | `POST /api/models/preview` |
| Browser-native sim2sim manifest | `GET /api/simulation/browser-config/{robot_id}` |
| Policy acceptance (headless) | `POST /api/simulation/policies/acceptance` |
| Export/import project package | `POST /api/project/export`, `POST /api/project/import` |
| Training options | `GET /api/training/options` |
| Training tasks | `GET /api/training/list` |
| Training config introspection | `GET /api/training/config-preview`, `GET /api/training/profile-schema` |
| Scenario validation | `POST /api/scenarios/validate` |
| API documentation | `GET /docs` |

The health response includes `app_id=legged-studio`, `api_schema=legged-studio-api-1`,
the release version, and only the routes that successfully loaded. The desktop
launcher checks these identity fields before accepting an existing process on a
configured port.

`POST /api/models/import` accepts a list of UTF-8 XML files and base64-encoded
mesh files with relative paths. It stores the complete asset package under
`workspace/packages/<package-id>`, validates the selected URDF/MJCF, and returns a
generated Robot Contract draft. The Web workbench uses this route for user
assets; presets are only shortcuts for canonical Go2/ZEX-W fixtures.

Project packages are ZIP files with a versioned manifest. They contain imported
robot assets, their contracts, the active MJLab training recipe and the active
MuJoCo scenario. Package import rewrites model paths into the local workspace
and never executes files from the archive.

## Robot packages

Every imported robot is stored as a package with `robot_package.json`,
`contract.json`, its MJCF/URDF and referenced meshes. Every package uses the
same generic MJLab task builder. Historical source code may be retained in the
package for reference, but it is never an execution requirement.
Mature robot projects can additionally ship `training/profiles/*.json` and
`training/source/`. Each profile declares `source_root` plus
`entrypoints.env` and `entrypoints.runner` (optionally
`entrypoints.runner_class`); the isolated MJLab worker loads those factories
and registers the resulting task through the same API. When no profile is
selected, the generic Contract builder remains the fallback.

All 16 shipped packages carry profiles (55 in total, all passing the
`tools/validate_training_smoke.py` rollout smoke). Implementation styles span
generic-contract builds (A1/B2/B2W/D1/TRON1), slim local velocity sources
(A2/H1_2/Go2W/ZEX-W/Lite3/B2), and full local task frameworks (Go2
`local_tasks`, G1 amp/tracking, microduck, wuji_hand, M20).

The same importer accepts a ZIP of the ZEX-W source project (or any other robot
project). After extraction it persists one package directory containing the
model, `contract.json`, `robot_package.json`, recipes and scenario data. Its
historical source folders remain available as portable reference files; the
the selected profile or generic Contract task is the training entrypoint.

## Browser simulation

`/sim2sim/` is the 1000framesai-style path. The browser loads MuJoCo WASM,
Three.js and ONNX Runtime Web, copies the selected package's MJCF and meshes
into the WASM virtual filesystem, then advances physics and renders every
frame locally. The Python MuJoCo session API remains available for headless
verification and automation; it is not used for the browser render loop.

## Tests

```powershell
python -m unittest discover -s backend -p "test_*.py" -v
```
