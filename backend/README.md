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
| Export/import project package | `POST /api/project/export`, `POST /api/project/import` |
| Training options | `GET /api/training/options` |
| Training tasks | `GET /api/training/list` |
| Scenario validation | `POST /api/scenarios/validate` |
| API documentation | `GET /docs` |

The health response includes `app_id=legged-studio`, `api_schema=legged-studio-api-1`,
the release version, and only the routes that successfully loaded. The desktop
launcher checks these identity fields before accepting an existing process on a
configured port.

`POST /api/models/import` accepts a list of UTF-8 XML files and base64-encoded
mesh files with relative paths. It stores the complete asset package under
`workspace/imports/<id>`, validates the selected URDF/MJCF, and returns a
generated Robot Contract draft. The Web workbench uses this route for user
assets; presets are only shortcuts for canonical Go2/Go2W fixtures.

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
`training/source/`; these profiles expose tuned rewards, terrain curricula,
actuator gains and PPO settings without changing the generic API.

The same importer accepts a ZIP of the ZEX-W source project (or any other robot
project). After extraction it persists one package directory containing the
model, `contract.json`, `robot_package.json`, recipes and scenario data. Its
historical source folders remain available as portable reference files; the
generic MJLab builder is the only training entrypoint.

## Tests

```powershell
python -m unittest discover -s backend -p "test_*.py" -v
```
