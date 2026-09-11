from robolab.frameworks.mjlab.runtime import (
    resolve_mjlab_source,
    run_mjlab_evaluate,
    run_mjlab_play,
    run_mjlab_smoke,
    run_mjlab_train,
)
from robolab.robots.unitree_a1.bindings.mjlab import CONTROL_DT, canonical_mjcf
from robolab.robots.unitree_a1.spec import ACTION, UNITREE_A1_JOINT_ORDER


def test_resolve_mjlab_checkout(tmp_path) -> None:
    package = tmp_path / "src" / "mjlab"
    package.mkdir(parents=True)
    (package / "__init__.py").touch()

    assert resolve_mjlab_source(tmp_path) == tmp_path / "src"


def test_run_mjlab_train_builds_worker_request(monkeypatch, tmp_path) -> None:
    captured = None

    def fake_run_worker(*arguments: str) -> dict[str, str]:
        nonlocal captured
        captured = arguments
        return {"checkpoint": "model_0.pt"}

    monkeypatch.setattr("robolab.frameworks.mjlab.runtime._run_worker", fake_run_worker)
    result = run_mjlab_train(num_envs=8, max_iterations=2, run_dir=tmp_path)

    assert result == {"checkpoint": "model_0.pt"}
    assert captured is not None
    assert captured[0] == "train"
    assert captured[captured.index("--run-dir") + 1] == str(tmp_path)
    assert captured[captured.index("--checkpoint-interval") + 1] == "300"


def test_run_mjlab_smoke_builds_a1_worker_request(monkeypatch) -> None:
    captured = None

    def fake_run_worker(*arguments: str) -> dict[str, str]:
        nonlocal captured
        captured = arguments
        return {"task_id": "RoboLab-Velocity-Flat-Unitree-A1"}

    monkeypatch.setattr("robolab.frameworks.mjlab.runtime._run_worker", fake_run_worker)
    result = run_mjlab_smoke("RoboLab-Velocity-Flat-Unitree-A1", num_envs=2)

    assert result == {"task_id": "RoboLab-Velocity-Flat-Unitree-A1"}
    assert captured is not None
    assert captured[:2] == ("smoke", "--task")
    assert captured[captured.index("--num-envs") + 1] == "2"


def test_run_mjlab_play_builds_worker_request(monkeypatch, tmp_path) -> None:
    checkpoint = tmp_path / "model_0.pt"
    checkpoint.write_bytes(b"checkpoint")
    captured = None

    def fake_run_worker(*arguments: str) -> dict[str, float]:
        nonlocal captured
        captured = arguments
        return {"mean_reward": 1.0}

    monkeypatch.setattr("robolab.frameworks.mjlab.runtime._run_worker", fake_run_worker)
    assert run_mjlab_play(checkpoint, steps=8) == {"mean_reward": 1.0}
    assert captured is not None
    assert captured[0] == "play"
    assert captured[captured.index("--checkpoint") + 1] == str(checkpoint.resolve())


def test_run_mjlab_play_can_request_web_viewer(monkeypatch, tmp_path) -> None:
    checkpoint = tmp_path / "model_0.pt"
    checkpoint.write_bytes(b"checkpoint")
    captured = None

    def fake_run_worker(*arguments: str) -> dict[str, str]:
        nonlocal captured
        captured = arguments
        return {"mode": "viser"}

    monkeypatch.setattr("robolab.frameworks.mjlab.runtime._run_worker", fake_run_worker)
    assert run_mjlab_play(checkpoint, visualize=True) == {"mode": "viser"}
    assert captured is not None
    assert "--visualize" in captured


def test_run_mjlab_evaluate_builds_worker_request(monkeypatch, tmp_path) -> None:
    checkpoint = tmp_path / "model_0.pt"
    checkpoint.write_bytes(b"checkpoint")
    captured = None

    def fake_run_worker(*arguments: str) -> dict[str, float]:
        nonlocal captured
        captured = arguments
        return {"mean_abs_forward_tracking_error": 0.1}

    monkeypatch.setattr("robolab.frameworks.mjlab.runtime._run_worker", fake_run_worker)
    assert run_mjlab_evaluate(checkpoint, num_envs=8, steps=16) == {
        "mean_abs_forward_tracking_error": 0.1
    }
    assert captured is not None
    assert captured[0] == "evaluate"
    assert captured[captured.index("--checkpoint") + 1] == str(checkpoint.resolve())


def test_a1_mjcf_binding_points_to_canonical_resource() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    path = canonical_mjcf(root)
    assert path.is_file()
    assert path.parts[-4:] == ("robots", "unitree_a1", "xml", "unitree_a1.xml")
    assert ACTION.shape == (12,)
    assert len(UNITREE_A1_JOINT_ORDER) == ACTION.shape[0]
    assert CONTROL_DT == 0.02
