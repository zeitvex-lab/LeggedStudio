"""原生高级仿真的**运行时接口协议**（未来实现方必须满足的形状）。

这里只有协议（:class:`typing.Protocol`）与阶段常量，**没有任何实现**：
实现方分别在后续模块里 —— 原生 worker 的传感器适配器、策略运行时（onnxruntime）、
记录器（分块 NPZ/PNG）。把接口先钉死的原因是三方要能并行开发而**不必互相猜**：
谁在什么阶段被调用、必须返回什么、失败时该抛什么，全部写在类型里。

生命周期六阶段（**顺序即约束**）
--------------------------------
``prepare`` → ``bind`` → ``reset`` → ``on_physics_substep`` → ``sample`` → ``dispose``

* :func:`SensorAdapterProtocol.prepare` —— **编译前**：只允许读声明（插件参数、期望输出、
  需要的 MJCF 片段/传感器需求）。此阶段拿不到 ``mjModel``，因此**不可能**误查索引。
* :func:`SensorAdapterProtocol.bind` —— **编译后**：给定已编译的模型/数据，解析并缓存
  joint/site/body/tex 索引。所有"查不到就报错"必须发生在这里，而不是每 tick 查一次。
  同类型多实例由 ``instance_id`` 区分：每个实例**独立** bind（各自一份索引与随机流）。
* :func:`SensorAdapterProtocol.reset` —— 每个 epoch 开始（含重启/重连）清状态：历史缓冲、
  上次采样 tick、随机流按 ``seed + instance_id`` 重置。
* :func:`SensorAdapterProtocol.on_physics_substep` —— 每个**物理子步**调用一次（500 Hz），
  用来做高频积分/缓存（如 IMU 偏置、接触峰值累积）。不允许在此做渲染。
* :func:`SensorAdapterProtocol.sample` —— 只在**该实例的采样 tick** 被调用（由调度器按
  ``sample_period_ticks`` 决定），返回 ``SampleEnvelope | None``（``None`` = 本 tick 该实例
  未启用；"没有数据"必须用带 ``validity`` 的 envelope 表达，不能返回 None 让上层猜）。
* :func:`SensorAdapterProtocol.dispose` —— 释放渲染缓冲/句柄。必须可重复调用（幂等）。

失败语义
--------
适配器只抛 :class:`AdapterError`（带稳定 ``code`` 与 ``recoverable``）。
调度器据此把该实例标记为 ``fault``（样本有效性），而不是让整次运行崩掉 ——
一个坏传感器应当表现为"这一路没有数据"，这正是 ``validity`` 存在的理由。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:  # 只在类型检查期引用，避免"接口模块依赖数据契约"的循环
    from contracts.simulation_run_contract import (
        NativeProbeReport,
        PolicyInputBinding,
        ResolvedRunSpec,
        SampleEnvelope,
    )
    from contracts.sensor_plugin_contract import SensorPluginDefinition

__all__ = [
    "AdapterError",
    "LIFECYCLE_PHASES",
    "PolicyRuntimeError",
    "PolicyRuntimeProtocol",
    "RecorderSinkProtocol",
    "RuntimePhase",
    "SensorAdapterProtocol",
    "SubstepContext",
    "CommandProviderProtocol",
    "NativeProbe",
    "NativeProbeResult",
    "probe_is_supported",
]


class RuntimePhase:
    """生命周期阶段名（顺序即调用约束）。"""

    PREPARE = "prepare"
    BIND = "bind"
    RESET = "reset"
    PHYSICS_SUBSTEP = "physics_substep"
    SAMPLE = "sample"
    DISPOSE = "dispose"


#: 阶段顺序表。测试据此断言"没有实现可以跳过 bind 直接 sample"。
LIFECYCLE_PHASES: tuple[str, ...] = (
    RuntimePhase.PREPARE,
    RuntimePhase.BIND,
    RuntimePhase.RESET,
    RuntimePhase.PHYSICS_SUBSTEP,
    RuntimePhase.SAMPLE,
    RuntimePhase.DISPOSE,
)


class AdapterError(RuntimeError):
    """传感器适配器错误。``code`` 稳定可枚举（供记录与前端提示），``recoverable`` 决定调度器是否重试。"""

    def __init__(self, code: str, message: str, *, recoverable: bool = True) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.recoverable = recoverable


class PolicyRuntimeError(RuntimeError):
    """策略运行时错误（加载/元数据不匹配/推理失败）。推理失败一律不可静默跳过。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code


# --------------------------------------------------------------------------------------
# 物理子步上下文
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SubstepContext:
    """传给适配器的最小物理上下文。**故意不给 ``data``/``model`` 裸对象的可写视图**：
    写状态是运行引擎的职责，传感器只读，否则"传感器改了机器人"这类 bug 无从追查。
    """

    tick: int
    sim_time: float
    epoch: int
    model: Any = None
    data: Any = None
    extras: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.tick < 0 or self.sim_time < 0.0 or self.epoch < 0:
            raise AdapterError("bad_context", "tick/sim_time/epoch 必须非负", recoverable=False)
        if self.sim_time != self.sim_time:
            raise AdapterError("bad_context", "sim_time 非有限", recoverable=False)


# --------------------------------------------------------------------------------------
# 传感器适配器
# --------------------------------------------------------------------------------------


@runtime_checkable
class SensorAdapterProtocol(Protocol):
    """一个**传感器实例**的适配器（实例化后与 ``instance_id`` 一一对应）。

    实现必须支持：同一 ``plugin_id`` 多实例、任意整数采样周期、噪声与延迟（由
    ``declared.noise`` / ``declared.latency`` 给出，**不是**适配器自己写死的）。
    """

    #: 适配器构造后必须填好这三项，调度器据此核对"声明与实现是否同一个插件"。
    @property
    def instance_id(self) -> str: ...  # pragma: no cover - 协议

    @property
    def plugin_id(self) -> str: ...  # pragma: no cover

    @property
    def plugin_version(self) -> str: ...  # pragma: no cover

    def prepare(self, definition: "SensorPluginDefinition") -> Sequence[str]:
        """编译前准备。返回**该实例需要引擎提供的能力名**（如 ``("raycast",)`` /
        ``("offscreen_render",)``），供解析器与 probe 结果对照：需要而未支持的 → 阻断。"""
        ...  # pragma: no cover

    def bind(self, spec: "ResolvedRunSpec", context: SubstepContext) -> None:
        """编译后绑定：解析并缓存索引；查不到目标即抛 :class:`AdapterError`（fail-closed）。"""
        ...  # pragma: no cover

    def reset(self, epoch: int, *, seed: int) -> None: ...  # pragma: no cover

    def on_physics_substep(self, context: SubstepContext) -> None: ...  # pragma: no cover

    def sample(self, context: SubstepContext) -> "SampleEnvelope | None":
        """产出一个样本。``None`` 只表示"该实例当前被禁用"；无数据（missing/stale/no_hit/fault）
        必须用带 ``validity`` 的 envelope 表达。"""
        ...  # pragma: no cover

    def dispose(self) -> None: ...  # pragma: no cover


@runtime_checkable
class CommandProviderProtocol(Protocol):
    """命令提供器（B 类：只修改指令）。**不得**在此改观测、改策略权重、改物理状态。"""

    @property
    def provider_id(self) -> str: ...  # pragma: no cover

    def bind(self, spec: "ResolvedRunSpec", adapters: Mapping[str, SensorAdapterProtocol]) -> None:
        """绑定到它声明的输入实例（按 ``instance_id``）。缺实例即抛错，不静默降级。"""
        ...  # pragma: no cover

    def reset(self, epoch: int, *, seed: int) -> None: ...  # pragma: no cover

    def decide(
        self, context: SubstepContext, source_command: Sequence[float]
    ) -> Any:
        """返回 :class:`contracts.sensor_plugin_contract.ProviderDecision`。

        无可用样本时必须返回带 ``reason=no_sample``/``stale_sample``/``sensor_fault`` 的决策
        （而不是抛异常）—— "雷达没数据所以要停下"本身就是一次有效裁决。
        """
        ...  # pragma: no cover

    def dispose(self) -> None: ...  # pragma: no cover


# --------------------------------------------------------------------------------------
# 策略运行时
# --------------------------------------------------------------------------------------


@runtime_checkable
class PolicyRuntimeProtocol(Protocol):
    """策略运行时（原生 worker 里由 onnxruntime 实现；本模块不导入它）。

    ``declared_inputs`` 是**从产物实际元数据读出来的**，不是从文件名/配置里抄的 ——
    解析器据此与 ``PolicyInputBinding`` 逐条对账（名称 + 形状 + dtype）。
    只看"profile 里写了 depth"这种词形命中**不构成认证**（见
    :mod:`backend.simulation_resolver` 的 certification 规则）。
    """

    def load(self, *, model_bytes: bytes) -> None:
        """从**已核对摘要**的字节加载（路径由调用方解析，运行时不做文件 IO）。"""
        ...  # pragma: no cover

    @property
    def declared_inputs(self) -> Sequence["PolicyInputBinding"]: ...  # pragma: no cover

    @property
    def output_names(self) -> Sequence[str]: ...  # pragma: no cover

    def reset(self, *, seed: int) -> None:
        """清循环状态（如 ``memory_h``）。每个 epoch 必须显式调用，不允许"忘了 reset"。"""
        ...  # pragma: no cover

    def step(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        """一次控制步：输入名 → 张量，返回输出名 → 张量（含动作与循环状态）。

        形状/类型与 :attr:`declared_inputs` 不符必须抛 :class:`PolicyRuntimeError`，
        不得"尽力广播"—— 广播会把观测拼接错误变成一段能跑但错的动作。
        """
        ...  # pragma: no cover

    def dispose(self) -> None: ...  # pragma: no cover


# --------------------------------------------------------------------------------------
# 记录器
# --------------------------------------------------------------------------------------


@runtime_checkable
class RecorderSinkProtocol(Protocol):
    """记录器汇聚点（实现者：后续的记录模块）。

    **背压语义是硬约束**：队列满时必须返回 ``False`` 并在 **tick 边界**暂停，
    不允许丢样本、也不允许阻塞物理循环（阻塞会让实时性看不出来但时间基已经错）。
    """

    def open(self, spec: "ResolvedRunSpec") -> None: ...  # pragma: no cover

    def accept_sample(self, envelope: "SampleEnvelope", payload: bytes) -> bool:
        """返回是否已入队（``False`` = 队列满，调用方须在当前 tick 边界暂停）。"""
        ...  # pragma: no cover

    def accept_event(self, event: Mapping[str, Any]) -> None: ...  # pragma: no cover

    def accept_status(self, snapshot: Mapping[str, Any]) -> None: ...  # pragma: no cover

    def current_chunk_id(self) -> str | None: ...  # pragma: no cover

    def flush(self) -> None: ...  # pragma: no cover

    def close(self) -> Mapping[str, Any]:
        """收尾并返回 manifest 字典（含 chunk 索引与完整性摘要）。"""
        ...  # pragma: no cover


# --------------------------------------------------------------------------------------
# 原生能力探测（**可注入边界**）
# --------------------------------------------------------------------------------------


#: ``(spec, definition) -> report``：worker 侧真正探测；控制面只消费结果。
#: 用 Callable 而不是抽象类，是为了让"注入一个假报告"在测试里是一行，
#: 而不是一个继承树 —— 同时类型仍然是 :class:`NativeProbeReport`（不能塞字典）。
NativeProbe = Callable[["ResolvedRunSpec", Mapping[str, Any]], "NativeProbeReport"]


@dataclass(frozen=True)
class NativeProbeResult:
    """探测结果的轻量包装（用于在没有 :class:`NativeProbeReport` 时表达"未探测"）。"""

    probed: bool = False
    reason: str = "not_probed"


def probe_is_supported(report: "NativeProbeReport | None", feature: str) -> bool:
    """只有**明确 supported** 才算 True；``unknown`` / 缺报告 / 未探测都算 False。

    这是 fail-closed 的唯一判定入口 —— 写成函数是为了让"忘了判 unknown"这种
    静默放行没有第二处实现可抄。
    """

    if report is None or not getattr(report, "probed", False):
        return False
    features = getattr(report, "features", None) or {}
    state = features.get(feature)
    return state == "supported"
