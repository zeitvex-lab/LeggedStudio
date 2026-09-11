---
name: robolab-export
description: Create and validate a traceable RoboLab PolicyArtifact manifest from a checkpoint without claiming deployment export.
---

# RoboLab export

Use this skill when the user asks to package a checkpoint for later consumption.

## Workflow

```bash
PYTHONPATH=src python -m robolab.cli workflow run export \
  --checkpoint <checkpoint> [--output <manifest.json>]
```

Verify that the checkpoint has a neighboring `resolved_config.json`. Inspect
the generated `policy_artifact.json` for framework, method, task, observation,
action, control timestep, joint order, and source configuration.

The current export is a provenance manifest only. Do not call it an ONNX,
TorchScript, deployment, or hardware-control artifact; those are P7 concerns.
