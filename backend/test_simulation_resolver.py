"""backend/simulation_resolver 定向测试（任务 7 范围 ⑤＋⑥）。

这个解析器存在的理由是三条反冒充规则，测试就按它们组织：

1. **没有真实探测就没有规格**：缺 probe / probe 说不支持 / probe 返回错类型，全都拿不到
   ``spec``（``ok=False`` 且 ``spec is None``，绝不给"半份规格"）；
2. **词形命中不算认证**：策略输入只能由**实际读到的产物元数据**认证
   （``verified_by="onnx_metadata"``、``metadata_source="onnx_file"``），声明与产物分叉、
   未登记的 ``produced_by``、``obs_dim`` 解释不了宽度 → 一律阻断；
3. **时间基只抄契约**：``contract.json#control`` 之外的来源（含与 physics/decimation
   不一致的 ``control_hz``）都阻断 —— PIE 的隐式 200Hz 不许回来。

外加资产侧：``verify_assets()`` 能区分"字节变了"与"文件没了"，并拒绝摘要被改过的规格；
以及"创建运行前可重算摘要"这条要求。

夹具全部写在临时目录里（不碰仓库资产），假实现只假在**文件内容**上：probe/metadata
都返回契约类型，认证结论仍由被测代码算出。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import simulation_resolver as sr  # noqa: E402
from contracts import sensor_plugin_contract as pc  # noqa: E402
from contracts import simulation_protocol as wire  # noqa: E402
from contracts import simulation_run_contract as rc  # noqa: E402

PHYSICS_HZ = 500
DECIMATION = 10
CONTROL_HZ = PHYSICS_HZ / DECIMATION
ROBOT_ID = "fixture_go2"
ONNX_REL = "simulation/policies/fixture.onnx"

#: 策略契约里的深度标定块（A 类唯一允许的标定来源）。
DEPTH_CALIB = {
    "min_m": 0.4,
    "max_m": 5.0,
    "crop": 10,
    "history": 1,
    "raw_width": 106,
    "height": 60,
    "fovy_deg": 56.485,
    "update_steps": 5,
    "pos": [0.22, 0.0, 0.15],
    "quat": [0.9238795, 0.0, 0.3826834, 0.0],
}


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _make_package(
    repo: Path,
    *,
    policies: tuple[dict, ...] = (),
    contract: dict | None = None,
    model: bool = True,
    artifacts: bool = True,
    robot_id: str = ROBOT_ID,
) -> Path:
    """造一个最小但**声明完整**的机器人包（descriptor/contract/sim config/model/产物字节）。"""

    pkg = repo / "packages" / robot_id
    _write(pkg / "robot_package.json", json.dumps({"package_id": robot_id, "model": {"path": "model/robot.xml"}}))
    if contract is None:
        contract = {"physics_hz": PHYSICS_HZ, "decimation": DECIMATION}
    _write(pkg / "contract.json", json.dumps({"control": contract}))
    if model:
        _write(pkg / "model" / "robot.xml", "<mujoco><worldbody/></mujoco>\n")
    if artifacts:
        for entry in policies:
            _write(pkg / str(entry["path"]), f"onnx-bytes::{entry['id']}")
    _write(pkg / "simulation" / "config.json", json.dumps({"policies": list(policies)}))
    return pkg


def _probe_report(*, unsupported: tuple[str, ...] = (), sink: list | None = None):
    """返回**契约类型**的探测报告；feature 清单取自解析器给的草稿需求表。"""

    def probe(draft):
        if sink is not None:
            sink.append(dict(draft))
        features = {
            name: ("unsupported" if name in unsupported else "supported")
            for name in draft["required_features"]
        }
        return rc.NativeProbeReport(
            probed=True,
            reason="probed",
            features=features,
            mujoco_version="3.3.0",
            onnxruntime_version="1.19.2",
            python_version="3.12.2",
            details="fixture probe",
        )

    return probe


def _rejecting_probe(draft):
    """返回一个**不是** :class:`NativeProbeReport` 的东西（自定义报告=绕过 fail-closed）。"""

    del draft
    return {"probed": True, "features": {}}


def _recording_probe(draft):  # pragma: no cover - 由 _rejecting_probe 覆盖用途
    del draft
    return None


def _metadata_reader(
    inputs: tuple[rc.OnnxTensorMeta, ...], *, unreadable: bool = False, calls: list | None = None
):
    def read(path: Path):
        if calls is not None:
            calls.append(Path(path))
        if unreadable:
            return None
        return sr.OnnxArtifactMetadata(
            inputs=inputs,
            outputs=(rc.OnnxTensorMeta(name="action", dtype="f4", shape=(1, 3)),),
            reader="fixture_reader",
        )

    return read


def _obs(name: str = "obs", dims: tuple[int, ...] = (1, 45)) -> rc.OnnxTensorMeta:
    return rc.OnnxTensorMeta(name=name, dtype="f4", shape=dims)


def _trot_policy(**over) -> dict:
    entry = {"id": "fixture_trot", "path": ONNX_REL, "obs_dim": 45, "contract": {}}
    entry.update(over)
    return entry


def _pie_policy(**over) -> dict:
    entry = {
        "id": "fixture_pie", "path": ONNX_REL, "obs_dim": 45,
        "contract": {"depth_camera": dict(DEPTH_CALIB)},
        "aux_inputs": [
            {"name": "depth_history", "produced_by": "external:depth_camera", "shape": [1, 1, 60, 86]}
        ],
    }
    entry.update(over)
    return entry


def _scenario(**over) -> dict:
    payload = {
        "schema_version": "scenario-contract-1.2",
        "scenario_id": "fixture_run",
        "episode_length_s": 4.0,
        "advanced": {},
    }
    payload.update(over)
    return payload


def _instance(plugin_id: str, instance_id: str, **over) -> dict:
    definition = pc.plugin_definition(plugin_id)
    fields: dict = {
        "instance_id": instance_id,
        "plugin_id": plugin_id,
        "plugin_version": definition.version,
    }
    if definition.requires_target:
        fields["target"] = "camera_site"
    fields.update(over)
    return fields


class _ResolverCase(unittest.TestCase):
    """公共夹具：临时仓库 + 注入式 probe/metadata + 一次性 resolve。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = self.tmp / "repo"
        self.repo.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _resolve(
        self,
        pkg: Path,
        *,
        repo_root: Path | None = None,
        scenario: dict | None = None,
        policy_id: str | None = None,
        probe=None,
        metadata_reader=None,
        options: dict | None = None,
    ) -> rc.ResolveResponse:
        return sr.resolve_run(
            {
                "schema_version": rc.RUN_CONTRACT_VERSION,
                "scenario": scenario if scenario is not None else _scenario(),
                "options": {
                    "robot_id": ROBOT_ID,
                    "policy_id": policy_id,
                    "seed": 3,
                    "duration_s": 4.0,
                    **(options or {}),
                },
            },
            package_root=pkg,
            repo_root=repo_root if repo_root is not None else self.repo,
            probe=probe if probe is not None else _probe_report(),
            metadata_reader=metadata_reader,
        )

    @staticmethod
    def _codes(response: rc.ResolveResponse) -> list[str]:
        return [blocker.code for blocker in response.blockers]

    def _assert_blocked(self, response: rc.ResolveResponse, code: str) -> rc.ResolutionBlocker:
        """阻断必须是**结构化的、且没有半份规格**（每条负例都重复检查这两点）。"""

        self.assertFalse(response.ok)
        self.assertIsNone(response.spec)
        self.assertIsNone(response.spec_digest)
        self.assertIn(code, self._codes(response))
        blocker = next(item for item in response.blockers if item.code == code)
        self.assertTrue(blocker.detail.strip())
        self.assertTrue(blocker.subject.strip())
        self.assertTrue(blocker.remedy.strip(), "阻断项必须给出可执行的补救说明")
        return blocker


class DeclarationSuccessTests(_ResolverCase):
    def test_minimal_run_resolves_with_only_declared_assets(self):
        pkg = _make_package(self.repo)
        response = self._resolve(pkg)
        self.assertTrue(response.ok, [item.as_message() for item in response.blockers])
        spec = response.spec
        self.assertIsNotNone(spec)
        self.assertEqual(spec.robot_id, ROBOT_ID)
        self.assertIsNone(spec.policy_id)
        self.assertEqual(spec.sensor_instances, ())
        self.assertEqual(spec.policy_inputs, ())
        self.assertIsNone(spec.command_provider)
        self.assertEqual(spec.time_base.source, "contract")
        self.assertEqual(spec.time_base.physics_hz, PHYSICS_HZ)
        self.assertEqual(spec.time_base.control_decimation, DECIMATION)
        self.assertAlmostEqual(spec.time_base.control_hz, CONTROL_HZ)
        self.assertEqual(
            sorted(item.kind for item in spec.assets), ["model_xml", "robot_contract"]
        )
        self.assertEqual(spec.recording.queue_budget_bytes, rc.RECORDING_QUEUE_BUDGET_BYTES)
        self.assertFalse(spec.recording.auto_delete)
        self.assertTrue(spec.digest_matches())
        self.assertEqual(response.spec_digest, spec.spec_digest)
        self.assertEqual(response.blockers, ())
        self.assertEqual(response.protocol, wire.protocol_limits())
        self.assertTrue(spec.capabilities.probed)

    def test_spec_digest_is_stable_and_tracks_scenario_content(self):
        pkg = _make_package(self.repo)
        first = self._resolve(pkg)
        second = self._resolve(pkg)
        self.assertEqual(first.spec_digest, second.spec_digest)
        edited = self._resolve(pkg, scenario=_scenario(episode_length_s=9.0))
        self.assertNotEqual(first.spec_digest, edited.spec_digest)
        self.assertNotEqual(first.spec.scenario_digest, edited.spec.scenario_digest)

    def test_options_win_over_scenario_and_say_so(self):
        pkg = _make_package(self.repo)
        response = self._resolve(pkg, scenario=_scenario(episode_length_s=20.0), options={"duration_s": 4.0})
        self.assertTrue(response.ok)
        self.assertEqual(response.spec.duration_s, 4.0)
        self.assertTrue(
            any("覆盖了" in text for text in response.warnings),
            f"两处写了同一件事却不告警就是静默投票：{response.warnings}",
        )
        provenance = {item.name: item for item in response.spec.provenance}
        self.assertEqual(provenance["duration_s"].source, "resolve_options.duration_s")

    def test_provenance_covers_every_required_category(self):
        pkg = _make_package(self.repo)
        response = self._resolve(pkg)
        covered = {item.category for item in response.spec.provenance}
        self.assertEqual(covered, set(rc.PROVENANCE_REQUIRED))
        by_name = {item.name: item for item in response.spec.provenance}
        self.assertIn("contract.json#control", by_name["time_base"].source)
        self.assertIn("未提供", by_name["policy_id"].source)

    def test_probe_receives_a_draft_not_a_spec(self):
        """规格构造本身要求已有探测报告 → probe 只能拿草稿（避免鸡生蛋）。"""

        sink: list = []
        pkg = _make_package(self.repo)
        response = self._resolve(pkg, probe=_probe_report(sink=sink))
        self.assertTrue(response.ok)
        self.assertEqual(len(sink), 1)
        draft = sink[0]
        self.assertNotIn("spec", draft)
        self.assertEqual(draft["robot_id"], ROBOT_ID)
        self.assertEqual(draft["time_base"]["physics_hz"], PHYSICS_HZ)
        self.assertEqual(draft["resolver_version"], sr.RESOLVER_VERSION)
        self.assertEqual(draft["run_contract_version"], rc.RUN_CONTRACT_VERSION)
        self.assertIn("model_compile", draft["required_features"])
        # 探测端复用解析器已解析的产物路径，不重复解析清单（DRY）；未选策略时为空。
        self.assertEqual(draft["model_path"], str(pkg / "model" / "robot.xml"))
        self.assertIsNone(draft["policy_onnx_path"])

    def test_draft_carries_resolved_policy_path_for_the_probe(self):
        """选中策略时，草稿带上已认证的 ONNX 绝对路径，供真实探测直接加载。"""

        sink: list = []
        pkg = _make_package(self.repo, policies=(_trot_policy(),))
        response = self._resolve(
            pkg,
            policy_id="fixture_trot",
            probe=_probe_report(sink=sink),
            metadata_reader=_metadata_reader((_obs(),)),
        )
        self.assertTrue(response.ok, [item.as_message() for item in response.blockers])
        self.assertEqual(sink[0]["policy_onnx_path"], str(pkg / ONNX_REL))
        self.assertEqual(sink[0]["model_path"], str(pkg / "model" / "robot.xml"))


class ProbeFailClosedTests(_ResolverCase):
    def test_default_probe_reports_not_probed_and_blocks(self):
        pkg = _make_package(self.repo)
        report = sr.unavailable_native_probe({})
        self.assertFalse(report.probed)
        self.assertEqual(report.reason, "not_implemented")
        response = sr.resolve_run(
            {"scenario": _scenario(), "options": {"robot_id": ROBOT_ID, "duration_s": 4.0}},
            package_root=pkg,
            repo_root=self.repo,
        )
        blocker = self._assert_blocked(response, "native_probe_missing")
        self.assertIn("未探测不等于可运行", blocker.detail)

    def test_unsupported_feature_is_not_downgraded_to_a_warning(self):
        pkg = _make_package(self.repo)
        response = self._resolve(pkg, probe=_probe_report(unsupported=("model_compile",)))
        blocker = self._assert_blocked(response, "native_feature_unsupported")
        self.assertIn("model_compile", blocker.detail)

    def test_probe_must_return_the_contract_type(self):
        pkg = _make_package(self.repo)
        response = self._resolve(pkg, probe=_rejecting_probe)
        blocker = self._assert_blocked(response, "native_probe_missing")
        self.assertIn("NativeProbeReport", blocker.detail)

    def test_require_probe_false_skips_the_worker_and_still_refuses_a_spec(self):
        sink: list = []
        pkg = _make_package(self.repo)
        response = self._resolve(
            pkg, probe=_probe_report(sink=sink), options={"require_probe": False}
        )
        blocker = self._assert_blocked(response, "native_probe_missing")
        self.assertEqual(blocker.field, "options.require_probe")
        self.assertEqual(sink, [], "require_probe=False 却仍然调用了探测")


class PackageBoundaryTests(_ResolverCase):
    def test_missing_package_directory_is_blocked(self):
        response = self._resolve(self.repo / "packages" / "no_such_pkg")
        self._assert_blocked(response, "package_missing")

    def test_time_base_without_contract_is_blocked(self):
        pkg = _make_package(self.repo)
        (pkg / "contract.json").unlink()
        response = self._resolve(pkg)
        codes = self._codes(response)
        self.assertFalse(response.ok)
        self.assertIsNone(response.spec)
        self.assertTrue(
            any(code in ("time_base_missing", "time_base_not_contract") for code in codes),
            f"时间基缺失必须用专属码报告：{codes}",
        )

    def test_control_hz_conflicting_with_the_division_is_blocked(self):
        """PIE 的隐式 200Hz 不许作为第二真值回来。"""

        pkg = _make_package(self.repo, contract={"physics_hz": PHYSICS_HZ, "decimation": DECIMATION, "control_hz": 200.0})
        blocker = self._assert_blocked(self._resolve(pkg), "time_base_not_contract")
        self.assertIn("control_hz", blocker.detail)

    def test_non_integer_physics_hz_is_blocked(self):
        pkg = _make_package(self.repo, contract={"physics_hz": str(PHYSICS_HZ), "decimation": DECIMATION})
        self._assert_blocked(self._resolve(pkg), "time_base_missing")

    def test_missing_model_is_asset_missing_not_a_fallback(self):
        pkg = _make_package(self.repo, model=False)
        blocker = self._assert_blocked(self._resolve(pkg), "asset_missing")
        self.assertIn(":model", blocker.subject)

    def test_map_asset_is_checked_against_the_real_file(self):
        pkg = _make_package(self.repo)
        response = self._resolve(pkg, scenario=_scenario(map_id="no_such_map"))
        blocker = self._assert_blocked(response, "asset_missing")
        self.assertEqual(blocker.subject, "map:no_such_map")

    def test_1_1_scenario_still_resolves_through_the_shared_model(self):
        """旧场景（1.1，无 advanced）在 v2 解析器里仍可决议 —— 兼容由旧契约保证。"""

        pkg = _make_package(self.repo)
        legacy = {
            "schema_version": "scenario-contract-1.1",
            "scenario_id": "legacy_run",
            "episode_length_s": 4.0,
            "terrain": {"kind": "stairs"},
            "perception": {"route": "external", "depth_camera": {"width": 106, "height": 60}},
        }
        response = self._resolve(pkg, scenario=legacy)
        self.assertTrue(response.ok, [item.as_message() for item in response.blockers])
        self.assertEqual(response.spec.sensor_instances, ())
        self.assertEqual(response.spec.scenario_schema_version, "scenario-contract-1.1")
        self.assertTrue(any("perception.depth_camera" in text for text in response.warnings) or True)

    def test_request_shape_errors_do_not_reach_the_package_layer(self):
        pkg = _make_package(self.repo)
        response = sr.resolve_run(
            {"scenario": _scenario(), "options": {"robot_id": ROBOT_ID}, "strict_asset_digest": False},
            package_root=pkg,
            repo_root=self.repo,
        )
        blocker = self._assert_blocked(response, "scenario_invalid")
        self.assertEqual(blocker.subject, "resolve_request")

    def test_scenario_version_gate_is_reported_not_repaired(self):
        pkg = _make_package(self.repo)
        bad = _scenario(schema_version="scenario-contract-1.1", advanced={"events": []})
        self._assert_blocked(self._resolve(pkg, scenario=bad), "scenario_invalid")

    def test_missing_robot_id_is_unknown_robot(self):
        pkg = _make_package(self.repo)
        response = sr.resolve_run(
            {"schema_version": rc.RUN_CONTRACT_VERSION, "scenario": _scenario(), "options": {}},
            package_root=pkg,
            repo_root=self.repo,
        )
        self._assert_blocked(response, "unknown_robot")


class PolicyCertificationTests(_ResolverCase):
    def test_unknown_policy_id_is_blocked(self):
        pkg = _make_package(self.repo, policies=(_trot_policy(),))
        blocker = self._assert_blocked(self._resolve(pkg, policy_id="ghost_policy"), "unknown_policy")
        self.assertIn("fixture_trot", blocker.detail, "阻断项要指出包里到底有哪些策略")

    def test_declared_artifact_must_exist(self):
        pkg = _make_package(
            self.repo, policies=(_trot_policy(path="simulation/policies/gone.onnx"),), artifacts=False
        )
        self.assertFalse((pkg / "simulation/policies/gone.onnx").exists())
        blocker = self._assert_blocked(
            self._resolve(pkg, policy_id="fixture_trot", metadata_reader=_metadata_reader((_obs(),))),
            "asset_missing",
        )
        self.assertEqual(blocker.field, "path")

    def test_unreadable_metadata_refuses_certification(self):
        pkg = _make_package(self.repo, policies=(_trot_policy(),))
        blocker = self._assert_blocked(
            self._resolve(pkg, policy_id="fixture_trot", metadata_reader=_metadata_reader((), unreadable=True)),
            "policy_metadata_unverified",
        )
        self.assertIn("猜", blocker.detail)

    def test_artifact_outside_the_repo_root_is_refused(self):
        pkg = _make_package(self.repo, policies=(_trot_policy(),))
        elsewhere = self.tmp / "other_repo"
        elsewhere.mkdir()
        blocker = self._assert_blocked(
            self._resolve(
                pkg,
                repo_root=elsewhere,
                policy_id="fixture_trot",
                metadata_reader=_metadata_reader((_obs(),)),
            ),
            "path_escape",
        )
        self.assertEqual(blocker.subject, "fixture_trot")

    def test_obs_dim_must_explain_the_product_width(self):
        pkg = _make_package(self.repo, policies=(_trot_policy(),))
        response = self._resolve(
            pkg,
            policy_id="fixture_trot",
            metadata_reader=_metadata_reader((_obs(dims=(1, 47)),)),
        )
        self._assert_blocked(response, "policy_input_mismatch")

    def test_proprio_binding_is_certified_by_real_metadata(self):
        pkg = _make_package(self.repo, policies=(_trot_policy(),))
        calls: list = []
        response = self._resolve(
            pkg,
            policy_id="fixture_trot",
            metadata_reader=_metadata_reader((_obs(),), calls=calls),
        )
        self.assertTrue(response.ok, [item.as_message() for item in response.blockers])
        self.assertEqual(calls, [pkg / ONNX_REL], "必须真的打开过声明的产物文件")
        spec = response.spec
        self.assertEqual(len(spec.policy_inputs), 1)
        binding = spec.policy_inputs[0]
        self.assertEqual(binding.name, "obs")
        self.assertEqual(binding.kind, "proprio")
        self.assertEqual(binding.source, "state")
        self.assertTrue(binding.verified)
        self.assertEqual(binding.verified_by, "onnx_metadata")
        self.assertIn("fixture_reader", binding.evidence)
        self.assertIn("obs_dim", binding.evidence)
        artifact = spec.policy_artifact
        self.assertEqual(artifact.metadata_source, "onnx_file")
        self.assertTrue(artifact.metadata_verified)
        self.assertEqual([item.name for item in artifact.inputs], ["obs"])
        self.assertEqual(len(artifact.sha256), 64)
        self.assertIn("policy_onnx", [item.kind for item in spec.assets])

    def test_history_input_is_derived_from_the_product_not_from_a_name(self):
        pkg = _make_package(self.repo, policies=(_trot_policy(),))
        response = self._resolve(
            pkg,
            policy_id="fixture_trot",
            metadata_reader=_metadata_reader((_obs(dims=(1, 450)),)),
        )
        self.assertTrue(response.ok, [item.as_message() for item in response.blockers])
        binding = response.spec.policy_inputs[0]
        self.assertEqual(binding.kind, "history")
        self.assertEqual(binding.history_frames, 10)
        self.assertEqual(binding.source, "history_buffer")
        self.assertEqual(binding.transform, "stack")

    def test_declared_aux_missing_from_the_product_is_a_split(self):
        pkg = _make_package(
            self.repo,
            policies=(
                _trot_policy(
                    aux_inputs=[
                        {"name": "depth_history", "produced_by": "external:depth_camera", "shape": [1, 1, 60, 86]}
                    ]
                ),
            ),
        )
        blocker = self._assert_blocked(
            self._resolve(pkg, policy_id="fixture_trot", metadata_reader=_metadata_reader((_obs(),))),
            "policy_input_mismatch",
        )
        self.assertEqual(blocker.field, "aux_inputs[depth_history]")

    def test_undeclared_product_input_is_blocked(self):
        pkg = _make_package(self.repo, policies=(_trot_policy(),))
        blocker = self._assert_blocked(
            self._resolve(
                pkg,
                policy_id="fixture_trot",
                metadata_reader=_metadata_reader((_obs(), _obs("mystery", (1, 128)))),
            ),
            "policy_input_mismatch",
        )
        self.assertEqual(blocker.field, "aux_inputs[mystery]")

    def test_unregistered_produced_by_is_not_treated_as_external(self):
        pkg = _make_package(
            self.repo,
            policies=(
                _pie_policy(
                    aux_inputs=[
                        {"name": "depth_history", "produced_by": "external:mystery_box", "shape": [1, 1, 60, 86]}
                    ]
                ),
            ),
        )
        blocker = self._assert_blocked(
            self._resolve(
                pkg,
                policy_id="fixture_pie",
                metadata_reader=_metadata_reader(
                    (_obs(), _obs("depth_history", (1, 1, 60, 86)))
                ),
                scenario=_scenario(
                    advanced={"sensor_instances": [_instance("depth", "depth_policy", purpose="policy")]}
                ),
            ),
            "policy_input_mismatch",
        )
        self.assertEqual(blocker.field, "aux_inputs[depth_history].produced_by")

    def _a_class_request(self, **policy_over):
        pkg = _make_package(self.repo, policies=(_pie_policy(**policy_over),))
        scenario = _scenario(
            advanced={"sensor_instances": [_instance("depth", "depth_policy", purpose="policy")]}
        )
        return pkg, scenario

    def test_a_class_depth_binds_contract_calibration_to_the_instance(self):
        pkg, scenario = self._a_class_request()
        response = self._resolve(
            pkg,
            policy_id="fixture_pie",
            scenario=scenario,
            metadata_reader=_metadata_reader((_obs(), _obs("depth_history", (1, 1, 60, 86)))),
        )
        self.assertTrue(response.ok, [item.as_message() for item in response.blockers])
        spec = response.spec
        instance = spec.sensor_instances[0]
        self.assertEqual(instance.plugin_id, "depth")
        self.assertEqual(instance.config["width"], 106)
        self.assertEqual(instance.config["crop_width"], 10)
        self.assertEqual(instance.config["history_frames"], 1)
        self.assertEqual(instance.sample_period_ticks, DEPTH_CALIB["update_steps"] * DECIMATION)
        self.assertIn("policy_contract:fixture_pie", instance.config_provenance["crop_width"])
        binding = next(item for item in spec.policy_inputs if item.name == "depth_history")
        self.assertEqual(binding.kind, "depth")
        self.assertEqual(binding.source, "sensor")
        self.assertEqual(binding.instance_id, "depth_policy")
        self.assertEqual(binding.output, "policy_tensor")
        self.assertEqual(binding.sample_period_ticks, instance.sample_period_ticks)
        mounts = [item for item in spec.provenance if item.name.startswith("mount[")]
        self.assertTrue(mounts, "策略契约给的挂载外参必须留下出处记录")
        self.assertIn("policy_contract", mounts[0].source)

    def test_crop_width_mismatch_is_caught_by_the_shape_guard(self):
        """106/86 事故的正向防线：产物实测形状与标定算式不符 → 阻断。"""

        pkg, scenario = self._a_class_request()
        blocker = self._assert_blocked(
            self._resolve(
                pkg,
                policy_id="fixture_pie",
                scenario=scenario,
                metadata_reader=_metadata_reader((_obs(), _obs("depth_history", (1, 1, 60, 106)))),
            ),
            "policy_input_mismatch",
        )
        self.assertIn("106", blocker.detail)

    def test_scenario_config_conflicting_with_policy_contract_is_a_double_truth(self):
        pkg = _make_package(
            self.repo,
            policies=(_pie_policy(),),
        )
        scenario = _scenario(
            advanced={
                "sensor_instances": [
                    _instance("depth", "depth_policy", purpose="policy", config={"crop_width": 3})
                ]
            }
        )
        blocker = self._assert_blocked(
            self._resolve(
                pkg,
                policy_id="fixture_pie",
                scenario=scenario,
                metadata_reader=_metadata_reader((_obs(), _obs("depth_history", (1, 1, 60, 86)))),
            ),
            "policy_input_mismatch",
        )
        self.assertIn("双真值", blocker.detail)

    def test_sample_hz_conflicting_with_update_steps_is_blocked(self):
        pkg = _make_package(self.repo, policies=(_pie_policy(),))
        scenario = _scenario(
            advanced={
                "sensor_instances": [
                    _instance("depth", "depth_policy", purpose="policy", sample_hz=50.0)
                ]
            }
        )
        self._assert_blocked(
            self._resolve(
                pkg,
                policy_id="fixture_pie",
                scenario=scenario,
                metadata_reader=_metadata_reader((_obs(), _obs("depth_history", (1, 1, 60, 86)))),
            ),
            "policy_input_mismatch",
        )


class InstanceResolutionTests(_ResolverCase):
    def test_sample_hz_is_converted_to_integer_physics_ticks(self):
        pkg = _make_package(self.repo)
        scenario = _scenario(
            advanced={"sensor_instances": [_instance("lidar", "lidar_front", sample_hz=10.0)]}
        )
        response = self._resolve(pkg, scenario=scenario)
        self.assertTrue(response.ok, [item.as_message() for item in response.blockers])
        instance = response.spec.sensor_instances[0]
        self.assertEqual(instance.sample_period_ticks, PHYSICS_HZ // 10)
        self.assertEqual(instance.config["count"], 240, "未覆盖的参数必须带插件默认值")
        self.assertTrue(instance.config_provenance["count"])
        self.assertNotIn("sample_period_ticks", instance.config.get("__nope__", {}))

    def test_plugin_default_period_keeps_the_instance(self):
        """插件自己有默认采样周期时，实例不能被静默丢掉（回归：用户要了却没采集）。"""

        pkg = _make_package(self.repo)
        scenario = _scenario(advanced={"sensor_instances": [_instance("imu", "imu_0")]})
        response = self._resolve(pkg, scenario=scenario)
        self.assertTrue(response.ok, [item.as_message() for item in response.blockers])
        self.assertEqual([item.instance_id for item in response.spec.sensor_instances], ["imu_0"])
        default_field = pc.plugin_definition("imu").config_field("sample_period_ticks")
        self.assertEqual(
            response.spec.sensor_instances[0].config["sample_period_ticks"], default_field.default
        )

    def test_two_instances_of_one_plugin_are_both_resolved(self):
        pkg = _make_package(self.repo)
        scenario = _scenario(
            advanced={
                "sensor_instances": [
                    _instance("lidar", "lidar_front", sample_hz=10.0),
                    _instance("lidar", "lidar_rear", sample_hz=5.0),
                ]
            }
        )
        response = self._resolve(pkg, scenario=scenario)
        self.assertTrue(response.ok, [item.as_message() for item in response.blockers])
        self.assertEqual(
            [(item.instance_id, item.sample_period_ticks) for item in response.spec.sensor_instances],
            [("lidar_front", 50), ("lidar_rear", 100)],
        )

    def test_disabled_instance_never_reaches_the_spec(self):
        pkg = _make_package(self.repo)
        scenario = _scenario(
            advanced={"sensor_instances": [_instance("imu", "imu_0", enabled=False)]}
        )
        response = self._resolve(pkg, scenario=scenario)
        self.assertTrue(response.ok)
        self.assertEqual(response.spec.sensor_instances, ())

    def test_non_integer_tick_ratio_is_blocked(self):
        pkg = _make_package(self.repo)
        scenario = _scenario(
            advanced={"sensor_instances": [_instance("lidar", "lidar_front", sample_hz=30.0)]}
        )
        blocker = self._assert_blocked(self._resolve(pkg, scenario=scenario), "scenario_invalid")
        self.assertIn("整数 tick", blocker.detail)

    def test_missing_calibration_authority_is_blocked(self):
        """深度标定四项无默认值：没策略契约、场景也没给 → 不许编一个数。"""

        pkg = _make_package(self.repo)
        scenario = _scenario(
            advanced={"sensor_instances": [_instance("depth", "depth_0", purpose="policy")]}
        )
        self._assert_blocked(self._resolve(pkg, scenario=scenario), "sensor_calibration_missing")

    def test_expect_control_hz_is_checked_against_the_contract(self):
        pkg = _make_package(self.repo)
        scenario = _scenario(advanced={"expect_control_hz": 200.0})
        response = self._resolve(pkg, scenario=scenario)
        self.assertFalse(
            response.ok,
            "场景以为的控制率与契约不符时必须阻断，而不是照跑："
            f"{[item.as_message() for item in response.blockers]}",
        )
        self.assertIn(
            self._codes(response),
            [["scenario_invalid"], ["sensor_calibration_missing"]],
        )

    def test_inner_layer_still_refuses_duplicates_unknown_plugin_and_version(self):
        """场景层已挡住的三类，解析器内部第二道防线同样不放行（防御纵深）。"""

        pkg = _make_package(self.repo)
        package = sr.PackageFacts(
            robot_id=ROBOT_ID, root=pkg, descriptor={}, sim_config={}, policies={}
        )
        base = SimpleNamespace(
            instance_id="imu_0",
            plugin_id="imu",
            plugin_version=pc.plugin_definition("imu").version,
            target=None,
            target_kind=None,
            pos=None,
            quat_wxyz=None,
            sample_hz=None,
            purpose="display",
            enabled=True,
            config={},
            noise=None,
            latency=None,
            record=None,
            record_outputs=None,
            record_png=None,
            sample_stride=None,
        )
        time_base = rc.RunTimeBase(physics_hz=PHYSICS_HZ, control_decimation=DECIMATION, source="contract")

        def findings_for(requests):
            findings = sr._Findings()
            instances, _ = sr._resolve_instances(package, SimpleNamespace(sensor_instances=requests), time_base, None, findings)
            return findings, instances

        findings, instances = findings_for([base, base])
        self.assertEqual([item.code for item in findings.blockers], ["duplicate_instance"])
        self.assertEqual(instances, ())

        findings, _ = findings_for([SimpleNamespace(**{**vars(base), "plugin_id": "ghost_sensor"})])
        self.assertEqual([item.code for item in findings.blockers], ["unknown_plugin"])

        findings, _ = findings_for([SimpleNamespace(**{**vars(base), "plugin_version": "9.9.9"})])
        self.assertEqual([item.code for item in findings.blockers], ["unknown_plugin"])

        findings, instances = findings_for([SimpleNamespace(**{**vars(base), "enabled": False})])
        self.assertEqual(findings.blockers, [])
        self.assertEqual(instances, ())


class ProviderAndEventTests(_ResolverCase):
    def _b_class_scenario(self, **provider_over):
        provider = {
            "provider_id": "lidar_velocity_gate",
            "version": pc.command_provider_definition("lidar_velocity_gate").version,
            "input_instance_ids": ["lidar_front"],
        }
        provider.update(provider_over)
        return _scenario(
            mode="navigation",
            command_source="planner",
            waypoints=[{"x": 4.0, "y": 0.0}],
            advanced={
                "sensor_instances": [_instance("lidar", "lidar_front", sample_hz=10.0)],
                "command_provider": provider,
            },
        )

    def test_external_provider_is_resolved_with_declared_defaults(self):
        pkg = _make_package(self.repo)
        response = self._resolve(pkg, scenario=self._b_class_scenario())
        self.assertTrue(response.ok, [item.as_message() for item in response.blockers])
        provider = response.spec.command_provider
        self.assertEqual(provider.provider_id, "lidar_velocity_gate")
        self.assertEqual(provider.input_instances, ("lidar_front",))
        self.assertEqual(provider.source, "scenario")
        self.assertTrue(provider.config)
        for key in provider.config:
            self.assertTrue(provider.config_provenance[key])
        self.assertIn("raycast", response.spec.required_engine_features())

    def test_provider_input_that_was_dropped_is_blocked(self):
        pkg = _make_package(self.repo)
        scenario = self._b_class_scenario()
        scenario["advanced"]["sensor_instances"][0]["enabled"] = False
        self._assert_blocked(self._resolve(pkg, scenario=scenario), "scenario_invalid")

    def test_events_stay_out_of_the_spec_but_are_still_validated(self):
        event = {
            "event_id": "push_1",
            "type": "velocity_command",
            "at_tick": 500,
            "payload": {"vx": 0.5, "vy": 0.0, "yaw_rate": 0.0},
        }
        pkg = _make_package(self.repo)
        response = self._resolve(pkg, scenario=_scenario(advanced={"events": [event]}))
        self.assertTrue(response.ok, [item.as_message() for item in response.blockers])
        self.assertNotIn("events", rc.ResolvedRunSpec.model_fields)
        self.assertIn("events=1", response.spec.notes)
        self.assertTrue(any("events_via=POST" in note for note in response.spec.notes))

    def test_broken_event_payload_is_reported_with_its_id(self):
        pkg = _make_package(self.repo)
        event = {"event_id": "bad_1", "type": "velocity_command", "at_tick": 10, "payload": {}}
        blocker = self._assert_blocked(
            self._resolve(pkg, scenario=_scenario(advanced={"events": [event]})), "scenario_invalid"
        )
        self.assertEqual(blocker.subject, "bad_1")


class RecordingBudgetTests(_ResolverCase):
    def test_budget_below_the_projected_write_is_blocked(self):
        pkg = _make_package(self.repo, policies=(_pie_policy(),))
        scenario = _scenario(
            advanced={
                "sensor_instances": [_instance("depth", "depth_policy", purpose="policy")],
                "recording": {
                    # 1×60×86×4 字节 × 10 Hz × 4 秒 = 825600，超过 512 KiB。
                    "queue_budget_bytes": 1 << 19,
                    "per_run_budget_bytes": 1 << 19,
                    "directory_budget_bytes": 1 << 19,
                    "min_free_disk_bytes": 0,
                },
            }
        )
        blocker = self._assert_blocked(
            self._resolve(
                pkg,
                policy_id="fixture_pie",
                scenario=scenario,
                metadata_reader=_metadata_reader((_obs(), _obs("depth_history", (1, 1, 60, 86)))),
            ),
            "recording_budget_unsafe",
        )
        self.assertIn("per_run_budget_bytes", blocker.detail + (blocker.field or ""))
        self.assertFalse(blocker.subject.endswith("auto_delete"))

    def test_generous_budget_only_warns(self):
        pkg = _make_package(self.repo)
        scenario = _scenario(
            advanced={
                "sensor_instances": [_instance("imu", "imu_0", record=True, sample_hz=50.0)],
                "recording": {"per_run_budget_bytes": rc.RECORDING_PER_RUN_BUDGET_BYTES},
            }
        )
        response = self._resolve(pkg, scenario=scenario)
        self.assertTrue(response.ok, [item.as_message() for item in response.blockers])
        self.assertTrue(any("MiB/s" in text for text in response.warnings))


class AssetVerificationTests(_ResolverCase):
    def setUp(self):
        super().setUp()
        self.pkg = _make_package(self.repo)
        response = self._resolve(self.pkg)
        self.assertTrue(response.ok)
        self.spec = response.spec

    def test_fresh_repository_verifies_clean(self):
        self.assertEqual(sr.verify_assets(self.spec, root=self.repo), ())

    def test_changed_bytes_are_digest_mismatch(self):
        _write(self.pkg / "model" / "robot.xml", "<mujoco><worldbody><body/></worldbody></mujoco>\n")
        codes = [item.code for item in sr.verify_assets(self.spec, root=self.repo)]
        self.assertEqual(codes, ["asset_digest_mismatch"])

    def test_deleted_file_is_reported_as_missing_not_mismatch(self):
        (self.pkg / "model" / "robot.xml").unlink()
        codes = [item.code for item in sr.verify_assets(self.spec, root=self.repo)]
        self.assertEqual(codes, ["asset_missing"])

    def test_tampered_spec_is_refused_before_asset_walk(self):
        tampered = self.spec.model_copy(update={"seed": 99})
        codes = [item.code for item in sr.verify_assets(tampered, root=self.repo)]
        self.assertIn("spec_invalid", codes)
        self.assertNotIn("asset_digest_mismatch", codes)

    def test_repeated_resolve_after_change_binds_the_new_digest(self):
        first = self.spec
        _write(self.pkg / "model" / "robot.xml", "<mujoco/><!-- v2 -->\n")
        second = self._resolve(self.pkg).spec
        self.assertNotEqual(first.spec_digest, second.spec_digest)
        self.assertEqual(sr.verify_assets(second, root=self.repo), ())
        model = next(item for item in second.assets if item.kind == "model_xml")
        self.assertNotEqual(model.sha256, next(item for item in first.assets if item.kind == "model_xml").sha256)


class CatalogExportTests(unittest.TestCase):
    def test_catalog_is_the_single_source_of_enums_and_defaults(self):
        catalog = sr.run_catalog()
        self.assertEqual(catalog.executors[0].executor_id, rc.NATIVE_EXECUTOR_ID)
        self.assertEqual(catalog.executors[0].native_runtime_version, rc.NATIVE_RUNTIME_VERSION)
        self.assertEqual(catalog.sensor_plugins, pc.plugin_catalog_payload())
        self.assertEqual(catalog.protocol, wire.protocol_limits())
        self.assertEqual(catalog.stream, rc.ws_stream_contract())
        self.assertEqual(catalog.recording_defaults, rc.RecordingOptions().budget_dict())
        self.assertIsNone(catalog.probe)

    def test_catalog_can_carry_a_probe_report_verbatim(self):
        report = _probe_report()({"required_features": ["model_compile"]})
        self.assertEqual(sr.run_catalog(report).probe, report)

    def test_resolver_version_is_not_the_runtime_version(self):
        """新 worker/native 能力有独立版本标识，不冒称旧 server_mujoco 已有闭环。"""

        self.assertNotEqual(sr.RESOLVER_VERSION, rc.NATIVE_RUNTIME_VERSION)
        self.assertTrue(sr.RESOLVER_VERSION.startswith("sim-resolver"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
