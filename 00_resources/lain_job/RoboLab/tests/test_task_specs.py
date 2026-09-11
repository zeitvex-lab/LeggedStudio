from __future__ import annotations

import pytest

from robolab.tasks import get_task_spec, list_task_specs, resolve_training_recipe


def test_task_specs_expose_canonical_backend_mapping() -> None:
    spec = get_task_spec("a1_cts", framework="isaacgym", method="cts")
    assert spec.task_id == "legacy_velocity.unitree_a1"
    assert spec.backend_task("isaacgym", "cts") == "a1_cts"
    assert spec.action_dim == 12


def test_recipe_resolution_rejects_unregistered_uploaded_model() -> None:
    with pytest.raises(ValueError, match="inspection-only"):
        resolve_training_recipe({
            "framework": "isaacgym",
            "task": "velocity_flat.unitree_go2",
            "method": "ppo",
            "model": "resources/robots/unitree_a1/urdf/unitree_a1.urdf",
            "run_dir": "logs/test",
        })


def test_recipe_resolution_uses_explicit_resume_only(tmp_path) -> None:
    resolved = resolve_training_recipe({
        "framework": "isaacgym",
        "task": "velocity_flat.unitree_a1",
        "method": "ppo",
        "run_dir": str(tmp_path),
        "checkpoint": "logs/does-not-exist.pt",
    })
    assert resolved["resume_from"] is None
    assert resolved["checkpoint_interval"] == 300
    assert resolved["use_standing_pose"] is False
    assert resolved["joint_defaults"] == {}


def test_standing_pose_override_is_explicit(tmp_path) -> None:
    resolved = resolve_training_recipe({
        "framework": "isaacgym",
        "task": "velocity_flat.unitree_a1",
        "method": "ppo",
        "run_dir": str(tmp_path),
        "use_standing_pose": True,
        "joints": {"FL_thigh_joint": {"default": 0.42}},
    })
    assert resolved["joint_defaults"]["FL_thigh_joint"] == 0.42
