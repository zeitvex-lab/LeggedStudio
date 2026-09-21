"""运行契约 :mod:`contracts.simulation_run_contract` 的严格类型边界测试。

这一层是高级仿真的**唯一决议格式**（resolve 产物、创建运行的输入、manifest 的一部分），
所以测试目标不是「字段有多少」，而是四类**冒充**必须在类型层就构造不出来：

* **数值冒充**：``NaN``/``inf``、非单位四元数、与 shape×dtype 不符的载荷长度；
* **来源冒充**：时间基不来自 ``contract.json``、策略元数据没读产物就宣称认证、
  能力没探测报告就写 ``available``/``verified``、探测未成功却带 feature；
* **标识冒充**：未知插件/未知 provider/重复 instance_id/仓库外路径/冒名 executor_id；
* **状态冒充**：系统失败写成 ``finalized``、未生效事件带 ``applied_tick``、
  白名单外块 id、缺探测的规格。

所有断言都打在**真实实现**上（构造真实模型、读真实常量），不使用替身。
"""

from __future__ import annotations

import unittest
from typing import get_args

from pydantic import TypeAdapter, ValidationError

import contracts.sensor_plugin_contract as pc
import contracts.simulation_run_contract as rc
from contracts.simulation_protocol import PROTOCOL_NAME, PROTOCOL_VERSION, protocol_limits

_SHA = "a" * 64
_OTHER_SHA = "b" * 64


# --------------------------------------------------------------------------------------
# 构造工厂（每个都产出**合法**对象，负例只覆盖被怀疑的那一项）
# --------------------------------------------------------------------------------------


def _time_base(**overrides) -> rc.RunTimeBase:
    base = dict(physics_hz=500, control_decimation=10, source="contract")
    base.update(overrides)
    return rc.RunTimeBase(**base)


def _assets(*items: rc.AssetRef) -> tuple[rc.AssetRef, ...]:
    if items:
        return items
    return (
        rc.AssetRef(
            kind="model_xml", path="model/robot.xml", sha256=_SHA, size_bytes=128,
            robot_id="unitree_go2",
        ),
    )


def _provenance(categories: tuple[str, ...] | None = None) -> tuple[rc.ParamProvenance, ...]:
    wanted = rc.PROVENANCE_REQUIRED if categories is None else categories
    return tuple(
        rc.ParamProvenance(name=category, category=category, source=f"fixture:{category}")
        for category in wanted
    )


#: 声明层**故意不给默认值**的标定参数（深度/LiDAR 的速率、量程、裁剪、历史）在这里
#: 给一个夹具值。这些值不是"第二套真值"：它们代表"实例显式参数"这一路的输入，
#: 真实解析时由场景或决策器提供，缺失时 :meth:`resolve_config` 必须报错（见插件契约测试）。
_REQUIRED_FIXTURES: dict[str, object] = {
    "sample_period_ticks": 10,
    "min_range": 0.1,
    "max_range": 5.0,
    "crop_width": 86,
    "history_frames": 1,
}


def _resolved_plugin_params(plugin_id: str,
                            overrides: dict | None = None) -> tuple[dict, dict]:
    """把"必填无默认"补齐后交给 :meth:`resolve_config`，返回完整参数集与出处表。"""

    definition = pc.plugin_definition(plugin_id)
    assert definition is not None, plugin_id
    wanted = {name: _REQUIRED_FIXTURES[name] for name in definition.required_config()
              if name in _REQUIRED_FIXTURES}
    wanted.update(overrides or {})
    missing = [name for name in definition.required_config() if name not in wanted]
    assert not missing, f"夹具缺少这些必填参数的取值：{missing}（请补 _REQUIRED_FIXTURES）"
    return definition.resolve_config(wanted)


def _instance(plugin_id: str = "imu", instance_id: str | None = None,
              config_overrides: dict | None = None, **fields) -> rc.SensorInstanceSpec:
    definition = pc.plugin_definition(plugin_id)
    assert definition is not None, plugin_id
    config, provenance = _resolved_plugin_params(plugin_id, config_overrides)
    base: dict = {
        "instance_id": instance_id or f"{plugin_id}0",
        "plugin_id": plugin_id,
        "plugin_version": definition.version,
        "config": config,
        "config_provenance": provenance,
        "capability_level": definition.capability_level,
    }
    if definition.requires_target:
        base["target"] = "camera_site"
    base.update(fields)
    return rc.SensorInstanceSpec(**base)


_IMU = pc.plugin_definition("imu")
_IMU_PARAMS = _IMU.resolve_config({})  # (完整参数集, 每个参数的出处)


def _instance_from_params(config: dict, provenance: dict, **fields) -> rc.SensorInstanceSpec:
    """绕开 :meth:`resolve_config` 直接给参数集，用于测**契约自己**的完整性检查。"""

    base: dict = {
        "instance_id": "imu0",
        "plugin_id": "imu",
        "plugin_version": _IMU.version,
        "config": config,
        "config_provenance": provenance,
        "capability_level": _IMU.capability_level,
    }
    base.update(fields)
    return rc.SensorInstanceSpec(**base)


_PROVIDER = pc.command_provider_definition("lidar_velocity_gate")
_PROVIDER_PARAMS = _PROVIDER.resolve_config({})


def _provider(**overrides) -> rc.CommandProviderSpec:
    base: dict = {
        "provider_id": "lidar_velocity_gate",
        "version": _PROVIDER.version,
        "input_instances": ("lidar0",),
        "command_dims": _PROVIDER.command_dims,
        "config": _PROVIDER_PARAMS[0],
        "config_provenance": _PROVIDER_PARAMS[1],
        "capability_level": _PROVIDER.capability_level,
    }
    base.update(overrides)
    return rc.CommandProviderSpec(**base)


def _required_features(plugin_ids=(), provider_id: str | None = None) -> list[str]:
    """与 :meth:`rc.ResolvedRunSpec.required_engine_features` 同口径的需求集。"""

    wanted = set(rc.PROBE_FEATURES_REQUIRED)
    for plugin_id in plugin_ids:
        wanted.update(pc.required_capabilities(plugin_id))
    if provider_id:
        wanted.update({"event_injection", "raycast"})
        wanted.update(pc.provider_required_capabilities(provider_id))
    return sorted(wanted)


def _probe(plugin_ids=("imu",), provider_id: str | None = None,
           **overrides) -> rc.NativeProbeReport:
    features = overrides.pop("features", None)
    if features is None:
        features = {name: "supported" for name in _required_features(plugin_ids, provider_id)}
    base = dict(
        probed=True, reason="probed", features=features,
        mujoco_version="3.3.0", onnxruntime_version="1.22.0", probed_at_unix=1000.0,
    )
    base.update(overrides)
    return rc.NativeProbeReport(**base)


def _capabilities(plugin_ids=("imu",), provider_id: str | None = None,
                  **overrides) -> rc.Capabilities:
    report = overrides.pop("probe", None)
    if report is None:
        report = _probe(plugin_ids, provider_id)
    base = dict(probed=bool(report.probed), probe=report)
    base.update(overrides)
    return rc.Capabilities(**base)


def _spec(*, plugin_ids=("imu",), provider_id: str | None = None, **overrides) -> rc.ResolvedRunSpec:
    """一份**可创建运行**的合法规格（自洽签名）。负例只覆盖被怀疑的那一项。"""

    instances = overrides.pop("sensor_instances", None)
    if instances is None:
        instances = tuple(
            _instance(plugin_id, instance_id=f"{plugin_id}{index}")
            for index, plugin_id in enumerate(plugin_ids)
        )
    base: dict = {
        "robot_id": "unitree_go2",
        "time_base": _time_base(),
        "duration_s": 2.0,
        "seed": 3,
        "assets": _assets(),
        "sensor_instances": instances,
        "capabilities": overrides.pop(
            "capabilities", None
        ) or _capabilities(plugin_ids, provider_id),
        "provenance": _provenance(),
    }
    if provider_id is not None:
        base["command_provider"] = rc.command_provider_spec_from(
            provider_id, input_instances=tuple(item.instance_id for item in instances)[:1]
        )
    base.update(overrides)
    return rc.ResolvedRunSpec.with_digest(**base)


def _envelope(**overrides) -> rc.SampleEnvelope:
    base = dict(
        run_id="run1", epoch=0, seq=7, instance_id="imu0", plugin_id="imu",
        plugin_version="1.0.0", output="accel", sample_tick=100, available_tick=104,
        sim_time=0.2, shape=(1, 45), dtype="f4", unit="m/s^2", payload_bytes=180,
        checksum=_SHA,
    )
    base.update(overrides)
    return rc.SampleEnvelope(**base)


def _tensor_meta(name: str = "obs", shape=(1, 45), dtype: str = "f4") -> rc.OnnxTensorMeta:
    return rc.OnnxTensorMeta(name=name, shape=shape, dtype=dtype)


def _chunk(**overrides) -> rc.ChunkMeta:
    base = dict(
        chunk_id="chunk0", episode_id="ep1", kind="tensors",
        path="ep1/tensors/chunk0.npz", sha256=_SHA, size_bytes=1024,
        first_tick=0, last_tick=9, first_sim_time=0.0, last_sim_time=0.02,
        sample_count=5, dtype="f4", shape=(1, 45), unit="m/s^2",
        format="npz-chunk", instance_id="imu0", output="accel",
    )
    base.update(overrides)
    return rc.ChunkMeta(**base)


def _index(*chunks: rc.ChunkMeta, **overrides) -> rc.RecordingChunkIndex:
    base = dict(episode_id="ep1", chunks=chunks or (_chunk(),))
    base.update(overrides)
    return rc.RecordingChunkIndex(**base)


def _manifest(**overrides) -> rc.EpisodeManifest:
    base = dict(
        episode_id="ep1", run_id="run1", spec_digest=_SHA, seed=3,
        time_base=_time_base(), robot_id="unitree_go2", index=_index(),
        status="finalized", start_tick=0, end_tick=9, duration_s=0.02,
        created_at_unix=1000.0,
    )
    base.update(overrides)
    return rc.EpisodeManifest(**base)


# --------------------------------------------------------------------------------------
# 标量与路径
# --------------------------------------------------------------------------------------


class FiniteScalarTests(unittest.TestCase):
    """:data:`rc.FiniteFloat` / :data:`rc.Vec3` / :data:`rc.QuatWxyz` 的真实边界。"""

    def test_vec3_rejects_non_finite_and_wrong_arity(self) -> None:
        adapter = TypeAdapter(rc.Vec3)
        self.assertEqual(adapter.validate_python([1.5, -2.0, 0.0]), (1.5, -2.0, 0.0))
        for bad in ((float("nan"), 0.0, 0.0), (float("inf"), 0.0, 0.0),
                    (0.0, float("-inf"), 0.0), (1.0, 2.0), (1.0, 2.0, 3.0, 4.0)):
            with self.assertRaises(ValidationError, msg=f"应拒绝 {bad}"):
                adapter.validate_python(bad)

    def test_quaternion_is_wxyz_and_unit_norm(self) -> None:
        adapter = TypeAdapter(rc.QuatWxyz)
        self.assertEqual(adapter.validate_python((1.0, 0.0, 0.0, 0.0)), (1.0, 0.0, 0.0, 0.0))
        # xyzw 口径的 (0,0,0,1) 同样是单位四元数 —— 顺序靠**字段名**与 :data:`rc.QUAT_ORDER` 固定，
        # 而不是靠"看起来不像"，所以这里断言的是口径声明本身。
        self.assertEqual(rc.QUAT_ORDER, "wxyz")
        self.assertEqual(rc.Units().quat_order, "wxyz")
        for bad in ((0.0, 0.0, 0.0, 0.0), (2.0, 0.0, 0.0, 0.0), (float("nan"), 0.0, 0.0, 1.0),
                    (1.0, 0.0, 0.0)):
            with self.assertRaises(ValidationError, msg=f"应拒绝 {bad}"):
                adapter.validate_python(bad)

    def test_non_finite_float_rejected_in_nested_models(self) -> None:
        config, provenance = _IMU_PARAMS
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValidationError, msg=str(value)):
                _envelope(sim_time=value)
            with self.assertRaises(ValidationError, msg=str(value)):
                rc.ResolveOptions(duration_s=value)
            with self.assertRaises(ValidationError, msg=str(value)):
                _instance_from_params(config={**config, "accel_noise_sigma": value},
                                      provenance=provenance)
            with self.assertRaises(ValidationError, msg=str(value)):
                _instance_from_params(config=config, provenance=provenance, pos=(value, 0.0, 0.0))


class SafePathTests(unittest.TestCase):
    """路径逃逸拒绝：这些字符串最终都会去拼真实文件系统。"""

    def test_rejected_forms(self) -> None:
        for bad in ("", "   ", "../secret", "a/../../b", "/etc/passwd", "~/x",
                    "C:/Windows/x", "model\\robot.xml", "."):
            with self.assertRaises(ValueError, msg=repr(bad)):
                rc.safe_relative_path(bad)

    def test_normalized_acceptance(self) -> None:
        self.assertEqual(rc.safe_relative_path("./model/robot.xml"), "model/robot.xml")
        self.assertEqual(rc.safe_relative_path("model//robot.xml"), "model/robot.xml")
        # ``a/../b`` 归一化后仍在包内 —— 归一化本身就是防逃逸的手段，不是漏洞
        self.assertEqual(rc.safe_relative_path("model/../other.xml"), "other.xml")

    def test_path_fields_use_the_same_rule(self) -> None:
        """资产、策略产物、块索引、下载四条路径共用 :func:`safe_relative_path`。"""

        with self.assertRaises(ValidationError):
            rc.AssetRef(kind="model_xml", path="../x")
        with self.assertRaises(ValidationError):
            rc.PolicyArtifactRef(relative_path="../x", sha256=_SHA)
        with self.assertRaises(ValidationError):
            _chunk(path="../escape.npz")
        with self.assertRaises(ValidationError):
            rc.ChunkDownload(episode_id="ep1", chunk_id="chunk0", path="../secrets",
                             sha256=_SHA, size_bytes=1024,
                             media_type="application/octet-stream")
        # 合法路径被规范化为 posix（下游拼路径时不会再出现 "./"）
        self.assertEqual(rc.AssetRef(kind="model_xml", path="./model/robot.xml",
                                     sha256=_SHA).path, "model/robot.xml")


# --------------------------------------------------------------------------------------
# 时间基：唯一真值
# --------------------------------------------------------------------------------------


class TimeBaseAuthorityTests(unittest.TestCase):
    def test_only_two_stored_integers_and_derived_values(self) -> None:
        tb = _time_base()
        self.assertEqual(tb.control_hz, 50.0)
        self.assertEqual(tb.physics_dt, 0.002)
        self.assertEqual(tb.control_dt, 0.02)
        self.assertEqual(tb.ticks_for_control_steps(4), 40)
        self.assertEqual(tb.hz_for_period_ticks(40), 12.5)
        self.assertEqual(
            set(tb.as_dict()) >= {"physics_hz", "control_decimation", "control_hz",
                                  "physics_dt", "control_dt", "source"},
            True,
        )

    def test_source_is_mandatory_and_non_contract_is_refused_by_the_spec(self) -> None:
        """``source`` 无默认值 + 规格只认 ``contract``：PIE 的隐式 200Hz 写不进来。"""

        with self.assertRaises(ValidationError):
            rc.RunTimeBase(physics_hz=500, control_decimation=10)
        for source in ("legacy_config", "missing"):
            with self.assertRaises(ValidationError, msg=source):
                _spec(time_base=_time_base(source=source))

    def test_control_rate_must_divide_exactly(self) -> None:
        with self.assertRaises(ValidationError):
            _time_base(physics_hz=500, control_decimation=3)

    def test_there_is_no_second_frequency_field(self) -> None:
        """规格里没有 ``control_hz``/``physics_dt`` 字段：频率只能由那两个整数导出。"""

        names = set(rc.ResolvedRunSpec.model_fields)
        self.assertNotIn("control_hz", names)
        self.assertNotIn("physics_dt", names)
        self.assertNotIn("policy_dt", names)
        self.assertIn("time_base", names)


# --------------------------------------------------------------------------------------
# 记录预算
# --------------------------------------------------------------------------------------


class RecordingBudgetTests(unittest.TestCase):
    def test_user_approved_defaults_and_no_auto_delete(self) -> None:
        opts = rc.RecordingOptions()
        self.assertEqual(opts.queue_budget_bytes, 128 * 1024 * 1024)
        self.assertEqual(opts.per_run_budget_bytes, 5 * 1024**3)
        self.assertEqual(opts.directory_budget_bytes, 20 * 1024**3)
        self.assertEqual(opts.min_free_disk_bytes, 2 * 1024**3)
        self.assertIs(opts.auto_delete, False)
        self.assertEqual(opts.budget_dict()["auto_delete"], False)
        # 词面：自动删除在类型里就写不出来（Literal[False]）
        with self.assertRaises(ValidationError):
            rc.RecordingOptions(auto_delete=True)

    def test_budget_hierarchy_is_enforced(self) -> None:
        with self.assertRaises(ValidationError):
            rc.RecordingOptions(queue_budget_bytes=2**31, per_run_budget_bytes=2**30)
        with self.assertRaises(ValidationError):
            rc.RecordingOptions(per_run_budget_bytes=2**35, directory_budget_bytes=2**34)
        with self.assertRaises(ValidationError):
            rc.RecordingOptions(directory_budget_bytes=1024, min_free_disk_bytes=2048)

    def test_backpressure_and_display_policy_are_single_valued(self) -> None:
        opts = rc.RecordingOptions()
        self.assertEqual(opts.on_backpressure, "pause_at_tick")
        self.assertEqual(opts.display_policy, "latest_frame")
        with self.assertRaises(ValidationError):
            rc.RecordingOptions(on_backpressure="drop_samples")
        self.assertEqual(
            opts.formats.model_dump(),
            {"tensors": "npz-chunk", "image": "png-lossless", "depth": "float32",
             "events": "jsonl", "status": "npz-chunk"},
        )

    def test_resolve_options_has_no_digest_escape_hatch(self) -> None:
        """没有 ``strict_asset_digest``：摘要无条件必需，一个可关的旋钮会承诺做不到的事。"""

        self.assertNotIn("strict_asset_digest", rc.ResolveOptions.model_fields)
        with self.assertRaises(ValidationError):
            rc.ResolveOptions(strict_asset_digest=True)
        self.assertTrue(rc.ResolveOptions().require_probe)
        with self.assertRaises(ValidationError):
            rc.ResolveOptions(ignore_assets=True)  # extra=forbid：不许私加旋钮
        self.assertEqual(
            set(rc.ResolveOptions.model_fields),
            {"robot_id", "policy_id", "seed", "duration_s", "recording", "require_probe"},
        )


# --------------------------------------------------------------------------------------
# 样本信封
# --------------------------------------------------------------------------------------


class SampleEnvelopeTests(unittest.TestCase):
    def test_valid_tensor_payload_must_match_shape_and_dtype(self) -> None:
        self.assertEqual(_envelope().payload_bytes, 180)
        with self.assertRaises(ValidationError):
            _envelope(payload_bytes=179)
        with self.assertRaises(ValidationError):
            _envelope(dtype="f8", payload_bytes=180)
        self.assertEqual(_envelope(dtype="f8", payload_bytes=360).dtype, "f8")

    def test_valid_tensor_requires_shape_dtype_and_unit(self) -> None:
        for kwargs in ({"shape": None}, {"dtype": None}, {"unit": None}):
            with self.assertRaises(ValidationError, msg=str(kwargs)):
                _envelope(**kwargs)

    def test_available_tick_cannot_precede_sample_tick(self) -> None:
        with self.assertRaises(ValidationError):
            _envelope(available_tick=99)
        self.assertEqual(_envelope().age_ticks(110), 10)

    def test_empty_validities_are_distinct_from_valid(self) -> None:
        for validity in sorted(rc.SAMPLE_EMPTY_VALIDITIES):
            sample = _envelope(validity=validity, payload_bytes=0, shape=None,
                               dtype=None, checksum=None, unit=None)
            self.assertEqual(sample.validity, validity)
            self.assertIsNone(sample.checksum)
            self.assertFalse(sample.is_usable(200, max_age_ticks=999))
        self.assertNotIn("valid", rc.SAMPLE_EMPTY_VALIDITIES)
        self.assertEqual(set(rc.SAMPLE_DATA_VALIDITIES), {"valid"})

    def test_empty_validity_cannot_carry_shape_or_bytes(self) -> None:
        empty = dict(validity="fault", payload_bytes=0, shape=None, dtype=None,
                     unit=None, checksum=None)
        for kwargs in ({"payload_bytes": 4}, {"shape": (1, 45)}, {"dtype": "f4"}):
            with self.assertRaises(ValidationError, msg=str(kwargs)):
                _envelope(**{**empty, **kwargs})
        # 空样本没有载荷，也就没有能兑现的摘要
        with self.assertRaises(ValidationError):
            _envelope(**{**empty, "checksum": "deadbeef"})

    def test_unimplemented_payload_kinds_cannot_claim_valid_data(self) -> None:
        for kind in ("cloud", "graph"):
            with self.assertRaises(ValidationError, msg=kind):
                _envelope(payload_kind=kind, shape=None, dtype=None, unit=None)
        png = _envelope(payload_kind="image_png", shape=None, dtype=None)
        self.assertEqual(png.payload_kind, "image_png")
        with self.assertRaises(ValidationError):
            _envelope(payload_kind="image_png", dtype=None)  # 不得重复声明 shape/dtype

    def test_identity_and_schema_fields_are_checked(self) -> None:
        with self.assertRaises(ValidationError):
            _envelope(schema_version="sim-run-contract-0.9")
        with self.assertRaises(ValidationError):
            _envelope(instance_id="IMU0")  # 大写不在 SAFE_ID 词法内
        with self.assertRaises(ValidationError):
            _envelope(checksum="deadbeef")
        with self.assertRaises(ValidationError):
            _envelope(seq=-1)
        with self.assertRaises(ValidationError):
            _envelope(sample_seq=-1)

    def test_stream_seq_and_instance_sample_seq_are_different_things(self) -> None:
        """``seq`` 是跨实例的流帧号，``sample_seq`` 是该路输出自己的样本序号。"""

        sample = _envelope(sample_seq=3)
        self.assertEqual((sample.seq, sample.sample_seq), (7, 3))
        self.assertEqual(sample.model_dump()["sample_seq"], 3)

    def test_is_usable_requires_valid_fresh_and_arrived(self) -> None:
        sample = _envelope()
        self.assertTrue(sample.is_usable(104, max_age_ticks=5))
        self.assertFalse(sample.is_usable(103, max_age_ticks=5))  # 还没到可用时刻
        self.assertFalse(sample.is_usable(200, max_age_ticks=5))  # 过期
        self.assertFalse(
            _envelope(validity="stale", payload_bytes=0, shape=None, dtype=None,
                      checksum=None, unit=None).is_usable(104, max_age_ticks=99)
        )

    def test_envelope_names_match_the_wire_contract(self) -> None:
        """信封字段与 WS ``sample_frame`` 声明的头部附加项**同名**（前端只学一套词）。"""

        stream = rc.ws_stream_contract()
        extra = set(stream["sample_frame"]["header_extra"])
        self.assertTrue(extra.isdisjoint(stream["frame_common_fields"]))
        fields = set(rc.SampleEnvelope.model_fields)
        self.assertTrue(extra <= fields, extra - fields)
        for name in ("reference_frame", "sample_seq", "available_tick", "validity", "source"):
            self.assertIn(name, extra)
        # 有效性词表只有一份：字段类型的 Literal 与导出的常量必须逐字相同
        self.assertEqual(set(rc.SAMPLE_VALIDITY),
                         set(get_args(rc.SampleEnvelope.model_fields["validity"].annotation)))
        # 公共帧头字段名与封包实现共用一处声明（前端不必再猜第二套）
        self.assertEqual(rc.ws_stream_contract()["message_types"],
                         list(protocol_limits()["message_types"]))


# --------------------------------------------------------------------------------------
# 传感器实例
# --------------------------------------------------------------------------------------


class SensorInstanceSpecTests(unittest.TestCase):
    def test_config_must_be_the_full_resolved_parameter_set(self) -> None:
        definition = pc.plugin_definition("imu")
        with self.assertRaises(ValidationError):
            rc.SensorInstanceSpec(
                instance_id="imu0", plugin_id="imu", plugin_version=definition.version,
                config={"sample_period_ticks": 10},
                config_provenance={"sample_period_ticks": "fixture"},
            )

    def test_unknown_parameter_and_unknown_plugin_are_refused(self) -> None:
        """未声明参数在**声明层**就报 :class:`SensorDeclarationError`；未知插件在**实例层**被拒。"""

        with self.assertRaises(ValueError):
            _instance(config_overrides={"not_declared": 1})
        with self.assertRaises(ValidationError):
            rc.SensorInstanceSpec(instance_id="x0", plugin_id="no_such_plugin",
                                  plugin_version="1.0.0")
        imu = pc.plugin_definition("imu")
        config, provenance = _IMU_PARAMS
        with self.assertRaises(ValidationError):
            _instance_from_params(config={**config, "not_declared": 1},
                                  provenance={**provenance, "not_declared": "fixture"})
        self.assertEqual(imu.version, _instance().plugin_version)

    def test_provenance_table_mirrors_config_exactly(self) -> None:
        instance = _instance()
        self.assertEqual(set(instance.config_provenance), set(instance.config))
        self.assertTrue(all(text.strip() for text in instance.config_provenance.values()))
        config, provenance = _IMU_PARAMS
        with self.assertRaises(ValidationError):  # 少一个出处
            _instance_from_params(config=config,
                                  provenance={k: v for k, v in provenance.items()
                                              if k != "sample_period_ticks"})
        with self.assertRaises(ValidationError):  # 多一个出处
            _instance_from_params(config=config, provenance={**provenance, "ghost": "fixture"})
        with self.assertRaises(ValidationError):  # 出处是空话
            _instance_from_params(config=config,
                                  provenance={**provenance, "sample_period_ticks": "   "})
        broken = _instance().model_dump()
        broken["config_provenance"] = {k: v for k, v in broken["config_provenance"].items()
                                       if k != "sample_period_ticks"}
        with self.assertRaises(ValidationError):
            rc.SensorInstanceSpec.model_validate(broken)
        blank = _instance().model_dump()
        blank["config_provenance"]["sample_period_ticks"] = "   "
        with self.assertRaises(ValidationError):
            rc.SensorInstanceSpec.model_validate(blank)

    def test_sample_period_lives_only_in_config(self) -> None:
        instance = _instance("lidar", instance_id="lidar0", config_overrides={"sample_period_ticks": 10})
        self.assertEqual(instance.sample_period_ticks, 10)
        self.assertNotIn("sample_period_ticks", rc.SensorInstanceSpec.model_fields)
        payload = instance.model_dump()
        payload["config"].pop("sample_period_ticks")
        with self.assertRaises(ValidationError):
            rc.SensorInstanceSpec.model_validate(payload)

    def test_multi_instance_same_plugin_is_allowed_but_ids_must_be_unique(self) -> None:
        first = _instance("imu", instance_id="imu_front")
        second = _instance("imu", instance_id="imu_rear")
        self.assertEqual(first.plugin_id, second.plugin_id)
        spec = _spec(sensor_instances=(first, second))
        self.assertEqual([item.instance_id for item in spec.sensor_instances],
                         ["imu_front", "imu_rear"])
        self.assertEqual(spec.sample_hz("imu_rear"), spec.sample_hz("imu_front"))
        with self.assertRaises(ValidationError):
            _spec(sensor_instances=(first, first.model_copy(update={"config": dict(first.config)})))
        with self.assertRaises(ValidationError):
            _spec(sensor_instances=(first, first))

    def test_target_mount_and_capability_declarations_are_enforced(self) -> None:
        with self.assertRaises(ValidationError):
            _instance("lidar", instance_id="lidar0", config_overrides={"sample_period_ticks": 10},
                      target=None)
        with self.assertRaises(ValidationError):
            _instance("odom", instance_id="odom0", pos=(0.1, 0.0, 0.0))  # 不可挂载
        rgb = pc.plugin_definition("rgb")
        self.assertFalse(rgb.supports_noise)
        with self.assertRaises(ValidationError):
            _instance("rgb", instance_id="rgb0", config_overrides={"sample_period_ticks": 5},
                      noise=pc.NoiseSpec(kind="dropout", dropout_rate=0.1))
        self.assertEqual(_instance("rgb", instance_id="rgb0",
                                   config_overrides={"sample_period_ticks": 5}).noise.kind,
                         "none")
        self.assertFalse(pc.plugin_definition("odom").mountable)

    def test_record_outputs_must_exist_and_png_needs_a_png_output(self) -> None:
        with self.assertRaises(ValidationError):
            _instance(record=rc.InstanceRecordOptions(record=True, outputs=("nope",)))
        with self.assertRaises(ValidationError):
            _instance(record=rc.InstanceRecordOptions(record=True, outputs=("accel", "accel")))
        with self.assertRaises(ValidationError):
            _instance(record=rc.InstanceRecordOptions(record=True, record_png=True))

    def test_plugin_version_cannot_point_at_an_unregistered_version(self) -> None:
        with self.assertRaises(ValidationError):
            _instance(plugin_version="9.9.9")

    def test_in_spec_capability_level_cannot_be_upgraded_in_place(self) -> None:
        instance = _instance(capability_level="verified")
        with self.assertRaises(ValidationError):
            _spec(sensor_instances=(instance,))


# --------------------------------------------------------------------------------------
# 探测报告与能力（fail-closed）
# --------------------------------------------------------------------------------------


class ProbeFailClosedTests(unittest.TestCase):
    def test_spec_without_a_completed_probe_cannot_be_constructed(self) -> None:
        with self.assertRaises(ValidationError):
            _spec(capabilities=rc.Capabilities.unprobed())
        with self.assertRaises(ValidationError):
            _spec(capabilities=rc.Capabilities(
                probed=False, probe=rc.NativeProbeReport(probed=False, reason="not_probed")))

    def test_unsupported_or_unknown_feature_blocks_the_spec(self) -> None:
        for state in ("unsupported", "unknown"):
            features = {name: "supported" for name in _required_features(("imu",))}
            features["imu_bias"] = state
            with self.assertRaises(ValidationError, msg=state):
                _spec(capabilities=_capabilities(probe=_probe(("imu",), features=features)))

    def test_not_probed_report_carrying_features_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            rc.NativeProbeReport(probed=False, reason="probe_failed",
                                 features={"model_compile": "supported"})
        with self.assertRaises(ValidationError):
            rc.NativeProbeReport(probed=True, reason="probed", features={},
                                 mujoco_version="3.3.0", onnxruntime_version="1.22.0")
        with self.assertRaises(ValidationError):
            rc.NativeProbeReport(probed=True, reason="probed",
                                 features={"model_compile": "supported"},
                                 onnxruntime_version="1.22.0")  # 缺 mujoco 版本 → 无法复现
        with self.assertRaises(ValidationError):
            rc.NativeProbeReport(probed=False, reason="probed")

    def test_feature_vocabulary_and_lookup_are_closed(self) -> None:
        with self.assertRaises(ValidationError):
            _probe(features={"model_conpil": "supported"})  # 拼错不会被当成"未支持"，而是被拒绝
        report = _probe()
        self.assertEqual(report.state_of("raycast"), "unknown")
        self.assertFalse(report.is_supported("raycast"))
        with self.assertRaises(ValueError):
            report.state_of("not_a_feature")
        self.assertEqual(set(rc.PROBE_FEATURES_REQUIRED) <= set(rc.PROBE_FEATURES), True)

    def test_executor_and_runtime_identity_cannot_be_impersonated(self) -> None:
        with self.assertRaises(ValidationError):
            _probe(executor_id="server_mujoco")
        with self.assertRaises(ValidationError):
            _probe(native_runtime_version="0.0.1")
        with self.assertRaises(ValidationError):
            rc.Capabilities(native_runtime_version="legacy")
        with self.assertRaises(ValidationError):
            _spec(executor_id="server_mujoco")
        with self.assertRaises(ValidationError):
            _spec(protocol_version=PROTOCOL_VERSION + 1)
        with self.assertRaises(ValidationError):
            _spec(plugin_contract_version="sim-sensor-plugin-0.9")

    def test_capability_levels_cannot_be_claimed_without_evidence(self) -> None:
        with self.assertRaises(ValidationError):
            rc.CapabilityEntry(name="plugin:imu", level="verified")
        with self.assertRaises(ValidationError):
            rc.Capabilities(probed=False,
                            entries=(rc.CapabilityEntry(name="plugin:imu", level="available"),))
        with self.assertRaises(ValidationError):
            rc.Capabilities(probed=True, probe=_probe(),
                            entries=(rc.CapabilityEntry(name="plugin:imu", level="available"),))
        caps = rc.Capabilities(
            probed=True, probe=_probe(capability_levels={"imu": "implemented"}),
            entries=(rc.CapabilityEntry(name="plugin:imu", level="available",
                                        evidence="fixture"),),
        )
        self.assertTrue(caps.is_implemented("plugin:imu"))
        self.assertEqual(caps.level_of("plugin:missing"), None)
        with self.assertRaises(ValidationError):
            rc.Capabilities(probed=True, probe=_probe(),
                            entries=(rc.CapabilityEntry(name="plugin:imu", level="registered",
                                                        evidence="x"),
                                     rc.CapabilityEntry(name="plugin:imu", level="registered")))

    def test_capabilities_limits_come_from_the_protocol(self) -> None:
        self.assertEqual(rc.Capabilities().limits, protocol_limits())

    def test_current_catalog_has_no_verified_plugin(self) -> None:
        """诚实边界：本任务没有任何采集器实现，所以声明层不允许出现 verified。"""

        for plugin_id in pc.plugin_ids():
            definition = pc.plugin_definition(plugin_id)
            self.assertNotEqual(definition.capability_level, "verified", plugin_id)


# --------------------------------------------------------------------------------------
# 策略产物与观测绑定
# --------------------------------------------------------------------------------------


class PolicyArtifactTests(unittest.TestCase):
    def test_artifact_requires_digest_and_real_metadata(self) -> None:
        with self.assertRaises(ValidationError):
            rc.PolicyArtifactRef(relative_path="simulation/policies/x.onnx")
        with self.assertRaises(ValidationError):
            rc.PolicyArtifactRef(relative_path="simulation/policies/x.onnx", sha256=_SHA,
                                 metadata_verified=True, metadata_source="none",
                                 inputs=(_tensor_meta(),), outputs=(_tensor_meta("actions"),))
        with self.assertRaises(ValidationError):
            rc.PolicyArtifactRef(relative_path="simulation/policies/x.onnx", sha256=_SHA,
                                 metadata_source="none", inputs=(_tensor_meta(),))
        verified = rc.PolicyArtifactRef(
            relative_path="simulation/policies/x.onnx", sha256=_SHA,
            metadata_verified=True, metadata_source="onnx_file",
            inputs=(_tensor_meta(),), outputs=(_tensor_meta("actions", (1, 12)),),
        )
        self.assertEqual(verified.tensor_meta("obs").shape, (1, 45))
        self.assertIsNone(verified.tensor_meta("actions"))
        self.assertEqual(verified.tensor_meta("actions", output=True).name, "actions")
        with self.assertRaises(ValidationError):
            rc.PolicyArtifactRef(relative_path="../outside.onnx", sha256=_SHA)

    def test_word_matching_is_not_certification(self) -> None:
        for verified_by in ("unverified", "word_match"):
            with self.assertRaises(ValidationError, msg=verified_by):
                rc.PolicyInputBinding(name="obs", kind="proprio", tensor_shape=(1, 45),
                                      source="state", verified=True, verified_by=verified_by)
        with self.assertRaises(ValidationError):
            rc.PolicyInputBinding(name="obs", kind="proprio", tensor_shape=(1, 45),
                                  source="state", verified=True,
                                  verified_by="onnx_metadata")  # 认证了却没给 evidence

    def test_sensor_bound_items_need_an_instance_and_non_sensor_items_must_not_carry_one(self) -> None:
        with self.assertRaises(ValidationError):
            rc.PolicyInputBinding(name="depth_history", kind="depth", tensor_shape=(1, 2, 60, 86),
                                  source="sensor")
        with self.assertRaises(ValidationError):
            rc.PolicyInputBinding(name="obs", kind="proprio", tensor_shape=(1, 45),
                                  source="state", instance_id="imu0")
        with self.assertRaises(ValidationError):
            rc.PolicyInputBinding(name="obs", kind="proprio", tensor_shape=(1, 45),
                                  source="history_buffer", output="accel")
        with self.assertRaises(ValidationError):
            rc.PolicyInputBinding(name="obs", kind="proprio", tensor_shape=(1, 0), source="state")
        with self.assertRaises(ValidationError):
            rc.PolicyInputBinding(name="obs", kind="proprio", tensor_shape=(1, 45),
                                  source="state", dtype="f64")

    def test_spec_refuses_bindings_without_an_artifact_or_verification(self) -> None:
        binding = rc.PolicyInputBinding(name="obs", kind="proprio", tensor_shape=(1, 45),
                                        source="state")
        with self.assertRaises(ValidationError):
            _spec(policy_id="pie_parkour", policy_inputs=(binding,))  # 没有产物引用
        artifact = rc.PolicyArtifactRef(
            relative_path="simulation/policies/x.onnx", sha256=_SHA,
            metadata_verified=True, metadata_source="onnx_file",
            inputs=(_tensor_meta(),), outputs=(_tensor_meta("actions", (1, 12)),),
        )
        with self.assertRaises(ValidationError):
            _spec(policy_id="pie_parkour", policy_artifact=artifact, policy_inputs=())
        with self.assertRaises(ValidationError):
            _spec(policy_id="pie_parkour", policy_artifact=artifact, policy_inputs=(binding,))
        with self.assertRaises(ValidationError):
            _spec(policy_artifact=artifact)  # 无主策略
        ghost = rc.PolicyInputBinding(name="obs", kind="proprio", tensor_shape=(1, 45),
                                      source="state", verified=True,
                                      verified_by="onnx_metadata", evidence="fixture")
        unlisted = ghost.model_copy(update={"name": "hidden"})
        self.assertEqual(unlisted.name, "hidden")  # copy 只用于造合法输入，不用于断言拒绝
        with self.assertRaises(ValidationError):  # 产物里没有这一路输入
            _spec(policy_id="pie_parkour", policy_artifact=artifact, policy_inputs=(unlisted,))
        ok = rc.PolicyInputBinding(name="obs", kind="proprio", tensor_shape=(1, 45),
                                   source="state", verified=True,
                                   verified_by="onnx_metadata", evidence="fixture")
        self.assertEqual(_spec(policy_id="pie_parkour", policy_artifact=artifact,
                               policy_inputs=(ok,)).policy_inputs[0].name, "obs")


# --------------------------------------------------------------------------------------
# 命令 / 排程事件
# --------------------------------------------------------------------------------------


class CommandAndEventTests(unittest.TestCase):
    def _command(self, **overrides) -> rc.RunCommand:
        base = dict(run_id="run1", transaction_id="tx1", command="pause", expected_epoch=0)
        base.update(overrides)
        return rc.RunCommand(**base)

    def test_step_requires_an_explicit_unit_and_steps(self) -> None:
        command = self._command(command="step", step_unit="physics", steps=10)
        self.assertEqual(command.steps, 10)
        for kwargs in ({"step_unit": "physics"}, {"steps": 10}, {}):
            with self.assertRaises(ValidationError, msg=str(kwargs)):
                self._command(command="step", **kwargs)
        with self.assertRaises(ValidationError):
            self._command(command="pause", steps=1)
        with self.assertRaises(ValidationError):
            self._command(command="step", step_unit="frames", steps=1)
        self.assertEqual(self._command(command="step", step_unit="control", steps=2).step_unit,
                         "control")

    def test_each_command_carries_only_its_own_payload(self) -> None:
        self.assertEqual(self._command(command="set_command",
                                       command_vector=(0.5, 0.0, 0.1)).command_vector,
                         (0.5, 0.0, 0.1))
        with self.assertRaises(ValidationError):
            self._command(command="set_command")
        with self.assertRaises(ValidationError):
            self._command(command="pause", command_vector=(1.0,))
        with self.assertRaises(ValidationError):
            self._command(command="set_command", command_vector=(1.0,) * 9)
        with self.assertRaises(ValidationError):
            self._command(command="set_command", command_vector=(float("nan"),))
        with self.assertRaises(ValidationError):
            self._command(command="switch_policy")
        with self.assertRaises(ValidationError):
            self._command(command="abort")
        self.assertTrue(self._command(command="abort", reason="user_abort").reason)
        with self.assertRaises(ValidationError):
            self._command(command="set_recording")
        with self.assertRaises(ValidationError):
            self._command(command="pause", recording=rc.RecordingOptions())
        with self.assertRaises(ValidationError):
            self._command(command="not_a_command")
        with self.assertRaises(ValidationError):
            self._command(command="pause", schema_version="v9")
        with self.assertRaises(ValidationError):
            self._command(command="pause", run_id="Run/1")

    def test_command_response_rules(self) -> None:
        ok = rc.RunCommandResponse(run_id="run1", transaction_id="tx1", code="accepted",
                                   status="running", epoch=0, applied_tick=10)
        self.assertEqual(ok.applied_tick, 10)
        with self.assertRaises(ValidationError):
            rc.RunCommandResponse(run_id="run1", transaction_id="tx1", code="accepted",
                                  status="running", epoch=0)  # 已接受却没落到 tick
        with self.assertRaises(ValidationError):
            rc.RunCommandResponse(run_id="run1", transaction_id="tx1", code="rejected",
                                  status="running", epoch=0)  # 拒绝必须说清为什么
        rejected = rc.RunCommandResponse(run_id="run1", transaction_id="tx1", code="stale_epoch",
                                         status="running", epoch=1, detail="epoch 1 != 0")
        self.assertIsNone(rejected.applied_tick)
        with self.assertRaises(ValidationError):  # 未生效的指令不得带 applied_tick
            rc.RunCommandResponse(run_id="run1", transaction_id="tx1", code="stale_epoch",
                                  status="running", epoch=1, detail="epoch 1 != 0",
                                  applied_tick=5)
        with self.assertRaises(ValidationError):  # 状态词表外的值写不出来
            rc.RunCommandResponse(run_id="run1", transaction_id="tx1", code="rejected",
                                  status="exploded", epoch=0, detail="x")
        with self.assertRaises(ValidationError):  # 结果码也是一份封闭词表
            rc.RunCommandResponse(run_id="run1", transaction_id="tx1", code="who_knows",
                                  status="running", epoch=0)
        replay = rc.RunCommandResponse(run_id="run1", transaction_id="tx1", code="duplicate",
                                       status="running", epoch=0)
        self.assertIsNone(replay.applied_tick)  # 重放：不重复生效，只回指首次结果

    def test_events_are_typed_with_an_exact_payload_shape(self) -> None:
        event = rc.ScheduledEvent(event_id="ev1", type="velocity_command", expected_epoch=0,
                                  at_tick=100, payload={"vx": 0.5, "vy": 0.0, "yaw_rate": 0.1})
        self.assertEqual(event.required_features(), ())
        with self.assertRaises(ValidationError):
            rc.ScheduledEvent(event_id="ev1", type="velocity_command", expected_epoch=0,
                              at_tick=100, payload={"vx": 0.5})
        with self.assertRaises(ValidationError):
            rc.ScheduledEvent(event_id="ev1", type="velocity_command", expected_epoch=0,
                              at_tick=100, payload={"vx": float("nan"), "vy": 0.0,
                                                    "yaw_rate": 0.0})
        with self.assertRaises(ValidationError):
            rc.ScheduledEvent(event_id="ev1", type="velocity_command", expected_epoch=0,
                              at_tick=100, payload={"vx": 0.5, "vy": 0.0, "yaw_rate": 0.0,
                                                    "extra": 1})
        for state in rc.FAULTABLE_VALIDITIES:
            fault = rc.ScheduledEvent(
                event_id="ev1", type="sensor_fault", expected_epoch=0, at_tick=10,
                duration_ticks=50,
                payload={"instance_id": "imu0", "state": state, "duration_ticks": 50},
            )
            self.assertEqual(fault.type, "sensor_fault")
        with self.assertRaises(ValidationError):  # "valid" 不是故障状态，注入它没有意义
            rc.ScheduledEvent(event_id="ev1", type="sensor_fault", expected_epoch=0, at_tick=10,
                              duration_ticks=50,
                              payload={"instance_id": "imu0", "state": "valid",
                                       "duration_ticks": 50})
        with self.assertRaises(ValidationError):  # 无期限故障说不清"为什么没数据"
            rc.ScheduledEvent(event_id="ev1", type="sensor_fault", expected_epoch=0, at_tick=10,
                              payload={"instance_id": "imu0", "state": "fault",
                                       "duration_ticks": 0})
        with self.assertRaises(ValidationError):
            rc.ScheduledEvent(event_id="ev1", type="wrench", expected_epoch=0, at_tick=10,
                              payload={"force": (1.0, 0.0, 0.0), "torque": (0.0, 0.0, 0.0),
                                       "body": "torso"})
        switch = rc.ScheduledEvent(
            event_id="ev1", type="policy_switch", expected_epoch=0, at_tick=10,
            payload={"policy_id": "lainlab_trot", "artifact_sha256": _SHA},
        )
        self.assertEqual(switch.required_features(), ("policy_closed_loop", "recurrent_reset"))
        with self.assertRaises(ValidationError):  # 换策略必须指向真实产物摘要
            rc.ScheduledEvent(event_id="ev1", type="policy_switch", expected_epoch=0,
                              at_tick=10,
                              payload={"policy_id": "lainlab_trot",
                                       "artifact_sha256": "nope"})

    def test_event_response_distinguishes_scheduled_from_applied(self) -> None:
        scheduled = rc.ScheduledEventResponse(run_id="run1", event_id="ev1", status="scheduled",
                                              epoch=0, at_tick=100)
        self.assertIsNone(scheduled.applied_tick)
        with self.assertRaises(ValidationError):  # 还没生效就写 applied_tick = 假承诺
            rc.ScheduledEventResponse(run_id="run1", event_id="ev1", status="scheduled",
                                      epoch=0, at_tick=100, applied_tick=100)
        applied = rc.ScheduledEventResponse(run_id="run1", event_id="ev1", status="applied",
                                            epoch=0, at_tick=100, applied_tick=100)
        self.assertEqual(applied.applied_tick, 100)
        with self.assertRaises(ValidationError):  # 生效时刻必须与排程一致（当前只允许精确命中）
            rc.ScheduledEventResponse(run_id="run1", event_id="ev1", status="applied",
                                      epoch=0, at_tick=100, applied_tick=99)
        for status in ("rejected", "skipped_stale_epoch", "failed"):
            with self.assertRaises(ValidationError, msg=status):
                rc.ScheduledEventResponse(run_id="run1", event_id="ev1", status=status,
                                          epoch=0, at_tick=100)  # 未生效必须给 reason
            honest = rc.ScheduledEventResponse(run_id="run1", event_id="ev1", status=status,
                                               epoch=0, at_tick=100, reason="fixture")
            self.assertIsNone(honest.applied_tick)
        # 「过期」与「本身不合法」是两件事，词表里必须同时存在且不同名
        self.assertIn("skipped_stale_epoch", rc.EVENT_STATUSES)
        self.assertIn("rejected", rc.EVENT_STATUSES)

    def test_command_provider_spec_is_bound_to_a_real_instance(self) -> None:
        provider = rc.command_provider_spec_from("lidar_velocity_gate",
                                                 input_instances=("lidar0",))
        definition = pc.command_provider_definition("lidar_velocity_gate")
        self.assertEqual(provider.version, definition.version)
        self.assertEqual(provider.command_dims, definition.command_dims)
        self.assertEqual(set(provider.config), set(provider.config_provenance))
        spec = _spec(plugin_ids=("lidar",), provider_id="lidar_velocity_gate")
        self.assertEqual(spec.command_provider.provider_id, "lidar_velocity_gate")
        self.assertIn("event_injection", spec.required_engine_features())
        self.assertIn("raycast", spec.required_engine_features())
        with self.assertRaises(ValueError):
            rc.command_provider_spec_from("no_such_provider", input_instances=("lidar0",))
        for kwargs in ({"command_dims": 2}, {"input_instances": ()},
                       {"input_instances": ("a", "a")}, {"provider_id": "no_such_provider"}):
            with self.assertRaises(ValidationError, msg=str(kwargs)):
                _provider(**kwargs)
        with self.assertRaises(ValidationError):  # 引用了不存在的实例（只有规格能核对）
            _spec(plugin_ids=("lidar",), provider_id="lidar_velocity_gate",
                  command_provider=_provider(input_instances=("ghost",)))


# --------------------------------------------------------------------------------------
# 运行规格：稳定摘要与自洽签名
# --------------------------------------------------------------------------------------


class ResolvedRunSpecTests(unittest.TestCase):
    def test_digest_is_stable_for_identical_resolution(self) -> None:
        self.assertEqual(_spec().spec_digest, _spec().spec_digest)
        self.assertTrue(_spec().digest_matches())

    def test_digest_tracks_every_decision_but_not_wall_clock(self) -> None:
        base = _spec()
        self.assertNotEqual(base.spec_digest, _spec(seed=base.seed + 1).spec_digest)
        self.assertNotEqual(base.spec_digest, _spec(duration_s=3.0).spec_digest)
        self.assertNotEqual(base.spec_digest, _spec(notes=("一条备注",)).spec_digest)
        self.assertNotEqual(
            base.spec_digest,
            _spec(time_base=_time_base(physics_hz=1000, control_decimation=20)).spec_digest,
        )
        later = _probe(plugin_ids=("imu",), probed_at_unix=base.capabilities.probe.probed_at_unix
                       + 3600.0)
        self.assertEqual(base.spec_digest,
                         _spec(capabilities=_capabilities(probe=later)).spec_digest)

    def test_tampered_digest_is_rejected(self) -> None:
        spec = _spec()
        payload = spec.model_dump()
        payload["seed"] = 999
        payload["spec_digest"] = spec.spec_digest  # 旧摘要配新内容
        with self.assertRaises(ValidationError):
            rc.ResolvedRunSpec.model_validate(payload)
        self.assertEqual(spec.spec_digest,
                         rc.ResolvedRunSpec.model_validate(spec.model_dump()).spec_digest)

    def test_assets_must_be_unique_digested_and_have_exactly_one_model(self) -> None:
        spec = _spec()
        with self.assertRaises(ValidationError):
            _spec(assets=())
        with self.assertRaises(ValidationError):
            _spec(assets=(spec.assets[0], spec.assets[0]))
        with self.assertRaises(ValidationError):
            _spec(assets=(rc.AssetRef(kind="model_xml", path="model/robot.xml"),))
        with self.assertRaises(ValidationError):
            _spec(assets=_assets() + (rc.AssetRef(kind="model_xml", path="model/other.xml",
                                                  sha256=_OTHER_SHA, robot_id="unitree_go2"),))
        two = _assets() + (rc.AssetRef(kind="scene_xml", path="assets/maps/warehouse.xml",
                                       sha256=_OTHER_SHA),)
        self.assertEqual(_spec(assets=two).assets, two)

    def test_provenance_must_cover_every_required_category(self) -> None:
        spec = _spec()
        self.assertEqual({item.category for item in spec.provenance},
                         set(rc.PROVENANCE_REQUIRED))
        with self.assertRaises(ValidationError):
            _spec(provenance=_provenance(rc.PROVENANCE_REQUIRED[:-1]))
        with self.assertRaises(ValidationError):
            _spec(provenance=_provenance() + _provenance()[:1])
        with self.assertRaises(ValidationError):
            rc.ParamProvenance(name="seed", category="seed", source="  ")
        for vague in ("default", "auto", "n/a"):
            with self.assertRaises(ValidationError, msg=vague):
                rc.ParamProvenance(name="seed", category="seed", source=vague)

    def test_exported_helpers(self) -> None:
        spec = _spec()
        self.assertEqual(spec.control_hz, 50.0)
        self.assertEqual(spec.max_ticks, 1000)
        with self.assertRaises(ValueError):
            spec.sample_hz("nope")
        handshake = spec.as_handshake_dict()
        self.assertEqual(handshake["spec_digest"], spec.spec_digest)
        self.assertEqual(handshake["max_ticks"], 1000)
        self.assertEqual(handshake["time_base"]["source"], "contract")
        self.assertEqual(handshake["instances"][0]["instance_id"], "imu0")
        self.assertEqual(handshake["recording"], rc.RecordingOptions().budget_dict())

    def test_unknown_ids_are_rejected_at_the_field_level(self) -> None:
        for kwargs in ({"robot_id": "Unitree GO2"}, {"policy_id": "bad/id"},
                      {"scenario_id": "s p a c e"}):
            with self.assertRaises(ValidationError, msg=str(kwargs)):
                _spec(**kwargs)


# --------------------------------------------------------------------------------------
# 记录：块索引与 manifest
# --------------------------------------------------------------------------------------


class RecordingManifestTests(unittest.TestCase):
    def test_chunk_format_table(self) -> None:
        self.assertEqual(_chunk().element_bytes(), 180)
        with self.assertRaises(ValidationError):
            _chunk(format="jsonl")
        events = _chunk(kind="events", format="jsonl", path="ep1/events.jsonl",
                        instance_id=None, output=None, dtype=None, shape=None, unit=None)
        self.assertEqual(events.kind, "events")
        with self.assertRaises(ValidationError):
            _chunk(kind="events", format="jsonl", path="ep1/events.jsonl", instance_id=None,
                   output=None, unit=None)  # 非张量块不重复声明 shape/dtype
        for kind, formats in rc.CHUNK_FORMATS.items():
            self.assertTrue(formats, kind)
        with self.assertRaises(ValidationError):
            _chunk(sample_count=0, dropped_count=0)
        with self.assertRaises(ValidationError):
            _chunk(last_tick=-1)
        with self.assertRaises(ValidationError):
            _chunk(last_sim_time=-1.0)
        with self.assertRaises(ValidationError):
            _chunk(path="../escape.npz")
        with self.assertRaises(ValidationError):
            _chunk(unit=None)
        with self.assertRaises(ValidationError):
            _chunk(dtype="f9")

    def test_index_is_a_whitelist_ordered_by_tick(self) -> None:
        index = _index()
        self.assertEqual(index.allowed_path("chunk0"), "ep1/tensors/chunk0.npz")
        self.assertIsNone(index.allowed_path("chunk999"))
        self.assertTrue(index.window_covered(start_tick=0, end_tick=9))
        self.assertFalse(index.window_covered(start_tick=0, end_tick=10))
        with self.assertRaises(ValidationError):
            _index(_chunk(), _chunk(chunk_id="chunk0"))
        with self.assertRaises(ValidationError):
            _index(_chunk(), _chunk(chunk_id="chunk1", first_tick=20, last_tick=9))
        with self.assertRaises(ValidationError):
            _index(interrupted=True, complete=True)
        with self.assertRaises(ValidationError):
            _index(final_chunk_count=7)
        self.assertEqual(index.total_bytes, 1024)

    def test_manifest_cross_checks_itself(self) -> None:
        manifest = _manifest()
        self.assertEqual(manifest.manifest_version, rc.EPISODE_MANIFEST_VERSION)
        self.assertIsNone(manifest.end_reason)
        self.assertFalse(manifest.is_system_failure())
        with self.assertRaises(ValidationError):
            _manifest(index=_index().model_copy(update={"episode_id": "other"}))
        with self.assertRaises(ValidationError):
            _manifest(end_tick=0, start_tick=5)
        spec = _spec()
        with self.assertRaises(ValidationError):  # 顶层摘要与内嵌规格不符 = 记录自相矛盾
            _manifest(spec=spec.model_copy(update={"spec_digest": _OTHER_SHA}),
                      spec_digest=spec.spec_digest, seed=spec.seed)
        attached = _manifest(spec=spec, spec_digest=spec.spec_digest, seed=spec.seed,
                             assets=spec.assets)
        self.assertEqual(attached.spec.spec_digest, spec.spec_digest)
        self.assertEqual(attached.seed, spec.seed)
        self.assertEqual(attached.assets, spec.assets)
        with self.assertRaises(ValidationError):  # 顶层 seed 与规格不符
            _manifest(spec=spec, spec_digest=spec.spec_digest, seed=spec.seed + 1,
                      assets=spec.assets)
        with self.assertRaises(ValidationError):  # 资产清单被局部改写
            _manifest(spec=spec, spec_digest=spec.spec_digest, seed=spec.seed, assets=())
        with self.assertRaises(ValidationError):
            _manifest(index=_index(interrupted=True, complete=False), status="finalized")
        with self.assertRaises(ValidationError):
            _manifest(status="exploded")  # 状态不在词表内
        with self.assertRaises(ValidationError):
            _manifest(end_reason="robot_melted")

    def test_manifest_end_reason_separates_system_and_policy_failure(self) -> None:
        for reason in rc.SYSTEM_FAILURE_REASONS:
            self.assertEqual(_manifest(end_reason=reason, status="failed").is_system_failure(),
                             True, reason)
        self.assertFalse(_manifest(end_reason="fall", status="failed").is_system_failure())
        with self.assertRaises(ValidationError):
            rc.RunFinal(run_id="run1", status="finalized", epoch=0,
                        end_reason="protocol_violation", end_tick=10, sim_time=0.02)


# --------------------------------------------------------------------------------------
# 下行消息形状（唯一一套，不留竞争形状）
# --------------------------------------------------------------------------------------


class DownlinkMessageTests(unittest.TestCase):
    def _snapshot(self, **overrides) -> rc.RunSnapshot:
        base = dict(run_id="run1", status="running", epoch=0, tick=10, sim_time=0.02)
        base.update(overrides)
        return rc.RunSnapshot(**base)

    def test_snapshot(self) -> None:
        health = rc.SensorHealth(instance_id="imu0", plugin_id="imu", epoch=0,
                                 sample_period_ticks=10, last_sample_tick=9,
                                 last_available_tick=10)
        snapshot = self._snapshot(base_pos=(0.0, 0.0, 0.5),
                                  base_quat_wxyz=(1.0, 0.0, 0.0, 0.0), sensors=(health,))
        self.assertFalse(snapshot.terminal)
        self.assertEqual(snapshot.sensors[0].age_ticks(11), 2)
        for kwargs in ({"base_pos": (float("nan"), 0.0, 0.0)},
                       {"base_quat_wxyz": (2.0, 0.0, 0.0, 0.0)},
                       {"sim_time": float("inf")},
                       {"status": "sprinting"},
                       {"real_time_factor": 0.0},
                       {"sensors": (health, health)}):
            with self.assertRaises(ValidationError, msg=str(kwargs)):
                self._snapshot(**kwargs)
        health_base = dict(instance_id="imu0", plugin_id="imu", epoch=0,
                           sample_period_ticks=10, last_sample_tick=9)
        with self.assertRaises(ValidationError):  # 可用时刻不可能早于采样时刻
            rc.SensorHealth(**{**health_base, "last_available_tick": 8})
        with self.assertRaises(ValidationError):  # 丢弃数不得超过总数
            rc.SensorHealth(instance_id="imu0", plugin_id="imu", epoch=0,
                            sample_period_ticks=10, last_sample_tick=9,
                            last_available_tick=10, samples_dropped=5)
        self.assertTrue(self._snapshot(status="failed").terminal)

    def test_run_event_and_error_share_the_status_vocabulary(self) -> None:
        event = rc.RunEvent(run_id="run1", epoch=0, tick=10, sim_time=0.02,
                            type="velocity_command", status="applied")
        self.assertEqual(event.status, "applied")
        with self.assertRaises(ValidationError):
            rc.RunEvent(run_id="run1", epoch=0, tick=10, sim_time=0.02, type="teleport",
                        status="applied")
        with self.assertRaises(ValidationError):  # 被拒绝却没给 detail = 说不出为什么
            rc.RunEvent(run_id="run1", epoch=0, tick=10, sim_time=0.02,
                        type="velocity_command", status="rejected")
        with self.assertRaises(ValidationError):  # 载荷里的 NaN 不许进事件流
            rc.RunEvent(run_id="run1", epoch=0, tick=10, sim_time=0.02,
                        type="velocity_command", status="applied",
                        payload={"vx": float("nan")})
        self.assertEqual(rc.RunEvent(run_id="run1", epoch=0, tick=10, sim_time=0.02,
                                     type="velocity_command", status="rejected",
                                     detail="epoch 不符").status, "rejected")
        error = rc.RunError(code="probe_required", message="缺探测报告", source="resolver")
        self.assertFalse(error.recoverable)
        for code in rc.RUN_ERROR_CODES:
            self.assertTrue(rc.RunError(code=code, message="x", detail={}).code)
        with self.assertRaises(ValidationError):
            rc.RunError(code="everything_is_broken", message="x")
        with self.assertRaises(ValidationError):  # 空消息不算消息
            rc.RunError(code="probe_required", message="   ")

    def test_handshake_carries_protocol_units_and_limits(self) -> None:
        handshake = rc.RunHandshake(
            run_id="run1", epoch=0, status="ready", spec_digest=_SHA,
            time_base=_time_base().as_dict(), spec=_spec().as_handshake_dict(),
        )
        self.assertEqual(handshake.protocol_name, PROTOCOL_NAME)
        self.assertEqual(handshake.protocol_version, PROTOCOL_VERSION)
        self.assertEqual(handshake.limits, protocol_limits())
        self.assertEqual(handshake.quat_order, "wxyz")
        self.assertEqual(handshake.units["length"], "m")
        with self.assertRaises(ValidationError):
            rc.RunHandshake(run_id="run1", epoch=0, status="ready", spec_digest=_SHA,
                            time_base={**_time_base().as_dict(), "source": "legacy_config"})
        with self.assertRaises(ValidationError):
            rc.RunHandshake(run_id="run1", epoch=0, status="ready", spec_digest=_SHA,
                            time_base={"physics_hz": 500})
        with self.assertRaises(ValidationError):
            rc.RunHandshake(run_id="run1", epoch=0, status="ready", spec_digest=_SHA,
                            time_base=_time_base().as_dict(), protocol_version=99)
        with self.assertRaises(ValidationError):
            rc.RunHandshake(run_id="run1", epoch=0, status="ready", spec_digest="0" * 8,
                            time_base=_time_base().as_dict())
        with self.assertRaises(ValidationError):
            rc.RunHandshake(run_id="run1", epoch=0, status="ready", spec_digest=_SHA,
                            time_base=_time_base().as_dict(),
                            limits={**protocol_limits(), "header_max_bytes": 10 ** 12})


# --------------------------------------------------------------------------------------
# 状态机
# --------------------------------------------------------------------------------------


class StatusMachineTests(unittest.TestCase):
    def test_every_status_is_in_the_transition_table(self) -> None:
        self.assertEqual(set(rc.RUN_TRANSITIONS), set(rc.RUN_STATUSES))
        for status in rc.TERMINAL_RUN_STATUSES:
            self.assertEqual(rc.RUN_TRANSITIONS[status], (), status)
        rc.assert_status_transition("resolved", "provisioning")
        rc.assert_status_transition("ready", "running")
        rc.assert_status_transition("running", "paused")
        for current, following in (("draft", "running"), ("ready", "finalized"),
                                   ("finalized", "running"), ("running", "ready")):
            with self.assertRaises(ValueError, msg=f"{current}->{following}"):
                rc.assert_status_transition(current, following)
        with self.assertRaises(ValueError):
            rc.assert_status_transition("sprinting", "running")
        self.assertEqual(set(rc.RUN_STATUSES) - set(rc.TERMINAL_RUN_STATUSES),
                         {"draft", "resolved", "provisioning", "ready", "running", "paused",
                          "stepping", "finishing"})


# --------------------------------------------------------------------------------------
# HTTP 契约（下游路由必须照抄这些形状）
# --------------------------------------------------------------------------------------


class HttpContractTests(unittest.TestCase):
    def test_catalog(self) -> None:
        catalog = rc.RunCatalogResponse()
        dumped = catalog.model_dump(mode="json")
        self.assertEqual(dumped["api_version"], rc.SIM_API_VERSION)
        self.assertEqual(dumped["resolution_blockers"], list(rc.RESOLUTION_BLOCKERS))
        self.assertEqual(dumped["probe_features"], list(rc.PROBE_FEATURES))
        self.assertEqual(dumped["run_statuses"], list(rc.RUN_STATUSES))
        self.assertEqual(dumped["command_types"], list(rc.COMMAND_TYPES))
        self.assertEqual(dumped["event_types"], list(rc.EVENT_TYPES))
        self.assertEqual(dumped["sample_validity"], list(rc.SAMPLE_VALIDITY))
        self.assertEqual(dumped["capability_levels"], list(rc.CAPABILITY_LEVELS))
        self.assertEqual(dumped["protocol"], protocol_limits())
        self.assertEqual(dumped["stream"], rc.ws_stream_contract())
        self.assertEqual(dumped["recording_defaults"], rc.RecordingOptions().budget_dict())
        self.assertEqual(dumped["sensor_plugins"], pc.plugin_catalog_payload())
        self.assertEqual(dumped["probe"], None)  # 未探测就不给探测结果字段编造内容
        executor = dumped["executors"][0]
        self.assertEqual(executor["executor_id"], rc.NATIVE_EXECUTOR_ID)
        self.assertEqual(executor["native_runtime_version"], rc.NATIVE_RUNTIME_VERSION)
        self.assertEqual(executor["policy_closed_loop"], True)
        self.assertEqual(executor["sensor_capture"], "registered_only")
        with self.assertRaises(ValidationError):
            rc.RunCatalogResponse(api_version="v1")

    def test_resolve_round_trip_is_all_or_nothing(self) -> None:
        spec = _spec()
        response = rc.ResolveResponse(ok=True, spec=spec, spec_digest=spec.spec_digest,
                                      capabilities=spec.capabilities)
        self.assertEqual(response.protocol, protocol_limits())
        with self.assertRaises(ValidationError):
            rc.ResolveResponse(ok=True)  # 必须给 spec
        with self.assertRaises(ValidationError):
            rc.ResolveResponse(ok=True, spec=spec, blockers=(
                rc.ResolutionBlocker(code="asset_missing", subject="m", detail="缺"),))
        with self.assertRaises(ValidationError):
            rc.ResolveResponse(ok=True, spec=spec, spec_digest=_OTHER_SHA)
        with self.assertRaises(ValidationError):
            rc.ResolveResponse(ok=False, spec=spec, blockers=(
                rc.ResolutionBlocker(code="native_probe_missing", subject="run", detail="缺"),))
        with self.assertRaises(ValidationError):
            rc.ResolveResponse(ok=False)  # 失败必须给出结构化阻断项
        with self.assertRaises(ValidationError):
            rc.ResolveRequest(schema_version="sim-run-contract-0.5")
        with self.assertRaises(ValidationError):
            rc.ResolveRequest(scenario={"advanced": {"x": float("nan")}})
        blocked = rc.ResolveResponse(ok=False, blockers=(
            rc.ResolutionBlocker(code="native_probe_missing", subject="unitree_go2",
                                 detail="没有探测报告", remedy="注入 worker probe",
                                 field="capabilities.probe"),))
        self.assertEqual(blocked.spec, None)
        self.assertTrue(blocked.blockers[0].as_message().startswith("native_probe_missing"))
        with self.assertRaises(ValidationError):
            rc.ResolutionBlocker(code="native_probe_missing", subject="x")  # 缺 detail
        with self.assertRaises(ValidationError):
            rc.ResolutionBlocker(code="who_knows", subject="x", detail="y")
        with self.assertRaises(ValidationError):
            rc.ResolutionBlocker(code="asset_missing", subject="  ", detail="y")

    def test_create_run_only_trusts_the_digest(self) -> None:
        spec = _spec()
        request = rc.CreateRunRequest(spec_digest=spec.spec_digest, spec=spec,
                                      transaction_id="tx1")
        self.assertTrue(request.verify_assets)
        self.assertFalse(request.auto_start)
        with self.assertRaises(ValidationError):
            rc.CreateRunRequest(spec_digest=spec.spec_digest,
                                spec=_spec(seed=spec.seed + 1), transaction_id="tx1")
        with self.assertRaises(ValidationError):
            rc.CreateRunRequest(spec_digest="abc", transaction_id="tx1")
        created = rc.RunCreatedResponse(run_id="run1", status="provisioning", epoch=0,
                                        spec_digest=spec.spec_digest, transaction_id="tx1",
                                        stream_path="/api/simulation/v2/runs/run1/stream",
                                        created_at_unix=1000.0)
        self.assertEqual(created.stream_path,
                         rc.ws_stream_contract()["path"].format(run_id="run1"))
        with self.assertRaises(ValidationError):  # 流地址只能由契约推导，不许自拟
            rc.RunCreatedResponse(run_id="run1", status="provisioning", epoch=0,
                                  spec_digest=spec.spec_digest, transaction_id="tx1",
                                  stream_path="/ws/run1", created_at_unix=1000.0)

    def test_run_detail_must_agree_with_its_snapshot(self) -> None:
        capabilities = _capabilities()
        base = dict(run_id="run1", status="resolved", epoch=0, spec_digest=_SHA,
                    capabilities=capabilities, created_at_unix=1000.0)
        detail = rc.RunDetailResponse(**base)
        self.assertIsNone(detail.snapshot)
        with self.assertRaises(ValidationError):
            rc.RunDetailResponse(**{**base, "status": "running"})
        snapshot = rc.RunSnapshot(run_id="run1", status="resolved", epoch=0, tick=0,
                                  sim_time=0.0)
        detail = rc.RunDetailResponse(**{**base, "snapshot": snapshot})
        self.assertEqual(detail.snapshot.tick, 0)
        for bad in ({"snapshot": snapshot.model_copy(update={"run_id": "other"})},
                    {"snapshot": snapshot.model_copy(update={"epoch": 1})}):
            with self.assertRaises(ValidationError, msg=str(bad)):
                rc.RunDetailResponse(**{**base, **bad})
        running = rc.RunSnapshot(run_id="run1", status="running", epoch=0, tick=5,
                                 sim_time=0.01)
        self.assertEqual(rc.RunDetailResponse(**{**base, "status": "running",
                                                 "snapshot": running}).snapshot.tick, 5)
        with self.assertRaises(ValidationError):
            rc.RunDetailResponse(**{**base, "status": "unknown_state"})

    def test_episode_manifest_endpoint_exposes_only_whitelisted_chunks(self) -> None:
        manifest = _manifest()
        response = rc.EpisodeManifestResponse(episode_id="ep1", manifest=manifest,
                                              allowed_chunk_ids=("chunk0",))
        self.assertGreater(response.chunk_limit_bytes, 0)  # 单次下载有硬上限
        self.assertIn("chunk_limit_bytes", rc.EpisodeManifestResponse.model_fields)
        for ids in ((), ("chunk9",), ("chunk0", "chunk0")):
            with self.assertRaises(ValidationError, msg=str(ids)):
                rc.EpisodeManifestResponse(episode_id="ep1", manifest=manifest,
                                           allowed_chunk_ids=ids)
        with self.assertRaises(ValidationError):
            rc.EpisodeManifestResponse(episode_id="ep2", manifest=manifest,
                                       allowed_chunk_ids=("chunk0",))
        download = rc.ChunkDownload(episode_id="ep1", chunk_id="chunk0",
                                    path=manifest.index.allowed_path("chunk0"),
                                    sha256=_SHA, size_bytes=1024,
                                    media_type="application/octet-stream")
        self.assertEqual(download.path, "ep1/tensors/chunk0.npz")
        with self.assertRaises(ValidationError):  # 下载描述里也不许出现逃逸路径
            rc.ChunkDownload(episode_id="ep1", chunk_id="chunk0", path="../secrets",
                             sha256=_SHA, size_bytes=1024,
                             media_type="application/octet-stream")
        with self.assertRaises(ValidationError):  # 只发二进制/图片，不发可执行内容
            rc.ChunkDownload(episode_id="ep1", chunk_id="chunk0",
                             path="ep1/tensors/chunk0.npz", sha256=_SHA, size_bytes=1024,
                             media_type="text/html")


class VocabularySingleSourceTests(unittest.TestCase):
    """词表只有一处声明：任何"再抄一份"的漂移都要在这里被抓到。"""

    def test_enumerations_are_tuples_without_duplicates(self) -> None:
        groups = {
            "RUN_STATUSES": rc.RUN_STATUSES, "EVENT_TYPES": rc.EVENT_TYPES,
            "COMMAND_TYPES": rc.COMMAND_TYPES, "SAMPLE_VALIDITY": rc.SAMPLE_VALIDITY,
            "PROBE_FEATURES": rc.PROBE_FEATURES, "ASSET_KINDS": rc.ASSET_KINDS,
            "RESOLUTION_BLOCKERS": rc.RESOLUTION_BLOCKERS, "RUN_ERROR_CODES": rc.RUN_ERROR_CODES,
            "RUN_END_REASONS": rc.RUN_END_REASONS, "CAPABILITY_LEVELS": rc.CAPABILITY_LEVELS,
        }
        for name, values in groups.items():
            self.assertIsInstance(values, tuple, name)
            self.assertEqual(len(values), len(set(values)), name)
            self.assertTrue(all(isinstance(item, str) and item for item in values), name)

    def test_blocker_and_error_tables_feed_the_catalog(self) -> None:
        catalog = rc.RunCatalogResponse().model_dump()
        self.assertEqual(set(catalog["resolution_blockers"]), set(rc.RESOLUTION_BLOCKERS))
        self.assertEqual(rc.SYSTEM_FAILURE_REASONS <= set(rc.RUN_END_REASONS), True)
        self.assertEqual(
            set(rc.FAULTABLE_VALIDITIES) <= set(rc.SAMPLE_VALIDITY) - {"valid"}, True
        )
        self.assertEqual(set(rc.SAMPLE_DATA_VALIDITIES) | set(rc.SAMPLE_EMPTY_VALIDITIES),
                         set(rc.SAMPLE_VALIDITY))

    def test_version_identity_strings(self) -> None:
        self.assertEqual(rc.SIM_API_VERSION, "v2")
        self.assertEqual(rc.PROTOCOL_NAME, "lsim")
        self.assertEqual(rc.NATIVE_EXECUTOR_ID, "native_mujoco")
        self.assertTrue(rc.NATIVE_RUNTIME_VERSION.startswith("native-mujoco-runtime/"))
        self.assertNotEqual(rc.NATIVE_RUNTIME_VERSION, rc.RUN_CONTRACT_VERSION)
        self.assertEqual(rc.ws_stream_contract()["direction"], "downlink_only")
        self.assertEqual(rc.ws_stream_contract()["first_frame"], "hello")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
