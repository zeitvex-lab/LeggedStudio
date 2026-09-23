import json
from pathlib import Path

from backend.paths import workspace_root

EFFECTIVE_CONFIG_SCHEMA = 'training-effective-config-1.0'


def schema_cache_path(profile_id: str) -> Path:
    safe = ''.join(ch if ch.isalnum() or ch in '._-' else '_' for ch in str(profile_id)) or 'profile'
    return workspace_root() / 'schema_cache' / f'{safe}.json'


def cached_param_catalog(profile_id: str) -> list[dict] | None:
    try:
        cached = json.loads(schema_cache_path(profile_id).read_text(encoding='utf-8-sig'))
    except (OSError, json.JSONDecodeError):
        return None
    schema = cached.get('schema') if isinstance(cached, dict) else None
    if not isinstance(schema, dict) or schema.get('schema') != EFFECTIVE_CONFIG_SCHEMA:
        return None
    from adapters.mjlab.param_descriptors import resolve_params
    return [{**item, 'path': item['id']} for item in resolve_params(schema)]
