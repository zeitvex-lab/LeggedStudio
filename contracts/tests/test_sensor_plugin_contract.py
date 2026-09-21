"""传感器/命令提供器**声明层** :mod:`contracts.sensor_plugin_contract` 的定向测试。

这一层是"插件默认值与参数出处只有一份"的落点，所以测试重点不是数量，而是：

* **默认值不可编造**：标定类参数（深度的 min/max/crop/history/采样周期）必须无默认值且必填；
* **覆盖只能落到已声明参数上**：未知参数名、越界值、违反交叉约束的取值一律拒绝；
* **能力级别不可跳级宣称**：``verified`` 必须带证据，且当前目录里没人能凭声明升格；
* **catalog 与解析结果同源**：浏览器看到的默认值就是 :meth:`resolve_config` 用的那份。
"""

from __future__ import annotations

import unittest

from pydantic import ValidationError

import contracts.sensor_plugin_contract as pc
from contracts.simulation_protocol import DTYPE_ITEMSIZE


def _tensor_output(name: str = "depth", dtype: str = "f4", dims=(4, 4), unit: str = "m"):
    return pc.SensorOutputSpec(name=name, payload_kind="tensor", dtype=dtype,
                               dims=dims, unit=unit)


def _definition(**overrides):
    base = dict(
        plugin_id="probe_plugin",
        version="1.0.0",
        display_name="测试插件",
        sensor_class="exteroceptive",
        ui_panel="readout",
        config=(),
        outputs=(_tensor_output(),),
    )
    base.update(overrides)
    return pc.SensorPluginDefinition(**base)


class RegistryTests(unittest.TestCase):
    def test_all_plugins_are_constructible_and_addressable(self) -> None:
        ids = pc.plugin_ids()
        self.assertEqual(len(ids), len(set(ids)))
        for plugin_id in ids:
            definition = pc.plugin_definition(plugin_id)
            self.assertIsNotNone(definition, plugin_id)
            self.assertEqual(definition.plugin_id, plugin_id)
            self.assertEqual(pc.capability_level_of(plugin_id), definition.capability_level)
        # A/B 两类闭环都要用到的插件必须在册
        for required in ("depth", "lidar", "imu", "odom", "rgb", "foot_contact", "height", "rangefinder"):
            self.assertIn(required, ids)

    def test_unknown_ids_return_none_not_default(self) -> None:
        """``None`` 而不是 ``registered``：把未知插件当已登记放行就是静默冒充。"""

        self.assertIsNone(pc.plugin_definition("does_not_exist"))
        self.assertIsNone(pc.capability_level_of("does_not_exist"))
        self.assertIsNone(pc.command_provider_definition("does_not_exist"))

    def test_every_output_declares_units_and_known_dtype(self) -> None:
        for plugin_id in pc.plugin_ids():
            for output in pc.plugin_definition(plugin_id).outputs:
                self.assertIsInstance(output.name, str)
                if output.payload_kind == "tensor":
                    self.assertIn(output.dtype, DTYPE_ITEMSIZE, f"{plugin_id}.{output.name}")
                    self.assertTrue(output.unit, f"{plugin_id}.{output.name} 缺单位")
                else:
                    self.assertIsNone(output.dtype)

    def test_multi_instance_prerequisites_are_declared(self) -> None:
        """同类型多实例 + 频率/噪声/延迟：这些能力必须写在**声明**里，而不是实现里猜。"""

        self.assertEqual(pc.NoiseSpec.model_fields["rng_stream"].default, "instance")
        for plugin_id in ("depth", "lidar", "imu", "odom"):
            definition = pc.plugin_definition(plugin_id)
            self.assertTrue(definition.instantiable, plugin_id)
            self.assertTrue(definition.supports_noise, plugin_id)
            self.assertTrue(definition.supports_latency, plugin_id)
            self.assertTrue(definition.config_field("sample_period_ticks") is not None)

    def test_derived_views_cannot_be_instantiated(self) -> None:
        for plugin_id in pc.plugin_ids():
            definition = pc.plugin_definition(plugin_id)
            if definition.derived_from:
                self.assertFalse(definition.instantiable, plugin_id)
                self.assertIn(definition.derived_from, pc.plugin_ids())

    def test_engine_requirements_reference_real_probe_features(self) -> None:
        import contracts.simulation_run_contract as rc

        for plugin_id in pc.plugin_ids():
            for feature in pc.required_capabilities(plugin_id):
                self.assertIn(feature, rc.PROBE_FEATURES, f"{plugin_id} 要求未知特征 {feature}")
        for provider_id in pc.command_provider_ids():
            for feature in pc.provider_required_capabilities(provider_id):
                self.assertIn(feature, rc.PROBE_FEATURES)
            self.assertEqual(pc.PROVIDER_ENGINE_REQUIREMENTS[provider_id],
                             pc.provider_required_capabilities(provider_id))


class HonestCapabilityLevelTests(unittest.TestCase):
    def test_no_plugin_claims_verified_without_evidence(self) -> None:
        """采集器尚未实现/探测：当前**每一条**声明都只能停在 registered。"""

        for plugin_id in pc.plugin_ids():
            definition = pc.plugin_definition(plugin_id)
            self.assertEqual(definition.capability_level, "registered", plugin_id)
            self.assertIsNone(definition.verified_evidence, plugin_id)
        for provider_id in pc.command_provider_ids():
            definition = pc.command_provider_definition(provider_id)
            self.assertEqual(definition.capability_level, "registered", provider_id)

    def test_verified_level_requires_evidence_at_construction(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            _definition(capability_level="verified")
        self.assertIn("verified_evidence", str(caught.exception))
        ok = _definition(capability_level="verified", verified_evidence="tests/fixtures/baseline.json")
        self.assertEqual(ok.capability_level, "verified")

    def test_level_vocabulary_is_ordered_and_closed(self) -> None:
        self.assertEqual(pc.CAPABILITY_LEVELS, ("registered", "implemented", "available", "verified"))
        with self.assertRaises(ValidationError):
            _definition(capability_level="almost_there")

    def test_derived_view_cannot_be_instantiable(self) -> None:
        with self.assertRaises(ValidationError):
            _definition(derived_from="depth", instantiable=True)

    def test_duplicate_output_names_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            _definition(outputs=(_tensor_output("a"), _tensor_output("a")))

    def test_empty_outputs_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            _definition(outputs=())


class PolicyOutputTests(unittest.TestCase):
    def test_depth_policy_output_is_the_tensor_route(self) -> None:
        """「哪一路输出喂给策略」只有一个声明处，且必须是张量。"""

        depth = pc.plugin_definition("depth")
        self.assertEqual(depth.policy_output, "policy_tensor")
        names = [output.name for output in depth.outputs]
        self.assertIn(depth.policy_output, names)

    def test_policy_output_must_reference_existing_tensor_output(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            _definition(policy_output="ghost")
        self.assertIn("policy_output", str(caught.exception))
        with self.assertRaises(ValidationError) as caught:
            _definition(
                outputs=(_tensor_output("t"),
                         pc.SensorOutputSpec(name="image", payload_kind="image_png")),
                policy_output="image",
            )
        self.assertIn("张量", str(caught.exception))

    def test_only_depth_feeds_the_policy_observation(self) -> None:
        """背景约束：A 类吃深度，B 类的 LiDAR 只改指令 → lidar 不得有 policy_output。"""

        self.assertIsNone(pc.plugin_definition("lidar").policy_output)
        self.assertIsNone(pc.plugin_definition("rgb").policy_output)
        declared = [pid for pid in pc.plugin_ids()
                    if pc.plugin_definition(pid).policy_output]
        self.assertEqual(declared, ["depth"])


class ConfigFieldTests(unittest.TestCase):
    def test_calibration_fields_have_no_default(self) -> None:
        """标定四项 + 采样周期：默认值属于策略契约，写进契约里就是允许两处不同真值。"""

        depth = pc.plugin_definition("depth")
        for name in ("sample_period_ticks", "min_range", "max_range", "crop_width",
                     "history_frames"):
            field = depth.config_field(name)
            self.assertIsNotNone(field, name)
            self.assertTrue(field.required, name)
            self.assertIsNone(field.default, name)
            self.assertTrue(field.provenance, f"{name} 必须写明权威来源")
        self.assertEqual(depth.required_config(),
                         ("sample_period_ticks", "min_range", "max_range", "crop_width",
                          "history_frames"))

    def test_display_parameters_do_have_defaults_and_provenance(self) -> None:
        depth = pc.plugin_definition("depth")
        for name in ("width", "height", "fovy_deg", "normalize"):
            field = depth.config_field(name)
            self.assertIsNotNone(field.default, name)
        # 默认值的出处必须可核对（浏览器口径 vs 策略口径的区别就靠这句话留住）
        self.assertIn("sensor_catalog.js", depth.config_field("width").provenance)

    def test_default_config_and_resolve_config_agree(self) -> None:
        for plugin_id in pc.plugin_ids():
            definition = pc.plugin_definition(plugin_id)
            defaults = definition.default_config()
            for name, value in defaults.items():
                self.assertNotIn(name, definition.required_config())
                self.assertEqual(definition.config_field(name).default, value)

    def test_choice_fields_reject_values_outside_vocabulary(self) -> None:
        depth = pc.plugin_definition("depth")
        depth.resolve_config({"sample_period_ticks": 5, "min_range": 0.3, "max_range": 4.0,
                              "crop_width": 86, "history_frames": 2, "normalize": "none"})
        with self.assertRaises(pc.SensorDeclarationError):
            depth.resolve_config({"sample_period_ticks": 5, "min_range": 0.3, "max_range": 4.0,
                                  "crop_width": 86, "history_frames": 2, "normalize": "zscore"})

    def test_int_fields_reject_bool_and_float(self) -> None:
        field = pc.plugin_definition("depth").config_field("crop_width")
        for bad in (True, 86.0, "86", None):
            with self.assertRaises(pc.SensorDeclarationError, msg=repr(bad)):
                field.accepts(bad)
        field.accepts(86)

    def test_float_fields_reject_non_finite(self) -> None:
        field = pc.plugin_definition("depth").config_field("min_range")
        for bad in (float("nan"), float("inf")):
            with self.assertRaises(pc.SensorDeclarationError):
                field.accepts(bad)

    def test_field_consistency_rules(self) -> None:
        with self.assertRaises(ValidationError):  # required=True 却带默认值
            pc.ConfigFieldSpec(name="x", kind="int", default=3, required=True)
        with self.assertRaises(ValidationError):  # choice 必须给枚举
            pc.ConfigFieldSpec(name="x", kind="choice")
        with self.assertRaises(ValidationError):  # 非 choice 不得带枚举
            pc.ConfigFieldSpec(name="x", kind="int", choices=("a",))
        with self.assertRaises(ValidationError):  # 下限高于上限
            pc.ConfigFieldSpec(name="x", kind="int", minimum=10.0, maximum=1.0)
        with self.assertRaises(ValidationError):  # 默认值本身要合法
            pc.ConfigFieldSpec(name="x", kind="int", default=99, maximum=10.0)
        with self.assertRaises(ValidationError):  # 参数名口径
            pc.ConfigFieldSpec(name="Bad-Name", kind="int")


class ResolveConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.depth = pc.plugin_definition("depth")
        self.overrides = {
            "sample_period_ticks": 5,
            "min_range": 0.3,
            "max_range": 4.0,
            "crop_width": 86,
            "history_frames": 2,
        }

    def test_missing_required_field_is_blocked(self) -> None:
        for name in self.overrides:
            partial = dict(self.overrides)
            partial.pop(name)
            with self.assertRaises(pc.SensorDeclarationError, msg=name):
                self.depth.resolve_config(partial)

    def test_unknown_parameter_is_blocked(self) -> None:
        """不允许"多写的参数被忽略"：那会让场景里的错拼静默失效。"""

        bad = dict(self.overrides, min_ragne=0.3)
        with self.assertRaises(pc.SensorDeclarationError) as caught:
            self.depth.resolve_config(bad)
        self.assertIn("min_ragne", str(caught.exception))

    def test_every_resolved_parameter_has_non_empty_provenance(self) -> None:
        values, provenance = self.depth.resolve_config(self.overrides)
        self.assertEqual(set(values), set(provenance))
        self.assertEqual(set(values), {field.name for field in self.depth.config})
        for name, text in provenance.items():
            self.assertTrue(text and text.strip(), name)
        # 覆盖项的出处必须回指覆盖，而不是继续挂着默认值的出处
        self.assertEqual(provenance["min_range"], "override:min_range")
        self.assertTrue(provenance["width"].startswith("browser:"))

    def test_out_of_range_override_is_blocked(self) -> None:
        for bad in ({"min_range": -1.0}, {"history_frames": 0}, {"sample_period_ticks": 0},
                    {"crop_width": 100000}):
            values = dict(self.overrides, **bad)
            with self.assertRaises(pc.SensorDeclarationError, msg=str(bad)):
                self.depth.resolve_config(values)

    def test_provider_ordering_is_enforced(self) -> None:
        """滞回三段 stop < resume < decelerate 是语义要求，不是调参偏好。"""

        provider = pc.command_provider_definition("lidar_velocity_gate")
        provider.resolve_config({})  # 默认值自身必须通过交叉约束
        with self.assertRaises(pc.SensorDeclarationError):
            provider.resolve_config({"stop_m": 2.0})  # stop > resume
        with self.assertRaises(pc.SensorDeclarationError):
            provider.resolve_config({"resume_m": 3.0})  # resume > decelerate
        with self.assertRaises(pc.SensorDeclarationError):
            provider.resolve_config({"unknown_switch": True})
        values, provenance = provider.resolve_config({"stop_m": 0.5})
        self.assertEqual(values["stop_m"], 0.5)
        self.assertEqual(provenance["stop_m"], "override:stop_m")


class NoiseLatencyTests(unittest.TestCase):
    def test_disabled_models_carry_no_parameters(self) -> None:
        self.assertEqual(pc.NoiseSpec().kind, "none")
        self.assertEqual(pc.LatencySpec().kind, "none")
        with self.assertRaises(ValidationError):
            pc.NoiseSpec(sigma=0.1)
        with self.assertRaises(ValidationError):
            pc.LatencySpec(ticks=3)

    def test_active_models_need_their_driver_parameter(self) -> None:
        for kind, kwargs in (
            ("gaussian", {}), ("uniform_bias", {}), ("dropout", {}),
        ):
            with self.assertRaises(ValidationError, msg=kind):
                pc.NoiseSpec(kind=kind, **kwargs)
        self.assertEqual(pc.NoiseSpec(kind="gaussian", sigma=0.05).sigma, 0.05)
        self.assertEqual(pc.NoiseSpec(kind="dropout", dropout_rate=0.1).dropout_rate, 0.1)
        self.assertEqual(pc.LatencySpec(kind="fixed", ticks=5).ticks, 5)
        self.assertEqual(pc.LatencySpec(kind="jitter", ticks=2, jitter_ticks=3).jitter_ticks, 3)

    def test_latency_is_expressed_in_ticks_not_seconds(self) -> None:
        """单位口径只有一处：延迟以物理 tick 计，秒由时间基换算（换算不得两处实现）。"""

        fields = pc.LatencySpec.model_fields
        self.assertIn("ticks", fields)
        self.assertNotIn("seconds", fields)
        with self.assertRaises(ValidationError):
            pc.LatencySpec(kind="fixed", ticks=-1)


class CatalogPayloadTests(unittest.TestCase):
    def test_catalog_is_self_describing_and_matches_constants(self) -> None:
        payload = pc.plugin_catalog_payload()
        self.assertEqual(payload["schema_version"], pc.PLUGIN_CONTRACT_VERSION)
        self.assertEqual(payload["capability_levels"], list(pc.CAPABILITY_LEVELS))
        self.assertEqual(payload["dtype_itemsize"], dict(DTYPE_ITEMSIZE))
        # 载荷列的是**全部定义**（含派生视图，条目自带 instantiable/derived_from 标志），
        # 所以要和同口径的常量比——拿 instantiable_only=True 的默认集去比会恒差一个
        # lidar_height_scan（派生视图），那是拿错了变体不是数据不一致。
        self.assertEqual({item["plugin_id"] for item in payload["sensors"]},
                         set(pc.plugin_ids(instantiable_only=False)))
        self.assertEqual({item["provider_id"] for item in payload["command_providers"]},
                         set(pc.command_provider_ids()))

    def test_catalog_defaults_are_the_same_objects_resolve_config_uses(self) -> None:
        for entry in pc.plugin_catalog_payload()["sensors"]:
            definition = pc.plugin_definition(entry["plugin_id"])
            self.assertEqual(entry["defaults"], definition.default_config())
            self.assertEqual(entry["required"], list(definition.required_config()))
            self.assertEqual(entry["capability_level"], definition.capability_level)
            self.assertEqual(entry["policy_output"], definition.policy_output)
            self.assertEqual(entry["version"], definition.version)

    def test_backend_sensor_suite_delegates_instead_of_copying(self) -> None:
        """p7：后端 v2 catalog 必须**转发**本模块，不再自带一份插件默认值。"""

        import backend.sensor_suite as suite

        # 转发必须逐字相等（包括出处文本）：只要 suite 里另抄了一份默认值，这里就会不同
        self.assertEqual(suite.plugin_catalog_v2(), pc.plugin_catalog_payload())
        for plugin_id in pc.plugin_ids():
            self.assertEqual(suite.plugin_default_config_v2(plugin_id),
                             pc.plugin_definition(plugin_id).default_config(),
                             plugin_id)
        with self.assertRaises(KeyError):
            suite.plugin_default_config_v2("does_not_exist")


class CommandProviderTests(unittest.TestCase):
    def test_provider_inputs_reference_registered_plugins(self) -> None:
        for provider_id in pc.command_provider_ids():
            definition = pc.command_provider_definition(provider_id)
            for plugin_id in definition.input_plugin_ids:
                self.assertIsNotNone(pc.plugin_definition(plugin_id), f"{provider_id}->{plugin_id}")
            self.assertEqual(pc.PROVIDER_ENGINE_REQUIREMENTS[provider_id],
                             pc.provider_required_capabilities(provider_id))

    def test_provider_command_dims_match_contract_spec(self) -> None:
        import contracts.simulation_run_contract as rc

        spec = rc.command_provider_spec_from("lidar_velocity_gate",
                                             input_instances=("lidar_front",))
        definition = pc.command_provider_definition("lidar_velocity_gate")
        self.assertEqual(spec.command_dims, definition.command_dims)
        self.assertEqual(spec.version, definition.version)
        self.assertEqual(spec.config, definition.default_config())
        self.assertEqual(set(spec.config_provenance), set(spec.config))
        # 外挂决策器**只改指令**：它的插件不产策略观测
        for plugin_id in definition.input_plugin_ids:
            self.assertIsNone(pc.plugin_definition(plugin_id).policy_output)

    def test_unknown_provider_is_rejected_by_the_spec_factory(self) -> None:
        import contracts.simulation_run_contract as rc

        with self.assertRaises((ValidationError, ValueError)):
            rc.command_provider_spec_from("ghost_gate", input_instances=())


class ProviderDecisionTests(unittest.TestCase):
    def _decision(self, **overrides):
        base = dict(run_id="r-1", epoch=0, tick=100, provider_id="lidar_velocity_gate",
                    provider_version="1.0.0", request_seq=3,
                    source_command=(0.6, 0.0, 0.2), final_command=(0.6, 0.0, 0.2),
                    reason="ok")
        base.update(overrides)
        return pc.ProviderDecision(**base)

    def test_source_and_final_command_are_both_recorded(self) -> None:
        """「为什么给了 0.6 只走 0.2」必须可复盘 ⇒ 原始与被裁决的指令都进记录。"""

        decision = self._decision(final_command=(0.0, 0.0, 0.0), reason="stop_obstacle",
                                  input_instance_id="lidar_front", input_sample_seq=7)
        self.assertEqual(decision.source_command, (0.6, 0.0, 0.2))
        self.assertEqual(decision.final_command, (0.0, 0.0, 0.0))

    def test_command_length_follows_declared_dims(self) -> None:
        with self.assertRaises(pc.ProviderDecisionError):
            self._decision(source_command=(0.6, 0.0))

    def test_sensor_fault_reasons_must_point_at_an_instance_sample(self) -> None:
        for reason in ("stale_sample", "no_sample", "sensor_fault"):
            with self.assertRaises(pc.ProviderDecisionError, msg=reason):
                self._decision(reason=reason)
            with self.assertRaises(pc.ProviderDecisionError, msg=reason):
                self._decision(reason=reason, input_instance_id="lidar_front")
            self._decision(reason=reason, input_instance_id="lidar_front",
                           input_sample_seq=2)

    def test_non_finite_commands_rejected(self) -> None:
        with self.assertRaises(pc.ProviderDecisionError):
            self._decision(final_command=(float("nan"), 0.0, 0.0))

    def test_reason_vocabulary_is_closed(self) -> None:
        with self.assertRaises(ValidationError):
            self._decision(reason="because")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
