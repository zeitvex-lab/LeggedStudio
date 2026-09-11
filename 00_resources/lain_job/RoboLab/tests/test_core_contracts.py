import pytest

from robolab.core import PolicyArtifact, Recipe, RunRecord, TensorContract
from robolab.visualization import SceneFrame, TrainingFrame


def test_recipe_is_serializable_and_copies_overrides() -> None:
    overrides = {"num_envs": 8}
    recipe = Recipe("unitree_a1", "velocity", "ppo", "isaacgym", overrides=overrides)
    overrides["num_envs"] = 16

    assert recipe.to_dict()["overrides"] == {"num_envs": 8}
    assert recipe.to_dict()["framework"] == "isaacgym"


def test_recipe_carries_robot_profile_mapping_and_control() -> None:
    recipe = Recipe(
        "custom", "velocity", "ppo", "isaacgym",
        robot_profile="derived/custom/robot-profile.json",
        joint_mapping={"hip": "hip_joint"},
        control={"decimation": 4},
    )
    data = recipe.to_dict()
    assert data["robot_profile"].endswith("robot-profile.json")
    assert data["joint_mapping"]["hip"] == "hip_joint"
    assert data["control"]["decimation"] == 4


def test_policy_artifact_carries_cross_framework_contract() -> None:
    artifact = PolicyArtifact(
        policy_path="artifacts/policy.pt",
        robot="unitree_a1",
        task="velocity",
        method="ppo",
        framework="isaacgym",
        observation=TensorContract("actor_observation", (48,), semantics="actor_obs"),
        action=TensorContract("action", (12,), semantics="joint_targets"),
        control_dt=0.02,
        joint_order=("FL_hip", "FL_thigh"),
    )

    assert artifact.to_dict()["observation"]["shape"] == (48,)
    assert artifact.to_dict()["control_dt"] == 0.02


def test_contracts_reject_invalid_values() -> None:
    with pytest.raises(ValueError, match="framework"):
        Recipe("a1", "velocity", "ppo", "")
    with pytest.raises(ValueError, match="control_dt"):
        PolicyArtifact(
            "policy.pt",
            "a1",
            "velocity",
            "ppo",
            "mjlab",
            TensorContract("obs", (1,)),
            TensorContract("action", (1,)),
            0,
            ("joint",),
        )


def test_run_record_nests_recipe() -> None:
    record = RunRecord("run-001", Recipe("a1", "velocity", "ppo", "mjlab"), "created")
    assert record.to_dict()["recipe"]["robot"] == "a1"


def test_scene_frame_is_backend_neutral_and_serializable() -> None:
    frame = SceneFrame(
        robot="unitree_a1",
        joint_order=("j0",),
        root_position=(0.0, 0.0, 0.4),
        root_orientation=(1.0, 0.0, 0.0, 0.0),
        joint_position=(0.1,),
        joint_velocity=(0.0,),
        command=(0.5, 0.0, 0.0),
        reward=1.0,
    )
    assert frame.to_dict()["robot"] == "unitree_a1"


def test_scene_frame_rejects_mismatched_joint_contract() -> None:
    with pytest.raises(ValueError, match="joint_order"):
        SceneFrame(
            robot="unitree_a1",
            joint_order=("j0",),
            root_position=(0.0, 0.0, 0.4),
            root_orientation=(1.0, 0.0, 0.0, 0.0),
            joint_position=(),
            joint_velocity=(),
            command=(),
            reward=0.0,
        )


def test_training_frame_serializes_metrics() -> None:
    frame = TrainingFrame("mjlab", "velocity", 3, {"reward": 1.0})
    assert frame.to_dict()["metrics"]["reward"] == 1.0


def test_viser_bridge_reorders_joint_configuration() -> None:
    from robolab.visualization.viser_bridge import _joint_configuration

    assert _joint_configuration(
        {"joint_order": ["b", "a"], "joint_position": [2.0, 1.0]},
        ("a", "b"),
    ) == [1.0, 2.0]
