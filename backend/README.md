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

## Tests

```powershell
python -m unittest discover -s backend -p "test_*.py" -v
```
