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
| Training options | `GET /api/training/options` |
| Training tasks | `GET /api/training/list` |
| Scenario validation | `POST /api/scenarios/validate` |
| API documentation | `GET /docs` |

The health response includes `app_id=legged-studio`, `api_schema=legged-studio-api-1`,
the release version, and only the routes that successfully loaded. The desktop
launcher checks these identity fields before accepting an existing process on a
configured port.

## Tests

```powershell
python -m unittest discover -s backend -p "test_*.py" -v
```
