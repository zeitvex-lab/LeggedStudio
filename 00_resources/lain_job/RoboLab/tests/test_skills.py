from __future__ import annotations

import json

from robolab.workflows import list_workflows, run_workflow


def test_builtin_skill_registry_is_complete() -> None:
    assert list_workflows() == ("evaluate", "export", "reproduce", "train")


def test_train_skill_delegates_to_selected_runtime(monkeypatch) -> None:
    captured = {}

    def fake_train(**kwargs):
        captured.update(kwargs)
        return {"checkpoint": "model_1.pt"}

    monkeypatch.setattr("robolab.workflows.builtin.run_isaacgym_train", fake_train)
    result = run_workflow(
        "train", framework="isaacgym", task="a1", method="ppo_ee",
        robot="unitree_a1", num_envs=2, device="cpu", seed=3, max_iterations=1,
    )
    assert result.status == "completed"
    assert captured["task_id"] == "a1"
    assert captured["method_id"] == "ppo_ee"


def test_export_skill_writes_policy_artifact_manifest(tmp_path) -> None:
    checkpoint = tmp_path / "model_1.pt"
    checkpoint.write_bytes(b"checkpoint")
    (tmp_path / "resolved_config.json").write_text(json.dumps({
        "framework": "isaacgym", "task": "a1_ee", "method": "ppo_ee"
    }))
    result = run_workflow("export", checkpoint=checkpoint)
    manifest = tmp_path / "policy_artifact.json"
    assert result.status == "completed"
    assert manifest.is_file()
    payload = json.loads(manifest.read_text())
    assert payload["task"] == "a1_ee"
    assert payload["action"]["shape"] == [12]
