from __future__ import annotations

import pytest

from robolab.methods import get_method, list_methods
from robolab.methods.registry import MethodSpec, register_method


def test_builtin_methods_are_framework_neutral_metadata() -> None:
    assert list_methods() == ("cts", "dreamwaq", "ppo", "ppo_ee", "teacher_student")
    spec = get_method("ppo_ee")
    assert spec.frameworks == ("isaacgym",)
    assert spec.paper == "2202.05481"
    assert spec.input_contract["action"] == "12-dim A1 joint action"


def test_dreamwaq_declares_its_extra_training_inputs() -> None:
    spec = get_method("dreamwaq")
    assert spec.frameworks == ("isaacgym",)
    assert spec.paper == "2210.17002"
    assert spec.input_contract["observation_history"].startswith("5 x 45-dim")
    assert "85 total" in spec.input_contract["actor_observation"]


def test_teacher_student_declares_privileged_distillation_contract() -> None:
    spec = get_method("teacher_student")
    assert spec.frameworks == ("isaacgym",)
    assert spec.input_contract["observation_history"] == "20 x 45-dim history (900 total)"


def test_method_registry_rejects_duplicate_ids() -> None:
    spec = MethodSpec(
        method_id="test_method",
        display_name="Test",
        algorithm="TestAlgorithm",
        policy="TestPolicy",
        runner="TestRunner",
        storage="TestStorage",
        frameworks=("isaacgym",),
    )
    register_method(spec)
    with pytest.raises(ValueError, match="already registered"):
        register_method(spec)
