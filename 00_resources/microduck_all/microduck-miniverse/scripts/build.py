#!/usr/bin/env python3
"""Build deterministic Miniverse bundles from the published Microduck checkpoints."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import onnx

ROOT = Path(__file__).parents[1]
JOINT_NAMES = [
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
    "neck_pitch", "head_pitch", "head_yaw", "head_roll",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
]
METADATA_KEY = "com.dollhouserobotics.miniverse.simulation_contract"
SCHEMA_KEY = "com.dollhouserobotics.miniverse.simulation_contract_schema_version"
HASH_KEY = "com.dollhouserobotics.miniverse.simulation_contract_hash"


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_contract(model, policy):
    executable = onnx.ModelProto()
    executable.CopyFrom(model)
    del executable.metadata_props[:]
    model_sha = hashlib.sha256(executable.SerializeToString(deterministic=True)).hexdigest()
    slices = [
        {"start": 0, "length": 3, "provider": "bodyAngularVelocity", "ids": ["trunk_base"], "frame": "body"},
        {"start": 3, "length": 3, "provider": "projectedGravity", "ids": ["trunk_base"], "frame": "body"},
        {"start": 6, "length": 14, "provider": "jointPosition", "ids": JOINT_NAMES},
        {"start": 20, "length": 14, "provider": "jointVelocity", "ids": JOINT_NAMES},
        {"start": 34, "length": 14, "provider": "previousAction"},
        {"start": 48, "length": 13, "provider": "constant", "value": [0.0] * 13},
    ]
    contract = {
        "schemaVersion": "0.3",
        "precision": "fp32",
        "modelSha256": model_sha,
        "skeletonId": policy["id"],
        "compatibleSceneContractHashes": [policy["sceneContractHash"]],
        "backends": [{"id": "mujoco-cpu", "versionRange": ">=3.3,<4", "providers": ["CPUExecutionProvider"]}],
        "opset": 18,
        "execution": {"kind": "singlePolicyStep"},
        "rates": {
            "physicsHz": 200, "policyHz": 50, "publishHz": 50,
            "actionHold": "zero-order-hold", "commandBoundary": "policy",
            "controlLoop": "policy-then-decimation",
        },
        "inputs": [{"name": "obs", "dtype": "float32", "shape": [1, 61], "slices": slices}],
        "outputs": [{
            "name": "actions", "dtype": "float32", "shape": [1, 14],
            "role": "actuatorTargets", "actuators": JOINT_NAMES,
            "controlMode": "position", "actuatorRanges": [[-10.0, 10.0] for _ in JOINT_NAMES],
            "clip": [-10.0, 10.0], "failsafe": [0.0] * 14,
        }],
        "commands": [],
        "stateEstimation": {"mode": "simulator-ground-truth"},
        "provenance": {
            "sourceRepository": "https://huggingface.co/spaces/pollen-robotics/microduck-simulator",
            "sourceRevision": "10c600e54ea52f239887308387cb8fc458ecb3e4",
            "sourceCheckpoint": policy["checkpoint"],
            "sourceCheckpointSha256": sha256(ROOT / "checkpoints" / policy["checkpoint"]),
            "controller": "policy.py:MicroduckPolicy",
            "controllerTransformsOutput": "default pose plus normalized joint offset",
            "graphTransform": "Elu lowered to Exp, Sub, Greater, and Where",
        },
    }
    contract["contractHash"] = hashlib.sha256(canonical_json(contract)).hexdigest()
    return contract


def lower_elu(model):
    """Lower ONNX Elu to the Miniverse runtime primitive allowlist."""
    rewritten = []
    for index, node in enumerate(model.graph.node):
        if node.op_type != "Elu":
            rewritten.append(node)
            continue
        alpha = next((attribute.f for attribute in node.attribute if attribute.name == "alpha"), 1.0)
        prefix = f"miniverse_elu_{index}"
        zero, one = prefix + "_zero", prefix + "_one"
        model.graph.initializer.extend([
            onnx.helper.make_tensor(zero, onnx.TensorProto.FLOAT, [], [0.0]),
            onnx.helper.make_tensor(one, onnx.TensorProto.FLOAT, [], [1.0]),
        ])
        exp, negative, condition = prefix + "_exp", prefix + "_negative", prefix + "_condition"
        rewritten.extend([
            onnx.helper.make_node("Exp", node.input, [exp], name=prefix + "/Exp"),
            onnx.helper.make_node("Sub", [exp, one], [negative], name=prefix + "/Sub"),
        ])
        selected = negative
        if alpha != 1.0:
            alpha_name, scaled = prefix + "_alpha", prefix + "_scaled"
            model.graph.initializer.append(
                onnx.helper.make_tensor(alpha_name, onnx.TensorProto.FLOAT, [], [alpha])
            )
            rewritten.append(
                onnx.helper.make_node("Mul", [negative, alpha_name], [scaled], name=prefix + "/Mul")
            )
            selected = scaled
        rewritten.extend([
            onnx.helper.make_node("Greater", [node.input[0], zero], [condition], name=prefix + "/Greater"),
            onnx.helper.make_node(
                "Where", [condition, node.input[0], selected], node.output,
                name=node.name or prefix + "/Where",
            ),
        ])
    del model.graph.node[:]
    model.graph.node.extend(rewritten)
    onnx.checker.check_model(model, full_check=True)


def write_model(source, destination, policy):
    model = onnx.load(str(source), load_external_data=False)
    lower_elu(model)
    contract = model_contract(model, policy)
    kept = [(item.key, item.value) for item in model.metadata_props if item.key not in {METADATA_KEY, SCHEMA_KEY, HASH_KEY}]
    del model.metadata_props[:]
    for key, value in kept + [
        (METADATA_KEY, canonical_json(contract).decode()),
        (SCHEMA_KEY, "0.3"),
        (HASH_KEY, contract["contractHash"]),
    ]:
        item = model.metadata_props.add()
        item.key, item.value = key, value
    onnx.save_model(model, str(destination))


def command_manifest(policy):
    mode = policy["mode"]
    if mode in {"walking", "roller"}:
        speed_range = [-0.5, 0.6] if mode == "roller" else [-0.2, 0.25]
        yaw_range = [-0.3, 0.3] if mode == "roller" else [-1.0, 1.0]
        return [
            {"id": "forward-speed", "kind": "scalar", "label": "Forward speed", "unit": "m/s", "default": 0.0, "range": speed_range, "step": 0.05, "frame": "root", "sliceLength": 1, "update": "continuous"},
            {"id": "yaw-rate", "kind": "scalar", "label": "Yaw rate", "unit": "rad/s", "default": 0.0, "range": yaw_range, "step": 0.05, "frame": "root", "sliceLength": 1, "update": "continuous"},
        ]
    if mode == "sitstand":
        return [{"id": "sit", "kind": "boolean", "label": "Sit", "unit": "boolean", "default": False, "range": [0, 1], "step": 1, "frame": "task", "sliceLength": 1, "update": "continuous"}]
    if mode in {"ground-pick", "roller-crouch", "kick", "roulade"}:
        return [{"id": "trigger", "kind": "momentary", "label": "Run motion", "unit": "boolean", "default": False, "range": [0, 1], "step": 1, "frame": "task", "sliceLength": 1, "update": "edge"}]
    return []


def manifest(policy):
    commands = command_manifest(policy)
    value = {
        "version": "v1", "id": policy["id"], "name": policy["name"],
        "description": policy["description"], "primarySimulator": "mujoco",
        "embodiment": {"appearance": {"geometry": "auto", "color": "#f2a900"}},
        "models": [{"id": "policy"}],
        "program": {"apiVersion": "dhr.python-policy/v1", "entrypoint": "policy:MicroduckPolicy"},
        "metadata": {
            "mode": policy["mode"], "checkpoint": policy["checkpoint"],
            "checkpointSha256": sha256(ROOT / "checkpoints" / policy["checkpoint"]),
            "embodimentArchive": policy["embodiment"],
            "embodimentSha256": sha256(ROOT / "embodiments" / policy["embodiment"]),
            "policySourceRevision": "10c600e54ea52f239887308387cb8fc458ecb3e4",
            "embodimentSourceRevision": "d424a0c899f6b33cbd3daeb279913134349c0b63",
        },
    }
    for key in ("runSeconds", "phasePeriodSeconds", "phaseEnd"):
        if key in policy:
            value["metadata"][key] = policy[key]
    if commands:
        value["commands"] = commands
        value["ui"] = {"components": [
            {"id": command["id"] + "-control", "renderer": "builtin/" + command["kind"], "commandId": command["id"]}
            for command in commands
        ]}
    return value


def deterministic_zip(source, destination):
    timestamp = (2026, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for relative in ("bundle.json", "policy.py", "embodiment/mjcf.zip", "models/policy.onnx"):
            info = zipfile.ZipInfo(relative, timestamp)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (source / relative).read_bytes())


def build_one(policy, output):
    with tempfile.TemporaryDirectory(prefix="microduck-miniverse-") as directory:
        stage = Path(directory)
        (stage / "embodiment").mkdir()
        (stage / "models").mkdir()
        (stage / "bundle.json").write_text(json.dumps(manifest(policy), indent=2) + "\n")
        shutil.copyfile(ROOT / "policy.py", stage / "policy.py")
        shutil.copyfile(ROOT / "embodiments" / policy["embodiment"], stage / "embodiment" / "mjcf.zip")
        write_model(ROOT / "checkpoints" / policy["checkpoint"], stage / "models" / "policy.onnx", policy)
        deterministic_zip(stage, output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", action="append", help="Build only this bundle id; repeatable")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--skip-validate", action="store_true")
    args = parser.parse_args()
    config = json.loads((ROOT / "policies.json").read_text())
    selected = [item for item in config["policies"] if not args.only or item["id"] in args.only]
    missing = set(args.only or ()) - {item["id"] for item in selected}
    if missing:
        raise SystemExit("unknown bundle id(s): " + ", ".join(sorted(missing)))
    args.output.mkdir(parents=True, exist_ok=True)
    for policy in selected:
        destination = args.output / (policy["id"] + ".dhsim")
        build_one(policy, destination)
        print(f"built {destination.relative_to(ROOT)} sha256={sha256(destination)}")
        if not args.skip_validate:
            subprocess.run(["miniverse", "bundle", "validate", str(destination), "--json"], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
