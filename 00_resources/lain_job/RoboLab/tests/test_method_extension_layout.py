from __future__ import annotations

from pathlib import Path

from robolab.frameworks.isaacgym.method_plugins import StandardPPOPlugin, load_method_plugin


def test_ppo_ee_extension_isolated_from_default_rsl_rl() -> None:
    root = Path(__file__).parents[1]
    extension = root / "backends/isaacgym/methods/ppo_ee"
    assert (extension / "method.toml").is_file()
    assert (extension / "NOTICE.md").is_file()
    assert (extension / "README.md").is_file()
    assert not (root / "backends/isaacgym/rsl_rl/rsl_rl/algorithms/ppo_ee.py").exists()
    assert not (root / "backends/isaacgym/rsl_rl/rsl_rl/runners/ee_runner.py").exists()


def test_dreamwaq_extension_isolated_from_default_rsl_rl() -> None:
    root = Path(__file__).parents[1]
    extension = root / "backends/isaacgym/methods/dreamwaq"
    assert (extension / "method.toml").is_file()
    assert (extension / "NOTICE.md").is_file()
    assert (extension / "README.md").is_file()
    assert (extension / "algorithm.py").is_file()
    assert (extension / "storage.py").is_file()
    assert not (root / "backends/isaacgym/rsl_rl/rsl_rl/algorithms/ppo_dreamwaq.py").exists()
    assert not (root / "backends/isaacgym/rsl_rl/rsl_rl/runners/dreamwaq_runner.py").exists()


def test_teacher_student_extension_isolated_from_default_rsl_rl() -> None:
    root = Path(__file__).parents[1]
    extension = root / "backends/isaacgym/methods/teacher_student"
    assert (extension / "method.toml").is_file()
    assert (extension / "NOTICE.md").is_file()
    assert (extension / "README.md").is_file()
    assert (extension / "algorithm.py").is_file()
    assert (extension / "storage.py").is_file()
    assert not (root / "backends/isaacgym/rsl_rl/rsl_rl/algorithms/ppo_ts.py").exists()


def test_cts_extension_writes_tensorboard_scalars():
    root = Path(__file__).parents[1]
    runner = (root / "backends/isaacgym/methods/cts/runner.py").read_text()
    assert "SummaryWriter" in runner
    assert "add_scalar" in runner


def test_standard_ppo_uses_the_common_plugin_contract() -> None:
    plugin = load_method_plugin("ppo")
    assert isinstance(plugin, StandardPPOPlugin)
    assert plugin.method_id == "ppo"
