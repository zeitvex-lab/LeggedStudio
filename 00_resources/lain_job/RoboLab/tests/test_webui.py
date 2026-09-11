from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _server_module():
    spec = importlib.util.spec_from_file_location("robolab_webui_server", ROOT / "webui" / "server.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_webui_scans_robot_assets():
    entries = _server_module().robots()
    ids = {entry["id"] for entry in entries}
    assert "unitree_a1" in ids
    assert all(entry["models"] for entry in entries)


def test_webui_inspects_real_urdf_joint_limits_and_tree():
    model = _server_module().inspect_model(
        "resources/robots/unitree_a1/urdf/unitree_a1.urdf"
    )
    assert model["summary"]["links"] > 0
    assert model["summary"]["joints"] >= 12
    actuated = [joint for joint in model["joints"] if joint["type"] != "fixed"]
    assert actuated
    assert all(joint["parent"] and joint["child"] for joint in actuated)
    assert all(joint["lower"] is not None for joint in actuated)
    assert sum(len(link["geometry"]) for link in model["links"]) > 0
    assert any(item.get("resolved_mesh") for link in model["links"] for item in link["geometry"])


def test_webui_does_not_report_official_auxiliary_links_as_structural_errors():
    model = _server_module().inspect_model("resources/robots/unitree_go2/urdf/go2.urdf")
    assert model["summary"]["warnings"] == 0
    assert any(link["role"] == "auxiliary" for link in model["links"])
    roles = {link["name"]: link["role"] for link in model["links"]}
    assert roles["FL_foot"] == "structural"
    assert roles["FR_foot"] == "structural"


def test_webui_does_not_treat_optional_collision_as_model_warning(tmp_path):
    model = tmp_path / "visual_only.urdf"
    model.write_text("""<robot name="visual-only">
      <link name="base"><inertial><mass value="1"/><inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/></inertial></link>
    </robot>""")
    server = _server_module()
    server.ROOT = tmp_path
    result = server.inspect_model(model.name)
    assert result["warnings"] == []
    assert result["summary"]["notes"] == 1


def test_webui_warns_when_movable_rigid_body_has_no_inertial(tmp_path):
    model = tmp_path / "missing_inertial.urdf"
    model.write_text("""<robot name="missing-inertial">
      <link name="base"/><link name="moving"/>
      <joint name="axis" type="revolute"><parent link="base"/><child link="moving"/>
        <limit lower="-1" upper="1" effort="1" velocity="1"/>
      </joint>
    </robot>""")
    server = _server_module()
    server.ROOT = tmp_path
    result = server.inspect_model(model.name)
    assert any("moving" in warning and "inertial" in warning for warning in result["warnings"])


def test_webui_compatibility_rejects_unsupported_method_backend():
    server = _server_module()
    result = server.compatibility({
        "model": "resources/robots/unitree_a1/urdf/unitree_a1.urdf",
        "framework": "mjlab",
        "method": "teacher_student",
        "task": "a1",
        "num_envs": 1,
        "iterations": 1,
    })
    assert not result["ok"]
    assert any("不支持 backend" in issue for issue in result["issues"])


def test_webui_resolves_latest_checkpoint_by_iteration(tmp_path):
    server = _server_module()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    nested = run_dir / "run_abc"
    nested.mkdir()
    (nested / "model_9.pt").write_bytes(b"9")
    (nested / "model_1500.pt").write_bytes(b"1500")
    assert server.latest_checkpoint(run_dir).name == "model_1500.pt"


def test_webui_extracts_live_iteration_and_reward_progress(tmp_path):
    server = _server_module()
    log = "Learning iteration 12/100\nMean reward: 3.25\nLearning iteration 13/100\nMean reward: 4.5\n"
    result = server.training_progress(tmp_path, log, 100)
    assert result["current_iteration"] == 13
    assert result["max_iterations"] == 100
    assert result["reward_latest"] == 4.5
    assert result["reward_history"] == [3.25, 4.5]


def test_webui_recipe_defaults_match_concurrent_teacher_student_ui():
    page = (ROOT / "webui" / "index.html").read_text()
    script = (ROOT / "webui" / "app.js").read_text()
    assert 'id="envs" value="1024"' in page
    assert 'id="iterations" value="1500"' in page
    assert 'id="seed" value="0"' in page
    assert 'id="runDir" value="logs/webui"' in page
    assert '$("method").value = "cts"' in script
    assert "/api/run/latest" in script


def test_webui_zero_pose_reset_ignores_joint_limits_and_survives_reload():
    app = (ROOT / "webui" / "app.js").read_text()
    viewer = (ROOT / "webui" / "src" / "three-viewer.js").read_text()
    assert "function applyPreviewPose()" in app
    assert "ignoreLimits: !state.useStandingPose" in app
    assert '$("useStandingPose")?.addEventListener("change"' in app
    assert "applyPreviewPose();" in app
    assert "const revision = ++state.previewRevision" in app
    assert "const revision = ++this.loadRevision" in viewer
    assert "joint.ignoreLimits = true" in viewer
    assert "joint.ignoreLimits = previousIgnoreLimits" in viewer


def test_viser_uses_only_current_run_checkpoints_and_shows_filenames():
    worker = (ROOT / "src" / "robolab" / "frameworks" / "isaacgym" / "worker.py").read_text()
    bridge = (ROOT / "src" / "robolab" / "visualization" / "viser_bridge.py").read_text()
    assert 'selected_checkpoint.parent.glob("model_*.pt")' in worker
    assert 'for path in root.joinpath("logs").rglob("*.pt")' not in worker
    assert 'checkpoint_labels = tuple(Path(path).name for path in checkpoint_paths)' in bridge
    assert 'checkpoint_by_label' in bridge


def test_webui_auto_resolves_backend_runtime_python():
    server = _server_module()
    assert server.runtime_python("isaacgym").endswith("robolab-isaacgym/bin/python")
    assert server.runtime_python("mjlab").endswith("robolab-mjlab16/bin/python")


def test_webui_train_command_preserves_recipe_and_resume_path(tmp_path):
    server = _server_module()
    checkpoint = tmp_path / "model_300.pt"
    checkpoint.write_bytes(b"checkpoint")
    command = server.build_train_command({
        "framework": "isaacgym", "task": "a1_cts", "method": "cts",
        "num_envs": 1024, "iterations": 1500, "seed": 0,
        "checkpoint": str(checkpoint),
    }, tmp_path / "run")
    assert command[command.index("--task") + 1] == "a1_cts"
    assert command[command.index("--method") + 1] == "cts"
    assert command[command.index("--num-envs") + 1] == "1024"
    assert command[command.index("--max-iterations") + 1] == "1500"
    assert command[command.index("--seed") + 1] == "0"
    assert command[command.index("--resume-from") + 1] == str(checkpoint.resolve())


def test_webui_compatibility_returns_concrete_model_warnings():
    result = _server_module().compatibility({
        "model": "resources/robots/unitree_a1/urdf/unitree_a1.urdf",
        "framework": "isaacgym", "method": "cts", "task": "a1_cts",
        "num_envs": 1024, "iterations": 1500,
    })
    assert "model_warnings" in result
    assert isinstance(result["model_warnings"], list)


def test_webui_rejects_a1_only_method_for_another_robot():
    result = _server_module().compatibility({
        "model": "resources/robots/unitree_go2/urdf/go2.urdf",
        "framework": "isaacgym", "method": "cts", "task": "a1_cts",
        "num_envs": 1024, "iterations": 1500,
    })
    assert not result["ok"]
    assert any("只支持 Unitree A1" in issue for issue in result["issues"])


def test_webui_is_dependency_free_and_has_workflow_sections():
    page = (ROOT / "webui" / "index.html").read_text()
    assert "https://" not in page
    for section in ("模型", "控制", "训练", "运行"):
        assert section in page
    script = (ROOT / "webui" / "app.js").read_text()
    assert "/api/model" in script
    assert "/api/derive" in script


def test_three_viewer_uses_one_world_coordinate_conversion():
    source = (ROOT / "webui" / "src" / "three-viewer.js").read_text()
    assert 'this.world.name = "robolab-urdf-world"' in source
    assert "this.world.rotation.x = -Math.PI / 2" in source
    assert "this.robot.rotation.x" not in source
    assert "this.grid.rotation.x" not in source
    assert "this.worldAxes" not in source
    assert "this.modelAxes" not in source
    assert "setupOrientationGizmo" in source


def test_three_viewer_has_real_inertia_visualization_path():
    source = (ROOT / "webui" / "src" / "three-viewer.js").read_text()
    assert "buildInertiaHelpers" in source
    assert "inertia_ellipsoid" in source
    assert "this.visibility.inertia" in source
    assert "new THREE.ArrowHelper" in source
    assert "TubeGeometry" in source
    assert "positive_rotation_axis" in source
    assert "0x28d17c" in source
    assert "multiplyScalar(0.07)" in source
    assert "Math.PI * 1.65" in source
    assert "0.0012" in source
    assert "focusLink" in source
    assert '["revolute", "continuous"].includes(joint.jointType)' in source
    assert "robolabOriginalOpacity" in source
    assert "this.visibility.axis" in source
    assert "0xffd84d" in source


def test_structure_panel_uses_nested_tree_markup():
    source = (ROOT / "webui" / "app.js").read_text()
    assert "<details" in source
    assert "<summary" in source
    assert "robot-tree" in source
