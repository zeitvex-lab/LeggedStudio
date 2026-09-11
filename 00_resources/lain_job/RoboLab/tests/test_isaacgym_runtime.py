import pytest

from robolab.frameworks.isaacgym.runtime import (
    IsaacGymRuntimeError,
    resolve_isaacgym_runtime,
    run_isaacgym_play,
    run_isaacgym_train,
)
from robolab.frameworks.isaacgym.visualization import scene_frame_from_isaacgym


def test_resolve_isaacgym_runtime_from_environment(tmp_path, monkeypatch) -> None:
    python = tmp_path / "bin" / "python"
    sdk = tmp_path / "sdk"
    legged_gym = tmp_path / "legged"
    python.parent.mkdir()
    python.touch()
    (sdk / "isaacgym").mkdir(parents=True)
    (sdk / "isaacgym" / "__init__.py").touch()
    (legged_gym / "legged_gym").mkdir(parents=True)
    (legged_gym / "legged_gym" / "__init__.py").touch()
    monkeypatch.setenv("ROBO_ISAACGYM_PYTHON", str(python))
    monkeypatch.setenv("ROBO_ISAACGYM_SDK_PATH", str(sdk))
    monkeypatch.setenv("ROBO_LEGGED_GYM_PATH", str(legged_gym))

    assert resolve_isaacgym_runtime() == (
        python.resolve(),
        sdk.resolve(),
        legged_gym.resolve(),
    )


def test_resolve_isaacgym_runtime_reports_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ROBO_ISAACGYM_PYTHON", str(tmp_path / "missing"))
    with pytest.raises(IsaacGymRuntimeError, match="runtime is incomplete"):
        resolve_isaacgym_runtime()


def test_run_isaacgym_train_builds_worker_request(monkeypatch, tmp_path) -> None:
    captured = None

    def fake_run_worker(*arguments: str) -> dict[str, str]:
        nonlocal captured
        captured = arguments
        return {"checkpoint": "model_1.pt"}

    monkeypatch.setattr(
        "robolab.frameworks.isaacgym.runtime._run_worker", fake_run_worker
    )

    result = run_isaacgym_train(
        "a1",
        num_envs=64,
        max_iterations=1,
        run_dir=tmp_path,
    )

    assert result == {"checkpoint": "model_1.pt"}
    assert captured is not None
    assert captured[0] == "train"
    assert captured[captured.index("--run-dir") + 1] == str(tmp_path)
    assert captured[captured.index("--checkpoint-interval") + 1] == "300"


def test_run_isaacgym_train_builds_resume_request(monkeypatch, tmp_path) -> None:
    checkpoint = tmp_path / "model_1.pt"
    checkpoint.write_bytes(b"checkpoint")
    captured = None

    def fake_run_worker(*arguments: str) -> dict[str, str]:
        nonlocal captured
        captured = arguments
        return {"checkpoint": "model_2.pt"}

    monkeypatch.setattr(
        "robolab.frameworks.isaacgym.runtime._run_worker", fake_run_worker
    )
    run_isaacgym_train(
        num_envs=64,
        max_iterations=1,
        run_dir=tmp_path / "run",
        resume_from=checkpoint,
    )

    assert captured is not None
    assert captured[captured.index("--resume-from") + 1] == str(checkpoint.resolve())


def test_run_isaacgym_play_builds_worker_request(monkeypatch, tmp_path) -> None:
    checkpoint = tmp_path / "model_1.pt"
    checkpoint.write_bytes(b"checkpoint")
    captured = None

    def fake_run_worker(*arguments: str) -> dict[str, str]:
        nonlocal captured
        captured = arguments
        return {"mean_reward": 1.0}

    monkeypatch.setattr(
        "robolab.frameworks.isaacgym.runtime._run_worker", fake_run_worker
    )
    assert run_isaacgym_play(checkpoint, steps=8) == {"mean_reward": 1.0}
    assert captured is not None
    assert captured[0] == "play"
    assert captured[captured.index("--checkpoint") + 1] == str(checkpoint.resolve())


def test_run_isaacgym_play_can_request_native_viewer(monkeypatch, tmp_path) -> None:
    checkpoint = tmp_path / "model_1.pt"
    checkpoint.write_bytes(b"checkpoint")
    captured = None

    def fake_run_worker(*arguments: str) -> dict[str, str]:
        nonlocal captured
        captured = arguments
        return {"backend": "isaacgym"}

    monkeypatch.setattr(
        "robolab.frameworks.isaacgym.runtime._run_worker", fake_run_worker
    )
    run_isaacgym_play(checkpoint, num_envs=4, steps=0, visualize=True)

    assert captured is not None
    assert "--visualize" in captured
    assert captured[captured.index("--num-envs") + 1] == "4"


def test_isaacgym_scene_frame_reorders_public_joint_contract() -> None:
    torch = pytest.importorskip("torch")

    class FakeEnv:
        dof_names = [
            "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
            "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
            "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
            "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint",
        ]
        root_states = torch.tensor([[1.0, 2.0, 3.0, 0.1, 0.2, 0.3, 0.9, 0, 0, 0, 0, 0, 0]])
        commands = torch.tensor([[0.5, -0.2, 0.1]])
        dof_pos = torch.arange(12, dtype=torch.float32).reshape(1, 12)
        dof_vel = torch.zeros(1, 12)

    frame = scene_frame_from_isaacgym(FakeEnv(), reward=2.0)
    assert frame.joint_order[0] == "FL_hip_joint"
    assert frame.joint_position[0] == 3.0
    assert frame.root_orientation == (0.9, 0.1, 0.2, 0.3)
    assert frame.reward == 2.0




@pytest.mark.parametrize("field,value", [("num_envs", 0), ("max_iterations", 0)])
def test_run_isaacgym_train_rejects_non_positive_values(field, value) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        run_isaacgym_train(**{field: value})
