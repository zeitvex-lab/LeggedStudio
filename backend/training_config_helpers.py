"""Training configuration introspection helpers.

Pure helper functions for training profile introspecition: terrain mix
normalization, observation/temination summaries, schema workspace resolution,
and worker-based schema dumping. Extracted from ``training_api.py`` to reduce
the size of the god file and enable independent testing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, List, Optional

from fastapi import HTTPException

_ROOT = Path(__file__).resolve().parents[1]
_SCHEMA_TIMEOUT_S = 60


def terrain_mixes(terrain: Any) -> Optional[List[dict]]:
    """Normalize a profile terrain block into a flat sub-terrain mix list."""
    if not isinstance(terrain, dict):
        return None
    subs = terrain.get("sub_terrains")
    if isinstance(subs, dict):
        return [{"name": str(name), "proportion": value} for name, value in subs.items()]
    if isinstance(subs, list):
        return [{"name": str(name), "proportion": None} for name in subs]
    return None


def observation_summary(contract: dict, profile: dict) -> Optional[str]:
    """Build a human-readable observation dimension/component summary."""
    observation = contract.get("observation") if isinstance(contract.get("observation"), dict) else {}
    parts: List[str] = []
    if observation.get("dimension") is not None:
        parts.append(f"{observation['dimension']} 维")
    components = observation.get("components")
    if isinstance(components, list) and components:
        parts.append(" + ".join(str(item) for item in components))
    if profile.get("history_length"):
        parts.append(f"历史 {profile['history_length']} 步堆叠")
    return "；".join(parts) if parts else None


def terminations_summary(profile: dict) -> Optional[str]:
    """Build a human-readable termination condition summary."""
    terminations = profile.get("terminations")
    if isinstance(terminations, dict) and terminations:
        return "、".join(str(name) for name in terminations)
    if isinstance(terminations, list) and terminations:
        return "、".join(str(item) for item in terminations)
    reward_terms = profile.get("reward_terms")
    if isinstance(reward_terms, list) and any("terminat" in str(term) for term in reward_terms):
        return "配方内置失败终止（is_terminated 计入奖励惩罚）；完整终止项由配方源码决定"
    return None


def domain_randomization(profile: dict) -> Optional[dict]:
    """Extract the domain-randomization block if present."""
    for key in ("domain_randomization", "domain_rand", "randomization", "noise"):
        value = profile.get(key)
        if isinstance(value, dict) and value:
            return {"source_key": key, **value}
    return None


def schema_workspace() -> Path:
    """Resolve the schema-cache workspace directory."""
    configured = os.environ.get("LEGGED_STUDIO_WORKSPACE")
    return Path(configured).expanduser().resolve() if configured else _ROOT / "workspace"


def schema_cache_path(profile_id: str) -> Path:
    """Resolve the per-profile schema cache file path."""
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(profile_id)) or "profile"
    return schema_workspace() / "schema_cache" / f"{safe}.json"


def schema_interpreter() -> Optional[Path]:
    """Pick an interpreter able to import the profile's source dependencies."""
    from adapters.mjlab.native_adapter import _venv_python

    candidates = []
    candidates.append(_venv_python(_ROOT / "adapters" / "mjlab" / ".venv"))
    explicit = os.environ.get("LEGGED_STUDIO_MJLAB_PYTHON")
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(Path(sys.executable))
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            probe = subprocess.run(
                [str(candidate), "-c", "import mjlab"],
                capture_output=True,
                timeout=30,
            )
            if probe.returncode == 0:
                return candidate
        except (OSError, subprocess.SubprocessError):
            continue
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def read_profile_mtime(profile: dict) -> Optional[float]:
    """Return the mtime of a profile file, or None if unreadable."""
    raw_path = profile.get("path")
    if not raw_path:
        return None
    profile_path = Path(str(raw_path))
    if not profile_path.is_absolute():
        profile_path = _ROOT / profile_path
    try:
        return profile_path.stat().st_mtime
    except OSError:
        return None


def dump_schema_via_worker(robot_id: str, profile_id: str, profile: dict, package_root: str) -> dict:
    """Spawn the adapter interpreter in --dump-schema mode and parse its JSON."""
    interpreter = schema_interpreter()
    if interpreter is None:
        raise HTTPException(
            status_code=501,
            detail={"message": "需要先配置运行时：未找到 MJLab 适配器 Python 解释器（adapters/mjlab/.venv）", "robot_id": robot_id, "profile_id": profile_id},
        )
    source_root = str(profile.get("source_root", "training/source"))
    dump_config = {
        "profile_id": profile_id,
        "package_root": package_root,
        "source_root": source_root,
        "entrypoints": profile.get("entrypoints") or {},
    }
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    schema_out = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    try:
        json.dump(dump_config, tmp, ensure_ascii=False)
        tmp.close()
        schema_out.close()
        source_abs = Path(source_root)
        if not source_abs.is_absolute():
            source_abs = Path(package_root) / source_abs
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join([str(source_abs), env.get("PYTHONPATH", "")]).strip(os.pathsep)
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            completed = subprocess.run(
                [
                    str(interpreter),
                    "-m", "adapters.mjlab.native_worker",
                    "--dump-schema",
                    "--config", tmp.name,
                    "--schema-output", schema_out.name,
                ],
                cwd=str(_ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=_SCHEMA_TIMEOUT_S,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise HTTPException(status_code=502, detail={"message": f"schema dump worker failed to launch: {exc}", "interpreter": str(interpreter)}) from exc
        schema = None
        schema_file = Path(schema_out.name)
        if schema_file.exists() and schema_file.stat().st_size > 0:
            try:
                schema = json.loads(schema_file.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError:
                schema = None
        if schema is None:
            stdout = completed.stdout or ""
            start = stdout.find("{")
            if start >= 0:
                try:
                    schema, _end = json.JSONDecoder().raw_decode(stdout[start:])
                except json.JSONDecodeError:
                    schema = None
        if completed.returncode != 0 or not isinstance(schema, dict) or not schema:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "schema dump worker did not return a config tree",
                    "interpreter": str(interpreter),
                    "returncode": completed.returncode,
                    "stderr": (completed.stderr or "")[-800:],
                    "stdout_head": (completed.stdout or "")[:300],
                },
            )
        return schema
    finally:
        for handle in (tmp, schema_out):
            try:
                os.unlink(handle.name)
            except OSError:
                pass


# Re-export private aliases for backward-compat with training_api.py
_terrain_mixes = terrain_mixes
_observation_summary = observation_summary
_terminations_summary = terminations_summary
_domain_randomization = domain_randomization
_schema_workspace = schema_workspace
_schema_cache_path = schema_cache_path
_schema_interpreter = schema_interpreter
_read_profile_mtime = read_profile_mtime
_dump_schema_via_worker = dump_schema_via_worker
