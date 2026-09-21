"""线协议 :mod:`contracts.simulation_protocol` 的定向测试。

这些测试**驱动真实编解码**（不是自证式 stub）：每一条都从字节层面构造输入，
再断言解码器/校验器实际做出的判断，包括「应该拒绝」的那一半 ——
长度定界协议的截断、摘要不符、非有限浮点、日志混入，全都是真实管道里会出现的故障。
"""

from __future__ import annotations

import io
import json
import struct
import unittest

import contracts.simulation_protocol as proto


def _header(**overrides):
    """一条**结构完整**的帧头（含编码端强制写入的三件套），便于单独驱动 validate。"""

    payload = overrides.pop("payload", b"{}")
    base = {
        "v": proto.PROTOCOL_VERSION,
        "type": "status",
        "run_id": "run-1",
        "epoch": 0,
        "seq": 0,
        "tick": 12,
        "sim_time": 0.24,
        "content_type": proto.CONTENT_JSON,
        "payload_bytes": len(payload),
        "payload_sha256": proto.payload_checksum(payload),
    }
    base.update(overrides)
    return base, payload


def _check(**overrides):
    header, payload = _header(**overrides)
    proto.validate_header(header, payload)


class FrameRoundTripTests(unittest.TestCase):
    def test_json_message_round_trip(self) -> None:
        raw = proto.encode_json_message(
            "status", run_id="run-7", epoch=1, seq=3, tick=50, sim_time=1.5,
            body={"status": "running", "tick": 50},
        )
        frame = proto.decode_frame(raw)
        self.assertEqual(frame.type, "status")
        self.assertEqual((frame.epoch, frame.seq, frame.tick), (1, 3, 50))
        self.assertEqual(frame.json_body(), {"status": "running", "tick": 50})
        # 编码端强制写入的三件套（调用方不可能"忘了算摘要"）
        self.assertEqual(frame.header["v"], proto.PROTOCOL_VERSION)
        self.assertEqual(frame.header["payload_bytes"], len(frame.payload))
        self.assertEqual(frame.header["payload_sha256"], proto.payload_checksum(frame.payload))

    def test_stream_multiple_frames(self) -> None:
        stream = io.BytesIO()
        for index in range(3):
            stream.write(
                proto.encode_json_message(
                    "event", run_id="r", epoch=0, seq=index, tick=index, sim_time=index * 0.1,
                    body={"index": index},
                )
            )
        frames = list(proto.iter_frames(io.BytesIO(stream.getvalue())))
        self.assertEqual([frame.seq for frame in frames], [0, 1, 2])
        self.assertEqual(frames[-1].json_body(), {"index": 2})

    def test_write_then_read_frame_matches_encode_frame(self) -> None:
        stream = io.BytesIO()
        payload = struct.pack("<3f", 1.0, -2.5, 3.0)
        header, _ = _header(
            type="sample", content_type=proto.CONTENT_OCTET, payload=payload,
            shape=[3], dtype="f4", instance_id="imu", output="vel",
            validity="valid", source="measurement",
        )
        written = proto.write_frame(stream, header, payload)
        frame = proto.read_frame(io.BytesIO(stream.getvalue()))
        self.assertEqual(written.header, frame.header)
        self.assertEqual(frame.payload, payload)
        self.assertEqual(list(frame.header["shape"]), [3])
        self.assertIsNone(proto.read_frame(io.BytesIO(b"")))  # 干净 EOF

    def test_write_refuses_invalid_sample_before_touching_stream(self) -> None:
        stream = io.BytesIO()
        header, payload = _header(
            type="sample", content_type=proto.CONTENT_OCTET,
            shape=[3], dtype="f4", instance_id="imu", output="vel",
            validity="valid", source="measurement",
        )
        with self.assertRaises(proto.ProtocolViolationError):
            proto.write_frame(stream, header, payload)
        self.assertEqual(stream.getvalue(), b"")

    def test_written_frame_reports_the_normalized_wire_header(self) -> None:
        header, payload = _header()
        header["payload_bytes"] = 999
        header["payload_sha256"] = "old"
        stream = io.BytesIO()
        written = proto.write_frame(stream, header, payload)
        decoded = proto.decode_frame(stream.getvalue())
        self.assertEqual(written.header, decoded.header)
        self.assertEqual(header["payload_bytes"], 999)

    def test_sample_frames_share_one_seq_counter(self) -> None:
        encoder = proto.StreamEncoder(run_id="r", epoch=0)
        blobs = [
            encoder.json_message("status", tick=0, sim_time=0.0, body={}),
            encoder.sample(run_id="ignored", epoch=9, seq=99, tick=5, sim_time=0.01,
                           instance_id="d", output="depth", validity="valid",
                           source="measurement", shape=[1, 2, 2], dtype="f4",
                           payload=b"\x00" * 16),
            encoder.json_message("bye", tick=6, sim_time=0.02, body={}),
        ]
        frames = [proto.decode_frame(blob) for blob in blobs]
        self.assertEqual([frame.seq for frame in frames], [0, 1, 2])
        # 发射端的 run_id/epoch 权威：调用方传的 seq/epoch 一律被覆盖
        self.assertEqual({frame.epoch for frame in frames}, {0})
        self.assertEqual({frame.header["run_id"] for frame in frames}, {"r"})
        for previous, current in zip(frames, frames[1:]):
            proto.check_stream_order(current, previous)

    def test_empty_payload_has_stable_digest(self) -> None:
        self.assertEqual(proto.EMPTY_PAYLOAD_SHA256, proto.payload_checksum(b""))
        self.assertEqual(len(proto.EMPTY_PAYLOAD_SHA256), proto.PAYLOAD_SHA256_HEX_LEN)


class TruncationTests(unittest.TestCase):
    def test_short_prefix_is_truncated(self) -> None:
        with self.assertRaises(proto.ProtocolTruncatedError) as caught:
            proto.decode_frame(b"\x00\x00")
        self.assertEqual(caught.exception.code, "truncated")
        self.assertEqual((caught.exception.wanted, caught.exception.got), (4, 2))

    def test_cut_header_raises_wanted_got(self) -> None:
        raw = proto.encode_json_message("status", run_id="r", epoch=0, seq=0, tick=0,
                                        sim_time=0.0, body={"a": 1})
        with self.assertRaises(proto.ProtocolTruncatedError) as caught:
            proto.decode_frame(raw[:6])  # 只留下 2 个头字节
        self.assertGreater(caught.exception.wanted, caught.exception.got)
        self.assertEqual(caught.exception.got, 6)

    def test_cut_payload_mid_stream_raises_not_partial_frame(self) -> None:
        """半帧必须报错，不能"读到哪儿算哪儿"——静默跳帧会让之后每一帧都错位。"""

        good = proto.encode_json_message("status", run_id="r", epoch=0, seq=0, tick=0,
                                         sim_time=0.0, body={})
        broken = proto.encode_json_message("status", run_id="r", epoch=0, seq=1, tick=1,
                                           sim_time=0.1, body={"x": "y" * 40})
        stream = io.BytesIO(good + broken[:-10])
        self.assertEqual(proto.read_frame(stream).seq, 0)
        with self.assertRaises(proto.ProtocolTruncatedError):
            proto.read_frame(stream)


class LimitsTests(unittest.TestCase):
    def test_header_over_limit_rejected_on_encode(self) -> None:
        giant = "x" * proto.HEADER_MAX_BYTES
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.encode_json_message("status", run_id=giant, epoch=0, seq=0, tick=0,
                                      sim_time=0.0, body={})
        self.assertEqual(caught.exception.code, "header_too_large")

    def test_declared_header_length_over_limit_rejected_on_decode(self) -> None:
        raw = struct.pack(">I", proto.HEADER_MAX_BYTES + 1) + b"{}"
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.decode_frame(raw)
        self.assertEqual(caught.exception.code, "header_too_large")

    def test_payload_over_limit_rejected_on_encode(self) -> None:
        header, _ = _header(payload=b"")
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.encode_frame(header, b"\x00" * (proto.PAYLOAD_MAX_BYTES + 1))
        self.assertEqual(caught.exception.code, "payload_too_large")

    def test_control_line_over_limit_rejected(self) -> None:
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.encode_control(kind="command", run_id="r", transaction_id="t",
                                 expected_epoch=0,
                                 payload={"blob": "y" * proto.CONTROL_LINE_MAX_BYTES})
        self.assertEqual(caught.exception.code, "control_too_large")
        long_line = "z" * (proto.CONTROL_LINE_MAX_BYTES + 1)
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.parse_control(long_line)
        self.assertEqual(caught.exception.code, "control_too_large")

    def test_limits_are_exported_for_frontend(self) -> None:
        """前端与管理器同源：catalog 转发的上限必须就是模块常量。"""

        limits = proto.protocol_limits()
        self.assertEqual(limits["name"], proto.PROTOCOL_NAME)
        self.assertEqual(limits["version"], proto.PROTOCOL_VERSION)
        self.assertEqual(limits["header_max_bytes"], proto.HEADER_MAX_BYTES)
        self.assertEqual(limits["payload_max_bytes"], proto.PAYLOAD_MAX_BYTES)
        self.assertEqual(limits["control_line_max_bytes"], proto.CONTROL_LINE_MAX_BYTES)
        self.assertEqual(limits["frame_common_fields"], list(proto.FRAME_COMMON_FIELDS))
        self.assertEqual(limits["dtype_itemsize"], dict(proto.DTYPE_ITEMSIZE))
        self.assertEqual(limits["message_types"], list(proto.MESSAGE_TYPES))
        self.assertEqual(limits["control_kinds"], list(proto.CONTROL_KINDS))


class HeaderValidationTests(unittest.TestCase):
    def test_every_common_field_is_mandatory(self) -> None:
        for name in proto.FRAME_COMMON_FIELDS:
            header, payload = _header()
            header.pop(name)
            with self.assertRaises(proto.ProtocolViolationError) as caught:
                proto.validate_header(header, payload)
            self.assertEqual(caught.exception.code, "missing_fields", f"字段 {name}")

    def test_version_mismatch(self) -> None:
        header, payload = _header(v=proto.PROTOCOL_VERSION + 1)
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.validate_header(header, payload)
        self.assertEqual(caught.exception.code, "version_mismatch")

    def test_unknown_message_type(self) -> None:
        header, payload = _header(type="telemetry")
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.validate_header(header, payload)
        self.assertEqual(caught.exception.code, "unknown_type")

    def test_unknown_content_type(self) -> None:
        header, payload = _header(content_type="text/plain")
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.validate_header(header, payload)
        self.assertEqual(caught.exception.code, "unknown_content")

    def test_non_sample_binary_content_rejected(self) -> None:
        """单一形状纪律：只有样本能带二进制，状态/事件一律 JSON。"""

        header, payload = _header(type="status", content_type=proto.CONTENT_OCTET)
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.validate_header(header, payload)
        self.assertEqual(caught.exception.code, "shape_conflict")

    def test_sample_type_cannot_go_through_json_message_encoder(self) -> None:
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.encode_json_message("sample", run_id="r", epoch=0, seq=0, tick=0,
                                      sim_time=0.0, body={})
        self.assertEqual(caught.exception.code, "unknown_type")

    def test_checksum_mismatch(self) -> None:
        header, _ = _header()
        header["payload_sha256"] = "0" * proto.PAYLOAD_SHA256_HEX_LEN
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.validate_header(header, b"{}")
        self.assertEqual(caught.exception.code, "checksum")

    def test_declared_length_not_matching_payload(self) -> None:
        header, _ = _header(payload=b"")
        header.pop("payload_sha256")
        header["payload_sha256"] = proto.payload_checksum(b"")
        header["payload_bytes"] = 1
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.validate_header(header, b"")
        self.assertEqual(caught.exception.code, "payload_length")

    def test_negative_and_bool_integers_rejected(self) -> None:
        for name, value in (("seq", -1), ("tick", True), ("epoch", "0"), ("sim_time", -0.1)):
            with self.assertRaises(proto.ProtocolViolationError) as caught:
                _check(**{name: value})
            self.assertEqual(caught.exception.code, "bad_header", f"{name}={value!r}")

    def test_run_id_must_be_non_empty(self) -> None:
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            _check(run_id="")
        self.assertEqual(caught.exception.code, "bad_header")

    def test_log_mixed_into_binary_stream_is_violation(self) -> None:
        """stdout 只走协议：一句 print 日志必须报错，不能被跳过。"""

        stream = io.BytesIO(b"loaded model ok\n" + b"\x00" * 6)
        with self.assertRaises(proto.ProtocolViolationError):
            proto.read_frame(stream)

    def test_non_object_header_rejected(self) -> None:
        for blob in (b"[1,2,3]", b'"text"', b"null"):
            with self.assertRaises(proto.ProtocolViolationError) as caught:
                proto.decode_frame(struct.pack(">I", len(blob)) + blob)
            self.assertEqual(caught.exception.code, "bad_header")


class NonFiniteTests(unittest.TestCase):
    def test_encode_rejects_nan_header_field(self) -> None:
        header, _ = _header(sim_time=float("nan"))
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.encode_frame(header)
        self.assertEqual(caught.exception.code, "non_finite")

    def test_encode_rejects_inf_in_body(self) -> None:
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.encode_json_message("status", run_id="r", epoch=0, seq=0, tick=0,
                                      sim_time=0.0, body={"v": float("inf")})
        self.assertEqual(caught.exception.code, "non_finite")

    def test_decode_rejects_nan_literal(self) -> None:
        """json.loads 默认**接受** NaN（非法 JSON）——协议入口必须拒收。"""

        blob = b'{"a": NaN}'
        header, _ = _header(payload=blob)
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.decode_frame(proto.encode_frame(header, blob))
        self.assertEqual(caught.exception.code, "non_finite")

    def test_decode_rejects_infinity_literal_in_header(self) -> None:
        header, payload = _header()
        blob = json.dumps(header).replace('"sim_time": 0.24', '"sim_time": Infinity')
        blob = blob.encode("utf-8")
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.decode_frame(struct.pack(">I", len(blob)) + blob)
        self.assertEqual(caught.exception.code, "non_finite")
        self.assertEqual(payload, b"{}")


class SampleShapeTests(unittest.TestCase):
    def _sample(self, **kwargs):
        defaults = dict(run_id="r", epoch=0, seq=0, tick=1, sim_time=0.02,
                        instance_id="depth_left", output="policy_tensor",
                        validity="valid", source="measurement")
        defaults.update(kwargs)
        return proto.encode_sample(**defaults)

    def test_tensor_shape_must_match_payload_bytes(self) -> None:
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            self._sample(shape=[1, 2, 60, 86], dtype="f4", payload=b"\x00" * 64)
        self.assertEqual(caught.exception.code, "bad_sample")

    def test_tensor_round_trip_declares_shape_dtype(self) -> None:
        payload = b"\x00" * (4 * 60 * 86 * 2)
        frame = proto.decode_frame(
            self._sample(shape=[1, 2, 60, 86], dtype="f4", payload=payload)
        )
        self.assertEqual(frame.header["dtype"], "f4")
        self.assertEqual(frame.header["payload_bytes"], len(payload))
        self.assertEqual(frame.header["content_type"], proto.CONTENT_OCTET)
        self.assertEqual(list(frame.header["shape"]), [1, 2, 60, 86])

    def test_dtype_table_is_the_single_size_source(self) -> None:
        for dtype, size in proto.DTYPE_ITEMSIZE.items():
            payload = b"\x00" * size
            frame = proto.decode_frame(self._sample(shape=[1], dtype=dtype, payload=payload))
            self.assertEqual(frame.header["dtype"], dtype)
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            self._sample(shape=[4], dtype="f2", payload=b"\x00" * 8)
        self.assertEqual(caught.exception.code, "bad_sample")

    def test_zero_and_negative_dims_rejected(self) -> None:
        for shape in ([0], [1, -2]):
            with self.assertRaises(proto.ProtocolViolationError) as caught:
                self._sample(shape=shape, dtype="f4", payload=b"\x00" * 16)
            self.assertEqual(caught.exception.code, "bad_sample")

    def test_png_sample_carries_no_shape_and_requires_magic(self) -> None:
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 12
        frame = proto.decode_frame(
            self._sample(content_type=proto.CONTENT_PNG, payload=png)
        )
        self.assertIsNone(frame.header.get("shape"))
        self.assertIsNone(frame.header.get("dtype"))
        self.assertEqual(frame.header["content_type"], proto.CONTENT_PNG)
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            self._sample(content_type=proto.CONTENT_PNG, payload=b"not-a-png")
        self.assertEqual(caught.exception.code, "bad_sample")
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            self._sample(content_type=proto.CONTENT_PNG, shape=[4], dtype="u1", payload=png)
        self.assertEqual(caught.exception.code, "shape_conflict")

    def test_empty_validity_has_exactly_one_shape(self) -> None:
        """missing/stale/no_hit/disabled/unsupported/fault/dropped：只有 JSON 说明这一种形状。"""

        for validity in sorted(proto.SAMPLE_EMPTY_VALIDITIES):
            frame = proto.decode_frame(self._sample(validity=validity, note="说明文本"))
            self.assertEqual(frame.header["content_type"], proto.CONTENT_JSON)
            self.assertIsNone(frame.header.get("shape"))
            self.assertIsNone(frame.header.get("dtype"))
            self.assertEqual(frame.json_body()["validity"], validity)
            self.assertEqual(frame.json_body()["instance_id"], "depth_left")
            self.assertEqual(frame.json_body()["note"], "说明文本")
            with self.assertRaises(proto.ProtocolViolationError) as caught:
                self._sample(validity=validity, shape=[4], dtype="f4", payload=b"\x00" * 16)
            self.assertEqual(caught.exception.code, "shape_conflict")
            # 对端送来"无数据 + 二进制"这种自相矛盾的形状必须被拒
            header, payload = _header(type="sample", content_type=proto.CONTENT_OCTET,
                                      instance_id="i", output="o", validity=validity,
                                      source="measurement")
            with self.assertRaises(proto.ProtocolViolationError) as caught:
                proto.decode_frame(proto.encode_frame(header, payload))
            self.assertEqual(caught.exception.code, "shape_conflict")

    def test_source_vocabulary_is_three(self) -> None:
        for source in ("truth", "measurement", "estimate"):
            frame = proto.decode_frame(
                self._sample(source=source, shape=[2], dtype="f4", payload=b"\x00" * 8)
            )
            self.assertEqual(frame.header["source"], source)
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            self._sample(source="ground_truth", shape=[2], dtype="f4", payload=b"\x00" * 8)
        self.assertEqual(caught.exception.code, "bad_sample")

    def test_sample_identity_fields_are_mandatory(self) -> None:
        blob = self._sample(shape=[2], dtype="f4", payload=b"\x00" * 8)
        frame = proto.decode_frame(blob)
        for name in ("instance_id", "output", "validity", "source"):
            header = dict(frame.header)
            header.pop(name)
            with self.assertRaises(proto.ProtocolViolationError) as caught:
                proto.validate_header(header, frame.payload)
            self.assertEqual(caught.exception.code, "bad_sample", name)

    def test_sample_frame_header_matches_ws_stream_contract(self) -> None:
        """前端与管理器读同一份契约：**双向**相等，字段名不允许两处不同。"""

        import contracts.simulation_run_contract as rc

        blob = self._sample(shape=[2], dtype="f4", payload=b"\x00" * 8, unit="m",
                            reference_frame="camera", sample_tick=1, available_tick=5,
                            sample_seq=0)
        frame = proto.decode_frame(blob)
        contract = rc.ws_stream_contract()
        self.assertEqual(list(contract["frame_common_fields"]),
                         list(proto.FRAME_COMMON_FIELDS))
        declared = set(contract["frame_common_fields"]) | set(
            contract["sample_frame"]["header_extra"]
        )
        self.assertEqual(set(frame.header), declared)
        self.assertEqual(contract["payload_max_bytes"], proto.PAYLOAD_MAX_BYTES)
        self.assertEqual(contract["header_max_bytes"], proto.HEADER_MAX_BYTES)
        self.assertEqual(contract["framing"], proto.protocol_limits()["framing"])
        self.assertEqual(contract["message_types"], list(proto.MESSAGE_TYPES))
        self.assertEqual(contract["content_types"], list(proto.CONTENT_TYPES))
        self.assertEqual(sorted(contract["sample_frame"]["empty_validities"]),
                         sorted(proto.SAMPLE_EMPTY_VALIDITIES))
        self.assertEqual(contract["direction"], "downlink_only")

    def test_sample_envelope_and_header_share_vocabulary(self) -> None:
        """头里的样本字段与 :class:`SampleEnvelope` 一一对应（不留第二个名字）。"""

        import contracts.simulation_run_contract as rc

        fields = rc.SampleEnvelope.model_fields
        for name in ("instance_id", "output", "sample_tick", "available_tick", "shape",
                     "dtype", "unit", "reference_frame", "source", "validity",
                     "sample_seq"):
            self.assertIn(name, fields, f"样本头字段 {name} 在权威信封模型里没有对应")


class ControlChannelTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        line = proto.encode_control(kind="command", run_id="r", transaction_id="tx-1",
                                    expected_epoch=2, payload={"command": "pause"})
        row = proto.parse_control(line)
        self.assertEqual(row["kind"], "command")
        self.assertEqual(row["transaction_id"], "tx-1")
        self.assertEqual(row["expected_epoch"], 2)
        self.assertEqual(row["payload"], {"command": "pause"})
        self.assertEqual(row["v"], proto.PROTOCOL_VERSION)

    def test_jsonl_stream_skips_blank_lines(self) -> None:
        stream = io.StringIO(
            proto.encode_control(kind="shutdown", run_id="r", transaction_id="a",
                                 expected_epoch=0) + "\n"
            + "\n"
            + proto.encode_control(kind="event", run_id="r", transaction_id="b",
                                   expected_epoch=0, payload={"type": "wrench"}) + "\n"
        )
        rows = list(proto.iter_control(stream))
        self.assertEqual([row["transaction_id"] for row in rows], ["a", "b"])
        self.assertEqual([row["kind"] for row in rows], ["shutdown", "event"])

    def test_write_control_adapts_to_binary_stream(self) -> None:
        stream = io.BytesIO()
        text = proto.write_control(stream, kind="command", run_id="r",
                                   transaction_id="t", expected_epoch=0)
        self.assertEqual(stream.getvalue(), text.encode("utf-8"))
        self.assertEqual(proto.parse_control(stream.getvalue())["transaction_id"], "t")

    def test_unknown_kind_and_empty_transaction(self) -> None:
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.encode_control(kind="kill", run_id="r", transaction_id="t", expected_epoch=0)
        self.assertEqual(caught.exception.code, "unknown_kind")
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.encode_control(kind="command", run_id="r", transaction_id="", expected_epoch=0)
        self.assertEqual(caught.exception.code, "bad_control")
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.encode_control(kind="command", run_id="r", transaction_id="t",
                                 expected_epoch=-1)
        self.assertEqual(caught.exception.code, "bad_control")

    def test_log_line_in_control_channel_is_rejected(self) -> None:
        for bad in ("loaded model ok", "[]", '{"a":1}', ""):
            with self.assertRaises(proto.ProtocolViolationError):
                proto.parse_control(bad)

    def test_missing_field_and_version(self) -> None:
        row = {"v": proto.PROTOCOL_VERSION, "kind": "command", "run_id": "r",
               "expected_epoch": 0, "payload": {}}
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.parse_control(json.dumps(row))
        self.assertEqual(caught.exception.code, "missing_fields")
        row["transaction_id"] = "t"
        row["v"] = 99
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.parse_control(json.dumps(row))
        self.assertEqual(caught.exception.code, "version_mismatch")
        row["v"] = proto.PROTOCOL_VERSION
        row["kind"] = "restart"
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.parse_control(json.dumps(row))
        self.assertEqual(caught.exception.code, "unknown_kind")

    def test_control_rejects_non_finite(self) -> None:
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.encode_control(kind="command", run_id="r", transaction_id="t",
                                 expected_epoch=0, payload={"gain": float("nan")})
        self.assertEqual(caught.exception.code, "non_finite")

    def test_control_kinds_match_message_vocabulary(self) -> None:
        self.assertEqual(set(proto.CONTROL_KINDS), {"command", "event", "shutdown"})


class StreamOrderTests(unittest.TestCase):
    def _frame(self, *, epoch: int, seq: int) -> proto.Frame:
        return proto.decode_frame(
            proto.encode_json_message("status", run_id="r", epoch=epoch, seq=seq,
                                      tick=seq, sim_time=0.0, body={})
        )

    def test_gap_detected(self) -> None:
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.check_stream_order(self._frame(epoch=0, seq=2), self._frame(epoch=0, seq=0))
        self.assertEqual(caught.exception.code, "seq_gap")

    def test_epoch_advance_restarts_sequence(self) -> None:
        proto.check_stream_order(self._frame(epoch=1, seq=0), self._frame(epoch=0, seq=9))
        proto.check_stream_order(self._frame(epoch=0, seq=0), None)

    def test_epoch_regression_detected(self) -> None:
        with self.assertRaises(proto.ProtocolViolationError) as caught:
            proto.check_stream_order(self._frame(epoch=0, seq=0), self._frame(epoch=1, seq=3))
        self.assertEqual(caught.exception.code, "epoch_regression")

    def test_encoder_rejects_negative_start(self) -> None:
        with self.assertRaises(proto.ProtocolViolationError):
            proto.StreamEncoder(run_id="r", epoch=-1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
