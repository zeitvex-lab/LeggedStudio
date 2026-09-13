"""The policy manifest (schema 2) and the checks a published policy has to pass.

One vocabulary for two shapes — a single-policy repo (fields at the top level) and the official
set (the same fields per entry under ``policies``). This module writes the first; the daemon
(`pollen-robotics/microduck`, ``updater/src/policy.rs`` and ``robotd-params``) reads both. The
contract is `docs/policy-manifest.md` over there; the numbers below are what the daemon publishes
in ``duck_ipc_proto`` and refuses a policy for disagreeing with.

Deliberately free of mjlab / torch imports so the tests run on a laptop in milliseconds and the
CLI can validate an ONNX file without a GPU.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

SCHEMA_VERSION = 2
# `duck_ipc_proto`: the daemon refuses a policy whose manifest disagrees with these, and refuses
# at load a network whose graph does. 61 = 48 proprioception + 13 command; 14 = the servos.
MODEL_API = 1
OBS_LEN = 61
ACTION_LEN = 14
ROBOT: dict[str, Any] = {"model": "microduck", "hw_rev": 1, "servos": "xl330", "control_hz": 50}

# The one `.onnx` a repo carries. The daemon takes the sole `.onnx` in a repo and refuses several.

KINDS: tuple[str, ...] = ("episodic", "perpetual")

ZERO_TWIST: tuple[float, float, float] = (0.0, 0.0, 0.0)

# The daemon's policy slots, for a gait's `slot` hint (display-only: `robotctl policy load <slot>`).
SLOTS: tuple[str, ...] = ("walk", "stand", "sitstand", "ground_pick", "kick_left", "kick_right", "roulade")


class ManifestError(ValueError):
    """A manifest that the daemon would refuse, or that would load and run wrongly."""


@dataclass(frozen=True)
class Provenance:
    """Where the weights came from. Display-only for the daemon; the part people skip by hand."""

    task_id: str | None = None
    repo: str = "pollen-robotics/microduck_rl"
    commit: str | None = None
    branch: str | None = None
    dirty: bool | None = None
    run: str | None = None
    checkpoint: int | None = None
    source_file: str | None = None
    exported: str = field(default_factory=lambda: _now_utc())

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_manifest(manifest: dict[str, Any]) -> None:
    """Refuse what the daemon would refuse, plus the mistakes it would load and run wrongly.

    Accepts both shapes and any schema version, because absence is not evidence — a repo is under
    no obligation to carry any field. Only a claim that is present and wrong fails.
    """
    if "policies" in manifest:
        for entry in manifest["policies"]:
            if "file" not in entry:
                raise ManifestError("every set entry needs a `file`")
            validate_manifest({k: v for k, v in entry.items() if k != "file"})
        return
    if (obs := manifest.get("obs_len")) is not None and obs != OBS_LEN:
        raise ManifestError(f"obs_len {obs}: this robot builds {OBS_LEN}")
    if (act := manifest.get("action_len")) is not None and act != ACTION_LEN:
        raise ManifestError(f"action_len {act}: this robot has {ACTION_LEN}")
    if (api := manifest.get("model_api")) is not None and api > MODEL_API:
        raise ManifestError(f"model_api {api}: this repo targets {MODEL_API}")
    model = (manifest.get("robot") or {}).get("model")
    if model is not None and model.lower() != ROBOT["model"]:
        raise ManifestError(f"robot.model {model!r}: this is a {ROBOT['model']} policy repo")
    kind = manifest.get("kind")
    if kind is not None and kind not in (*KINDS, "scripted"):
        raise ManifestError(f"kind {kind!r} is not one of episodic, perpetual, scripted")
    encoding = (manifest.get("command") or {}).get("encoding")
    if encoding is not None and encoding not in ("constant", "phase", "posture_flag"):
        raise ManifestError(f"command.encoding {encoding!r} is not one the daemon drives")
    if kind == "episodic" and encoding in (None, "constant"):
        duration = manifest.get("duration_s")
        if duration is None or duration <= 0:
            raise ManifestError("an episodic constant-command policy needs duration_s > 0")
    idle = (manifest.get("command") or {}).get("idle")
    if idle is not None and len(idle) != 3:
        raise ManifestError("command.idle is a 3-vector twist")


# ---------------------------------------------------------------------------------------------
# The ONNX file: the shape gate the daemon applies at load, applied before the upload.


@dataclass(frozen=True)
class OnnxShape:
    input_name: str
    output_name: str
    obs_len: int
    action_len: int


def inspect_onnx(path: Path) -> OnnxShape:
    """The graph's single input and output widths, as the daemon checks them at load."""
    import onnx

    model = onnx.load(str(path), load_external_data=False)
    graph = model.graph
    initializers = {i.name for i in graph.initializer}
    inputs = [i for i in graph.input if i.name not in initializers]
    if len(inputs) != 1 or len(graph.output) != 1:
        raise ManifestError(
            f"{path.name}: expected one input and one output, found "
            f"{[i.name for i in inputs]} -> {[o.name for o in graph.output]}"
        )

    def last_dim(value) -> int:
        dims = value.type.tensor_type.shape.dim
        if not dims:
            raise ManifestError(f"{path.name}: {value.name} has no shape")
        last = dims[-1]
        if not last.HasField("dim_value"):
            raise ManifestError(f"{path.name}: {value.name}'s last dimension is symbolic")
        return int(last.dim_value)

    return OnnxShape(
        input_name=inputs[0].name,
        output_name=graph.output[0].name,
        obs_len=last_dim(inputs[0]),
        action_len=last_dim(graph.output[0]),
    )


# ---------------------------------------------------------------------------------------------
# What else goes in the repo.


def install_commands(manifest: dict[str, Any], repo_id: str) -> str:
    """The `robotctl` lines that put this policy on a robot — one story per shape.

    Episodic: a skill, length from the manifest. Perpetual with `unwind_s`: a held pose the owner
    runs as a skill with `--hold`. Perpetual without: a gait, loaded into a slot.
    """
    name = manifest["name"]
    if manifest["kind"] == "episodic":
        return f"sudo robotctl policy add {name} {repo_id}\nrobotctl robot do {name}"
    if manifest.get("unwind_s") is not None:
        return f"sudo robotctl policy add {name} {repo_id} --hold <seconds>\nrobotctl robot do {name}"
    slot = manifest.get("slot", "<slot>")
    return f"sudo robotctl policy load {slot} {repo_id}"


