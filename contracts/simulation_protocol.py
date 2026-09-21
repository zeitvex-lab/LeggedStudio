"""高级仿真的**线协议**：有版本的 JSONL 控制通道 + 长度定界遥测封包通道。

为什么要有这个模块
------------------
原生 MuJoCo 高级执行器（worker）与控制面（manager）之间要传两类完全不同性质的数据：

* **控制**（manager → worker）：低频、人可读、要能一行一行落审计日志 ⇒ **JSONL**（一行一条）；
* **遥测**（worker → manager）：高频、含张量与 PNG 二进制 ⇒ **长度定界帧**（JSON 头 + 原始字节载荷）。

把这两类**混在一个文本通道**里（历史做法：把观测 ``print`` 成 JSON 行）会同时失去两样东西：
二进制进不去（PNG/float32 深度只能 base64，带宽与内存双倍），以及**日志与协议无法区分** ——
一句 ``print("loaded model")`` 就变成一条坏消息。本模块把边界钉死：

* **stdout 只走协议**（帧或控制行），任何非协议字节都必须报错而不是被跳过；
* **stderr 只走日志**，不参与本模块的任何解析。

单一形状纪律（不留多个互相竞争的形状）
--------------------------------------
每条帧**头**都带同一组公共字段（:data:`FRAME_COMMON_FIELDS`），载荷语义只由 ``content_type``
决定，共三种、互不重叠：

======================  ==========================================  ==============================
``content_type``         载荷                                       允许的 ``type``
======================  ==========================================  ==============================
``application/json``     UTF-8 JSON 对象（消息 body 整体在这里）      除 ``sample`` 外全部
``application/octet``    C 连续张量字节（形状/类型在头里）            仅 ``sample``（``validity=valid``）
``image/png``            PNG 原始字节（**不**在头里重复 shape/dtype） 仅 ``sample``（``validity=valid``）
======================  ==========================================  ==============================

**无数据的样本**（missing / stale / no_hit / disabled / unsupported / fault）用
``content_type=application/json`` + ``type=sample`` + **空 shape/dtype** 表达 —— 它是该样本
唯一的一种形状，不存在"既可以是内联 JSON 也可以是分离字段"的歧义。

seq 由谁负责
------------
``seq`` 是**整条 worker→manager 流的帧号**，不是每个生产者各数一份。所以发射端用
:class:`StreamEncoder`（持有 epoch 与计数器），接收端用 :func:`check_stream_order` 校验逐 1 递增；
``epoch`` 变更后从 0 重来。这样"谁都能自己编一个 seq"的分支不存在。

前端与管理器共用同一份上限
--------------------------
浏览器（``web/sim2sim``）与管理器都必须拒绝超大头/超大载荷，两处上限一旦不同，
"一边收得下一边收不下"就会变成一个只能在线上复现的故障。所以上限由 :func:`protocol_limits`
单点导出，HTTP catalog 把它原样发给前端 —— **这里改一次，两边同时改**。
"""

from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "CONTENT_JSON",
    "CONTENT_OCTET",
    "CONTENT_PNG",
    "CONTENT_TYPES",
    "CONTROL_KINDS",
    "CONTROL_LINE_MAX_BYTES",
    "DTYPES",
    "DTYPE_ITEMSIZE",
    "EMPTY_PAYLOAD_SHA256",
    "FRAME_COMMON_FIELDS",
    "HEADER_MAX_BYTES",
    "MESSAGE_TYPES",
    "PAYLOAD_MAX_BYTES",
    "PAYLOAD_SHA256_HEX_LEN",
    "PROTOCOL_NAME",
    "PROTOCOL_VERSION",
    "SAMPLE_EMPTY_VALIDITIES",
    "Frame",
    "ProtocolTruncatedError",
    "ProtocolViolationError",
    "StreamEncoder",
    "check_stream_order",
    "decode_frame",
    "encode_control",
    "encode_frame",
    "encode_json_message",
    "encode_sample",
    "iter_control",
    "iter_frames",
    "parse_control",
    "parse_json_payload",
    "payload_checksum",
    "payload_is_png",
    "protocol_limits",
    "read_frame",
    "validate_header",
    "write_control",
    "write_frame",
]

# --------------------------------------------------------------------------------------
# 版本与上限（**唯一真值**）
# --------------------------------------------------------------------------------------

#: 协议名。与 :data:`PROTOCOL_VERSION` 一起构成 ``lsim/1`` 这样的线格式标识。
PROTOCOL_NAME = "lsim"
#: 线格式版本。**不兼容改动必须升版本而不是加可选字段**，否则对端无法判断该怎么解。
PROTOCOL_VERSION = 1

#: 帧头（JSON 文本）最大字节数。头里只有元数据，16 KiB 足够描述 60×86×2 的张量。
HEADER_MAX_BYTES = 16 * 1024
#: 单帧载荷最大字节数。32 MiB 覆盖一张未压缩 4K RGBA 与一段深度历史（float32）。
PAYLOAD_MAX_BYTES = 32 * 1024 * 1024
#: 一条控制行（不含换行）最大字节数。控制是低频小对象；超限说明有人想把数据塞进控制通道。
CONTROL_LINE_MAX_BYTES = 64 * 1024
#: ``payload_sha256`` 的十六进制串长度。
PAYLOAD_SHA256_HEX_LEN = 64

#: 帧头里表示版本的字段名（值为整数 :data:`PROTOCOL_VERSION`，由编码端强制写入）。
FRAME_HEADER_VERSION_FIELD = "v"

#: 每条帧头都必须存在的公共字段。缺任何一个即协议违规（不做"尽力解析"）。
FRAME_COMMON_FIELDS: tuple[str, ...] = (
    "v",
    "type",
    "run_id",
    "epoch",
    "seq",
    "tick",
    "sim_time",
    "content_type",
    "payload_bytes",
    "payload_sha256",
)

# --------------------------------------------------------------------------------------
# 消息词汇（**不留多个竞争形状**）
# --------------------------------------------------------------------------------------

#: worker → manager 的全部帧类型。body 的字段形状由
#: :mod:`contracts.simulation_run_contract` 的模型定义（本模块不复制字段清单）。
MESSAGE_TYPES: tuple[str, ...] = (
    "hello",           # RunHandshake：runtime 版本、能力、时间基
    "status",          # RunSnapshot（状态快照；同一时刻只有一份，最新的覆盖旧的）
    "event",           # RunEvent（离散事件：命令注入、传感器故障、终止）
    "sample",          # SampleEnvelope 的样本帧（张量 / PNG / 空数据说明）
    "command_result",  # RunCommandResponse（对某 transaction_id 的答复；幂等回放同形）
    "error",           # RunError（协议/运行错误）
    "bye",             # RunFinal（收尾：最终统计、episode_id、记录清单引用）
)

#: manager → worker 的控制行种类。``command`` = 运行控制（启停/单步/设指令），
#: ``event`` = 注入一个排程事件，``shutdown`` = 有序退出。
CONTROL_KINDS: tuple[str, ...] = ("command", "event", "shutdown")

CONTENT_JSON = "application/json"
CONTENT_OCTET = "application/octet-stream"
CONTENT_PNG = "image/png"
CONTENT_TYPES: tuple[str, ...] = (CONTENT_JSON, CONTENT_OCTET, CONTENT_PNG)

#: 张量元素类型码（numpy 小端记法）→ 单元素字节数。**只有这一份** dtype→size 表；
#: :mod:`contracts.simulation_run_contract` 也用它校验 ``payload_bytes`` 与形状自洽。
DTYPE_ITEMSIZE: dict[str, int] = {
    "f4": 4,
    "f8": 8,
    "i1": 1,
    "i2": 2,
    "i4": 4,
    "i8": 8,
    "u1": 1,
    "u2": 2,
    "u4": 4,
    "u8": 8,
    "b1": 1,
}
DTYPES: tuple[str, ...] = tuple(DTYPE_ITEMSIZE)

#: 样本"没有数据"的有效性（与 :data:`contracts.simulation_run_contract.SAMPLE_VALIDITY` 的
#: 无效子集一致）：这些情况下载荷必须为空，且头里**不带** shape/dtype。
SAMPLE_EMPTY_VALIDITIES: frozenset[str] = frozenset(
    {"missing", "stale", "no_hit", "disabled", "unsupported", "fault", "dropped"}
)

_HEADER_LEN_STRUCT = struct.Struct(">I")
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


# --------------------------------------------------------------------------------------
# 异常
# --------------------------------------------------------------------------------------


class ProtocolViolationError(ValueError):
    """流上出现**不符合协议**的字节（坏头、未知类型、超限、缺字段、seq 倒退）。

    带 ``code`` 是为了让管理器映射成稳定错误码（前端据此提示），而不是靠读异常文本。
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code


class ProtocolTruncatedError(ProtocolViolationError):
    """帧在 ``header_len`` / 载荷中途结束（进程被杀、管道关闭、写了一半）。"""

    def __init__(self, message: str, *, wanted: int, got: int) -> None:
        super().__init__("truncated", f"{message}（期望 {wanted} 字节，实得 {got}）")
        self.wanted = wanted
        self.got = got


# --------------------------------------------------------------------------------------
# 严格 JSON / 摘要原语
# --------------------------------------------------------------------------------------


def _reject_constant(token: str) -> float:
    """拒绝 ``NaN`` / ``Infinity`` / ``-Infinity``：协议里**不允许**非有限浮点。

    ``json.dumps`` 会静默写出 ``NaN``（非法 JSON），``json.loads`` 又会静默接受它 ——
    一个非有限的 ``sim_time`` 会污染所有下游时序统计，所以在这唯一入口处直接判失败。
    """

    raise ProtocolViolationError("non_finite", f"协议不允许非有限数值字面量：{token!r}")


def payload_checksum(payload: bytes) -> str:
    """载荷摘要（**原始字节**，不做行尾归一）。

    这里必须是裸 sha256：载荷是 PNG / 张量字节，任何 CRLF 归一都会改坏图像。
    落盘工件的归一摘要口径（``contracts.validator.normalized_sha256``）是另一件事，
    两者不能混用同一个函数。
    """

    digest = hashlib.sha256(payload)
    return digest.hexdigest()


#: 空载荷的固定摘要（解码器可据此快速判定"无数据"帧）。
EMPTY_PAYLOAD_SHA256 = payload_checksum(b"")


def payload_is_png(payload: bytes) -> bool:
    return payload.startswith(_PNG_MAGIC)


def parse_json_payload(payload: bytes) -> Any:
    """严格解析 JSON 载荷（拒 NaN/Infinity、拒非 UTF-8）。"""

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProtocolViolationError("bad_header", f"JSON 载荷非 UTF-8：{exc}") from exc
    try:
        return json.loads(text, parse_constant=_reject_constant)
    except ProtocolViolationError:
        raise
    except json.JSONDecodeError as exc:
        raise ProtocolViolationError("bad_header", f"JSON 载荷不可解析：{exc.msg}") from exc


# --------------------------------------------------------------------------------------
# 头校验
# --------------------------------------------------------------------------------------


def validate_header(header: Mapping[str, Any], payload: bytes = b"") -> None:
    """校验头字段集合、类型，以及"头声明 == 实际载荷"。违规抛 :class:`ProtocolViolationError`。"""

    if not isinstance(header, Mapping):
        raise ProtocolViolationError(
            "bad_header", f"帧头必须是 JSON 对象，实为 {type(header).__name__}"
        )
    missing = [name for name in FRAME_COMMON_FIELDS if name not in header]
    if missing:
        raise ProtocolViolationError("missing_fields", f"帧头缺必备字段：{missing}")

    version = header["v"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise ProtocolViolationError("bad_header", f"字段 v 必须是整数，实为 {version!r}")
    if version != PROTOCOL_VERSION:
        raise ProtocolViolationError(
            "version_mismatch", f"协议版本不匹配：线上 {version}，本端 {PROTOCOL_VERSION}"
        )

    message_type = header["type"]
    if message_type not in MESSAGE_TYPES:
        raise ProtocolViolationError("unknown_type", f"未知消息类型：{message_type!r}")

    content_type = header["content_type"]
    if content_type not in CONTENT_TYPES:
        raise ProtocolViolationError("unknown_content", f"未知 content_type：{content_type!r}")
    if message_type != "sample" and content_type != CONTENT_JSON:
        raise ProtocolViolationError(
            "shape_conflict",
            f"非 sample 消息的 content_type 必须是 {CONTENT_JSON}，实为 {content_type!r}",
        )

    for name in ("epoch", "seq", "tick"):
        value = header[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ProtocolViolationError("bad_header", f"字段 {name} 必须是非负整数，实为 {value!r}")
    sim_time = header["sim_time"]
    if isinstance(sim_time, bool) or not isinstance(sim_time, (int, float)) or sim_time < 0:
        raise ProtocolViolationError("bad_header", f"sim_time 必须非负有限，实为 {sim_time!r}")

    run_id = header["run_id"]
    if not isinstance(run_id, str) or not run_id:
        raise ProtocolViolationError("bad_header", f"run_id 必须是非空字符串，实为 {run_id!r}")

    declared = header["payload_bytes"]
    if isinstance(declared, bool) or not isinstance(declared, int) or declared < 0:
        raise ProtocolViolationError("bad_header", f"payload_bytes 非法：{declared!r}")
    if declared > PAYLOAD_MAX_BYTES:
        raise ProtocolViolationError(
            "payload_too_large", f"载荷上限 {PAYLOAD_MAX_BYTES}，声明 {declared}"
        )
    if declared != len(payload):
        raise ProtocolViolationError(
            "payload_length", f"头声明 {declared} 字节，实际载荷 {len(payload)} 字节"
        )

    digest = header["payload_sha256"]
    if not isinstance(digest, str) or len(digest) != PAYLOAD_SHA256_HEX_LEN:
        raise ProtocolViolationError(
            "bad_header", f"payload_sha256 必须是 {PAYLOAD_SHA256_HEX_LEN} 位十六进制串"
        )
    if digest != payload_checksum(payload):
        raise ProtocolViolationError("checksum", "载荷摘要与头声明不符（传输已损坏）")

    if message_type == "sample":
        _validate_sample_header(header, content_type=content_type, payload=payload)
    elif payload:
        body = parse_json_payload(payload)
        if not isinstance(body, dict):
            raise ProtocolViolationError("bad_header", "JSON 消息的载荷必须是对象")


def _validate_sample_header(
    header: Mapping[str, Any], *, content_type: str, payload: bytes
) -> None:
    """``sample`` 头的附加规则：实例/输出/有效性/来源，以及形状与载荷字节严格自洽。"""

    for name in ("instance_id", "output", "validity", "source"):
        value = header.get(name)
        if not isinstance(value, str) or not value:
            raise ProtocolViolationError("bad_sample", f"sample 头字段 {name} 缺失或为空")
    if header["source"] not in ("truth", "measurement", "estimate"):
        raise ProtocolViolationError(
            "bad_sample",
            f"sample.source 必须是 truth/measurement/estimate，实为 {header['source']!r}",
        )
    validity = header["validity"]
    empty_data = validity in SAMPLE_EMPTY_VALIDITIES

    if empty_data:
        # 无数据的样本只有一种形状：JSON 说明载荷（可空），且**不带** shape/dtype。
        if content_type != CONTENT_JSON:
            raise ProtocolViolationError(
                "shape_conflict",
                f"validity={validity} 的样本必须用 content_type={CONTENT_JSON}（没有二进制可传）",
            )
        if header.get("shape") is not None or header.get("dtype") is not None:
            raise ProtocolViolationError(
                "shape_conflict", f"validity={validity} 的样本不得声明 shape/dtype（没有数据）"
            )
        return

    if content_type == CONTENT_OCTET:
        shape = header.get("shape")
        dtype = header.get("dtype")
        if not isinstance(shape, list) or not shape or any(
            isinstance(dim, bool) or not isinstance(dim, int) or dim <= 0 for dim in shape
        ):
            raise ProtocolViolationError("bad_sample", f"sample.shape 必须是正整数列表，实为 {shape!r}")
        if dtype not in DTYPE_ITEMSIZE:
            raise ProtocolViolationError("bad_sample", f"sample.dtype 未知：{dtype!r}")
        expected = DTYPE_ITEMSIZE[str(dtype)]
        for dim in shape:
            expected *= int(dim)
        if header["payload_bytes"] != expected:
            raise ProtocolViolationError(
                "bad_sample", f"形状/类型算出 {expected} 字节，载荷实为 {header['payload_bytes']}"
            )
    elif content_type == CONTENT_PNG:
        if header.get("shape") is not None or header.get("dtype") is not None:
            raise ProtocolViolationError(
                "shape_conflict", "PNG 样本不在头里重复 shape/dtype（以 PNG 自身为准）"
            )
        if not payload_is_png(payload):
            raise ProtocolViolationError("bad_sample", "声明 image/png 但载荷没有 PNG 魔术字节")
    else:
        raise ProtocolViolationError(
            "shape_conflict", f"有效样本的载荷必须是张量或 PNG，实为 {content_type!r}"
        )


# --------------------------------------------------------------------------------------
# 帧
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Frame:
    """一条已校验的遥测帧。``header`` 原样保留（便于直接转发前端），``payload`` 是原始字节。"""

    header: Mapping[str, Any]
    payload: bytes

    @property
    def type(self) -> str:
        return str(self.header["type"])

    @property
    def seq(self) -> int:
        return int(self.header["seq"])

    @property
    def epoch(self) -> int:
        return int(self.header["epoch"])

    @property
    def tick(self) -> int:
        return int(self.header["tick"])

    @property
    def is_sample(self) -> bool:
        return self.type == "sample"

    def json_body(self) -> dict[str, Any]:
        """取出 JSON 载荷（含样本的"无数据"说明）。非 JSON 内容即协议违规。"""

        if self.header["content_type"] != CONTENT_JSON:
            raise ProtocolViolationError(
                "shape_conflict",
                f"content_type={self.header['content_type']} 的帧没有 JSON body",
            )
        body = parse_json_payload(self.payload)
        if not isinstance(body, dict):
            raise ProtocolViolationError("bad_header", "JSON 载荷必须是对象")
        return body


def encode_frame(header: Mapping[str, Any], payload: bytes = b"") -> bytes:
    """把（头, 载荷）编成一条帧：``4B 头长(大端) | 头 JSON | 载荷原始字节``。

    ``v`` / ``payload_bytes`` / ``payload_sha256`` 由本函数强制写入 ⇒ 调用方不可能"忘了算摘要"
    或"版本忘了升"。
    """

    return _encode_frame_parts(header, payload)[1]


def _encode_frame_parts(
    header: Mapping[str, Any], payload: bytes, *, validate: bool = False
) -> tuple[Frame, bytes]:
    """统一生成线上头与字节；生产发送入口在写出前复用接收端校验。"""

    if len(payload) > PAYLOAD_MAX_BYTES:
        raise ProtocolViolationError(
            "payload_too_large", f"载荷上限 {PAYLOAD_MAX_BYTES}，实为 {len(payload)}"
        )
    merged = dict(header)
    merged[FRAME_HEADER_VERSION_FIELD] = PROTOCOL_VERSION
    merged["payload_bytes"] = len(payload)
    merged["payload_sha256"] = payload_checksum(payload)
    try:
        text = json.dumps(merged, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except ValueError as exc:  # allow_nan=False 命中非有限值
        raise ProtocolViolationError("non_finite", f"帧头含非有限数值：{exc}") from exc
    blob = text.encode("utf-8")
    if len(blob) > HEADER_MAX_BYTES:
        raise ProtocolViolationError(
            "header_too_large", f"帧头上限 {HEADER_MAX_BYTES}，实为 {len(blob)} 字节"
        )
    if validate:
        validate_header(merged, payload)
    return Frame(header=merged, payload=payload), _HEADER_LEN_STRUCT.pack(len(blob)) + blob + payload


def _decode_header(blob: bytes) -> dict[str, Any]:
    if len(blob) > HEADER_MAX_BYTES:  # 防御：绕过 length 校验的调用方
        raise ProtocolViolationError(
            "header_too_large", f"帧头上限 {HEADER_MAX_BYTES}，实为 {len(blob)} 字节"
        )
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProtocolViolationError(
            "bad_header", f"帧头非 UTF-8（疑似日志混入协议流）：{exc}"
        ) from exc
    try:
        header = json.loads(text, parse_constant=_reject_constant)
    except ProtocolViolationError:
        raise
    except json.JSONDecodeError as exc:
        raise ProtocolViolationError(
            "bad_header", f"帧头不是 JSON 对象（疑似日志混入协议流）：{exc.msg}"
        ) from exc
    if not isinstance(header, dict):
        raise ProtocolViolationError("bad_header", "帧头必须是 JSON 对象")
    return header


def decode_frame(raw: bytes) -> Frame:
    """从**完整**帧字节解码（含 4 字节定界前缀）。用于已有整块缓冲的场景（WebSocket 消息）。"""

    if len(raw) < _HEADER_LEN_STRUCT.size:
        raise ProtocolTruncatedError(
            "帧头长度字段不完整", wanted=_HEADER_LEN_STRUCT.size, got=len(raw)
        )
    header_len = _HEADER_LEN_STRUCT.unpack_from(raw, 0)[0]
    if header_len > HEADER_MAX_BYTES:
        raise ProtocolViolationError(
            "header_too_large", f"声明头长 {header_len} 超过上限 {HEADER_MAX_BYTES}"
        )
    end = _HEADER_LEN_STRUCT.size + header_len
    if len(raw) < end:
        raise ProtocolTruncatedError("帧头被截断", wanted=end, got=len(raw))
    header = _decode_header(raw[_HEADER_LEN_STRUCT.size : end])
    validate_header(header, raw[end:])
    return Frame(header=header, payload=raw[end:])


def _read_exact(stream: Any, size: int, *, what: str, eof_ok: bool = False) -> bytes | None:
    if size == 0:
        return b""
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        part = stream.read(remaining)
        if not part:
            got = size - remaining
            if got == 0 and eof_ok:
                return None
            raise ProtocolTruncatedError(f"{what}读取中断", wanted=size, got=got)
        if not isinstance(part, (bytes, bytearray)):
            raise ProtocolViolationError(
                "bad_stream", f"{what}：遥测帧流必须是二进制流，实为文本流（请用 buffer）"
            )
        chunks.append(bytes(part))
        remaining -= len(part)
    return b"".join(chunks)


def read_frame(stream: Any) -> Frame | None:
    """从二进制流读一帧；**干净 EOF 返回 ``None``**，半帧抛 :class:`ProtocolTruncatedError`。

    长度定界协议**无法重同步**：读满头长后载荷不足即判截断，不返回"部分帧"、不猜边界 ——
    静默跳过一帧会让之后每一帧都错位，比立刻报错糟得多。
    """

    prefix = _read_exact(stream, _HEADER_LEN_STRUCT.size, what="帧头长度字段", eof_ok=True)
    if prefix is None:
        return None
    header_len = _HEADER_LEN_STRUCT.unpack(prefix)[0]
    if header_len > HEADER_MAX_BYTES:
        raise ProtocolViolationError(
            "header_too_large", f"声明头长 {header_len} 超过上限 {HEADER_MAX_BYTES}"
        )
    header = _decode_header(_read_exact(stream, header_len, what="帧头") or b"")
    declared = header.get("payload_bytes")
    if isinstance(declared, bool) or not isinstance(declared, int) or declared < 0:
        raise ProtocolViolationError("bad_header", f"payload_bytes 非法：{declared!r}")
    if declared > PAYLOAD_MAX_BYTES:
        raise ProtocolViolationError(
            "payload_too_large", f"声明载荷 {declared} 字节超过上限 {PAYLOAD_MAX_BYTES}"
        )
    payload = _read_exact(stream, declared, what="载荷") or b""
    validate_header(header, payload)
    return Frame(header=header, payload=payload)


def write_frame(stream: Any, header: Mapping[str, Any], payload: bytes = b"") -> Frame:
    """编码并写入一帧。``flush`` 由调用方按批处理策略决定（避免每帧一次系统调用）。"""

    frame, raw = _encode_frame_parts(header, payload, validate=True)
    stream.write(raw)
    return frame


def iter_frames(stream: Any) -> Iterator[Frame]:
    """逐帧迭代到干净 EOF。截断/违规原样抛（不静默结束迭代）。"""

    while True:
        frame = read_frame(stream)
        if frame is None:
            return
        yield frame


def check_stream_order(frame: Frame, previous: Frame | None) -> None:
    """同一条流上 ``seq`` 必须逐 1 递增；``epoch`` 变更则从新序列开始。

    背压丢帧在真实管道里会发生，所以这里**报错但不重同步**：管理器据此判定"这条流不可信"
    并要求重连（重连后 epoch 递增，序列重新开始）。
    """

    if previous is None:
        return
    if frame.epoch != previous.epoch:
        if frame.epoch < previous.epoch:
            raise ProtocolViolationError(
                "epoch_regression", f"epoch 倒退：{previous.epoch} → {frame.epoch}"
            )
        return
    if frame.seq != previous.seq + 1:
        raise ProtocolViolationError("seq_gap", f"seq 必须逐 1 递增：{previous.seq} → {frame.seq}")


# --------------------------------------------------------------------------------------
# 高层编码入口（**唯一构造点**）
# --------------------------------------------------------------------------------------


def _common_header(
    *, message_type: str, run_id: str, epoch: int, seq: int, tick: int, sim_time: float
) -> dict[str, Any]:
    return {
        "type": message_type,
        "run_id": run_id,
        "epoch": epoch,
        "seq": seq,
        "tick": tick,
        "sim_time": sim_time,
    }


def encode_json_message(
    message_type: str,
    *,
    run_id: str,
    epoch: int,
    seq: int,
    tick: int,
    sim_time: float,
    body: Mapping[str, Any] | None = None,
) -> bytes:
    """一条 JSON 消息（状态/事件/结果/握手/收尾）：body 只放载荷，**不并进头**。"""

    if message_type not in MESSAGE_TYPES or message_type == "sample":
        raise ProtocolViolationError("unknown_type", f"{message_type!r} 不是 JSON 消息类型")
    payload = _json_bytes(body or {})
    header = _common_header(
        message_type=message_type, run_id=run_id, epoch=epoch, seq=seq, tick=tick, sim_time=sim_time
    )
    header["content_type"] = CONTENT_JSON
    return encode_frame(header, payload)


def encode_sample(
    *,
    run_id: str,
    epoch: int,
    seq: int,
    tick: int,
    sim_time: float,
    instance_id: str,
    output: str,
    validity: str,
    source: str,
    payload: bytes = b"",
    content_type: str = CONTENT_OCTET,
    shape: list[int] | None = None,
    dtype: str | None = None,
    unit: str | None = None,
    reference_frame: str | None = None,
    sample_tick: int | None = None,
    available_tick: int | None = None,
    sample_seq: int | None = None,
    note: str | None = None,
) -> bytes:
    """一条样本帧。张量给 ``shape``/``dtype``；PNG 两者都必须省略；"无数据"的有效性由
    :func:`_apply_sample_validity` 归一成 **JSON 说明载荷**这一种形状（不带二进制）。"""

    header = _common_header(
        message_type="sample", run_id=run_id, epoch=epoch, seq=seq, tick=tick, sim_time=sim_time
    )
    header.update(
        {
            "instance_id": instance_id,
            "output": output,
            "validity": validity,
            "source": source,
        }
    )
    content, body = _apply_sample_validity(
        header, content_type=content_type, shape=shape, dtype=dtype, payload=payload, note=note
    )
    if unit is not None:
        header["unit"] = unit
    if reference_frame is not None:
        # 字段名与 :class:`contracts.simulation_run_contract.SampleEnvelope.reference_frame`
        # 以及 WS 契约的 ``sample_frame.header_extra`` **逐字一致**：头里出现 ``frame``
        # 而信封里叫 ``reference_frame``，前端就会两处猜一处。
        header["reference_frame"] = reference_frame
    if sample_tick is not None:
        header["sample_tick"] = sample_tick
    if available_tick is not None:
        header["available_tick"] = available_tick
    if sample_seq is not None:
        header["sample_seq"] = sample_seq
    header["content_type"] = content
    return _encode_frame_parts(header, body, validate=True)[1]


def _apply_sample_validity(
    header: dict[str, Any],
    *,
    content_type: str,
    shape: list[int] | None,
    dtype: str | None,
    payload: bytes,
    note: str | None,
) -> tuple[str, bytes]:
    """把"无数据"的有效性统一成 JSON 说明帧，并拒绝调用方夹带二进制/形状。

    返回真正写进头的 ``(content_type, 载荷)``。统一在这里做，是为了让发射端不可能造出
    "validity=stale 但带 5KB 张量"这种自相矛盾的形状。
    """

    validity = header["validity"]
    if validity in SAMPLE_EMPTY_VALIDITIES:
        if payload or shape is not None or dtype is not None:
            raise ProtocolViolationError(
                "shape_conflict", f"validity={validity} 的样本不得携带载荷或 shape/dtype"
            )
        body: dict[str, Any] = {"validity": validity, "instance_id": header["instance_id"]}
        if note:
            body["note"] = note
        return CONTENT_JSON, _json_bytes(body)
    if content_type == CONTENT_PNG:
        if shape is not None or dtype is not None:
            raise ProtocolViolationError("shape_conflict", "PNG 样本不得在头里重复 shape/dtype")
    elif shape is None or dtype is None:
        raise ProtocolViolationError("bad_sample", "有效张量样本必须同时给 shape 与 dtype")
    else:
        header["shape"] = list(shape)
        header["dtype"] = str(dtype)
    return content_type, payload


def _json_bytes(body: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(body), ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")
    except ValueError as exc:
        raise ProtocolViolationError("non_finite", f"载荷含非有限数值：{exc}") from exc


class StreamEncoder:
    """一条 worker→manager 流的**帧号权威**（seq 逐 1 递增，epoch 变更即重置）。

    使用它而不是各处手写 ``seq=...``：状态帧、样本帧、事件帧共用同一个计数器，
    接收端的 :func:`check_stream_order` 才有意义。
    """

    def __init__(self, *, run_id: str, epoch: int = 0, seq: int = 0) -> None:
        if epoch < 0 or seq < 0:
            raise ProtocolViolationError("bad_header", "epoch/seq 必须非负")
        self.run_id = run_id
        self.epoch = epoch
        self._seq = seq

    @property
    def next_seq(self) -> int:
        return self._seq

    def _take(self) -> int:
        value = self._seq
        self._seq += 1
        return value

    def json_message(
        self,
        message_type: str,
        *,
        tick: int,
        sim_time: float,
        body: Mapping[str, Any] | None = None,
    ) -> bytes:
        return encode_json_message(
            message_type,
            run_id=self.run_id,
            epoch=self.epoch,
            seq=self._take(),
            tick=tick,
            sim_time=sim_time,
            body=body,
        )

    def sample(self, **kwargs: Any) -> bytes:
        kwargs.pop("seq", None)
        kwargs["run_id"] = self.run_id
        kwargs["epoch"] = self.epoch
        kwargs["seq"] = self._take()
        return encode_sample(**kwargs)


# --------------------------------------------------------------------------------------
# 控制通道（manager → worker，JSONL）
# --------------------------------------------------------------------------------------


def encode_control(
    *,
    kind: str,
    run_id: str,
    transaction_id: str,
    expected_epoch: int,
    payload: Mapping[str, Any] | None = None,
) -> str:
    """一条控制行（**不含**换行）。``transaction_id`` 全局唯一 ⇒ 幂等回放有依据。"""

    if kind not in CONTROL_KINDS:
        raise ProtocolViolationError("unknown_kind", f"未知控制种类：{kind!r}")
    if expected_epoch < 0:
        raise ProtocolViolationError("bad_control", "expected_epoch 必须非负")
    if not transaction_id:
        raise ProtocolViolationError("bad_control", "transaction_id 不能为空")
    try:
        line = json.dumps(
            {
                "v": PROTOCOL_VERSION,
                "kind": kind,
                "run_id": run_id,
                "transaction_id": transaction_id,
                "expected_epoch": expected_epoch,
                "payload": dict(payload or {}),
            },
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    except ValueError as exc:
        raise ProtocolViolationError("non_finite", f"控制行含非有限数值：{exc}") from exc
    if len(line.encode("utf-8")) > CONTROL_LINE_MAX_BYTES:
        raise ProtocolViolationError(
            "control_too_large", f"控制行上限 {CONTROL_LINE_MAX_BYTES} 字节，实为 {len(line.encode('utf-8'))}"
        )
    return line


def parse_control(line: str | bytes) -> dict[str, Any]:
    """解析一条控制行（严格：非对象 / 缺字段 / NaN / 版本不符都判违规）。"""

    if isinstance(line, (bytes, bytearray)):
        try:
            line = bytes(line).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolViolationError("bad_control", f"控制行非 UTF-8：{exc}") from exc
    text = line.strip()
    if not text:
        raise ProtocolViolationError("bad_control", "控制行为空")
    if len(text.encode("utf-8")) > CONTROL_LINE_MAX_BYTES:
        raise ProtocolViolationError(
            "control_too_large", f"控制行超过上限 {CONTROL_LINE_MAX_BYTES} 字节"
        )
    try:
        row = json.loads(text, parse_constant=_reject_constant)
    except ProtocolViolationError:
        raise
    except json.JSONDecodeError as exc:
        raise ProtocolViolationError(
            "bad_control", f"控制行不是 JSON 对象（疑似日志混入）：{exc.msg}"
        ) from exc
    if not isinstance(row, dict):
        raise ProtocolViolationError("bad_control", "控制行必须是 JSON 对象")
    for name in ("v", "kind", "run_id", "transaction_id", "expected_epoch", "payload"):
        if name not in row:
            raise ProtocolViolationError("missing_fields", f"控制行缺字段 {name}")
    if row["v"] != PROTOCOL_VERSION:
        raise ProtocolViolationError(
            "version_mismatch", f"控制协议版本不匹配：{row['v']} != {PROTOCOL_VERSION}"
        )
    if row["kind"] not in CONTROL_KINDS:
        raise ProtocolViolationError("unknown_kind", f"未知控制种类：{row['kind']!r}")
    if not isinstance(row["payload"], dict):
        raise ProtocolViolationError("bad_control", "payload 必须是对象")
    return row


def write_control(stream: Any, **kwargs: Any) -> str:
    """写一条控制行并补换行；自动适配文本/二进制流（**不猜**：不支持的流直接报错）。"""

    text = encode_control(**kwargs) + "\n"
    data = text.encode("utf-8")
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        buffer.write(data)
        return text
    try:
        stream.write(data)  # 已经是二进制流
    except TypeError:
        stream.write(text)  # 文本流
    return text


def iter_control(stream: Any) -> Iterator[dict[str, Any]]:
    """逐行读控制（接受文本或二进制流）。空行跳过（尾随换行不算消息）；坏行**报错不跳过**。"""

    for raw in stream:
        if not raw.strip():
            continue
        yield parse_control(raw)


# --------------------------------------------------------------------------------------
# 上限导出（前端与管理器同源）
# --------------------------------------------------------------------------------------


def protocol_limits() -> dict[str, Any]:
    """协议自我描述：HTTP catalog 原样转发给浏览器，前端据此设缓冲区与拒绝阈值。"""

    return {
        "name": PROTOCOL_NAME,
        "version": PROTOCOL_VERSION,
        "framing": "u32be_header_len|header_json|payload_bytes",
        "header_max_bytes": HEADER_MAX_BYTES,
        "payload_max_bytes": PAYLOAD_MAX_BYTES,
        "control_line_max_bytes": CONTROL_LINE_MAX_BYTES,
        "frame_common_fields": list(FRAME_COMMON_FIELDS),
        "message_types": list(MESSAGE_TYPES),
        "control_kinds": list(CONTROL_KINDS),
        "content_types": list(CONTENT_TYPES),
        "dtype_itemsize": dict(DTYPE_ITEMSIZE),
        "sample_empty_validities": sorted(SAMPLE_EMPTY_VALIDITIES),
    }
