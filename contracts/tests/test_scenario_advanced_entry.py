"""scenario-contract-1.2 高级仿真入口测试（任务 7 范围 ①＋⑥）。

守什么（每条都对应 :mod:`contracts.scenario_contract` 里一处**真实存在**的约束）：

1. **旧场景兼容**：1.0/1.1 载荷不带 ``advanced`` 时行为逐字不变 —— 默认版本仍是
   1.1、1.1 的四组高级字段与感知分层约束都不因 1.2 落地而被稀释；
2. **版本门**：带 ``advanced`` 必须显式写 ``scenario-contract-1.2``，代码升级不会让
   旧文件突然多出新行为；
3. **防双真值**：``perception.depth_camera`` 与 ``purpose=policy`` 的 depth 实例、
   ``command_provider`` 与 ``route=obs`` / ``command_source=policy`` 三组互斥；调度
   tick、插件默认参数、记录预算数字在场景侧一律**不出现**；
4. **声明复用**：参数名、版本、target、mount、噪声/延迟能力、输出与 PNG 记录全部回查
   :mod:`contracts.sensor_plugin_contract`；事件形状**完全交给**
   :class:`~contracts.simulation_run_contract.ScheduledEvent`（这里不复制任何规则）。

负例一律走**构造函数**（``model_validate``）而不是 ``model_copy`` —— 后者会绕过校验器，
测出来的"通过"是假的。
"""

from __future__ import annotations

import unittest
from typing import get_args

from pydantic import ValidationError

from contracts import scenario_contract as sc
from contracts import sensor_plugin_contract as pc
from contracts import simulation_run_contract as rc
from contracts.scenario_contract import (
    SCENARIO_CONTRACT_VERSION_1_2,
    CommandProviderRequest,
    ScenarioAdvanced,
    ScenarioContract,
    ScenarioEventRequest,
    SensorInstanceRequest,
)

#: ``velocity_command`` 的权威载荷键（来自 ``EVENT_PAYLOAD_SPEC``，此处只是夹具）。
VELOCITY = {"vx": 0.5, "vy": 0.0, "yaw_rate": 0.0}
SHA_A = "a" * 64


def _fields_for(plugin_id: str, instance_id: str) -> dict:
    """按 catalog 声明造一份该插件**合法**的请求（``requires_target`` 自动补 target）。"""

    definition = pc.plugin_definition(plugin_id)
    fields: dict = {
        "instance_id": instance_id,
        "plugin_id": plugin_id,
        "plugin_version": definition.version if definition is not None else "1.0.0",
    }
    if definition is not None and definition.requires_target:
        fields["target"] = "camera_site"
    return fields


def _instance(plugin_id: str = "imu", instance_id: str | None = None, **overrides) -> SensorInstanceRequest:
    fields = _fields_for(plugin_id, f"{plugin_id}_0" if instance_id is None else instance_id)
    fields.update(overrides)
    return SensorInstanceRequest.model_validate(fields)


def _provider(**overrides) -> CommandProviderRequest:
    fields: dict = {
        "provider_id": "lidar_velocity_gate",
        "version": "1.0.0",
        "input_instance_ids": ["lidar_0"],
    }
    fields.update(overrides)
    return CommandProviderRequest.model_validate(fields)


def _event(**overrides) -> ScenarioEventRequest:
    fields: dict = {"event_id": "push_1", "type": "velocity_command", "at_tick": 500, "payload": dict(VELOCITY)}
    fields.update(overrides)
    return ScenarioEventRequest.model_validate(fields)


def _advanced(**overrides) -> ScenarioAdvanced:
    return ScenarioAdvanced.model_validate(dict(overrides))


def _scenario(**overrides) -> ScenarioContract:
    fields: dict = {"scenario_id": "adv_gate", "schema_version": SCENARIO_CONTRACT_VERSION_1_2}
    fields.update(overrides)
    return ScenarioContract.model_validate(fields)


class LegacyEntryTests(unittest.TestCase):
    """1.0 / 1.1 载荷在 1.2 落地后必须逐字不变。"""

    LEGACY_1_0 = {
        "schema_version": "scenario-contract-1.0",
        "scenario_id": "legacy_flat",
        "mode": "basic",
        "seed": 7,
        "episode_length_s": 30.0,
        "command_limits": {"vx": 0.8, "vy": 0.4, "wz": 1.2},
        "metrics": ["reward"],
    }
    LEGACY_1_1 = {
        "schema_version": "scenario-contract-1.1",
        "scenario_id": "legacy_nav",
        "mode": "navigation",
        "waypoints": [{"x": 3.0, "y": 1.0}],
        "command_source": "planner",
        "terrain": {"kind": "stairs"},
        "termination": {"fall_pitch": 0.8, "timeout": 30.0},
        "assessment": {"route_completion_min": 0.9},
        "perception": {
            "heightfield": True,
            "depth_camera": {"width": 106, "height": 60},
            "route": "external",
        },
    }

    def test_legacy_payloads_build_without_advanced_and_round_trip(self):
        for payload in (self.LEGACY_1_0, self.LEGACY_1_1):
            with self.subTest(schema_version=payload["schema_version"]):
                scenario = ScenarioContract.model_validate(payload)
                self.assertIsNone(scenario.advanced)
                restored = ScenarioContract.model_validate(scenario.to_payload())
                self.assertEqual(restored.model_dump(mode="json"), scenario.model_dump(mode="json"))

    def test_default_schema_version_was_not_moved_to_1_2(self):
        # 老调用方（backend/api_complete.validate_scenario、backend/simulation_api）不传版本号。
        self.assertEqual(ScenarioContract(scenario_id="probe").schema_version, "scenario-contract-1.1")
        self.assertEqual(SCENARIO_CONTRACT_VERSION_1_2, "scenario-contract-1.2")

    def test_1_1_perception_routing_rules_are_not_diluted(self):
        with self.assertRaises(ValidationError):
            ScenarioContract.model_validate(
                {**self.LEGACY_1_1, "command_source": "planner", "perception": {"route": "obs"}}
            )
        with self.assertRaises(ValidationError):
            ScenarioContract.model_validate({"scenario_id": "no_target", "command_source": "planner"})

    def test_1_1_terrain_group_still_survives_to_payload(self):
        scenario = ScenarioContract.model_validate(self.LEGACY_1_1)
        payload = scenario.to_payload()
        self.assertEqual(payload["terrain"]["kind"], "stairs")
        self.assertEqual(payload["termination"]["timeout"], 30.0)
        self.assertEqual(payload["perception"]["depth_camera"]["width"], 106)
        self.assertIsNone(payload["advanced"])


class VersionGateTests(unittest.TestCase):
    def test_advanced_requires_explicit_1_2(self):
        for version in ("scenario-contract-1.0", "scenario-contract-1.1"):
            with self.subTest(version=version), self.assertRaises(ValidationError) as ctx:
                _scenario(schema_version=version, advanced=_advanced(events=[_event()]))
            self.assertIn("scenario-contract-1.2", str(ctx.exception))

    def test_1_2_without_advanced_is_a_valid_intermediate_state(self):
        scenario = _scenario()
        self.assertIsNone(scenario.advanced)
        self.assertEqual(scenario.mode, "basic")

    def test_unknown_schema_version_is_still_refused(self):
        with self.assertRaises(ValidationError):
            _scenario(schema_version="scenario-contract-2.0")

    def test_empty_advanced_injects_no_default_behaviour(self):
        # 空 advanced 只表示"走 v2 入口但暂不声明实例"，不会偷偷长出传感器/记录器
        advanced = _advanced()
        self.assertEqual(advanced.sensor_instances, [])
        self.assertEqual(advanced.events, [])
        self.assertIsNone(advanced.command_provider)
        self.assertIsNone(advanced.recording)
        self.assertIsNone(advanced.expect_control_hz)


class SensorInstanceRequestTests(unittest.TestCase):
    def test_minimal_request_reads_version_from_the_catalog(self):
        instance = _instance("imu", "imu_0")
        self.assertEqual(instance.plugin_version, pc.plugin_definition("imu").version)
        self.assertTrue(instance.enabled)
        self.assertEqual(instance.purpose, "display")
        self.assertEqual(instance.config, {})
        self.assertIsNone(instance.sample_hz)
        self.assertIsNone(instance.target)

    def test_every_instantiable_plugin_can_be_requested(self):
        # 反向扫 catalog：合法插件不该被场景层误伤（新增插件时这条会立刻指出谁不合规）。
        for plugin_id in pc.plugin_ids():
            with self.subTest(plugin_id=plugin_id):
                _instance(plugin_id, f"{plugin_id}_0")

    def test_unknown_and_derived_plugins_are_refused(self):
        with self.assertRaises(ValidationError) as ctx:
            _instance("no_such_sensor", "x_0")
        self.assertIn("未知传感器插件", str(ctx.exception))
        derived = pc.plugin_definition("lidar_height_scan")
        self.assertIsNotNone(derived)
        self.assertFalse(derived.instantiable)
        with self.assertRaises(ValidationError) as ctx:
            _instance("lidar_height_scan", "view_0")
        self.assertIn("派生视图", str(ctx.exception))

    def test_plugin_version_must_be_the_registered_semver(self):
        with self.assertRaises(ValidationError) as ctx:
            _instance("lidar", "lidar_0", plugin_version="0.9.0")
        self.assertIn("catalog 登记", str(ctx.exception))
        with self.assertRaises(ValidationError):
            _instance("lidar", "lidar_0", plugin_version="1.0")

    def test_scheduling_period_cannot_be_written_in_a_scenario(self):
        # Hz 与 tick 不能同时是真相：场景只写 sample_hz，tick 由解析器按时间基换算。
        with self.assertRaises(ValidationError) as ctx:
            _instance("lidar", "lidar_0", config={"sample_period_ticks": 10})
        self.assertIn("sample_hz", str(ctx.exception))
        self.assertEqual(_instance("lidar", "lidar_0", sample_hz=50.0).sample_hz, 50.0)

    def test_undeclared_parameter_names_are_refused(self):
        with self.assertRaises(ValidationError) as ctx:
            _instance("lidar", "lidar_0", config={"numbers_of_rays": 240})
        self.assertIn("未声明参数", str(ctx.exception))
        declared = _instance("lidar", "lidar_0", config={"count": 108})
        self.assertEqual(declared.config["count"], 108)

    def test_value_ranges_live_in_the_declaration_not_in_the_scenario(self):
        """请求层只查"名字声明过没有"，**取值范围只住在插件声明里**（一份真值）。

        两侧同时钉住：越界值能穿过请求层（说明这里没抄一份范围），但一定被
        ``resolve_config`` 挡下（说明范围规则确实存在且生效）。
        """

        definition = pc.plugin_definition("lidar")
        self.assertGreater(definition.config_field("max_range").maximum, 1.0)
        request = _instance("lidar", "lidar_0", config={"max_range": 99999.0})
        self.assertEqual(request.config["max_range"], 99999.0)
        with self.assertRaises(ValueError):
            definition.resolve_config({"sample_period_ticks": 10, "max_range": 99999.0})

    def test_required_calibration_is_not_invented_by_the_scenario(self):
        request = _instance("depth", "depth_0", purpose="policy", sample_hz=10.0)
        self.assertEqual(request.config, {})
        self.assertIn("sample_period_ticks", pc.plugin_definition("depth").required_config())
        with self.assertRaises(ValueError):
            pc.plugin_definition("depth").resolve_config({})

    def test_target_and_mount_extrinsics_follow_the_declaration(self):
        with self.assertRaises(ValidationError) as ctx:
            _instance("depth", "depth_0", target=None)
        self.assertIn("必须给 target", str(ctx.exception))
        self.assertEqual(_instance("depth", "depth_0").target, "camera_site")
        self.assertFalse(pc.plugin_definition("odom").mountable)
        with self.assertRaises(ValidationError) as ctx:
            _instance("odom", "odom_0", pos=[0.0, 0.0, 0.1])
        self.assertIn("不是物理器件", str(ctx.exception))
        self.assertEqual(_instance("imu", "imu_0", pos=[0.0, 0.0, 0.3]).pos, [0.0, 0.0, 0.3])

    def test_non_finite_extrinsics_are_refused(self):
        with self.assertRaises(ValidationError) as ctx:
            _instance("imu", "imu_0", pos=[float("nan"), 0.0, 0.0])
        self.assertIn("非有限", str(ctx.exception))
        with self.assertRaises(ValidationError):
            _instance("imu", "imu_0", quat_wxyz=[float("inf"), 0.0, 0.0, 0.0])

    def test_noise_and_latency_capability_come_from_the_plugin(self):
        self.assertFalse(pc.plugin_definition("rgb").supports_noise)
        with self.assertRaises(ValidationError) as ctx:
            _instance("rgb", "cam_0", noise={"kind": "gaussian", "sigma": 0.01})
        self.assertIn("不支持噪声", str(ctx.exception))
        self.assertFalse(pc.plugin_definition("foot_contact").supports_latency)
        with self.assertRaises(ValidationError) as ctx:
            _instance("foot_contact", "foot_fl", latency={"kind": "fixed", "ticks": 2})
        self.assertIn("不支持延迟", str(ctx.exception))
        both = _instance(
            "lidar",
            "lidar_0",
            noise={"kind": "dropout", "dropout_rate": 0.05},
            latency={"kind": "jitter", "jitter_ticks": 3},
        )
        self.assertIsInstance(both.noise, pc.NoiseSpec)
        self.assertIsInstance(both.latency, pc.LatencySpec)

    def test_record_options_must_name_declared_outputs(self):
        outputs = {output.name for output in pc.plugin_definition("depth").outputs}
        self.assertIn("policy_tensor", outputs)
        self.assertEqual(_instance("depth", "depth_0", record_outputs=["policy_tensor"]).record_outputs, ["policy_tensor"])
        with self.assertRaises(ValidationError) as ctx:
            _instance("depth", "depth_0", record_outputs=["depth_raw", "no_such_output"])
        self.assertIn("未声明的输出", str(ctx.exception))

    def test_record_png_needs_a_png_output(self):
        # 与 SensorInstanceSpec 读同一份 ``definition.outputs``，不另立规则。
        png_outputs = [
            output.name for output in pc.plugin_definition("depth").outputs if output.payload_kind == "image_png"
        ]
        self.assertTrue(png_outputs)
        self.assertTrue(_instance("depth", "depth_0", record_png=True).record_png)
        self.assertFalse(any(o.payload_kind == "image_png" for o in pc.plugin_definition("imu").outputs))
        with self.assertRaises(ValidationError) as ctx:
            _instance("imu", "imu_0", record_png=True)
        self.assertIn("PNG", str(ctx.exception))

    def test_stride_rate_and_purpose_bounds_are_enforced(self):
        for kwargs in (
            {"sample_stride": 0},
            {"sample_stride": 100_001},
            {"sample_hz": 0.0},
            {"sample_hz": 30_000.0},
        ):
            with self.subTest(**kwargs), self.assertRaises(ValidationError):
                _instance("imu", "imu_0", **kwargs)
        with self.assertRaises(ValidationError):
            _instance("imu", "imu_0", purpose="training")
        for purpose in ("policy", "display", "evaluation"):
            self.assertEqual(_instance("imu", "imu_0", purpose=purpose).purpose, purpose)

    def test_unknown_field_and_mutation_are_refused(self):
        with self.assertRaises(ValidationError) as ctx:
            _instance("imu", "imu_0", vendor_default="mjlab")
        self.assertIn("vendor_default", str(ctx.exception))
        instance = _instance("imu", "imu_0")
        with self.assertRaises(ValidationError):
            instance.instance_id = "other"

    def test_instance_id_uses_the_same_safe_identifier_rule(self):
        self.assertEqual(sc._SCENARIO_SAFE_ID_RE.pattern, pc.SAFE_ID_PATTERN)
        for bad in ("../evil", "a/b", "a\\b", "IMU_0", "..", ""):
            with self.subTest(instance_id=bad), self.assertRaises(ValidationError):
                _instance("imu", bad)
        self.assertEqual(_instance("imu", "imu.0-front").instance_id, "imu.0-front")


class CommandProviderTests(unittest.TestCase):
    def test_registered_provider_request_is_accepted(self):
        definition = pc.command_provider_definition("lidar_velocity_gate")
        self.assertIsNotNone(definition)
        provider = _provider(version=definition.version)
        self.assertEqual(provider.source, "scenario")
        self.assertEqual(provider.input_instance_ids, ["lidar_0"])

    def test_unknown_provider_and_version_are_refused(self):
        with self.assertRaises(ValidationError) as ctx:
            _provider(provider_id="waypoint_follower")
        self.assertIn("未知命令提供器", str(ctx.exception))
        with self.assertRaises(ValidationError):
            _provider(version="9.9.9")

    def test_input_ids_must_be_unique_and_non_empty(self):
        with self.assertRaises(ValidationError):
            _provider(input_instance_ids=[])
        with self.assertRaises(ValidationError) as ctx:
            _provider(input_instance_ids=["lidar_0", "lidar_0"])
        self.assertIn("重复", str(ctx.exception))

    def test_undeclared_provider_parameter_is_refused(self):
        declared = {field.name for field in pc.command_provider_definition("lidar_velocity_gate").config}
        stray = sorted({"gain", "comfort", "gate_m", "min_speed_mps", "max_speed_mps"} - declared)
        self.assertTrue(stray, "夹具假设被 catalog 推翻：请改这条测试的候选参数名")
        with self.assertRaises(ValidationError) as ctx:
            _provider(config={stray[0]: 1.0})
        self.assertIn("未声明参数", str(ctx.exception))

    def test_membership_and_plugin_kind_are_checked_by_the_container(self):
        # 单个请求对象没有"实例清单"可查；引用校验住在 ScenarioAdvanced，两处都不放行。
        _provider(input_instance_ids=["ghost"])
        with self.assertRaises(ValidationError) as ctx:
            _advanced(command_provider=_provider(input_instance_ids=["ghost"]))
        self.assertIn("未在 sensor_instances 里声明", str(ctx.exception))
        with self.assertRaises(ValidationError) as ctx:
            _advanced(
                sensor_instances=[_instance("depth", "depth_0")],
                command_provider=_provider(input_instance_ids=["depth_0"]),
            )
        self.assertIn("不接受插件", str(ctx.exception))

    def test_valid_b_class_container(self):
        advanced = _advanced(
            sensor_instances=[_instance("lidar", "lidar_0"), _instance("imu", "imu_0")],
            command_provider=_provider(input_instance_ids=["lidar_0"]),
        )
        self.assertEqual([item.instance_id for item in advanced.sensor_instances], ["lidar_0", "imu_0"])
        self.assertEqual(advanced.command_provider.provider_id, "lidar_velocity_gate")


class ScenarioEventTests(unittest.TestCase):
    def test_to_scheduled_event_produces_the_authoritative_shape(self):
        request = _event(event_id="push_1", at_tick=500, duration_ticks=100)
        event = request.to_scheduled_event()
        self.assertIsInstance(event, rc.ScheduledEvent)
        self.assertEqual(event.schema_version, rc.RUN_CONTRACT_VERSION)
        self.assertEqual(event.expected_epoch, 0)
        self.assertEqual(event.source, "scenario")
        self.assertEqual(event.at_tick, 500)
        self.assertEqual(event.duration_ticks, 100)
        self.assertEqual(event.payload, VELOCITY)
        self.assertIsNot(event.payload, request.payload)

    def test_epoch_is_supplied_by_the_runtime_not_by_the_scenario(self):
        self.assertEqual(_event().to_scheduled_event(expected_epoch=3).expected_epoch, 3)

    def test_payload_validation_is_delegated_not_copied(self):
        # 场景侧不重写载荷规则：键不全 / 键多写 / 非法故障状态都由 ScheduledEvent 拒绝。
        with self.assertRaises(ValidationError) as ctx:
            _event(payload={}).to_scheduled_event()
        self.assertIn("载荷键不符", str(ctx.exception))
        with self.assertRaises(ValidationError):
            _event(payload={**VELOCITY, "z": 1.0}).to_scheduled_event()
        with self.assertRaises(ValidationError):
            _event(
                type="sensor_fault",
                payload={"instance_id": "imu_0", "state": "valid", "duration_ticks": 10},
            ).to_scheduled_event()
        with self.assertRaises(ValidationError):
            _event(type="sensor_fault", payload={"instance_id": "imu_0", "state": "missing"}).to_scheduled_event()

    def test_every_scenario_event_type_maps_to_the_authoritative_table(self):
        """场景侧的 ``type`` 词表必须与 ``EVENT_PAYLOAD_SPEC`` 完全同一份。"""

        annotation = ScenarioEventRequest.model_fields["type"].annotation
        self.assertEqual(set(get_args(annotation)), set(rc.EVENT_PAYLOAD_SPEC))
        payloads = {
            "velocity_command": VELOCITY,
            "wrench": {"force": [1.0, 0.0, 0.0], "torque": [0.0, 0.0, 0.0], "body": "base"},
            "sensor_fault": {"instance_id": "imu_0", "state": "missing", "duration_ticks": 10},
            "policy_switch": {"policy_id": "go2_pie_parkour", "artifact_sha256": SHA_A},
            "run_control": {"action": "pause"},
        }
        self.assertEqual(set(payloads), set(rc.EVENT_PAYLOAD_SPEC))
        for event_type, payload in payloads.items():
            with self.subTest(type=event_type):
                event = _event(
                    event_id=f"e_{event_type}", type=event_type, duration_ticks=50, payload=payload
                ).to_scheduled_event()
                self.assertEqual(event.type, event_type)
                self.assertEqual(event.payload, payload)

    def test_event_id_and_tick_are_checked(self):
        with self.assertRaises(ValidationError):
            _event(event_id="../push")
        with self.assertRaises(ValidationError):
            _event(at_tick=-1)
        with self.assertRaises(ValidationError):
            _event(unknown_field=1)

    def test_duplicate_event_ids_are_refused_in_one_scenario(self):
        with self.assertRaises(ValidationError) as ctx:
            _advanced(events=[_event(event_id="e1"), _event(event_id="e1", at_tick=900)])
        self.assertIn("重复 event_id", str(ctx.exception))
        self.assertEqual(len(_advanced(events=[_event(event_id="e1"), _event(event_id="e2")]).events), 2)


class ScenarioAdvancedContainerTests(unittest.TestCase):
    def test_duplicate_instance_ids_are_refused(self):
        with self.assertRaises(ValidationError) as ctx:
            _advanced(sensor_instances=[_instance("imu", "imu_0"), _instance("imu", "imu_0")])
        self.assertIn("重复实例", str(ctx.exception))

    def test_two_instances_of_the_same_plugin_are_allowed(self):
        advanced = _advanced(
            sensor_instances=[_instance("lidar", "lidar_front"), _instance("lidar", "lidar_rear")]
        )
        self.assertEqual([item.instance_id for item in advanced.sensor_instances], ["lidar_front", "lidar_rear"])

    def test_executor_is_not_a_free_choice(self):
        self.assertEqual(_advanced().executor_id, "native_mujoco")
        with self.assertRaises(ValidationError):
            _advanced(executor_id="wasm")
        with self.assertRaises(ValidationError):
            _advanced(executor_id="")

    def test_scenario_never_produces_a_time_base(self):
        fields = set(ScenarioAdvanced.model_fields)
        self.assertFalse(
            {"sample_period_ticks", "physics_hz", "decimation", "control_period_ticks", "tick"} & fields
        )
        self.assertEqual(_advanced(expect_control_hz=50.0).expect_control_hz, 50.0)
        with self.assertRaises(ValidationError):
            _advanced(expect_control_hz=0.0)

    def test_recording_budget_is_delegated_to_the_shared_model(self):
        advanced = _advanced(recording=rc.RecordingOptions())
        self.assertEqual(advanced.recording.queue_budget_bytes, rc.RECORDING_QUEUE_BUDGET_BYTES)
        self.assertFalse(advanced.recording.auto_delete)
        with self.assertRaises(ValidationError) as ctx:
            _advanced(recording={"queue_budget_bytes": 4096, "per_run_budget_bytes": 1024})
        self.assertIn("队列预算", str(ctx.exception))
        with self.assertRaises(ValidationError):
            _advanced(recording={"auto_delete": True})
        with self.assertRaises(ValidationError):
            _advanced(recording={"data_root": "../episodes"})

    def test_unknown_container_field_is_refused(self):
        with self.assertRaises(ValidationError):
            _advanced(sensors=[])


class AntiDoubleTruthTests(unittest.TestCase):
    """``ScenarioContract.validate_advanced_entry`` 的三条互斥门。"""

    def test_provider_conflicts_with_a_class_layering(self):
        advanced = _advanced(
            sensor_instances=[_instance("lidar", "lidar_0")],
            command_provider=_provider(input_instance_ids=["lidar_0"]),
        )
        with self.assertRaises(ValidationError) as ctx:
            _scenario(perception={"route": "obs"}, advanced=advanced)
        self.assertIn("command_provider 冲突", str(ctx.exception))

    def test_provider_conflicts_with_policy_command_source(self):
        advanced = _advanced(
            sensor_instances=[_instance("lidar", "lidar_0")],
            command_provider=_provider(input_instance_ids=["lidar_0"]),
        )
        with self.assertRaises(ValidationError) as ctx:
            _scenario(command_source="policy", advanced=advanced)
        self.assertIn("不能是 policy", str(ctx.exception))

    def test_b_class_positive_control(self):
        # 外部决策器 + 外部命令源 + 航点：这是 B 类（外置 LiDAR 只改指令）的唯一合法形状。
        scenario = _scenario(
            mode="navigation",
            command_source="planner",
            waypoints=[{"x": 4.0, "y": 0.0}],
            perception={"route": "external", "mount": "scene:lidar_pole"},
            advanced=_advanced(
                sensor_instances=[_instance("lidar", "lidar_0", sample_hz=10.0)],
                command_provider=_provider(input_instance_ids=["lidar_0"]),
            ),
        )
        self.assertEqual(scenario.advanced.command_provider.provider_id, "lidar_velocity_gate")
        self.assertEqual(scenario.perception.mount, "scene:lidar_pole")

    def test_policy_depth_cannot_be_declared_twice(self):
        policy_depth = _instance("depth", "depth_policy", purpose="policy")
        with self.assertRaises(ValidationError) as ctx:
            _scenario(
                perception={"depth_camera": {"width": 106, "height": 60}},
                advanced=_advanced(sensor_instances=[policy_depth]),
            )
        self.assertIn("同一策略输入有两条", str(ctx.exception))

    def test_display_depth_may_coexist_with_1_1_depth_camera(self):
        scenario = _scenario(
            perception={"depth_camera": {"width": 106, "height": 60}, "route": "obs"},
            command_source="policy",
            advanced=_advanced(
                sensor_instances=[_instance("depth", "depth_view", purpose="display", sample_hz=5.0)]
            ),
        )
        self.assertEqual(scenario.advanced.sensor_instances[0].purpose, "display")

    def test_a_class_positive_control(self):
        # A 类（go2-pie-parkour 吃深度）：只有一个来源声明 —— advanced 实例，且没有 depth_camera。
        scenario = _scenario(
            perception={"route": "obs", "heightfield": True},
            command_source="policy",
            advanced=_advanced(
                sensor_instances=[
                    _instance("imu", "imu_0", purpose="policy", sample_hz=50.0),
                    _instance("depth", "depth_0", purpose="policy", sample_hz=10.0),
                ],
                expect_control_hz=50.0,
            ),
        )
        self.assertIsNone(scenario.perception.depth_camera)
        self.assertEqual(
            [item.purpose for item in scenario.advanced.sensor_instances], ["policy", "policy"]
        )
        payload = scenario.to_payload()
        self.assertEqual(payload["advanced"]["sensor_instances"][1]["plugin_id"], "depth")
        self.assertEqual(payload["advanced"]["expect_control_hz"], 50.0)
        self.assertEqual(
            ScenarioContract.model_validate(payload).model_dump(mode="json"),
            scenario.model_dump(mode="json"),
        )

    def test_events_are_not_tick_validated_at_scenario_level(self):
        """**刻意**不在场景层换算 tick（那需要第二个频率真值）→ 超长时间基也放行。

        这条钉住"检查归解析器"的边界：若有人把换算塞回场景层，本测试变红。
        """
        scenario = _scenario(
            episode_length_s=1.0,
            advanced=_advanced(events=[_event(at_tick=10_000_000)]),
        )
        self.assertEqual(scenario.advanced.events[0].at_tick, 10_000_000)


class SingleSourceTests(unittest.TestCase):
    def test_scenario_reuses_the_shared_contract_classes(self):
        self.assertIs(sc.RecordingOptions, rc.RecordingOptions)
        self.assertIs(sc.ScheduledEvent, rc.ScheduledEvent)
        self.assertIs(sc.NoiseSpec, pc.NoiseSpec)
        self.assertIs(sc.LatencySpec, pc.LatencySpec)

    def test_catalog_membership_is_queried_not_copied(self):
        # 未登记插件被拒时，消息列出的是**当前 catalog** 的 id 清单（不是抄下来的一份名单）。
        with self.assertRaises(ValidationError) as ctx:
            _instance("no_such_sensor", "x_0")
        message = str(ctx.exception)
        for plugin_id in pc.plugin_ids():
            self.assertIn(plugin_id, message)

    def test_scenario_does_not_carry_plugin_defaults(self):
        """场景层不接受"整份插件参数"（那等于把默认值搬第二个家）。"""

        first = _instance("imu", "first")
        second = _instance("imu", "second")
        self.assertEqual(first.config, {})
        self.assertEqual(second.config, {})
        self.assertIsNot(first.config, second.config)
        self.assertNotIn("plugin_defaults", ScenarioAdvanced.model_fields)
        self.assertNotIn("sensors", ScenarioAdvanced.model_fields)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
