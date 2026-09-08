"""最小 TensorBoard events 解析器（T2.2，批次 2 / M3）。

控制面不引入 tensorboard 依赖：本模块自包含实现 TFRecord 帧格式 +
Event/Summary protobuf 子集的解码（rsl_rl 写入的标量曲线只需要
Event{step, summary{value[{tag, simple_value}]}} 这一小块）。

wire 格式（tensorflow/core/util/event.proto）：
  Event.wall_time = 1 (double fixed64)
  Event.step      = 2 (varint int64)
  Event.summary   = 5 (message)
  Summary.value   = 1 (repeated message)
  Value.tag          = 1 (string)
  Value.simple_value = 2 (float fixed32)
TFRecord 帧：uint64 little-endian length + uint32 length_crc + data + uint32 data_crc。
CRC 校验在这里跳过（解析自产/受信文件，读取损坏时报错降级）。
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

_BUFF_SIZE = 16 * 1024 * 1024


def _read_varint(buf: memoryview, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if pos >= len(buf):
            raise ValueError("truncated varint")
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")


def _decode_message(buf: memoryview) -> dict[int, list[tuple[int, Any]]]:
    """protobuf wire → {field_number: [(wire_type, raw_value), ...]}。"""

    fields: dict[int, list[tuple[int, Any]]] = {}
    pos = 0
    while pos < len(buf):
        key, pos = _read_varint(buf, pos)
        field_number = key >> 3
        wire_type = key & 0x07
        if wire_type == 0:  # varint
            value, pos = _read_varint(buf, pos)
        elif wire_type == 1:  # fixed64
            value = bytes(buf[pos:pos + 8])
            pos += 8
        elif wire_type == 2:  # length-delimited
            length, pos = _read_varint(buf, pos)
            value = bytes(buf[pos:pos + length])
            pos += length
        elif wire_type == 5:  # fixed32
            value = bytes(buf[pos:pos + 4])
            pos += 4
        else:
            raise ValueError(f"unsupported wire type {wire_type}")
        fields.setdefault(field_number, []).append((wire_type, value))
    return fields


def _decode_string(raw: Any) -> str:
    return raw.decode("utf-8", errors="replace")


def parse_events_file(path: Path) -> dict[str, list[tuple[int, float]]]:
    """events.out.tfevents 文件 → {tag: [(step, value), ...]}（按出现顺序）。"""

    series: dict[str, list[tuple[int, float]]] = {}
    data = Path(path).read_bytes()
    view = memoryview(data)
    pos = 0
    while pos + 12 <= len(view):
        (length,) = struct.unpack_from("<Q", view, pos)
        pos += 12  # length + length_crc
        if pos + length + 4 > len(view):
            break
        record = view[pos:pos + length]
        pos += length + 4  # data + data_crc
        try:
            event = _decode_message(record)
        except ValueError:
            continue
        if 5 not in event:  # 只关心 summary
            continue
        (summary_wire, summary_raw) = event[5][0]
        if summary_wire != 2:
            continue
        summary = _decode_message(memoryview(summary_raw))
        for _wire, value_raw in summary.get(1, []):
            value_fields = _decode_message(memoryview(value_raw))
            tag_field = value_fields.get(1)
            simple = value_fields.get(2)
            if not tag_field or not simple:
                continue
            tag = _decode_string(tag_field[0][1])
            (step,) = struct.unpack("<q", struct.pack("<Q", event.get(2, [(0, 0)])[0][1] & 0xFFFFFFFFFFFFFFFF)) if 2 in event else (0,)
            (value,) = struct.unpack("<f", simple[0][1])
            series.setdefault(tag, []).append((step, float(value)))
    return series


def iter_series_terms(series: dict[str, list[tuple[int, float]]]) -> dict[str, list[tuple[int, float]]]:
    """rsl_rl 标量键（Episode/rew_xxx 等）原样透传；过滤空序列。"""

    return {tag: points for tag, points in series.items() if points}
