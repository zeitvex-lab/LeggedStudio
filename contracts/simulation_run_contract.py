"""高级仿真的**运行契约**（v2）：解析后的不可变运行规格、样本信封、命令/事件、记录清单。

**本模块的边界（硬性）**
----------------------
* 只依赖标准库 + Pydantic v2 + 同目录的 ``contracts`` 模块；
  **不导入** MuJoCo、Torch、onnxruntime、FastAPI、运行引擎 —— 它是"数据形状"，
  控制面、worker、记录器、前端镜像都要能import它而不把重量级依赖拖进来。
* 全部模型 ``extra="forbid"`` + ``frozen=True``：拼错字段名必须报错，
  解析后的规格必须不可变（可变的"解析结果"会在中途被就地改掉，digest 就失去意义）。

为什么"解析后的规格"与"场景输入"是两个东西（**避免双真值**）
----------------------------------------------------------
``ScenarioContract`` 是**用户意图**（可以没有传感器实例、可以只写"我要深度"）；
:class:`ResolvedRunSpec` 是**机器决议**（每一项参数都有出处、每个资产都有摘要）。
两者共享的字段（时间基、传感器参数、策略输入形状）**只存在于运行规格里**，
Scenario 里出现的是"请求"而不是"值"。因此不存在"Scenario 写 106、规格写 86"这种
两边都有值、谁也不知道该信谁的局面 —— :attr:`ResolvedRunSpec.provenance` 会说明每个值从哪来。

口径（单位 / 四元数 / 坐标系）
------------------------------
* 长度 **米**、角度 **弧度**、力 **牛顿**、力矩 **牛·米**、频率 **Hz**；
* 姿态四元数一律 **``wxyz``**（MuJoCo / mjlab 口径，**不是** ROS 的 ``xyzw``）；
* 世界系：MuJoCo 惯例 **z 轴向上**、右手系；机体系以 ``base_link`` 原点为机髋中心；
  光机系（相机）为 **x 右、y 下、z 前**；
* 时间的唯一权威是**整数物理 tick**（:class:`RunTimeBase`），``sim_time`` 是导出量；
  频率永远写成"物理率 + 整数分频"，因为浮点周期会随步数累积漂移。
"""

from __future__ import annotations

import math
import posixpath
import re
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, AfterValidator, field_validator, model_validator

from contracts.sensor_plugin_contract import (
    CAPABILITY_LEVELS,  # 再导出：能力四级只有 :mod:`contracts.sensor_plugin_contract` 一处定义
    PLUGIN_CONTRACT_VERSION,
    SAFE_ID_PATTERN,
    LatencySpec,
    NoiseSpec,
    SensorPluginDefinition,
    command_provider_definition,
    plugin_catalog_payload,
    plugin_definition,
    provider_required_capabilities,
    required_capabilities,
)
from contracts.simulation_protocol import (
    DTYPE_ITEMSIZE,
    SAMPLE_EMPTY_VALIDITIES,
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    protocol_limits,
)
from contracts.validator import canonical_sha256

__all__ = [
    "ASSET_KINDS",
    "AssetRef",
    "CAPABILITY_LEVELS",
    "COORD_SYSTEM_DOC",
    "COMMAND_RESPONSE_CODES",
    "COMMAND_TYPES",
    "Capabilities",
    "CapabilityEntry",
    "ChunkMeta",
    "CreateRunRequest",
    "EpisodeManifest",
    "EpisodeManifestResponse",
    "EVENT_STATUSES",
    "EVENT_TYPES",
    "FiniteFloat",
    "NativeProbeReport",
    "OnnxTensorMeta",
    "ParamProvenance",
    "PolicyArtifactRef",
    "PolicyInputBinding",
    "QUAT_ORDER",
    "QuatWxyz",
    "RESOLUTION_BLOCKERS",
    "RUN_CONTRACT_VERSION",
    "RUN_END_REASONS",
    "RUN_ERROR_CODES",
    "RUN_STATUSES",
    "RECORDING_DIRECTORY_BUDGET_BYTES",
    "RECORDING_MIN_FREE_DISK_BYTES",
    "RECORDING_PER_RUN_BUDGET_BYTES",
    "RECORDING_QUEUE_BUDGET_BYTES",
    "RecordingChunkIndex",
    "RecordingFormats",
    "RecordingOptions",
    "ResolutionBlocker",
    "ResolutionBlockerCode",
    "ResolveOptions",
    "ResolveRequest",
    "ResolveResponse",
    "ResolvedRunSpec",
    "RunCatalogResponse",
    "RunCommand",
    "RunCommandResponse",
    "RunDetailResponse",
    "RunError",
    "RunEvent",
    "RunFinal",
    "RunHandshake",
    "RunSnapshot",
    "SAMPLE_VALIDITY",
    "SIM_API_VERSION",
    "STEP_UNITS",
    "ScheduledEvent",
    "ScheduledEventResponse",
    "SampleEnvelope",
    "SensorHealth",
    "SensorInstanceSpec",
    "NATIVE_EXECUTOR_ID",
    "NATIVE_RUNTIME_VERSION",
    "TERMINAL_RUN_STATUSES",
    "TRUTH_SOURCE_KINDS",
    "Units",
    "Vec3",
    "command_provider_spec_from",
    "safe_relative_path",
    "ws_stream_contract",
]

# --------------------------------------------------------------------------------------
# 版本与枚举
# --------------------------------------------------------------------------------------

#: 本运行契约的版本（进 :class:`ResolvedRunSpec.schema_version` 与 digest）。
RUN_CONTRACT_VERSION = "sim-run-contract-1.0"
#: HTTP 面版本。**新原生能力的路由前缀**，不复用旧 ``/api/simulation/sessions`` 词汇。
SIM_API_VERSION = "v2"

#: 原生执行器的稳定 id。**故意不叫 ``server_mujoco``**：旧执行器没有策略闭环，
#: 复用它会让前端以为"老的已经支持"（见 ``backend/executors.py`` 的 ``policy_inference: False``）。
NATIVE_EXECUTOR_ID = "native_mujoco"
#: worker/native 能力的独立版本标识（随实现推进而升，不冒称旧 server_mujoco 已具备）。
NATIVE_RUNTIME_VERSION = "native-mujoco-runtime/0.1"

#: 坐标/姿态口径的**唯一**文字描述（catalog、前端图例、记录 manifest 都引用这一份）。
COORD_SYSTEM_DOC = (
    "world: MuJoCo z-up right-handed, meters; body: base_link at hip origin; "
    "optical: x-right y-down z-forward. quat order = wxyz (scalar-first)."
)
#: 四元数分量顺序（防止有人按 ROS 习惯写 xyzw）。
QUAT_ORDER = "wxyz"

#: 资源类型的**唯一**声明处（``ASSET_KINDS`` 由它派生，避免"清单一份、字段一份"）。
AssetKind = Literal[
    "model_xml",
    "scene_xml",
    "mesh",
    "terrain_heightmap",
    "policy_onnx",
    "policy_contract",
    "robot_contract",
    "training_profile",
    "recording_manifest",
]
#: 允许的资产类型（只允许这些"包内相对路径"进入运行规格；任何绝对路径都拒绝）。
ASSET_KINDS: tuple[str, ...] = get_args(AssetKind)

#: 运行状态机（``draft → resolved → provisioning → ready → running ⇄ paused/stepping →
#: finishing → finalized``；``failed/aborted`` 为终态）。
RUN_STATUSES: tuple[str, ...] = (
    "draft",
    "resolved",
    "provisioning",
    "ready",
    "running",
    "paused",
    "stepping",
    "finishing",
    "finalized",
    "failed",
    "aborted",
)
#: 终态（进入后不接受任何运行控制命令，只允许读取）。
TERMINAL_RUN_STATUSES: frozenset[str] = frozenset({"finalized", "failed", "aborted"})

#: 单步单位。**只有两种**：物理 tick 与控制步（换算必须由时间基做，不接受浮点秒 —— 秒会累积漂移）。
STEP_UNITS: tuple[str, ...] = ("physics", "control")

#: 样本有效性（用户要求"缺失/过期/无命中/故障分开"，且各自主张不同的下游行为）。
#: ``valid``     有数据；
#: ``missing``   该到的样本没到（调度器超时）；
#: ``stale``     拿到了，但比当前 tick 老于允许年龄（不允许当新数据用）；
#: ``no_hit``    器件工作正常但环境无回波（雷达无命中 ≠ 故障）；
#: ``dropped``   因背压/预算被主动丢弃（记录侧，不是传感器侧）；
#: ``disabled``  实例被关掉（不是错误）；
#: ``unsupported`` 当前运行时不支持该插件（能力缺口，不是运行时故障）；
#: ``fault``     适配器抛错（真故障）。
SAMPLE_VALIDITY: tuple[str, ...] = (
    "valid",
    "missing",
    "stale",
    "no_hit",
    "dropped",
    "disabled",
    "unsupported",
    "fault",
)

#: 只有 ``valid`` 携带数据；其余都必须空载荷（与线协议同源，见 ``simulation_protocol``）。
SAMPLE_DATA_VALIDITIES: frozenset[str] = frozenset({"valid"})

#: 样本来源语义（与 :mod:`contracts.sensor_plugin_contract` 同一套词）。
TRUTH_SOURCE_KINDS: tuple[str, ...] = ("truth", "measurement", "estimate")

#: 运行控制命令类型（HTTP ``POST /runs/{id}/commands`` 与 WS 无关 —— 指令只走 HTTP，见 :func:`ws_stream_contract`）。
COMMAND_TYPES: tuple[str, ...] = (
    "start",
    "pause",
    "resume",
    "step",
    "set_command",
    "switch_policy",
    "set_recording",
    "abort",
)
#: 命令应答码。``duplicate`` 表示同一 ``transaction_id`` 重放，必须**原样回放首次结果**（幂等）。
COMMAND_RESPONSE_CODES: tuple[str, ...] = (
    "accepted",
    "duplicate",
    "stale_epoch",
    "invalid_state",
    "unknown_command",
    "rejected",
)

#: 注入事件类型（``POST /runs/{id}/events``）。
EVENT_TYPES: tuple[str, ...] = (
    "velocity_command",
    "wrench",
    "sensor_fault",
    "policy_switch",
    "run_control",
)
#: 事件处理结果。``skipped_stale_epoch`` 与 ``rejected`` 分开：前者是"过期，不是错"，
#: 后者是"这条事件本身不合法"。
EVENT_STATUSES: tuple[str, ...] = (
    "scheduled",
    "applied",
    "rejected",
    "skipped_stale_epoch",
    "failed",
)

#: 运行结束原因（**系统失败与策略/任务失败必须分开**，否则"策略摔了"和"worker 崩了"
#: 会共用同一个红色状态，评测结论就不可信）。
RUN_END_REASONS: tuple[str, ...] = (
    "user_abort",            # 人为终止（正常）
    "max_time",              # 场景时长跑满（正常）
    "target_reached",        # 任务目标达成（正常）
    "termination_condition", # 命中场景终止条件（任务侧失败）
    "fall",                  # 跌倒（任务侧失败）
    "policy_failure",        # 策略输出越界/NaN（任务侧失败，但归因策略）
    "recording_budget",      # 记录预算耗尽（系统侧，数据仍可用到最后一个 tick）
    "runtime_error",         # 运行时异常（系统侧）
    "asset_drift",           # resolve 后资产变了（系统侧，必须重解析）
    "protocol_violation",    # 线协议违规（系统侧，流不可信）
)
#: 属于"系统失败"的子集（前端显示为 blocked，不计入策略评测）。
SYSTEM_FAILURE_REASONS: frozenset[str] = frozenset(
    {"recording_budget", "runtime_error", "asset_drift", "protocol_violation"}
)

#: 阻断码（:class:`ResolutionBlocker.code` 的稳定词表；解析器与前端都按它分支，不读中文文本）。
#: 类型是**唯一**声明处，``RESOLUTION_BLOCKERS`` 由它派生（避免"清单一份、字段一份"）。
ResolutionBlockerCode = Literal[
    "unknown_robot",
    "unknown_policy",
    "unknown_plugin",
    "unknown_provider",
    "package_missing",
    "capability_missing",
    "asset_missing",
    "asset_digest_mismatch",
    "time_base_not_contract",
    "time_base_missing",
    "duplicate_instance",
    "path_escape",
    "policy_input_mismatch",
    "policy_metadata_unverified",
    "perception_binding_missing",
    "sensor_calibration_missing",
    "native_probe_missing",
    "native_feature_unsupported",
    "recording_budget_unsafe",
    "scenario_invalid",
    # 契约自身的交叉校验没过（例如"摘要与内容不符"、参数集不完整）。它必须与
    # "场景写错了"分开：前者是**解析器/规格自身的缺陷**，后者是用户可修的输入问题；
    # 混在一个码里会让前端把内部错误提示成"请检查你的场景"。
    "spec_invalid",
]
RESOLUTION_BLOCKERS: tuple[str, ...] = get_args(ResolutionBlockerCode)

#: 运行错误码（WS ``error`` 消息与 ``GET /runs/{id}`` 的 ``error.code`` 共用这一份）。
RunErrorCode = Literal[
    "not_resolved",
    "probe_required",
    "asset_drift",
    "worker_exited",
    "native_import_failed",
    "model_compile_failed",
    "sensor_bind_failed",
    "policy_inference_failed",
    "recording_budget",
    "recording_failed",
    "protocol_violation",
    "stale_epoch",
    "invalid_command",
    "internal",
]
RUN_ERROR_CODES: tuple[str, ...] = get_args(RunErrorCode)

_MIB = 1024 * 1024
_GIB = 1024 * _MIB
#: 记录默认预算（用户指定，写在这里是唯一真值）：队列 128 MiB、单运行 5 GiB、
#: 目录 20 GiB、保留磁盘 2 GiB，且**永不自动删除**。
RECORDING_QUEUE_BUDGET_BYTES = 128 * _MIB
RECORDING_PER_RUN_BUDGET_BYTES = 5 * _GIB
RECORDING_DIRECTORY_BUDGET_BYTES = 20 * _GIB
RECORDING_MIN_FREE_DISK_BYTES = 2 * _GIB

_SAFE_ID_RE = re.compile(SAFE_ID_PATTERN)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


# --------------------------------------------------------------------------------------
# 标量类型与路径规则
# --------------------------------------------------------------------------------------


def _finite(value: float) -> float:
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"不接受非有限数值：{value!r}")
    return value


#: 任何浮点字段都用它 —— 一个 ``NaN`` 溜进运行规格就会让 digest 每次算出来都不一样。
FiniteFloat = Annotated[float, AfterValidator(_finite)]


def safe_relative_path(value: str, *, what: str = "路径") -> str:
    """把"包内相对路径"规范化成 posix，并**拒绝一切逃逸**。

    拒绝项：绝对路径、Windows 盘符（``C:``）、反斜杠、前导 ``/``、任何 ``..`` 段、
    空串、以及归一化后跳出包根的 ``./`` 组合。理由：这些路径会被拿去拼真实文件系统，
    一个 ``..`` 就把"读机器人包"变成"读任意文件"。
    """

    text = (value or "").strip()
    if not text:
        raise ValueError(f"{what}不能为空")
    if "\\" in text:
        raise ValueError(f"{what}不得使用反斜杠分隔符：{value!r}")
    if text.startswith("/") or text.startswith("~"):
        raise ValueError(f"{what}必须是包内相对路径（不得以 / 或 ~ 开头）：{value!r}")
    if len(text) >= 2 and text[1] == ":":
        raise ValueError(f"{what}不得带盘符：{value!r}")
    parts = posixpath.normpath(text).split("/")
    if any(part == ".." for part in parts):
        raise ValueError(f"{what}不得含 '..'（路径逃逸）：{value!r}")
    if parts[0] in ("", "."):
        raise ValueError(f"{what}不得含 '.' 或前导 /：{value!r}")
    normalized = "/".join(parts)
    if normalized.startswith("/") or ":" in normalized:
        raise ValueError(f"{what}归一化后仍不安全：{normalized!r}")
    return normalized


def _vec3(value: Any) -> tuple[float, float, float]:
    items = tuple(value or ())
    if len(items) != 3:
        raise ValueError(f"需要 3 个分量，实为 {len(items)}：{value!r}")
    return tuple(float(_finite(float(item))) for item in items)  # type: ignore[return-value]


#: 三元有限向量（单位由字段自己声明；类型只保证"3 个有限数"）。
Vec3 = Annotated[tuple[FiniteFloat, FiniteFloat, FiniteFloat], AfterValidator(_vec3)]


#: 单位四元数容差（写出来是为了让"为什么是 1e-3"可被讨论）。
QUAT_TOLERANCE = 1e-3


def _quat_wxyz(value: Any) -> tuple[float, float, float, float]:
    """单位四元数，**顺序 wxyz**（MuJoCo/mjlab）。非单位模长即拒绝。

    为什么强制模长检查：非单位四元数在 MuJoCo 的四元数运算里会被**静默**用错，
    表现为姿态抖一下、方向偏几度 —— 这类误差不报错，只会污染整条轨迹与观测。
    """

    items = tuple(value or ())
    if len(items) != 4:
        raise ValueError(f"四元数需要 4 个分量（{QUAT_ORDER}），实为 {len(items)}：{value!r}")
    cleaned = tuple(float(_finite(float(item))) for item in items)
    norm = math.sqrt(sum(item * item for item in cleaned))
    if norm <= 0.0:
        raise ValueError("四元数不能是零四元数")
    if abs(norm - 1.0) > QUAT_TOLERANCE:
        raise ValueError(
            f"四元数必须单位模长（{QUAT_ORDER}），当前模长 {norm:.6f}（容差 {QUAT_TOLERANCE}）"
        )
    return cleaned  # type: ignore[return-value]


#: 姿态四元数（**wxyz**）。
QuatWxyz = Annotated[
    tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat], AfterValidator(_quat_wxyz)
]


class _Strict(BaseModel):
    """所有运行契约模型的共同基类：禁未知字段 + 不可变。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _check_safe_id(value: str, *, what: str) -> str:
    if not _SAFE_ID_RE.match(value):
        raise ValueError(
            f"{what}={value!r} 不符合安全标识规则 {SAFE_ID_PATTERN}（禁止 / \\ .. 与大写）"
        )
    return value


def _check_sha256(value: str | None, *, what: str) -> str | None:
    if value is None:
        return None
    if not _SHA256_RE.match(value):
        raise ValueError(f"{what}必须是 64 位小写十六进制 sha256，实为 {value!r}")
    return value


# --------------------------------------------------------------------------------------
# 时间基与资产
# --------------------------------------------------------------------------------------


class RunTimeBase(_Strict):
    """时间基：**只存物理率与整数分频**，其余全是导出量（这是"不新建隐式 200Hz 真值"的实现）。

    ``source`` 是**必填**字段且没有默认值：调用方必须明说这份时间基是从哪读到的。
    :class:`ResolvedRunSpec` 只接受 ``source="contract"``（机器人包 ``contract.json``），
    于是"从旧 ``simulation/config.json`` 顺手抄一个数"或"PIE 当年是 200Hz 就写 200"
    在构造运行规格时就被拒绝 —— 而不是靠注释提醒。
    """

    physics_hz: int = Field(gt=0, le=20_000)
    control_decimation: int = Field(default=1, ge=1, le=2000)
    source: Literal["contract", "legacy_config", "missing"]

    @model_validator(mode="after")
    def _check(self) -> "RunTimeBase":
        if self.physics_hz % self.control_decimation:
            raise ValueError(
                f"physics_hz={self.physics_hz} 必须能被 control_decimation="
                f"{self.control_decimation} 整除（否则控制率不是精确值，tick 无法对齐）"
            )
        return self

    @property
    def control_hz(self) -> float:
        return float(self.physics_hz) / float(self.control_decimation)

    @property
    def physics_dt(self) -> float:
        return 1.0 / float(self.physics_hz)

    @property
    def control_dt(self) -> float:
        return float(self.control_decimation) / float(self.physics_hz)

    def ticks_for_control_steps(self, steps: int) -> int:
        """把"每 N 个**控制步**一次"换算成物理 tick（深度相机的 ``update_steps`` 就是这个口径）。"""

        if steps < 1:
            raise ValueError("控制步周期必须 >= 1")
        return steps * self.control_decimation

    def hz_for_period_ticks(self, ticks: int) -> float:
        if ticks < 1:
            raise ValueError("采样周期 tick 必须 >= 1")
        return float(self.physics_hz) / float(ticks)

    def as_dict(self) -> dict[str, Any]:
        """导出量一并给出（catalog / manifest 用），但**存进规格的还是那两个整数**。"""

        return {
            "physics_hz": self.physics_hz,
            "control_decimation": self.control_decimation,
            "control_hz": self.control_hz,
            "physics_dt": self.physics_dt,
            "control_dt": self.control_dt,
            "source": self.source,
        }


class AssetRef(_Strict):
    """一个必需资产的**包内**引用（路径 + 摘要 + 字节数）。

    ``sha256`` 允许 ``None`` 只有一种合法情形：尚未计算（``resolved`` 之前的草稿）。
    :class:`ResolvedRunSpec` 会拒绝任何 ``sha256 is None`` 的资产 —— 没有摘要就无法在
    运行创建后重算并发现"资产变了"。
    """

    kind: AssetKind
    path: str
    sha256: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    robot_id: str | None = None

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        return safe_relative_path(value, what="资产路径")

    @field_validator("sha256")
    @classmethod
    def _digest(cls, value: str | None) -> str | None:
        return _check_sha256(value, what="资产 sha256")

    @field_validator("robot_id")
    @classmethod
    def _robot(cls, value: str | None) -> str | None:
        return None if value is None else _check_safe_id(value, what="robot_id")


# --------------------------------------------------------------------------------------
# 传感器实例与样本
# --------------------------------------------------------------------------------------


class InstanceRecordOptions(_Strict):
    """单实例的记录选项（默认只记"策略实际吃的那一路"，避免把每个中间量都写盘）。"""

    record: bool = True
    outputs: tuple[str, ...] = ()
    record_png: bool = False
    sample_stride: int = Field(default=1, ge=1, le=10000)

    @field_validator("outputs")
    @classmethod
    def _unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError(f"record.outputs 有重复：{list(value)}")
        return value


class SensorInstanceSpec(_Strict):
    """一个**已决议**的传感器实例（同类型可有多个实例，靠 ``instance_id`` 区分）。

    ``binding_state`` 在解析后必须是 ``pending_compile``：索引（site/joint/body id）
    只有 MuJoCo 编译完模型才知道，提前"绑定"就是假承诺。

    **采样周期只有一个真值**：它写在 :attr:`config` 里（``sample_period_ticks``），
    默认值与出处由插件声明给出（见 :mod:`contracts.sensor_plugin_contract`）；
    :attr:`sample_period_ticks` 只是读它的**派生属性**，因此不存在"字段写 10、
    参数写 5"这种两份数值。同理，``config`` 必须是**完整参数集**：解析器要把
    插件默认值也展开进来，使"这个实例实际用的 max_range 是多少"只有一个答案。
    """

    instance_id: str
    plugin_id: str
    plugin_version: str
    target_kind: Literal["body", "site", "joint", "camera"] | None = None
    target: str | None = None
    pos: Vec3 = (0.0, 0.0, 0.0)
    quat_wxyz: QuatWxyz = (1.0, 0.0, 0.0, 0.0)
    max_age_ticks: int = Field(default=0, ge=0, le=1_000_000)
    noise: NoiseSpec = Field(default_factory=NoiseSpec)
    latency: LatencySpec = Field(default_factory=LatencySpec)
    config: dict[str, Any] = Field(default_factory=dict)
    config_provenance: dict[str, str] = Field(default_factory=dict)
    capability_level: Literal["registered", "implemented", "available", "verified"] = "registered"
    binding_state: Literal["pending_compile"] = "pending_compile"
    record: InstanceRecordOptions = Field(default_factory=InstanceRecordOptions)

    @field_validator("instance_id")
    @classmethod
    def _iid(cls, value: str) -> str:
        return _check_safe_id(value, what="instance_id")

    @field_validator("plugin_id")
    @classmethod
    def _pid(cls, value: str) -> str:
        return _check_safe_id(value, what="plugin_id")

    @field_validator("plugin_version")
    @classmethod
    def _pver(cls, value: str) -> str:
        if not _SEMVER_RE.match(value):
            raise ValueError(f"plugin_version 必须是 x.y.z，实为 {value!r}")
        return value

    @property
    def sample_period_ticks(self) -> int:
        """调度周期（物理 tick）。**存在** :attr:`config` 里，这里只是读取。"""

        value = self.config.get("sample_period_ticks")
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(
                f"实例 {self.instance_id} 的 config 缺少已决议的 sample_period_ticks"
            )
        return value

    @model_validator(mode="after")
    def _check(self) -> "SensorInstanceSpec":
        definition = plugin_definition(self.plugin_id)
        if definition is None:
            raise ValueError(f"未知传感器插件 {self.plugin_id!r}（catalog 里没有，拒绝解析成实例）")
        if definition.version != self.plugin_version:
            raise ValueError(
                f"实例 {self.instance_id} 声明插件版本 {self.plugin_version}，"
                f"而 catalog 里是 {definition.version}（不允许引用未登记的旧版本）"
            )
        if not definition.instantiable:
            raise ValueError(
                f"实例 {self.instance_id} 用了派生视图 {self.plugin_id}：它不是可实例化插件"
            )
        if definition.requires_target and not self.target:
            raise ValueError(
                f"实例 {self.instance_id}（{self.plugin_id}）必须有 target（射线/接触目标）"
            )
        if not definition.mountable and tuple(self.pos) != (0.0, 0.0, 0.0):
            raise ValueError(
                f"实例 {self.instance_id}（{self.plugin_id}）不可挂载，pos 必须为 0（它不是物理器件）"
            )
        if self.noise.kind != "none" and not definition.supports_noise:
            raise ValueError(
                f"实例 {self.instance_id}（{self.plugin_id}）不支持噪声，却声明了 noise.kind="
                f"{self.noise.kind!r}"
            )
        if self.latency.kind != "none" and not definition.supports_latency:
            raise ValueError(
                f"实例 {self.instance_id}（{self.plugin_id}）不支持延迟，却声明了 latency.kind="
                f"{self.latency.kind!r}"
            )
        declared = {field.name: field for field in definition.config}
        unknown_keys = sorted(set(self.config) - set(declared))
        if unknown_keys:
            raise ValueError(
                f"实例 {self.instance_id}（{self.plugin_id}）含未声明参数 {unknown_keys}"
                f"（已声明 {sorted(declared)}）"
            )
        missing_keys = sorted(set(declared) - set(self.config))
        if missing_keys:
            raise ValueError(
                f"实例 {self.instance_id}（{self.plugin_id}）参数不完整，缺 {missing_keys}："
                "解析后的规格必须携带**完整**参数集（含展开的默认值），"
                "否则下游只能自己去猜默认值 —— 那就会出现第二套真值"
            )
        for name, value in self.config.items():
            _assert_finite_tree(value, what=f"实例 {self.instance_id} 参数 {name}")
            declared[name].accepts(value)
        if set(self.config_provenance) != set(self.config):
            raise ValueError(
                f"实例 {self.instance_id} 的参数出处表与参数集不一致："
                f"参数 {sorted(self.config)}，出处 {sorted(self.config_provenance)}"
                "（解析后的每个值都必须说得出从哪来，且不多不少）"
            )
        for key, text in self.config_provenance.items():
            if not text or not text.strip():
                raise ValueError(f"实例 {self.instance_id} 参数 {key} 的出处为空")
        output_names = {output.name for output in definition.outputs}
        unknown_outputs = sorted(set(self.record.outputs) - output_names)
        if unknown_outputs:
            raise ValueError(
                f"实例 {self.instance_id} 记录了未声明的输出 {unknown_outputs}（可用 {sorted(output_names)}）"
            )
        if self.record.record_png and not any(
            output.payload_kind == "image_png" for output in definition.outputs
        ):
            raise ValueError(
                f"实例 {self.instance_id}（{self.plugin_id}）没有 PNG 输出，record.record_png 无意义"
            )
        return self


def _assert_finite_tree(value: Any, *, what: str, depth: int = 0) -> None:
    """递归拒绝 ``NaN``/``Infinity``（包括嵌套列表/字典里的）。"""

    if depth > 8:
        raise ValueError(f"{what} 嵌套过深（可能是循环引用）")
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        _finite(float(value))
        return
    if isinstance(value, str):
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{what} 的字典键必须是字符串")
            _assert_finite_tree(item, what=f"{what}[{key}]", depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_finite_tree(item, what=f"{what}[{index}]", depth=depth + 1)
        return
    if value is None:
        return
    raise ValueError(f"{what} 含不支持的类型 {type(value).__name__}")


class SampleEnvelope(_Strict):
    """一次样本的**元数据信封**（张量字节本身走线协议载荷，不进信封）。

    ``sample_tick`` 是"数据在物理上是什么时候的"，``available_tick`` 是"什么时候可被消费"
    （= ``sample_tick`` + 延迟 tick 数）。两者分开才能诚实表达延迟传感器：
    只有 ``sample_tick`` 的话，策略在 t=10 吃到 t=0 的图像看起来就像 t=10 的图像。
    """

    schema_version: str = RUN_CONTRACT_VERSION
    run_id: str
    epoch: int = Field(ge=0)
    seq: int = Field(ge=0)
    #: 该**实例输出自己**的样本序号（可选）。``seq`` 是整条流的帧号（跨实例共用），
    #: 记录器/策略要问「这一路传感器是不是每 5 tick 都到了一次」用的是本字段，
    #: 不是帧号 —— 两者混成一个就会把"别的帧插进来了"误判成丢样本。
    sample_seq: int | None = Field(default=None, ge=0)
    instance_id: str
    plugin_id: str
    plugin_version: str
    output: str
    sample_tick: int = Field(ge=0)
    available_tick: int = Field(ge=0)
    sim_time: FiniteFloat = Field(ge=0.0)
    shape: tuple[int, ...] | None = None
    dtype: str | None = None
    payload_kind: Literal["tensor", "image_png", "cloud", "graph"] = "tensor"
    unit: str | None = None
    reference_frame: str = "sensor"
    source: Literal["truth", "measurement", "estimate"] = "measurement"
    validity: Literal[
        "valid", "missing", "stale", "no_hit", "dropped", "disabled", "unsupported", "fault"
    ] = "valid"
    payload_bytes: int = Field(ge=0)
    checksum: str | None = None
    rng_stream: Literal["instance", "run"] = "instance"
    processing_version: str | None = None
    calibration_ref: str | None = None
    note: str | None = None

    @field_validator("run_id", "instance_id", "plugin_id")
    @classmethod
    def _ids(cls, value: str) -> str:
        return _check_safe_id(value, what="样本标识")

    @field_validator("checksum")
    @classmethod
    def _sum(cls, value: str | None) -> str | None:
        return _check_sha256(value, what="样本 checksum")

    @model_validator(mode="after")
    def _check(self) -> "SampleEnvelope":
        if self.available_tick < self.sample_tick:
            raise ValueError(
                f"available_tick({self.available_tick}) 不得早于 sample_tick({self.sample_tick})"
            )
        if self.schema_version != RUN_CONTRACT_VERSION:
            raise ValueError(
                f"样本 schema_version={self.schema_version!r} 与本契约 {RUN_CONTRACT_VERSION!r} 不符"
            )
        if self.validity == "valid":
            if self.payload_bytes <= 0:
                raise ValueError("validity=valid 的样本必须有非空载荷")
            if self.checksum is None:
                raise ValueError("validity=valid 的样本必须带载荷摘要")
            if self.payload_kind == "tensor":
                if not self.shape or self.dtype is None:
                    raise ValueError("张量样本必须带 shape 与 dtype")
                if any(dim <= 0 for dim in self.shape):
                    raise ValueError(f"shape 各维必须为正，实为 {list(self.shape)}")
                if self.dtype not in DTYPE_ITEMSIZE:
                    raise ValueError(f"未知 dtype {self.dtype!r}（协议表 {sorted(DTYPE_ITEMSIZE)}）")
                expected = DTYPE_ITEMSIZE[self.dtype]
                for dim in self.shape:
                    expected *= int(dim)
                if self.payload_bytes != expected:
                    raise ValueError(
                        f"payload_bytes={self.payload_bytes} 与 shape×dtype 算出的 {expected} 不符"
                    )
                if self.unit is None:
                    raise ValueError("张量样本必须声明单位")
            elif self.payload_kind == "image_png":
                if self.shape is not None or self.dtype is not None:
                    raise ValueError("image_png 样本不在信封里重复 shape/dtype")
            else:
                raise ValueError(
                    f"payload_kind={self.payload_kind} 尚无实现，不能产出 valid 样本"
                )
        else:
            if self.validity not in SAMPLE_EMPTY_VALIDITIES:
                raise ValueError(
                    f"validity={self.validity!r} 不在"
                    f" {sorted(SAMPLE_EMPTY_VALIDITIES)}（有效样本请用 'valid'）"
                )
            if self.payload_bytes:
                raise ValueError(
                    f"validity={self.validity} 的样本 payload_bytes 必须为 0（没有数据就没有字节）"
                )
            if self.shape is not None or self.dtype is not None:
                raise ValueError(
                    f"validity={self.validity} 的样本不得声明 shape/dtype（声明会被当成有数据）"
                )
        return self

    def age_ticks(self, now_tick: int) -> int:
        """相对 ``now_tick`` 的新旧程度（负数 = 还没到可用时刻，调用方必须当成不可用）。"""

        return now_tick - self.sample_tick

    def is_usable(self, now_tick: int, *, max_age_ticks: int) -> bool:
        """只有 ``valid`` 且年龄在容差内且已到可用时刻，才算可用。"""

        if self.validity != "valid":
            return False
        age = now_tick - self.available_tick
        return 0 <= age <= max_age_ticks


# --------------------------------------------------------------------------------------
# 策略侧
# --------------------------------------------------------------------------------------


class OnnxTensorMeta(_Strict):
    """从**产物元数据**读出的一个张量描述（名称 + 形状 + dtype）。

    ``batch`` 维写成 1 或 ``-1``（动态）都允许，但必须由实际文件给出 ——
    解析器绝不把"看名字猜的形状"填进来。
    """

    name: str
    dtype: str
    shape: tuple[int, ...]

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("张量名不能为空")
        return value.strip()

    @field_validator("dtype")
    @classmethod
    def _dtype(cls, value: str) -> str:
        if value not in DTYPE_ITEMSIZE:
            raise ValueError(f"未知 dtype {value!r}（协议表 {sorted(DTYPE_ITEMSIZE)}）")
        return value


class PolicyInputBinding(_Strict):
    """策略的一个输入观测项与其**数据来源**的绑定（A 类吃传感器的实现处）。"""

    name: str
    kind: Literal["proprio", "history", "depth", "memory", "command", "external"]
    tensor_shape: tuple[int, ...]
    dtype: str = "f4"
    source: Literal["state", "sensor", "history_buffer", "recurrent_state", "command"]
    instance_id: str | None = None
    output: str | None = None
    sample_period_ticks: int | None = Field(default=None, ge=1)
    history_frames: int = Field(default=1, ge=1, le=10000)
    transform: Literal["none", "min_max_normalize", "crop", "stack", "scale"] = "none"
    verified: bool = False
    verified_by: Literal["unverified", "onnx_metadata", "word_match"] = "unverified"
    evidence: str = ""

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]{0,63}$", value):
            raise ValueError(f"观测项名不合法：{value!r}")
        return value

    @field_validator("output")
    @classmethod
    def _output(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not re.match(r"^[a-z][a-z0-9_]{0,63}$", text):
            raise ValueError(f"传感器输出名不合法：{value!r}")
        return text

    @field_validator("tensor_shape")
    @classmethod
    def _shape(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if not value:
            raise ValueError("tensor_shape 不能为空")
        if any(dim == 0 or dim < -1 for dim in value):
            raise ValueError(f"tensor_shape 含非法维度 {list(value)}（-1 表示动态批，0 不允许）")
        return value

    @model_validator(mode="after")
    def _check(self) -> "PolicyInputBinding":
        if self.dtype not in DTYPE_ITEMSIZE:
            raise ValueError(f"未知 dtype {self.dtype!r}")
        if self.source == "sensor" and not self.instance_id:
            raise ValueError("source=sensor 的观测项必须绑定 instance_id（否则数据从哪来不可知）")
        if self.source != "sensor" and self.instance_id:
            raise ValueError(
                f"source={self.source} 的观测项不得带 instance_id（那是传感器专用字段）"
            )
        if self.source != "sensor" and self.output:
            raise ValueError(
                f"source={self.source} 的观测项不得带 output（output 只在引用传感器实例时有意义）"
            )
        if self.verified and self.verified_by != "onnx_metadata":
            raise ValueError(
                f"verified_by={self.verified_by!r} 不能作为认证依据："
                "只有读过产物实际元数据（onnx_metadata）才允许 verified=True（词形命中不算）"
            )
        if self.verified_by == "onnx_metadata" and not self.evidence:
            raise ValueError("verified_by=onnx_metadata 必须给出 evidence（哪个文件、哪一段元数据）")
        return self


class PolicyArtifactRef(_Strict):
    """策略产物引用（包内相对路径 + 摘要 + **实际**输入输出元数据）。"""

    relative_path: str
    sha256: str | None = None
    runtime: Literal["onnxruntime"] = "onnxruntime"
    inputs: tuple[OnnxTensorMeta, ...] = ()
    outputs: tuple[OnnxTensorMeta, ...] = ()
    metadata_source: Literal["none", "onnx_file"] = "none"
    metadata_verified: bool = False

    @field_validator("relative_path")
    @classmethod
    def _path(cls, value: str) -> str:
        return safe_relative_path(value, what="策略路径")

    @field_validator("sha256")
    @classmethod
    def _digest(cls, value: str | None) -> str | None:
        return _check_sha256(value, what="策略 sha256")

    @model_validator(mode="after")
    def _check(self) -> "PolicyArtifactRef":
        if self.metadata_verified:
            if self.metadata_source != "onnx_file":
                raise ValueError(
                    "metadata_verified=True 必须由实际 ONNX 文件元数据支撑"
                    "（配置里写了形状、或按名字猜，都不算）"
                )
            if not self.inputs or not self.outputs:
                raise ValueError("metadata_verified=True 必须同时给出 inputs 与 outputs")
        elif self.inputs or self.outputs:
            raise ValueError(
                "metadata_source=none 却填了 inputs/outputs —— 元数据必须来自实际文件"
            )
        if self.sha256 is None:
            raise ValueError("策略产物必须带摘要（无摘要就无法在运行创建后重算发现变化）")
        return self

    def tensor_meta(self, name: str, *, output: bool = False) -> OnnxTensorMeta | None:
        items = self.outputs if output else self.inputs
        return next((item for item in items if item.name == name), None)


# --------------------------------------------------------------------------------------
# 单位与坐标系（口径的唯一表）
# --------------------------------------------------------------------------------------


#: 单位约定表。catalog / manifest / 前端图例都从这里取值，**不各自翻译**。
UNIT_CONVENTION: dict[str, str] = {
    "length": "m",
    "angle": "rad",
    "angular_velocity": "rad/s",
    "acceleration": "m/s^2",
    "force": "N",
    "torque": "N*m",
    "pressure": "Pa",
    "frequency": "Hz",
    "time": "s",
    "tick": "1/physics_hz",
    "range": "m",
    "height": "m",
    "depth": "m",
    "quat_order": QUAT_ORDER,
    "coordinate_system": "mujoco_z_up_right_handed",
}


class Units(_Strict):
    """一次运行的单位口径（默认值**只能**来自 :data:`UNIT_CONVENTION`）。

    单独成为一个模型而不是散落的字符串，是为了让 WS ``hello`` 与 manifest 能一次性、
    无歧义地把单位交给前端与离线分析：``float32`` 的 depth 到底是米还是归一化值，
    必须写在数据旁边。
    """

    length: str = UNIT_CONVENTION["length"]
    angle: str = UNIT_CONVENTION["angle"]
    angular_velocity: str = UNIT_CONVENTION["angular_velocity"]
    acceleration: str = UNIT_CONVENTION["acceleration"]
    force: str = UNIT_CONVENTION["force"]
    torque: str = UNIT_CONVENTION["torque"]
    frequency: str = UNIT_CONVENTION["frequency"]
    time: str = UNIT_CONVENTION["time"]
    tick: str = UNIT_CONVENTION["tick"]
    quat_order: Literal["wxyz"] = QUAT_ORDER  # type: ignore[assignment]
    coordinate_system: str = UNIT_CONVENTION["coordinate_system"]
    tensor_dtype_default: str = "f4"
    doc: str = COORD_SYSTEM_DOC

    @model_validator(mode="after")
    def _check(self) -> "Units":
        expected = {
            "length": UNIT_CONVENTION["length"],
            "angle": UNIT_CONVENTION["angle"],
            "force": UNIT_CONVENTION["force"],
            "time": UNIT_CONVENTION["time"],
            "quat_order": UNIT_CONVENTION["quat_order"],
            "coordinate_system": UNIT_CONVENTION["coordinate_system"],
        }
        drift = {
            key: (getattr(self, key), want)
            for key, want in expected.items()
            if getattr(self, key) != want
        }
        if drift:
            raise ValueError(f"单位口径不得被局部改写（否则同一份数据两种解释）：{drift}")
        if self.tensor_dtype_default not in DTYPE_ITEMSIZE:
            raise ValueError(f"未知默认 dtype {self.tensor_dtype_default!r}")
        return self

    def as_dict(self) -> dict[str, str]:
        return self.model_dump(mode="json")


def _definition_or_raise(plugin_id: str) -> SensorPluginDefinition:
    definition = plugin_definition(plugin_id)
    if definition is None:
        raise ValueError(f"未知传感器插件 {plugin_id!r}（catalog 未登记，不能进入运行规格）")
    return definition


# --------------------------------------------------------------------------------------
# 记录选项 / 分块索引 / episode manifest
# --------------------------------------------------------------------------------------


class RecordingFormats(_Strict):
    """落盘格式（**一次决定，不留多形状**）。"""

    tensors: Literal["npz-chunk"] = "npz-chunk"
    image: Literal["png-lossless"] = "png-lossless"
    depth: Literal["float32"] = "float32"
    events: Literal["jsonl"] = "jsonl"
    status: Literal["npz-chunk"] = "npz-chunk"


class RecordingOptions(_Strict):
    """记录预算。默认值就是用户批准的四个数，且**永不自动删除**。

    ``on_backpressure="pause_at_tick"``：队列满时在**tick 边界暂停**推进，
    而不是丢样本 —— 丢样本会让"记录里的轨迹"和"实际跑的轨迹"分叉，
    那比卡顿严重得多。``display_policy="latest_frame"`` 只作用于**显示**侧
    （浏览器可以跳帧），记录侧不受影响。
    """

    enabled: bool = True
    queue_budget_bytes: int = Field(default=RECORDING_QUEUE_BUDGET_BYTES, ge=1)
    per_run_budget_bytes: int = Field(default=RECORDING_PER_RUN_BUDGET_BYTES, ge=1)
    directory_budget_bytes: int = Field(default=RECORDING_DIRECTORY_BUDGET_BYTES, ge=1)
    min_free_disk_bytes: int = Field(default=RECORDING_MIN_FREE_DISK_BYTES, ge=0)
    auto_delete: Literal[False] = False
    chunk_sim_time_s: FiniteFloat = Field(default=1.0, gt=0.0, le=600.0)
    on_backpressure: Literal["pause_at_tick"] = "pause_at_tick"
    display_policy: Literal["latest_frame"] = "latest_frame"
    record_status: bool = True
    status_period_ticks: int = Field(default=50, ge=1, le=1_000_000)
    formats: RecordingFormats = Field(default_factory=RecordingFormats)
    data_root: str = "episodes"

    @field_validator("data_root")
    @classmethod
    def _root(cls, value: str) -> str:
        return safe_relative_path(value, what="记录根目录")

    @model_validator(mode="after")
    def _check(self) -> "RecordingOptions":
        if not self.queue_budget_bytes <= self.per_run_budget_bytes:
            raise ValueError(
                f"队列预算 {self.queue_budget_bytes} 不得大于单运行预算 {self.per_run_budget_bytes}"
            )
        if not self.per_run_budget_bytes <= self.directory_budget_bytes:
            raise ValueError(
                f"单运行预算 {self.per_run_budget_bytes} 不得大于目录预算 "
                f"{self.directory_budget_bytes}"
            )
        if self.min_free_disk_bytes > self.directory_budget_bytes:
            raise ValueError("保留磁盘空间不得大于目录预算（那样永远写不下）")
        return self

    def budget_dict(self) -> dict[str, int | bool]:
        return {
            "queue_budget_bytes": self.queue_budget_bytes,
            "per_run_budget_bytes": self.per_run_budget_bytes,
            "directory_budget_bytes": self.directory_budget_bytes,
            "min_free_disk_bytes": self.min_free_disk_bytes,
            "auto_delete": self.auto_delete,
        }


#: 分块类型 → 允许格式（**唯一**表；:class:`ChunkMeta` 与索引都按它核对）。
CHUNK_FORMATS: dict[str, tuple[str, ...]] = {
    "tensors": ("npz-chunk",),
    "image": ("png-lossless",),
    "events": ("jsonl",),
    "status": ("npz-chunk",),
}
CHUNK_KINDS: tuple[str, ...] = tuple(CHUNK_FORMATS)


class ChunkMeta(_Strict):
    """一个数据块（manifest 的一行）。

    ``sha256`` 是**块文件字节**的摘要：单写者 + 临时块原子提交 + 块校验和，
    下载侧据此核对，避免"文件名对、内容被换"。``path`` 是**记录根目录下的相对路径**，
    HTTP 只能通过 ``chunk_id`` 在索引白名单里查到它，不接受调用方拼路径（防任意文件读）。
    """

    schema_version: str = RUN_CONTRACT_VERSION
    chunk_id: str
    episode_id: str
    kind: Literal["tensors", "image", "events", "status"]
    path: str
    sha256: str
    size_bytes: int = Field(ge=1)
    first_tick: int = Field(ge=0)
    last_tick: int = Field(ge=0)
    first_sim_time: FiniteFloat = Field(ge=0.0)
    last_sim_time: FiniteFloat = Field(ge=0.0)
    sample_count: int = Field(ge=0)
    dropped_count: int = Field(default=0, ge=0)
    instance_id: str | None = None
    output: str | None = None
    dtype: str | None = None
    shape: tuple[int, ...] | None = None
    unit: str | None = None
    format: str

    @field_validator("chunk_id", "episode_id")
    @classmethod
    def _ids(cls, value: str) -> str:
        return _check_safe_id(value, what="记录标识")

    @field_validator("instance_id")
    @classmethod
    def _iid(cls, value: str | None) -> str | None:
        return None if value is None else _check_safe_id(value, what="instance_id")

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        return safe_relative_path(value, what="块路径")

    @field_validator("sha256")
    @classmethod
    def _digest(cls, value: str) -> str:
        checked = _check_sha256(value, what="块 sha256")
        assert checked is not None
        return checked

    @model_validator(mode="after")
    def _check(self) -> "ChunkMeta":
        if self.format not in CHUNK_FORMATS[self.kind]:
            raise ValueError(
                f"块 {self.chunk_id} kind={self.kind} 只允许格式 {list(CHUNK_FORMATS[self.kind])}，"
                f"实为 {self.format!r}"
            )
        if self.last_tick < self.first_tick:
            raise ValueError(f"块 {self.chunk_id} tick 区间倒置")
        if self.last_sim_time < self.first_sim_time:
            raise ValueError(f"块 {self.chunk_id} 时间区间倒置")
        if self.kind == "tensors":
            if self.instance_id is None or self.output is None:
                raise ValueError("张量块必须绑定 instance_id 与 output（否则无法对齐样本）")
            if self.dtype not in DTYPE_ITEMSIZE:
                raise ValueError(f"张量块 dtype 非法：{self.dtype!r}")
            if not self.shape or any(dim <= 0 for dim in self.shape):
                raise ValueError(f"张量块 shape 非法：{list(self.shape or ())}")
            if self.unit is None:
                raise ValueError("张量块必须声明单位")
        elif self.dtype is not None or self.shape is not None:
            raise ValueError(f"kind={self.kind} 的块不在块索引里重复声明 shape/dtype")
        expected = self.sample_count + self.dropped_count
        if self.kind in ("tensors", "image") and expected == 0:
            raise ValueError(f"块 {self.chunk_id} 既无样本也无丢弃，是空块（应合并或删除）")
        return self

    def element_bytes(self) -> int | None:
        """每样本字节数（张量块），供容量核算。"""

        if self.dtype is None or not self.shape:
            return None
        total = DTYPE_ITEMSIZE[self.dtype]
        for dim in self.shape:
            total *= int(dim)
        return total


class RecordingChunkIndex(_Strict):
    """块索引（manifest 的数据部分）。**下载只能通过 chunk_id 查白名单**。"""

    schema_version: str = RUN_CONTRACT_VERSION
    episode_id: str
    data_root: str = "episodes"
    chunks: tuple[ChunkMeta, ...] = ()
    complete: bool = True
    interrupted: bool = False
    final_chunk_count: int = Field(default=0, ge=0)

    @field_validator("episode_id")
    @classmethod
    def _eid(cls, value: str) -> str:
        return _check_safe_id(value, what="episode_id")

    @field_validator("data_root")
    @classmethod
    def _root(cls, value: str) -> str:
        return safe_relative_path(value, what="记录根目录")

    @model_validator(mode="after")
    def _check(self) -> "RecordingChunkIndex":
        ids = [chunk.chunk_id for chunk in self.chunks]
        if len(ids) != len(set(ids)):
            duplicates = sorted({item for item in ids if ids.count(item) > 1})
            raise ValueError(f"块 ID 重复：{duplicates}（同一 episode 内必须唯一）")
        ordered = [chunk.first_tick for chunk in self.chunks]
        if ordered != sorted(ordered):
            raise ValueError("块必须按 first_tick 升序登记（乱序会让顺序读放大）")
        if self.interrupted and self.complete:
            raise ValueError("interrupted 与 complete 不能同时为真")
        if self.final_chunk_count and self.final_chunk_count != len(self.chunks):
            raise ValueError(
                f"final_chunk_count={self.final_chunk_count} 与实际块数 {len(self.chunks)} 不符"
            )
        return self

    @property
    def total_bytes(self) -> int:
        return sum(chunk.size_bytes for chunk in self.chunks)

    def chunk(self, chunk_id: str) -> ChunkMeta | None:
        """按 ``chunk_id`` 取块（**唯一**取路径的方式）。找不到返回 ``None``。"""

        return next((chunk for chunk in self.chunks if chunk.chunk_id == chunk_id), None)

    def allowed_path(self, chunk_id: str) -> str | None:
        """HTTP 下载入口：返回白名单相对路径，或 ``None`` 表示拒绝（绝不接受外部拼路径）。"""

        chunk = self.chunk(chunk_id)
        return chunk.path if chunk is not None else None

    def window_covered(self, *, start_tick: int, end_tick: int) -> bool:
        """[start, end] 是否被连续覆盖（有洞就返回 False，评测据此拒绝用缺数据的段）。"""

        cursor = start_tick
        for chunk in sorted(self.chunks, key=lambda item: item.first_tick):
            if chunk.kind not in ("tensors", "status", "image"):
                continue
            if chunk.first_tick > cursor:
                return False
            cursor = max(cursor, chunk.last_tick + 1)
            if cursor > end_tick:
                return True
        return cursor > end_tick


#: manifest 版本（与运行契约版本分开：manifest 是**落盘格式**，可以比契约更稳）。
EPISODE_MANIFEST_VERSION = "sim-episode-manifest-1.0"


class EpisodeManifest(_Strict):
    """一次记录的完整清单（记录收尾时**最后**写完，作为提交点）。

    设计要点：manifest 里带**整份解析规格**（含 ``spec_digest``），因此离线分析一个
    episode 不需要再去猜"当时那台机器人是什么参数"；异常退出时保留可解释的未完成记录
    （``complete=False, interrupted=True``），重启**新建 episode**，不覆盖既有目录。
    """

    manifest_version: str = EPISODE_MANIFEST_VERSION
    schema_version: str = RUN_CONTRACT_VERSION
    episode_id: str
    run_id: str
    spec: ResolvedRunSpec | None = None
    spec_digest: str
    seed: int
    time_base: RunTimeBase
    robot_id: str
    policy_id: str | None = None
    plugin_versions: dict[str, str] = Field(default_factory=dict)
    assets: tuple[AssetRef, ...] = ()
    index: RecordingChunkIndex
    events_path: str | None = None
    events_count: int = Field(default=0, ge=0)
    status: str
    end_reason: str | None = None
    start_tick: int = Field(ge=0)
    end_tick: int = Field(ge=0)
    duration_s: FiniteFloat = Field(ge=0.0)
    bytes_used: int = Field(default=0, ge=0)
    integrity_sha256: str | None = None
    report_refs: tuple[str, ...] = ()
    created_at_unix: FiniteFloat = Field(ge=0.0)
    updated_at_unix: FiniteFloat | None = Field(default=None, ge=0.0)

    @field_validator("episode_id", "run_id", "robot_id")
    @classmethod
    def _ids(cls, value: str) -> str:
        return _check_safe_id(value, what="标识")

    @field_validator("spec_digest")
    @classmethod
    def _sd(cls, value: str) -> str:
        checked = _check_sha256(value, what="spec_digest")
        if checked is None:
            raise ValueError("spec_digest 必填")
        return checked

    @field_validator("status")
    @classmethod
    def _status(cls, value: str) -> str:
        if value not in RUN_STATUSES:
            raise ValueError(f"status={value!r} 不在 {list(RUN_STATUSES)}")
        return value

    @field_validator("end_reason")
    @classmethod
    def _reason(cls, value: str | None) -> str | None:
        if value is not None and value not in RUN_END_REASONS:
            raise ValueError(f"end_reason={value!r} 不在 {list(RUN_END_REASONS)}")
        return value

    @field_validator("events_path")
    @classmethod
    def _events(cls, value: str | None) -> str | None:
        return None if value is None else safe_relative_path(value, what="事件路径")

    @model_validator(mode="after")
    def _check(self) -> "EpisodeManifest":
        if not self.manifest_version == EPISODE_MANIFEST_VERSION:
            raise ValueError(f"manifest_version 必须是 {EPISODE_MANIFEST_VERSION}")
        if self.index.episode_id != self.episode_id:
            raise ValueError(
                f"块索引 episode_id={self.index.episode_id!r} 与清单 {self.episode_id!r} 不符"
            )
        if self.end_tick < self.start_tick:
            raise ValueError("end_tick 早于 start_tick")
        if self.spec is not None:
            if self.spec.spec_digest != self.spec_digest:
                raise ValueError("manifest.spec.spec_digest 与顶层 spec_digest 不符（记录自相矛盾）")
            if self.spec.seed != self.seed:
                raise ValueError("manifest.seed 与规格 seed 不符")
            if self.spec.assets != self.assets:
                raise ValueError("manifest.assets 与规格 assets 不符（摘要可能被局部改写）")
        if self.status == "finalized" and not self.index.complete:
            raise ValueError("finalized 的运行必须有 complete 的块索引")
        if self.index.interrupted and self.status == "finalized":
            raise ValueError("中断记录不能标 finalized")
        if self.bytes_used > self.spec.recording.directory_budget_bytes if self.spec else False:
            raise ValueError("bytes_used 超过目录预算")
        return self

    def is_system_failure(self) -> bool:
        return self.end_reason in SYSTEM_FAILURE_REASONS

    def chunk(self, chunk_id: str) -> ChunkMeta | None:
        return self.index.chunk(chunk_id)


# --------------------------------------------------------------------------------------
# 参数出处 / 阻断项
# --------------------------------------------------------------------------------------


ProvenanceCategory = Literal[
    "robot_id",
    "policy_id",
    "time_base",
    "seed",
    "duration",
    "assets",
    "sensor_instances",
    "policy_inputs",
    "command_provider",
    "recording",
    "scenario",
    "runtime",
]
#: :class:`ResolvedRunSpec` 必须解释清楚出处的那些类别（**唯一**声明处）。
PROVENANCE_REQUIRED: tuple[str, ...] = get_args(ProvenanceCategory)


class ParamProvenance(_Strict):
    """一个参数（或一组参数）的**来源记录**。

    用户明确要求"参数来源清楚"：出问题时最贵的不是值错，而是**没人知道这个值从哪来**。
    ``source`` 必须是可核对的字符串（``robot_package:contract.json#control`` /
    ``policy_contract:depth_camera.height`` / ``scenario.override:...`` / ``user_input``），
    空字符串或"默认"这种含糊说法会被拒绝。
    """

    name: str
    category: ProvenanceCategory
    source: str
    value: Any = None
    detail: str = ""

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_.\[\]-]{0,63}$", value):
            raise ValueError(f"参数名不合法：{value!r}")
        return value

    @field_validator("source")
    @classmethod
    def _source(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("出处不能为空（必须写清是哪个文件/哪一段/哪次覆盖）")
        if text in {"default", "defaults", "auto", "n/a", "-"}:
            raise ValueError(f"出处 {text!r} 过于含糊，不能作为决议记录")
        return text

    @model_validator(mode="after")
    def _check(self) -> "ParamProvenance":
        _assert_finite_tree(self.value, what=f"参数 {self.name} 的值")
        return self


class ResolutionBlocker(_Strict):
    """一条结构化阻断项。**调用方按 ``code`` 分支，不读 ``message``**（消息给人看）。"""

    code: ResolutionBlockerCode
    subject: str
    detail: str = ""
    remedy: str = ""
    field: str | None = None

    @field_validator("subject")
    @classmethod
    def _subject(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("阻断项必须指出受影响的对象（机器人/策略/实例/参数名）")
        return text

    @model_validator(mode="after")
    def _check(self) -> "ResolutionBlocker":
        if not self.detail.strip():
            raise ValueError(f"阻断项 {self.code} 必须给出可诊断的 detail（不能只有码）")
        return self

    def as_message(self) -> str:
        return f"{self.code}: {self.subject} —— {self.detail}"


# --------------------------------------------------------------------------------------
# 原生能力探测报告（**可注入边界的返回值类型**）
# --------------------------------------------------------------------------------------


#: 探测特征词表。**未知名字直接拒绝**，否则打错一个字母就会把"未支持"变成"静默放行"。
PROBE_FEATURES: tuple[str, ...] = (
    "model_compile",
    "physics_substep",
    "substep_callback",
    "contact_force",
    "raycast",
    "height_field_collision",
    "mesh_collision",
    "offscreen_render",
    "depth_raycast",
    "imu_bias",
    "onnx_inference",
    "policy_closed_loop",
    "episode_record",
    "multi_instance",
    "noise_latency",
    "event_injection",
    "recurrent_reset",
)
#: 本契约里唯一被允许进入策略闭环运行的执行器能力（缺一个就不能宣称"能跑"）。
PROBE_FEATURES_REQUIRED: tuple[str, ...] = (
    "model_compile",
    "physics_substep",
    "onnx_inference",
    "policy_closed_loop",
    "episode_record",
)
ProbeFeatureState = Literal["supported", "unsupported", "unknown"]
PROBE_REASONS: tuple[str, ...] = ("not_probed", "probe_failed", "not_implemented", "probed")


class NativeProbeReport(_Strict):
    """worker 侧真实探测的结果（:data:`contracts.runtime_interfaces.NativeProbe` 的返回类型）。

    **控制面永远拿不到"猜测的报告"**：未探测只能是 ``probed=False`` + ``reason``，
    而 :class:`Capabilities` 与 :class:`ResolvedRunSpec` 在 ``probed=False`` 时
    不允许任何 ``available``/``verified`` 说法。
    """

    schema_version: str = RUN_CONTRACT_VERSION
    probed: bool = False
    reason: Literal["not_probed", "probe_failed", "not_implemented", "probed"] = "not_probed"
    executor_id: str = NATIVE_EXECUTOR_ID
    native_runtime_version: str = NATIVE_RUNTIME_VERSION
    mujoco_version: str | None = None
    onnxruntime_version: str | None = None
    python_version: str | None = None
    features: dict[str, ProbeFeatureState] = Field(default_factory=dict)
    capability_levels: dict[str, str] = Field(default_factory=dict)
    details: str = ""
    probed_at_unix: FiniteFloat | None = Field(default=None, ge=0.0)

    @field_validator("features")
    @classmethod
    def _features(
        cls, value: dict[str, ProbeFeatureState]
    ) -> dict[str, ProbeFeatureState]:
        unknown = sorted(set(value) - set(PROBE_FEATURES))
        if unknown:
            raise ValueError(
                f"未知探测特征 {unknown}（可用 {list(PROBE_FEATURES)}）—— 打错名字会被当成未支持"
            )
        return value

    @field_validator("capability_levels")
    @classmethod
    def _levels(cls, value: dict[str, str]) -> dict[str, str]:
        for key, level in value.items():
            _check_safe_id(key, what="capability_levels 键")
            if level not in CAPABILITY_LEVELS:
                raise ValueError(f"能力级别 {level!r} 未知（{list(CAPABILITY_LEVELS)}）")
        return value

    @model_validator(mode="after")
    def _check(self) -> "NativeProbeReport":
        if self.executor_id != NATIVE_EXECUTOR_ID:
            raise ValueError(
                f"探测报告的 executor_id={self.executor_id!r} 与本契约执行器 "
                f"{NATIVE_EXECUTOR_ID!r} 不符（不得冒名）"
            )
        if self.native_runtime_version != NATIVE_RUNTIME_VERSION:
            raise ValueError(
                f"探测报告的 runtime 版本={self.native_runtime_version!r} 与契约声明的 "
                f"{NATIVE_RUNTIME_VERSION!r} 不符（新原生能力有独立版本标识，不冒称旧执行器）"
            )
        if self.probed:
            if self.reason != "probed":
                raise ValueError("probed=True 时 reason 必须是 'probed'")
            if not self.features:
                raise ValueError("probed=True 但没有 feature 结果 —— 那不是探测，是猜测")
            if not self.mujoco_version or not self.onnxruntime_version:
                raise ValueError(
                    "probed=True 必须记录 mujoco/onnxruntime 版本（否则报告无法复现）"
                )
        else:
            if self.reason == "probed":
                raise ValueError("probed=False 不能声称已探测")
            if self.features:
                raise ValueError("probed=False 却带 feature 结果 —— 来源可疑，拒绝")
        return self

    @classmethod
    def not_probed(cls, reason: str = "not_implemented", *, details: str = "") -> "NativeProbeReport":
        """显式的"没探过"（解析器默认注入这个，而不是 ``None``，让"缺探测"成为可见事实）。"""

        if reason not in ("not_probed", "probe_failed", "not_implemented"):
            raise ValueError(f"reason={reason!r} 不是合法的未探测原因")
        return cls(probed=False, reason=reason, details=details)  # type: ignore[arg-type]

    def state_of(self, feature: str) -> ProbeFeatureState:
        if feature not in PROBE_FEATURES:
            raise ValueError(f"未知探测特征 {feature!r}")
        if not self.probed:
            return "unknown"
        return self.features.get(feature, "unknown")

    def is_supported(self, feature: str) -> bool:
        """与 :func:`contracts.runtime_interfaces.probe_is_supported` 同一语义（只认 supported）。"""

        return self.state_of(feature) == "supported"


# --------------------------------------------------------------------------------------
# 能力（四级，不得跳级宣称）
# --------------------------------------------------------------------------------------


class CapabilityEntry(_Strict):
    """一项能力的当前级别（能力名 = 探测特征名或 ``plugin:<id>`` / ``provider:<id>``）。"""

    name: str
    level: Literal["registered", "implemented", "available", "verified"] = "registered"
    evidence: str = ""
    note: str = ""

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        text = (value or "").strip()
        if not re.match(r"^[a-z][a-z0-9_.:/-]{0,79}$", text):
            raise ValueError(f"能力名不合法：{value!r}")
        return text

    @model_validator(mode="after")
    def _check(self) -> "CapabilityEntry":
        if self.level == "verified" and not self.evidence.strip():
            raise ValueError(
                f"能力 {self.name} 宣称 verified 但没有 evidence —— "
                "verified 必须可核对（回归基线 / 对拍记录），否则只能说 available"
            )
        return self


class Capabilities(_Strict):
    """一次决议所依据的**能力快照**（进 digest，因此能力变化会让规格变化）。

    规则：``available`` / ``verified`` 必须有已完成的探测报告支撑 ——
    在 worker 还没被探测过的今天，任何"这个传感器可用"的说法都构造不出来。
    """

    schema_version: str = RUN_CONTRACT_VERSION
    executor_id: str = NATIVE_EXECUTOR_ID
    native_runtime_version: str = NATIVE_RUNTIME_VERSION
    probed: bool = False
    probe: NativeProbeReport | None = None
    entries: tuple[CapabilityEntry, ...] = ()
    limits: dict[str, Any] = Field(default_factory=protocol_limits)

    @model_validator(mode="after")
    def _check(self) -> "Capabilities":
        if self.executor_id != NATIVE_EXECUTOR_ID:
            raise ValueError(f"executor_id 必须是 {NATIVE_EXECUTOR_ID!r}，实为 {self.executor_id!r}")
        if self.native_runtime_version != NATIVE_RUNTIME_VERSION:
            raise ValueError(f"native_runtime_version 必须是 {NATIVE_RUNTIME_VERSION!r}")
        names = [entry.name for entry in self.entries]
        if len(names) != len(set(names)):
            raise ValueError(f"能力项重复：{sorted({n for n in names if names.count(n) > 1})}")
        if self.probed:
            if self.probe is None or not self.probe.probed:
                raise ValueError("probed=True 必须带一份已完成的探测报告（不能只写标志）")
        elif self.probe is not None and self.probe.probed:
            raise ValueError("探测报告说已探测，Capabilities.probed 却是 False（自相矛盾）")
        for entry in self.entries:
            if entry.level in ("available", "verified") and not self.probed:
                raise ValueError(
                    f"能力 {entry.name} 宣称 {entry.level} 但未探测 —— "
                    "available/verified 需要真实运行时探测结果，不能凭声明升级"
                )
            if entry.level in ("available", "verified") and entry.name.startswith("plugin:"):
                plugin_id = entry.name.split(":", 1)[1]
                if self.probe is None or plugin_id not in self.probe.capability_levels:
                    raise ValueError(
                        f"插件 {plugin_id} 宣称 {entry.level} 但探测报告里没有它的观测级别"
                    )
        return self

    @classmethod
    def unprobed(
        cls,
        *,
        plugin_levels: dict[str, str] | None = None,
        details: str = "native worker 尚未实现探测",
    ) -> "Capabilities":
        """默认能力快照：**未探测**，插件级别封顶在声明层。

        解析器在没有注入 probe 时用它 —— 于是"缺探测"会以阻断项的形式暴露，
        而不是让某个插件悄悄变成可用。
        """

        entries = [
            CapabilityEntry(name=f"plugin:{plugin_id}", level=level, note=details)
            for plugin_id, level in sorted((plugin_levels or {}).items())
        ]
        return cls(
            probed=False,
            probe=NativeProbeReport.not_probed("not_implemented", details=details),
            entries=tuple(entries),
        )

    def entry(self, name: str) -> CapabilityEntry | None:
        return next((item for item in self.entries if item.name == name), None)

    def level_of(self, name: str) -> str | None:
        entry = self.entry(name)
        return entry.level if entry else None

    def is_implemented(self, name: str) -> bool:
        """工作台"只允许启用有真实实现的组合"的判据：级别 ≥ implemented。"""

        level = self.level_of(name)
        return level in ("implemented", "available", "verified")

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


# --------------------------------------------------------------------------------------
# 命令提供器实例（B 类）
# --------------------------------------------------------------------------------------


class CommandProviderSpec(_Strict):
    """一个**已决议**的外部决策器（只改指令，不进观测）。"""

    provider_id: str
    version: str
    input_instances: tuple[str, ...]
    command_dims: int = Field(ge=1, le=3)
    config: dict[str, Any] = Field(default_factory=dict)
    config_provenance: dict[str, str] = Field(default_factory=dict)
    capability_level: Literal["registered", "implemented", "available", "verified"] = "registered"
    #: 指令源（谁产生被修改前的指令）。``joystick`` = 人在工作台推，``scenario`` = 场景常量。
    source: Literal["scenario", "joystick", "evaluation"] = "scenario"

    @field_validator("provider_id")
    @classmethod
    def _pid(cls, value: str) -> str:
        return _check_safe_id(value, what="provider_id")

    @field_validator("version")
    @classmethod
    def _ver(cls, value: str) -> str:
        if not _SEMVER_RE.match(value):
            raise ValueError(f"provider version 必须是 x.y.z，实为 {value!r}")
        return value

    @field_validator("input_instances")
    @classmethod
    def _instances(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("命令提供器必须绑定至少一个输入传感器实例")
        if len(value) != len(set(value)):
            raise ValueError(f"input_instances 有重复：{list(value)}")
        for item in value:
            _check_safe_id(item, what="input_instance")
        return value

    @model_validator(mode="after")
    def _check(self) -> "CommandProviderSpec":
        definition = command_provider_definition(self.provider_id)
        if definition is None:
            raise ValueError(f"未知命令提供器 {self.provider_id!r}（catalog 未登记）")
        if definition.version != self.version:
            raise ValueError(
                f"命令提供器版本 {self.version} 与 catalog 的 {definition.version} 不符"
            )
        if self.command_dims != definition.command_dims:
            raise ValueError(
                f"命令维度 {self.command_dims} 与声明 {definition.command_dims} 不符"
            )
        declared = {field.name: field for field in definition.config}
        unknown = sorted(set(self.config) - set(declared))
        if unknown:
            raise ValueError(f"命令提供器 {self.provider_id} 含未声明参数 {unknown}")
        missing = sorted(set(declared) - set(self.config))
        if missing:
            raise ValueError(
                f"命令提供器 {self.provider_id} 参数不完整，缺 {missing}"
                "（必须携带展开后的完整参数集）"
            )
        for name, value in self.config.items():
            _assert_finite_tree(value, what=f"命令提供器 {self.provider_id} 参数 {name}")
            declared[name].accepts(value)
        if set(self.config_provenance) != set(self.config):
            raise ValueError(f"命令提供器 {self.provider_id} 的参数出处表与参数集不一致")
        return self


def command_provider_spec_from(
    provider_id: str,
    *,
    input_instances: tuple[str, ...],
    overrides: dict[str, Any] | None = None,
    source: str = "scenario",
) -> CommandProviderSpec:
    """按声明解析一个命令提供器实例（默认值/出处**只**来自 :func:`command_provider_definition`）。"""

    definition = command_provider_definition(provider_id)
    if definition is None:
        raise ValueError(f"未知命令提供器 {provider_id!r}")
    config, provenance = definition.resolve_config(overrides)
    return CommandProviderSpec(
        provider_id=provider_id,
        version=definition.version,
        input_instances=tuple(input_instances),
        command_dims=definition.command_dims,
        config=config,
        config_provenance=provenance,
        capability_level=definition.capability_level,
        source=source,  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------------------
# 解析后的不可变运行规格
# --------------------------------------------------------------------------------------


#: ``spec_digest`` 的占位值：允许"先构造未签名规格、再算摘要"，但**非占位值必须自洽**。
UNSIGNED_DIGEST = "0" * 64


def _product(dims: tuple[int, ...]) -> int:
    total = 1
    for dim in dims:
        total *= int(dim)
    return total


class ResolvedRunSpec(_Strict):
    """**机器决议**出来的运行规格：创建运行的唯一输入，也是 manifest 的一部分。

    三条硬规则：

    1. **时间基只能来自机器人包**（``time_base.source == "contract"``）——
       于是"PIE 当年按 200Hz 跑"这种第二真值在类型层面就写不出来。
    2. **必须自洽签名**：:attr:`spec_digest` 由 :func:`compute_digest` 重算并比对，
       所以没人能构造一份"摘要写着 A、参数是 B"的规格（``with_digest()`` 是正规入口）。
    3. **一切都要有出处**：参数出处覆盖到请求的类别集合，资产必须带摘要 ——
       运行创建后重算摘要即可发现"resolve 之后资产被改过"。
    """

    schema_version: str = RUN_CONTRACT_VERSION
    api_version: str = SIM_API_VERSION
    spec_digest: str = UNSIGNED_DIGEST
    executor_id: str = NATIVE_EXECUTOR_ID
    native_runtime_version: str = NATIVE_RUNTIME_VERSION
    protocol_name: str = PROTOCOL_NAME
    protocol_version: int = PROTOCOL_VERSION
    plugin_contract_version: str = PLUGIN_CONTRACT_VERSION

    robot_id: str
    policy_id: str | None = None
    scenario_id: str | None = None
    scenario_schema_version: str | None = None
    scenario_digest: str | None = None

    time_base: RunTimeBase
    duration_s: FiniteFloat = Field(gt=0.0, le=86_400.0)
    seed: int

    assets: tuple[AssetRef, ...] = ()
    sensor_instances: tuple[SensorInstanceSpec, ...] = ()
    policy_artifact: PolicyArtifactRef | None = None
    policy_inputs: tuple[PolicyInputBinding, ...] = ()
    command_provider: CommandProviderSpec | None = None
    recording: RecordingOptions = Field(default_factory=RecordingOptions)
    units: Units = Field(default_factory=Units)
    capabilities: Capabilities
    provenance: tuple[ParamProvenance, ...] = ()
    notes: tuple[str, ...] = ()

    @field_validator("robot_id")
    @classmethod
    def _robot(cls, value: str) -> str:
        return _check_safe_id(value, what="robot_id")

    @field_validator("policy_id", "scenario_id")
    @classmethod
    def _opt_ids(cls, value: str | None) -> str | None:
        return None if value is None else _check_safe_id(value, what="标识")

    @field_validator("scenario_digest", "spec_digest")
    @classmethod
    def _digests(cls, value: str | None) -> str | None:
        return _check_sha256(value, what="摘要")

    @model_validator(mode="after")
    def _version_identity(self) -> "ResolvedRunSpec":
        if self.schema_version != RUN_CONTRACT_VERSION:
            raise ValueError(
                f"schema_version={self.schema_version!r} 与本契约 {RUN_CONTRACT_VERSION!r} 不符"
            )
        if self.api_version != SIM_API_VERSION:
            raise ValueError(f"api_version 必须是 {SIM_API_VERSION!r}")
        if self.executor_id != NATIVE_EXECUTOR_ID:
            raise ValueError(
                f"executor_id={self.executor_id!r}：v2 高级运行只允许原生执行器 {NATIVE_EXECUTOR_ID!r}"
                "（旧 server_mujoco 没有策略闭环，不能冒名）"
            )
        if self.native_runtime_version != NATIVE_RUNTIME_VERSION:
            raise ValueError(f"native_runtime_version 必须是 {NATIVE_RUNTIME_VERSION!r}")
        if self.protocol_version != PROTOCOL_VERSION:
            raise ValueError(
                f"protocol_version={self.protocol_version} 与线协议 {PROTOCOL_VERSION} 不符"
            )
        if self.plugin_contract_version != PLUGIN_CONTRACT_VERSION:
            raise ValueError(
                f"plugin_contract_version={self.plugin_contract_version!r} 与声明模块"
                f" {PLUGIN_CONTRACT_VERSION!r} 不符"
            )
        return self

    @model_validator(mode="after")
    def _time_base_authority(self) -> "ResolvedRunSpec":
        if self.time_base.source != "contract":
            raise ValueError(
                f"time_base.source={self.time_base.source!r}：运行规格只接受来自机器人包 "
                "contract.json 的时间基（legacy_config/missing 会制造第二个频率真值，"
                "例如把 PIE 的隐式 200Hz 当成物理真值）"
            )
        return self

    @model_validator(mode="after")
    def _assets_resolved(self) -> "ResolvedRunSpec":
        if not self.assets:
            raise ValueError("运行规格必须至少有一个资产（机器人模型），否则无从编译")
        keys = [(asset.kind, asset.path) for asset in self.assets]
        if len(keys) != len(set(keys)):
            duplicates = sorted({f"{kind}:{path}" for kind, path in keys if keys.count((kind, path)) > 1})
            raise ValueError(f"资产重复登记：{duplicates}")
        missing = sorted(
            asset.path for asset in self.assets if not asset.sha256
        )
        if missing:
            raise ValueError(
                f"资产缺摘要：{missing}（没有摘要就无法在运行创建后重算并发现资产漂移）"
            )
        kinds = [asset.kind for asset in self.assets]
        if "model_xml" not in kinds:
            raise ValueError("缺少 kind=model_xml 的机器人模型资产")
        if kinds.count("model_xml") > 1:
            raise ValueError("一次运行只允许一个 model_xml（多机器人编排在后续阶段）")
        return self

    @model_validator(mode="after")
    def _instances_resolved(self) -> "ResolvedRunSpec":
        ids = [instance.instance_id for instance in self.sensor_instances]
        if len(ids) != len(set(ids)):
            duplicates = sorted({item for item in ids if ids.count(item) > 1})
            raise ValueError(
                f"重复实例 instance_id={duplicates}（duplicate_instance：同类型可多实例，"
                "但标识必须唯一）"
            )
        for instance in self.sensor_instances:
            definition = _definition_or_raise(instance.plugin_id)
            if definition.capability_level != instance.capability_level:
                raise ValueError(
                    f"实例 {instance.instance_id} 的 capability_level="
                    f"{instance.capability_level!r} 与 catalog 声明"
                    f" {definition.capability_level!r} 不符（不许就地升级）"
                )
            features = set(required_capabilities(instance.plugin_id))
            unknown = sorted(features - set(PROBE_FEATURES))
            if unknown:
                raise ValueError(
                    f"插件 {instance.plugin_id} 声明了未知探测特征 {unknown}"
                    f"（词表 {list(PROBE_FEATURES)}）—— 拼错名字会伪装成'未支持'，禁止"
                )
        # 命令提供器的输入实例必须与这一批实例**同时决议**。放在这里而不是
        # ``_policy_resolved``：后者在没有策略时会提前返回，于是"外置 LiDAR 决策器
        # 引用了不存在的实例"这种规格会被放行（B 类闭环恰恰常常没有策略输入绑定）。
        if self.command_provider is not None:
            by_id = {instance.instance_id: instance for instance in self.sensor_instances}
            for instance_id in self.command_provider.input_instances:
                instance = by_id.get(instance_id)
                if instance is None:
                    raise ValueError(
                        f"命令提供器输入实例 {instance_id} 不存在（必须与传感器实例同一批决议）"
                    )
            provider_features = set(
                provider_required_capabilities(self.command_provider.provider_id)
            )
            unknown_provider = sorted(provider_features - set(PROBE_FEATURES))
            if unknown_provider:
                raise ValueError(f"命令提供器声明了未知探测特征 {unknown_provider}")
        return self

    @model_validator(mode="after")
    def _probe_required(self) -> "ResolvedRunSpec":
        """**没有真实探测就没有运行规格**（fail-closed 的最终落点）。

        "未探测"和"探测说不支持"都必须变成 :class:`ResolutionBlocker`，由解析器返回给
        前端，而不是产出一份"看起来能跑"的规格让运行管理器去试。
        """

        probe = self.capabilities.probe
        if probe is None or not probe.probed:
            raise ValueError(
                "缺少已完成的 native 探测报告：未探测不等于可运行（后续运行管理器负责调用 worker 探测）"
            )
        missing = [
            feature for feature in self.required_engine_features() if not probe.is_supported(feature)
        ]
        if missing:
            raise ValueError(
                f"原生运行时未确认支持 {missing}（state="
                f"{ {feature: probe.state_of(feature) for feature in missing} }）："
                "unknown/unsupported 一律阻断，不放行"
            )
        return self

    @model_validator(mode="after")
    def _policy_resolved(self) -> "ResolvedRunSpec":
        names = [item.name for item in self.policy_inputs]
        if len(names) != len(set(names)):
            raise ValueError(f"策略输入名重复：{sorted({n for n in names if names.count(n) > 1})}")
        if self.policy_id is None:
            if self.policy_artifact is not None or self.policy_inputs:
                raise ValueError("没有 policy_id 却带了策略产物/输入绑定（无主策略）")
            return self
        if self.policy_artifact is None:
            raise ValueError(f"策略 {self.policy_id} 缺少产物引用（policy_onnx）")
        if not self.policy_artifact.metadata_verified:
            raise ValueError(
                "策略元数据未经实际 ONNX 文件核对 —— 只有产物元数据能作为认证依据，"
                "配置里写了形状或按名字猜都不算"
            )
        if not self.policy_inputs:
            raise ValueError(f"策略 {self.policy_id} 没有任何输入绑定，无法构造观测")
        unverified = [item.name for item in self.policy_inputs if not item.verified]
        if unverified:
            raise ValueError(
                f"策略输入 {unverified} 未经 onnx_metadata 认证（verified=False）："
                "解析结果里不允许留未认证项，认证不了的项必须变成阻断项而不是进规格"
            )
        instances = {item.instance_id: item for item in self.sensor_instances}
        for item in self.policy_inputs:
            meta = self.policy_artifact.tensor_meta(item.name)
            if meta is None:
                raise ValueError(
                    f"观测项 {item.name} 不在策略产物实际输入里："
                    f"{[tensor.name for tensor in self.policy_artifact.inputs]}"
                )
            if meta.dtype != item.dtype:
                raise ValueError(
                    f"观测项 {item.name} dtype={item.dtype!r} 与产物元数据 {meta.dtype!r} 不符"
                )
            if len(meta.shape) != len(item.tensor_shape):
                raise ValueError(
                    f"观测项 {item.name} 阶数 {len(item.tensor_shape)} 与产物元数据"
                    f" {list(meta.shape)} 不符"
                )
            for want, got in zip(item.tensor_shape, meta.shape):
                if got == -1 or want == -1:
                    continue
                if want != got:
                    raise ValueError(
                        f"观测项 {item.name} 形状 {list(item.tensor_shape)} 与产物元数据"
                        f" {list(meta.shape)} 不符（第 {item.tensor_shape.index(want)} 维）"
                    )
            if item.source == "sensor":
                assert item.instance_id is not None
                instance = instances.get(item.instance_id)
                if instance is None:
                    raise ValueError(
                        f"观测项 {item.name} 绑定实例 {item.instance_id} 不存在"
                        f"（已解析 {sorted(instances)}）"
                    )
                if item.kind == "depth" and instance.plugin_id != "depth":
                    raise ValueError(
                        f"观测项 {item.name} 声明 kind=depth，但实例 {item.instance_id}"
                        f" 是 {instance.plugin_id}"
                    )
                output_name = item.output
                plugin_definition_for_binding = _definition_or_raise(instance.plugin_id)
                if output_name is None:
                    candidates = [
                        candidate.name
                        for candidate in plugin_definition_for_binding.outputs
                        if candidate.payload_kind == "tensor"
                    ]
                    if len(candidates) != 1:
                        raise ValueError(
                            f"观测项 {item.name} 必须显式声明 output：实例 {item.instance_id}"
                            f"（{instance.plugin_id}）有 {len(candidates)} 个张量输出 {candidates}，"
                            "让解析器去猜'哪一个'就是把绑定错误藏进默认行为"
                        )
                    output_name = candidates[0]
                output = next(
                    (
                        candidate
                        for candidate in plugin_definition_for_binding.outputs
                        if candidate.name == output_name
                    ),
                    None,
                )
                if output is None:
                    raise ValueError(
                        f"插件 {instance.plugin_id} 没有输出 {output_name!r}"
                        f"（观测项 {item.name} 无来源）"
                    )
                if output.payload_kind != "tensor":
                    raise ValueError(
                        f"观测项 {item.name} 不能引用非张量输出 {output.name}"
                        f"（payload_kind={output.payload_kind}）"
                    )
                if not output.is_dynamic():
                    elements = _product(tuple(dim for dim in item.tensor_shape if dim > 0))
                    if elements != output.element_count():
                        raise ValueError(
                            f"观测项 {item.name} 元素数 {elements} 与实例 {item.instance_id}"
                            f" 输出 {output.name} 的 {output.element_count()} 不符"
                            f"（dims={list(output.dims)}）—— 例如 86/106 这类裁剪宽度错配"
                            "会在这里被抓住"
                        )
                if item.history_frames > 1 and output.name == "policy_tensor":
                    raise ValueError(
                        f"policy_tensor 已在插件内完成历史堆叠，观测项 {item.name} 不得再"
                        "声明 history_frames（会叠两层）"
                    )
        return self

    @model_validator(mode="after")
    def _provenance_complete(self) -> "ResolvedRunSpec":
        names = [item.name for item in self.provenance]
        if len(names) != len(set(names)):
            raise ValueError(f"出处记录名重复：{sorted({n for n in names if names.count(n) > 1})}")
        covered = {item.category for item in self.provenance}
        missing = sorted(set(PROVENANCE_REQUIRED) - covered)
        if missing:
            raise ValueError(
                f"参数出处缺少类别 {missing}（每个类别都必须说明来源，否则无法复核决议）"
            )
        return self

    @model_validator(mode="after")
    def _digest_self_check(self) -> "ResolvedRunSpec":
        if self.spec_digest == UNSIGNED_DIGEST:
            return self
        expected = self.compute_digest()
        if self.spec_digest != expected:
            raise ValueError(
                f"spec_digest={self.spec_digest} 与按内容重算的 {expected} 不符："
                "运行规格必须自洽签名（请用 ResolvedRunSpec.with_digest(...)）"
            )
        return self

    # ---- 摘要 --------------------------------------------------------------

    def digest_payload(self) -> dict[str, Any]:
        """参与摘要的内容。

        排除项只有两处，且都是**刻意的**：

        * ``spec_digest`` 自身（否则无法自洽）；
        * ``capabilities.probe.probed_at_unix`` —— 它是"什么时候探的"的墙钟时间，不是
          决议内容。留着它会让同一份决议每次 resolve 都得到不同摘要，
          「先 resolve、再用同一摘要创建运行」这条链就必然失败（探测到的
          **能力集合本身**仍然参与摘要，所以时间被排除不等于结论被排除）。
        """

        payload = self.model_dump(mode="json")
        payload.pop("spec_digest", None)
        probe = payload.get("capabilities", {}).get("probe")
        if isinstance(probe, dict):
            probe.pop("probed_at_unix", None)
        return payload

    def compute_digest(self) -> str:
        """按内容重算摘要。摘要变化 ⟺ 决议内容变化（``notes`` 也参与，避免"只改备注"混过去）。"""

        return canonical_sha256(self.digest_payload())

    def digest_matches(self) -> bool:
        return self.spec_digest == self.compute_digest()

    @classmethod
    def with_digest(cls, **values: Any) -> "ResolvedRunSpec":
        """正规构造入口：先按内容算摘要，再产出自洽签名的不可变规格。"""

        unsigned = cls.model_validate({**values, "spec_digest": UNSIGNED_DIGEST})
        return cls.model_validate({**values, "spec_digest": unsigned.compute_digest()})

    # ---- 查询 --------------------------------------------------------------

    def instance(self, instance_id: str) -> SensorInstanceSpec | None:
        return next(
            (item for item in self.sensor_instances if item.instance_id == instance_id), None
        )

    @property
    def control_hz(self) -> float:
        return self.time_base.control_hz

    @property
    def max_ticks(self) -> int:
        """``duration_s`` 对应的物理 tick 数（向上取整，边界由运行管理器决定收尾）。"""

        return int(math.ceil(self.duration_s * self.time_base.physics_hz))

    def sample_hz(self, instance_id: str) -> float:
        instance = self.instance(instance_id)
        if instance is None:
            raise ValueError(f"未知实例 {instance_id!r}")
        return self.time_base.hz_for_period_ticks(instance.sample_period_ticks)

    def required_engine_features(self) -> tuple[str, ...]:
        """本次规格隐含需要的引擎能力（探测必须逐项确认，缺一项即阻断）。"""

        wanted = set(PROBE_FEATURES_REQUIRED)
        if self.command_provider is not None:
            wanted.update({"event_injection", "raycast"})
        for instance in self.sensor_instances:
            wanted.update(required_capabilities(instance.plugin_id))
        return tuple(sorted(wanted))

    def as_handshake_dict(self) -> dict[str, Any]:
        """WS ``hello`` 的规格部分（实例形状、时间基、单位、协议 —— 前端据此建面板）。"""

        return {
            "spec_digest": self.spec_digest,
            "schema_version": self.schema_version,
            "executor_id": self.executor_id,
            "native_runtime_version": self.native_runtime_version,
            "robot_id": self.robot_id,
            "policy_id": self.policy_id,
            "time_base": self.time_base.as_dict(),
            "duration_s": self.duration_s,
            "max_ticks": self.max_ticks,
            "seed": self.seed,
            "units": self.units.as_dict(),
            "instances": [
                {
                    "instance_id": item.instance_id,
                    "plugin_id": item.plugin_id,
                    "plugin_version": item.plugin_version,
                    "target": item.target,
                    "sample_period_ticks": item.sample_period_ticks,
                    "sample_hz": self.sample_hz(item.instance_id),
                    "max_age_ticks": item.max_age_ticks,
                    "capability_level": item.capability_level,
                    "record": item.record.model_dump(mode="json"),
                }
                for item in self.sensor_instances
            ],
            "policy_inputs": [item.model_dump(mode="json") for item in self.policy_inputs],
            "command_provider": (
                None
                if self.command_provider is None
                else self.command_provider.model_dump(mode="json")
            ),
            "recording": self.recording.budget_dict(),
        }


# --------------------------------------------------------------------------------------
# 运行控制命令 / 排程事件（HTTP 请求体）
# --------------------------------------------------------------------------------------


class RunCommand(_Strict):
    """``POST /api/simulation/v2/runs/{run_id}/commands`` 的请求体。

    **幂等靠** :attr:`transaction_id`：同一事务重放必须返回首次结果（``code="duplicate"``），
    因为 HTTP 超时后前端唯一的补救就是重发。
    **防跨 epoch 生效靠** :attr:`expected_epoch`：不匹配时返回 ``stale_epoch``，
    绝不"照办" —— 重启后的运行里执行一条旧暂停命令会留下无从解释的状态。
    """

    schema_version: str = RUN_CONTRACT_VERSION
    run_id: str
    transaction_id: str
    command: Literal[
        "start", "pause", "resume", "step", "set_command", "switch_policy", "set_recording", "abort"
    ]
    expected_epoch: int = Field(ge=0)
    step_unit: Literal["physics", "control"] | None = None
    steps: int | None = Field(default=None, ge=1, le=100_000)
    command_vector: tuple[FiniteFloat, ...] | None = None
    policy_id: str | None = None
    recording: RecordingOptions | None = None
    reason: str | None = None

    @field_validator("run_id", "transaction_id")
    @classmethod
    def _ids(cls, value: str) -> str:
        return _check_safe_id(value, what="命令标识")

    @field_validator("policy_id")
    @classmethod
    def _policy(cls, value: str | None) -> str | None:
        return None if value is None else _check_safe_id(value, what="policy_id")

    @field_validator("command_vector")
    @classmethod
    def _vector(cls, value: tuple[FiniteFloat, ...] | None) -> tuple[FiniteFloat, ...] | None:
        if value is None:
            return None
        if not 1 <= len(value) <= 8:
            raise ValueError(f"指令向量长度需在 1..8，实为 {len(value)}")
        return value

    @model_validator(mode="after")
    def _check(self) -> "RunCommand":
        if self.schema_version != RUN_CONTRACT_VERSION:
            raise ValueError(f"schema_version 必须是 {RUN_CONTRACT_VERSION!r}")
        step_like = self.command == "step"
        if step_like and (self.step_unit is None or self.steps is None):
            raise ValueError(
                "step 命令必须显式给出 step_unit（physics|control）与 steps："
                "不写就等于让服务器自己决定单步粒度，边界调试时无法复现"
            )
        if not step_like and (self.step_unit is not None or self.steps is not None):
            raise ValueError(f"step_unit/steps 只对 step 命令有意义，当前命令是 {self.command}")
        if self.command == "set_command" and self.command_vector is None:
            raise ValueError("set_command 必须带 command_vector（否则「要设成什么」不可知）")
        if self.command != "set_command" and self.command_vector is not None:
            raise ValueError(f"command_vector 只对 set_command 有效，当前命令是 {self.command}")
        if self.command == "switch_policy" and not self.policy_id:
            raise ValueError("switch_policy 必须给出目标 policy_id")
        if self.command != "switch_policy" and self.policy_id:
            raise ValueError(f"policy_id 只对 switch_policy 有效（当前 {self.command}）")
        if self.command == "set_recording" and self.recording is None:
            raise ValueError("set_recording 必须给出新的记录选项")
        if self.command != "set_recording" and self.recording is not None:
            raise ValueError(f"recording 只对 set_recording 有效（当前 {self.command}）")
        if self.command == "abort" and not (self.reason or "").strip():
            raise ValueError(
                "abort 必须写 reason：结束原因决定「这次失败算系统还是算策略」，不能事后猜"
            )
        return self


class RunCommandResponse(_Strict):
    """命令应答。``duplicate`` 表示事务重放，此时 ``applied_tick``/``status`` 是**首次**执行的结果。"""

    schema_version: str = RUN_CONTRACT_VERSION
    run_id: str
    transaction_id: str
    code: Literal[
        "accepted", "duplicate", "stale_epoch", "invalid_state", "unknown_command", "rejected"
    ]
    status: str
    epoch: int = Field(ge=0)
    applied_tick: int | None = Field(default=None, ge=0)
    detail: str = ""

    @field_validator("status")
    @classmethod
    def _status(cls, value: str) -> str:
        if value not in RUN_STATUSES:
            raise ValueError(f"status={value!r} 不在 {list(RUN_STATUSES)}")
        return value

    @model_validator(mode="after")
    def _check(self) -> "RunCommandResponse":
        if self.code == "accepted" and self.applied_tick is None:
            raise ValueError(
                "accepted 必须给出 applied_tick：调用方要知道这条命令**在哪个 tick** 生效，"
                "否则事件与状态的先后关系无法重建"
            )
        if self.code in ("stale_epoch", "invalid_state", "rejected", "unknown_command"):
            if self.applied_tick is not None:
                raise ValueError(f"code={self.code} 表示没有执行，不得带 applied_tick")
            if not self.detail.strip():
                raise ValueError(f"code={self.code} 必须给出可诊断的 detail")
        return self


#: 事件类型 → 必填载荷键与形状（**唯一**表；:class:`ScheduledEvent` 与文档都从这里出）。
EVENT_PAYLOAD_SPEC: dict[str, dict[str, str]] = {
    "velocity_command": {"vx": "float", "vy": "float", "yaw_rate": "float"},
    "wrench": {"force": "vec3", "torque": "vec3", "body": "str"},
    "sensor_fault": {"instance_id": "id", "state": "fault_state", "duration_ticks": "int"},
    "policy_switch": {"policy_id": "id", "artifact_sha256": "sha256"},
    "run_control": {"action": "str"},
}
#: 可注入的故障状态：``valid``/``disabled``/``dropped`` 不在列 —— 前两者不是故障，
#: 后者是记录侧背压，都由系统自己产生，不接受外部注入。
FAULTABLE_VALIDITIES: tuple[str, ...] = (
    "missing",
    "stale",
    "no_hit",
    "unsupported",
    "fault",
)


class ScheduledEvent(_Strict):
    """``POST /api/simulation/v2/runs/{run_id}/events`` 的请求体（类型化、带执行 tick）。

    ``at_tick`` 是**物理 tick**（不是秒）：秒会因时间基换算产生半 tick 的歧义。
    ``expected_epoch`` 让"重启之后旧事件自动失效"成为契约行为而不是运行管理器里的 if。
    """

    schema_version: str = RUN_CONTRACT_VERSION
    event_id: str
    type: Literal[
        "velocity_command", "wrench", "sensor_fault", "policy_switch", "run_control"
    ]
    expected_epoch: int = Field(ge=0)
    at_tick: int = Field(ge=0)
    duration_ticks: int = Field(default=0, ge=0, le=10_000_000)
    payload: dict[str, Any]
    source: Literal["user", "evaluation", "scenario"] = "user"

    @field_validator("event_id")
    @classmethod
    def _eid(cls, value: str) -> str:
        return _check_safe_id(value, what="event_id")

    @model_validator(mode="after")
    def _check(self) -> "ScheduledEvent":
        if self.schema_version != RUN_CONTRACT_VERSION:
            raise ValueError(f"schema_version 必须是 {RUN_CONTRACT_VERSION!r}")
        spec = EVENT_PAYLOAD_SPEC[self.type]
        if set(self.payload) != set(spec):
            raise ValueError(
                f"事件 {self.type} 载荷键不符：需要 {sorted(spec)}，实为 {sorted(self.payload)}"
                "（多写的键会被静默忽略 —— 那正是最难查的一类 bug）"
            )
        for key, kind in spec.items():
            value = self.payload[key]
            if kind == "float":
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"{self.type}.{key} 需要数值，实为 {value!r}")
                _finite(float(value))
            elif kind == "int":
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(f"{self.type}.{key} 需要非负整数，实为 {value!r}")
            elif kind == "vec3":
                _vec3(value)
            elif kind == "str":
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{self.type}.{key} 需要非空字符串")
            elif kind == "id":
                _check_safe_id(str(value), what=f"{self.type}.{key}")
            elif kind == "sha256":
                if _check_sha256(str(value), what=f"{self.type}.{key}") is None:
                    raise ValueError(f"{self.type}.{key} 缺少摘要")
            elif kind == "fault_state":
                if value not in FAULTABLE_VALIDITIES:
                    raise ValueError(
                        f"{self.type}.{key}={value!r} 不在可注入故障 {list(FAULTABLE_VALIDITIES)}"
                    )
            else:  # pragma: no cover - 表里新增类型时逼调用方显式处理
                raise ValueError(f"内部错误：未知载荷类型 {kind!r}")
        if self.type == "sensor_fault" and self.duration_ticks <= 0:
            raise ValueError(
                "sensor_fault 必须给 duration_ticks：无期限故障会让「这次运行为什么没数据」永远说不清"
            )
        if self.type == "wrench" and self.duration_ticks <= 0:
            raise ValueError("wrench 必须给 duration_ticks（0 = 永久施加，语义上等价于改重力，不允许）")
        return self

    def required_features(self) -> tuple[str, ...]:
        """该事件是否需要额外的引擎能力（射线/接触之类由传感器实例自己声明）。"""

        if self.type == "policy_switch":
            return ("policy_closed_loop", "recurrent_reset")
        return ()


class ScheduledEventResponse(_Strict):
    """事件受理结果。``scheduled`` 只代表"已排程"，真正生效由 WS 的 ``event`` 帧确认。"""

    schema_version: str = RUN_CONTRACT_VERSION
    run_id: str
    event_id: str
    status: Literal["scheduled", "applied", "rejected", "skipped_stale_epoch", "failed"]
    epoch: int = Field(ge=0)
    at_tick: int = Field(ge=0)
    applied_tick: int | None = Field(default=None, ge=0)
    reason: str | None = None

    @field_validator("run_id", "event_id")
    @classmethod
    def _ids(cls, value: str) -> str:
        return _check_safe_id(value, what="标识")

    @model_validator(mode="after")
    def _check(self) -> "ScheduledEventResponse":
        if self.status in ("rejected", "skipped_stale_epoch", "failed") and not self.reason:
            raise ValueError(f"status={self.status} 必须给出 reason（前端据此提示，不能只给状态）")
        if self.status == "applied" and self.applied_tick is None:
            raise ValueError("applied 必须给出实际生效 tick")
        if self.status == "applied" and self.applied_tick is not None and self.applied_tick < self.at_tick:
            raise ValueError(
                f"applied_tick={self.applied_tick} 早于请求 at_tick={self.at_tick}（不可能）"
            )
        if self.status == "scheduled" and self.applied_tick is not None:
            raise ValueError("尚未生效的事件不得带 applied_tick")
        return self


# --------------------------------------------------------------------------------------
# 下行消息（WS 帧的 JSON 头/JSON 载荷形状 —— **唯一**定义处）
# --------------------------------------------------------------------------------------


class SensorHealth(_Strict):
    """一个实例的遥测健康度（前端角标、记录器背压判断都读它）。"""

    instance_id: str
    plugin_id: str
    epoch: int = Field(ge=0)
    last_sample_tick: int | None = Field(default=None, ge=0)
    last_available_tick: int | None = Field(default=None, ge=0)
    last_seq: int | None = Field(default=None, ge=0)
    last_validity: Literal[
        "valid", "missing", "stale", "no_hit", "dropped", "disabled", "unsupported", "fault"
    ] = "valid"
    sample_period_ticks: int = Field(ge=1)
    max_age_ticks: int = Field(default=0, ge=0)
    samples_total: int = Field(default=0, ge=0)
    samples_dropped: int = Field(default=0, ge=0)
    samples_invalid: int = Field(default=0, ge=0)
    consecutive_faults: int = Field(default=0, ge=0)
    note: str | None = None

    @field_validator("instance_id", "plugin_id")
    @classmethod
    def _ids(cls, value: str) -> str:
        return _check_safe_id(value, what="实例标识")

    @model_validator(mode="after")
    def _check(self) -> "SensorHealth":
        if self.last_available_tick is not None and self.last_sample_tick is not None:
            if self.last_available_tick < self.last_sample_tick:
                raise ValueError("last_available_tick 不得早于 last_sample_tick")
        if self.samples_dropped > self.samples_total:
            raise ValueError("丢弃数不得大于样本总数")
        if self.samples_invalid > self.samples_total:
            raise ValueError("无效样本数不得大于样本总数")
        return self

    def age_ticks(self, now_tick: int) -> int | None:
        return None if self.last_sample_tick is None else now_tick - self.last_sample_tick


class RunSnapshot(_Strict):
    """WS ``status`` 帧的载荷（**不是**权威状态，权威在 worker；快照允许滞后一个 tick）。"""

    schema_version: str = RUN_CONTRACT_VERSION
    run_id: str
    status: str
    epoch: int = Field(ge=0)
    tick: int = Field(ge=0)
    sim_time: FiniteFloat = Field(ge=0.0)
    control_step: int | None = Field(default=None, ge=0)
    base_pos: Vec3 | None = None
    base_quat_wxyz: QuatWxyz | None = None
    base_lin_vel_world: Vec3 | None = None
    command: tuple[FiniteFloat, ...] | None = None
    action: tuple[FiniteFloat, ...] | None = None
    fell: bool | None = None
    real_time_factor: FiniteFloat | None = Field(default=None, gt=0.0)
    sensors: tuple[SensorHealth, ...] = ()
    recording_bytes_written: int = Field(default=0, ge=0)
    note: str | None = None

    @field_validator("run_id")
    @classmethod
    def _rid(cls, value: str) -> str:
        return _check_safe_id(value, what="run_id")

    @field_validator("status")
    @classmethod
    def _status(cls, value: str) -> str:
        if value not in RUN_STATUSES:
            raise ValueError(f"status={value!r} 不在 {list(RUN_STATUSES)}")
        return value

    @model_validator(mode="after")
    def _check(self) -> "RunSnapshot":
        ids = [item.instance_id for item in self.sensors]
        if len(ids) != len(set(ids)):
            raise ValueError(f"快照里实例健康度重复：{sorted({i for i in ids if ids.count(i) > 1})}")
        if self.schema_version != RUN_CONTRACT_VERSION:
            raise ValueError(f"schema_version 必须是 {RUN_CONTRACT_VERSION!r}")
        return self

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_RUN_STATUSES


class RunEvent(_Strict):
    """WS ``event`` 帧：某事件**实际发生了什么**（与 :class:`ScheduledEventResponse` 的受理回执不同）。"""

    schema_version: str = RUN_CONTRACT_VERSION
    run_id: str
    epoch: int = Field(ge=0)
    tick: int = Field(ge=0)
    sim_time: FiniteFloat = Field(ge=0.0)
    event_id: str | None = None
    type: str
    status: Literal["scheduled", "applied", "rejected", "skipped_stale_epoch", "failed"]
    detail: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("run_id")
    @classmethod
    def _rid(cls, value: str) -> str:
        return _check_safe_id(value, what="run_id")

    @field_validator("type")
    @classmethod
    def _type(cls, value: str) -> str:
        if value not in EVENT_TYPES:
            raise ValueError(f"事件类型 {value!r} 不在 {list(EVENT_TYPES)}（不留自由类型）")
        return value

    @model_validator(mode="after")
    def _check(self) -> "RunEvent":
        _assert_finite_tree(self.payload, what="事件载荷")
        if self.status in ("rejected", "failed", "skipped_stale_epoch") and not self.detail.strip():
            raise ValueError(f"status={self.status} 必须给出 detail")
        return self


class RunError(_Strict):
    """WS ``error`` 帧与 ``GET /runs/{id}`` 的 ``error`` 字段（同一形状，避免两套错误）。"""

    schema_version: str = RUN_CONTRACT_VERSION
    run_id: str | None = None
    epoch: int = Field(default=0, ge=0)
    tick: int | None = Field(default=None, ge=0)
    code: RunErrorCode
    message: str
    recoverable: bool = False
    source: Literal["control_plane", "worker", "protocol", "resolver"] = "worker"
    detail: dict[str, Any] = Field(default_factory=dict)

    @field_validator("run_id")
    @classmethod
    def _rid(cls, value: str | None) -> str | None:
        return None if value is None else _check_safe_id(value, what="run_id")

    @model_validator(mode="after")
    def _check(self) -> "RunError":
        if not self.message.strip():
            raise ValueError("错误必须有可读 message（但不能只靠它编程，请读 code）")
        _assert_finite_tree(self.detail, what="错误 detail")
        return self


class RunFinal(_Strict):
    """WS ``bye`` 帧 / 运行收尾记录。"""

    schema_version: str = RUN_CONTRACT_VERSION
    run_id: str
    status: str
    epoch: int = Field(ge=0)
    end_reason: str
    start_tick: int = Field(default=0, ge=0)
    end_tick: int = Field(ge=0)
    sim_time: FiniteFloat = Field(ge=0.0)
    episode_id: str | None = None
    spec_digest: str | None = None
    manifest_digest: str | None = None
    bytes_written: int = Field(default=0, ge=0)
    message: str = ""

    @field_validator("run_id")
    @classmethod
    def _rid(cls, value: str) -> str:
        return _check_safe_id(value, what="run_id")

    @field_validator("status")
    @classmethod
    def _status(cls, value: str) -> str:
        if value not in TERMINAL_RUN_STATUSES:
            raise ValueError(
                f"status={value!r}：收尾记录只能是终态 {sorted(TERMINAL_RUN_STATUSES)}"
            )
        return value

    @field_validator("end_reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        if value not in RUN_END_REASONS:
            raise ValueError(f"end_reason={value!r} 不在 {list(RUN_END_REASONS)}")
        return value

    @field_validator("spec_digest", "manifest_digest")
    @classmethod
    def _digests(cls, value: str | None) -> str | None:
        return _check_sha256(value, what="收尾摘要")

    @model_validator(mode="after")
    def _check(self) -> "RunFinal":
        if self.end_tick < self.start_tick:
            raise ValueError("end_tick 早于 start_tick")
        if self.status == "finalized" and self.end_reason in SYSTEM_FAILURE_REASONS:
            raise ValueError(
                f"系统失败({self.end_reason})不能记成 finalized —— 正常收尾与系统失败必须分开"
            )
        if self.status in ("failed", "aborted") and self.end_reason not in SYSTEM_FAILURE_REASONS.union(
            {"termination_condition", "fall", "policy_failure", "user_abort", "target_reached"}
        ):
            raise ValueError(f"end_reason={self.end_reason} 与 status={self.status} 不匹配")
        return self

    @property
    def is_system_failure(self) -> bool:
        """评测口径：系统失败**不计入**策略成绩。"""

        return self.end_reason in SYSTEM_FAILURE_REASONS


class RunHandshake(_Strict):
    """WS 连接后的第一帧（**前端与管理器共用**本模型的字段名与限额）。

    前端在收到握手之前不允许解任何样本帧：``limits`` 决定它该给环形缓冲开多大、
    ``frames`` 决定它怎么切包 —— 两边各写一份常数迟早会不一致。
    """

    schema_version: str = RUN_CONTRACT_VERSION
    protocol_name: str = PROTOCOL_NAME
    protocol_version: int = PROTOCOL_VERSION
    run_id: str
    epoch: int = Field(ge=0)
    status: str
    spec_digest: str
    from_tick: int = Field(default=0, ge=0)
    time_base: dict[str, Any]
    units: dict[str, str] = Field(default_factory=lambda: Units().as_dict())
    coord_system: str = COORD_SYSTEM_DOC
    quat_order: Literal["wxyz"] = QUAT_ORDER  # type: ignore[assignment]
    limits: dict[str, Any] = Field(default_factory=protocol_limits)
    spec: dict[str, Any] = Field(default_factory=dict)
    executor_id: str = NATIVE_EXECUTOR_ID
    native_runtime_version: str = NATIVE_RUNTIME_VERSION
    resume_from_seq: int = Field(default=0, ge=0)

    @field_validator("run_id")
    @classmethod
    def _rid(cls, value: str) -> str:
        return _check_safe_id(value, what="run_id")

    @field_validator("spec_digest")
    @classmethod
    def _sd(cls, value: str) -> str:
        checked = _check_sha256(value, what="spec_digest")
        if checked is None:
            raise ValueError("握手必须带 spec_digest（前端据此确认这是它 resolve 过的那份规格）")
        return checked

    @model_validator(mode="after")
    def _check(self) -> "RunHandshake":
        if self.protocol_name != PROTOCOL_NAME or self.protocol_version != PROTOCOL_VERSION:
            raise ValueError(
                f"握手协议 {self.protocol_name}/{self.protocol_version} 与本模块 "
                f"{PROTOCOL_NAME}/{PROTOCOL_VERSION} 不符（版本不匹配要拒绝连接，不要兼容猜测）"
            )
        if self.status not in RUN_STATUSES:
            raise ValueError(f"status={self.status!r} 不在 {list(RUN_STATUSES)}")
        for key in ("physics_hz", "control_decimation", "control_hz", "source"):
            if key not in self.time_base:
                raise ValueError(f"time_base 缺少 {key!r}")
        if self.time_base.get("source") != "contract":
            raise ValueError("握手里的时间基必须来自 contract（否则前端展示的频率就不是真的）")
        header_max = self.limits.get("header_max_bytes", 0)
        payload_max = self.limits.get("payload_max_bytes", 0)
        own = protocol_limits()
        if not 0 < header_max <= own["header_max_bytes"]:
            raise ValueError(
                f"header_max_bytes={header_max} 超出本端可接受上限 {own['header_max_bytes']}"
            )
        if not 0 < payload_max <= own["payload_max_bytes"]:
            raise ValueError(f"payload_max_bytes={payload_max} 超出 {own['payload_max_bytes']}")
        if self.executor_id != NATIVE_EXECUTOR_ID:
            raise ValueError(f"executor_id 必须是 {NATIVE_EXECUTOR_ID!r}")
        return self


# --------------------------------------------------------------------------------------
# WS 流契约（唯一定义，前后端都读这里）
# --------------------------------------------------------------------------------------


def ws_stream_contract() -> dict[str, Any]:
    """``WS /api/simulation/v2/runs/{run_id}/stream`` 的**固定形状**（唯一真值）。

    方向：**只做下行**（状态/事件/样本/错误/收尾）。所有上行控制走 HTTP
    ``POST .../commands`` 与 ``POST .../events`` —— 同一件事有两条通道就会产生
    "哪条先到"的未定义行为，所以这里刻意只留一条。

    返回的字典本身就是给前端与文档的机器可读说明（由 :func:`protocol_limits` 派生，
    不复述任何数字）。
    """

    limits = protocol_limits()
    return {
        "path": f"/api/simulation/{SIM_API_VERSION}/runs/{{run_id}}/stream",
        "direction": "downlink_only",
        "framing": limits["framing"],
        "frame_common_fields": list(limits["frame_common_fields"]),
        "message_types": list(limits["message_types"]),
        "content_types": list(limits["content_types"]),
        "header_max_bytes": limits["header_max_bytes"],
        "payload_max_bytes": limits["payload_max_bytes"],
        "first_frame": "hello",
        "first_frame_model": "RunHandshake",
        "ordering": {
            "seq": "每 epoch 从 0 递增 1，跨 epoch 重置；乱序即协议违规",
            "epoch": "重连/复位会推进 epoch；epoch 变小说明对端行为错误",
            "resume": "重连时带 ?from_seq=N，服务端从该序号之后续流（缺口以 status 帧说明）",
        },
        "uplink": {
            "commands": f"POST /api/simulation/{SIM_API_VERSION}/runs/{{run_id}}/commands",
            "events": f"POST /api/simulation/{SIM_API_VERSION}/runs/{{run_id}}/events",
            "control_framing": "JSONL（每行一条，见 contracts.simulation_protocol.iter_control）",
        },
        "sample_frame": {
            "header_extra": [
                "instance_id", "output", "sample_tick", "available_tick",
                "shape", "dtype", "unit", "reference_frame", "source", "validity",
                "sample_seq",
            ],
            "empty_validities": sorted(SAMPLE_EMPTY_VALIDITIES),
            "rule": "validity!=valid 时载荷是 JSON 说明，且头里不得带 shape/dtype",
        },
        "log_isolation": "stdout 只走协议帧；日志只走 stderr（混入即协议违规）",
    }


# --------------------------------------------------------------------------------------
# HTTP 请求/响应模型（下游路由**必须**使用这些形状，不再自拟字段）
# --------------------------------------------------------------------------------------


class ExecutorInfo(_Strict):
    """v2 catalog 里的一个执行器（只描述**原生**执行器；旧执行器由路由从
    :mod:`backend.executors` 自行追加，避免这里镜像一份会漂移的副本）。"""

    executor_id: str = NATIVE_EXECUTOR_ID
    native_runtime_version: str = NATIVE_RUNTIME_VERSION
    policy_closed_loop: Literal[True] = True
    sensor_capture: Literal["registered_only", "implemented", "verified"] = "registered_only"
    transport: Literal["subprocess_worker"] = "subprocess_worker"
    notes: str = (
        "v2 只登记原生执行器；旧 server_mujoco / WASM 基础仿真没有策略闭环，"
        "其权威登记仍在 backend/executors.py，由路由按需附加"
    )

    @model_validator(mode="after")
    def _check(self) -> "ExecutorInfo":
        if self.executor_id != NATIVE_EXECUTOR_ID:
            raise ValueError(f"v2 执行器 id 必须是 {NATIVE_EXECUTOR_ID!r}（不冒称旧执行器）")
        if self.native_runtime_version != NATIVE_RUNTIME_VERSION:
            raise ValueError(f"版本必须是 {NATIVE_RUNTIME_VERSION!r}")
        return self


class RunCatalogResponse(_Strict):
    """``GET /api/simulation/v2/catalog`` 的响应（唯一一份插件/限制/枚举来源）。"""

    schema_version: str = RUN_CONTRACT_VERSION
    api_version: str = SIM_API_VERSION
    run_contract_version: str = RUN_CONTRACT_VERSION
    plugin_contract_version: str = PLUGIN_CONTRACT_VERSION
    native_runtime_version: str = NATIVE_RUNTIME_VERSION
    executors: tuple[ExecutorInfo, ...] = Field(default_factory=lambda: (ExecutorInfo(),))
    sensor_plugins: dict[str, Any] = Field(default_factory=plugin_catalog_payload)
    protocol: dict[str, Any] = Field(default_factory=protocol_limits)
    stream: dict[str, Any] = Field(default_factory=ws_stream_contract)
    units: dict[str, str] = Field(default_factory=lambda: Units().as_dict())
    coord_system: str = COORD_SYSTEM_DOC
    quat_order: str = QUAT_ORDER
    capability_levels: tuple[str, ...] = CAPABILITY_LEVELS
    probe_features: tuple[str, ...] = PROBE_FEATURES
    run_statuses: tuple[str, ...] = RUN_STATUSES
    command_types: tuple[str, ...] = COMMAND_TYPES
    event_types: tuple[str, ...] = EVENT_TYPES
    sample_validity: tuple[str, ...] = SAMPLE_VALIDITY
    resolution_blockers: tuple[str, ...] = RESOLUTION_BLOCKERS
    recording_defaults: dict[str, Any] = Field(
        default_factory=lambda: RecordingOptions().budget_dict()
    )
    probe: NativeProbeReport | None = None

    @model_validator(mode="after")
    def _check(self) -> "RunCatalogResponse":
        if self.api_version != SIM_API_VERSION:
            raise ValueError("api_version 不匹配")
        if self.probe is not None and self.probe.probed:
            levels = self.sensor_plugins.get("sensors", [])
            observed = self.probe.capability_levels
            for entry in levels:
                plugin_id = entry.get("plugin_id")
                declared = entry.get("capability_level")
                seen = observed.get(plugin_id) if isinstance(plugin_id, str) else None
                if seen is None:
                    continue
                if CAPABILITY_LEVELS.index(seen) > CAPABILITY_LEVELS.index(str(declared)):
                    raise ValueError(
                        f"catalog 里插件 {plugin_id} 声明 {declared}，但探测观测到 {seen}："
                        "两处不一致必须修声明，禁止用观测值偷偷升级"
                    )
        return self


class ResolveOptions(_Strict):
    """resolve 的可选决议参数（**不携带时间基/频率**：那是机器人包的事实，不是请求者的意见）。

    这里刻意**没有** ``strict_asset_digest`` 这类开关：:class:`ResolvedRunSpec` 无条件
    要求每个资产带摘要（否则无法在运行创建后重算发现漂移），一个「可以不算摘要」的
    旋钮只会承诺它做不到的事。唯一有意义的开关是 :attr:`require_probe` ——
    ``False`` 表示「只做声明层校验」（见 :mod:`backend.simulation_resolver`），
    它同样**不会**产出规格，因为无探测报告的规格在类型层就构造不出来。
    """

    robot_id: str | None = None
    policy_id: str | None = None
    seed: int | None = None
    duration_s: FiniteFloat | None = Field(default=None, gt=0.0, le=86_400.0)
    recording: RecordingOptions | None = None
    require_probe: bool = True

    @field_validator("robot_id", "policy_id")
    @classmethod
    def _ids(cls, value: str | None) -> str | None:
        return None if value is None else _check_safe_id(value, what="标识")


class ResolveRequest(_Strict):
    """``POST /api/simulation/v2/resolve`` 的请求体。

    :attr:`scenario` 原样携带**旧** :class:`contracts.scenario_contract.ScenarioContract`
    的 JSON（本模块不导入它，以免数据契约互相牵扯）；路由层负责用旧模型解析它，
    因此 v1 场景文件到这里依然可用 —— 兼容性由旧模型保证，不由本模型复制字段。
    """

    schema_version: str = RUN_CONTRACT_VERSION
    scenario: dict[str, Any] = Field(default_factory=dict)
    options: ResolveOptions = Field(default_factory=ResolveOptions)

    @model_validator(mode="after")
    def _check(self) -> "ResolveRequest":
        if self.schema_version != RUN_CONTRACT_VERSION:
            raise ValueError(
                f"resolve 请求 schema_version={self.schema_version!r} 与本契约 "
                f"{RUN_CONTRACT_VERSION!r} 不符（请前端先升级，不要静默兼容）"
            )
        _assert_finite_tree(self.scenario, what="scenario")
        return self


class ResolveResponse(_Strict):
    """``POST /api/simulation/v2/resolve`` 的响应。

    ``ok=False`` 时 ``spec`` 必为 ``None``：半份规格比没有规格更危险
    （运行管理器可能拿它去创建运行）。阻断项永远成结构化列表返回，
    不塞进 HTTP 状态码文案里。
    """

    schema_version: str = RUN_CONTRACT_VERSION
    ok: bool
    spec: ResolvedRunSpec | None = None
    spec_digest: str | None = None
    blockers: tuple[ResolutionBlocker, ...] = ()
    warnings: tuple[str, ...] = ()
    capabilities: Capabilities | None = None
    protocol: dict[str, Any] = Field(default_factory=protocol_limits)

    @field_validator("spec_digest")
    @classmethod
    def _sd(cls, value: str | None) -> str | None:
        return _check_sha256(value, what="spec_digest")

    @model_validator(mode="after")
    def _check(self) -> "ResolveResponse":
        if self.ok:
            if self.spec is None:
                raise ValueError("ok=True 必须给出 spec")
            if self.blockers:
                raise ValueError("ok=True 却带阻断项（自相矛盾）")
            if self.spec_digest is not None and self.spec_digest != self.spec.spec_digest:
                raise ValueError("响应里的 spec_digest 与规格自带摘要不符")
        else:
            if self.spec is not None:
                raise ValueError("ok=False 不得返回可用规格（避免半份配置被拿去创建运行）")
            if not self.blockers:
                raise ValueError(
                    "ok=False 必须至少给一条结构化阻断项，否则调用方只能看到「解析失败」四个字"
                )
        return self


class CreateRunRequest(_Strict):
    """``POST /api/simulation/v2/runs``。只认**摘要**，不在这里重新解析。

    ``spec`` 可以省略（表示"用服务器缓存的那份"），但 ``spec_digest`` 必须与之一致；
    ``verify_assets=True`` 时运行管理器**必须**重算资产摘要，任一不符即拒绝创建
    （这就是"resolve 之后资产又变了"的拦截点）。
    """

    schema_version: str = RUN_CONTRACT_VERSION
    spec_digest: str
    spec: ResolvedRunSpec | None = None
    transaction_id: str
    auto_start: bool = False
    verify_assets: bool = True

    @field_validator("spec_digest", "transaction_id")
    @classmethod
    def _ids(cls, value: str) -> str:
        if len(value) == 64:
            return _check_sha256(value, what="spec_digest") or value
        return _check_safe_id(value, what="transaction_id")

    @model_validator(mode="after")
    def _check(self) -> "CreateRunRequest":
        if len(self.spec_digest) != 64:
            raise ValueError("spec_digest 必须是 64 位 sha256")
        if self.spec is not None and self.spec.spec_digest != self.spec_digest:
            raise ValueError(
                "内联 spec 的摘要与 spec_digest 不符（要么带对了要么别带，不许两份）"
            )
        return self


class RunCreatedResponse(_Strict):
    """``POST /api/simulation/v2/runs`` 的响应。"""

    schema_version: str = RUN_CONTRACT_VERSION
    run_id: str
    status: str
    epoch: int = Field(default=0, ge=0)
    spec_digest: str
    transaction_id: str
    stream_path: str
    created_at_unix: FiniteFloat = Field(ge=0.0)
    blockers: tuple[ResolutionBlocker, ...] = ()

    @field_validator("run_id", "transaction_id")
    @classmethod
    def _ids(cls, value: str) -> str:
        return _check_safe_id(value, what="标识")

    @field_validator("status")
    @classmethod
    def _status(cls, value: str) -> str:
        if value not in RUN_STATUSES:
            raise ValueError(f"status={value!r} 不在 {list(RUN_STATUSES)}")
        return value

    @model_validator(mode="after")
    def _check(self) -> "RunCreatedResponse":
        if self.spec_digest is None or len(self.spec_digest) != 64:
            raise ValueError("必须回带 spec_digest（前端据此确认创建的是它 resolve 的那份规格）")
        expected = f"/api/simulation/{SIM_API_VERSION}/runs/{self.run_id}/stream"
        if self.stream_path != expected:
            raise ValueError(f"stream_path={self.stream_path!r} 必须是 {expected!r}")
        return self


class RunDetailResponse(_Strict):
    """``GET /api/simulation/v2/runs/{run_id}``：状态、当前 episode、能力、错误、最新快照。"""

    schema_version: str = RUN_CONTRACT_VERSION
    run_id: str
    status: str
    epoch: int = Field(ge=0)
    spec_digest: str
    capabilities: Capabilities
    snapshot: RunSnapshot | None = None
    error: RunError | None = None
    episode_id: str | None = None
    recording_bytes_written: int = Field(default=0, ge=0)
    created_at_unix: FiniteFloat = Field(ge=0.0)
    last_command: RunCommandResponse | None = None

    @field_validator("run_id")
    @classmethod
    def _rid(cls, value: str) -> str:
        return _check_safe_id(value, what="run_id")

    @field_validator("status")
    @classmethod
    def _status(cls, value: str) -> str:
        if value not in RUN_STATUSES:
            raise ValueError(f"status={value!r} 不在 {list(RUN_STATUSES)}")
        return value

    @model_validator(mode="after")
    def _check(self) -> "RunDetailResponse":
        if self.status == "running" and self.snapshot is None:
            raise ValueError("running 的运行必须能给出最新快照（没有快照=状态可疑，宁可报 failed）")
        if self.snapshot is not None:
            if self.snapshot.run_id != self.run_id:
                raise ValueError("快照 run_id 与请求不一致")
            if self.snapshot.epoch != self.epoch:
                raise ValueError("快照 epoch 与运行 epoch 不一致（响应自相矛盾）")
            if self.snapshot.status != self.status:
                raise ValueError("快照 status 与运行 status 不一致")
        return self


class EpisodeManifestResponse(_Strict):
    """``GET /api/episode/v2/{episode_id}/manifest``。

    :attr:`allowed_chunk_ids` 是**下载白名单**：``GET .../chunks/{chunk_id}`` 只接受
    出现在这里的 id，服务端用 :meth:`RecordingChunkIndex.allowed_path` 解析路径，
    绝不接受调用方拼出来的路径。
    """

    schema_version: str = RUN_CONTRACT_VERSION
    episode_id: str
    manifest: EpisodeManifest
    allowed_chunk_ids: tuple[str, ...] = ()
    chunk_limit_bytes: int = Field(default=64 * 1024 * 1024, ge=1)

    @field_validator("episode_id")
    @classmethod
    def _eid(cls, value: str) -> str:
        return _check_safe_id(value, what="episode_id")

    @model_validator(mode="after")
    def _check(self) -> "EpisodeManifestResponse":
        if self.manifest.episode_id != self.episode_id:
            raise ValueError("响应 episode_id 与清单不一致")
        index_ids = tuple(chunk.chunk_id for chunk in self.manifest.index.chunks)
        if self.allowed_chunk_ids != index_ids:
            raise ValueError(
                "allowed_chunk_ids 必须与清单块索引**逐一同序**（不一致就等于给了错误的白名单）"
            )
        return self


class ChunkDownload(_Strict):
    """``GET /api/episode/v2/{episode_id}/chunks/{chunk_id}`` 的**元数据**（响应体是字节流）。

    ``media_type`` 由块类型决定；客户端下载后必须用 :attr:`sha256` 核对，
    这使"白名单 + 校验和"两件事在同一个类型里说清楚。
    """

    schema_version: str = RUN_CONTRACT_VERSION
    episode_id: str
    chunk_id: str
    path: str
    sha256: str
    size_bytes: int = Field(ge=1)
    media_type: Literal["application/octet-stream", "image/png", "application/json"]

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        return safe_relative_path(value, what="块路径")


#: 运行状态 → 允许的下一步（运行管理器的状态机表，**唯一**声明处）。
RUN_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "draft": ("resolved", "failed", "aborted"),
    "resolved": ("provisioning", "failed", "aborted"),
    "provisioning": ("ready", "failed", "aborted"),
    "ready": ("running", "failed", "aborted"),
    "running": ("paused", "stepping", "finishing", "failed", "aborted"),
    "paused": ("running", "stepping", "finishing", "failed", "aborted"),
    "stepping": ("paused", "running", "finishing", "failed", "aborted"),
    "finishing": ("finalized", "failed", "aborted"),
    "finalized": (),
    "failed": (),
    "aborted": (),
}


def assert_status_transition(current: str, following: str) -> None:
    """状态迁移检查（``ValueError`` = 非法迁移）。终态不接受任何迁移。"""

    if current not in RUN_STATUSES:
        raise ValueError(f"未知运行状态 {current!r}")
    if following not in RUN_TRANSITIONS.get(current, ()):
        raise ValueError(
            f"非法状态迁移 {current} → {following}（允许 "
            f"{list(RUN_TRANSITIONS.get(current, ()))}）"
        )


# ``EpisodeManifest.spec`` 前向引用（类型定义在本模块后段），此处一次性重建。
EpisodeManifest.model_rebuild()
