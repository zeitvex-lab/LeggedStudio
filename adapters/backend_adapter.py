"""BackendAdapter Protocol：训练后端插件化的正式接口契约（对应优化清单 #3）。

背景：
    项目当前仅一个 mjlab adapter（`adapters/mjlab/`），入口靠 profile 的
    `entrypoints.env / entrypoints.runner` 字符串延迟加载。为支撑后续
    UniLab / RoboLab / IsaacGym 以同一 manifest 接入，这里把「训练后端」
    收敛为显式的 Protocol（三入口：env 环境构造 / runner 训练循环 /
    exporter 策略导出），并提供一个轻量注册表。

刻意设计：
    - 本模块**只含标准库**，不含 torch / mjlab / pydantic——控制面在无训练栈
      环境下也能导入本协议做框架能力声明与校验（维持"控制面永不 import
      训练栈"的隔离原则）。
    - 训练栈 worker 通过字符串延迟解析（`load_backend_adapter`）在子进程内
      按模块路径加载对应实现；控制面只需按 manifest 声明能力，不触碰实现。

参考：
    报告 4 §1B / §2 的 framework 同名符号延迟解析范式（robot_lab /
    unilab EnvFactory Protocol），以及报告 7 §3 异构子进程隔离。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol, runtime_checkable


@runtime_checkable
class EnvFactoryProtocol(Protocol):
    """构造训练环境的三入口之一（environment）。"""

    def build(self, recipe: dict, contract: dict) -> object:
        """根据解析后的 recipe + 契约返回一个环境对象。"""
        ...


@runtime_checkable
class RunnerProtocol(Protocol):
    """构造训练循环的三入口之二（runner）。"""

    def build(self, recipe: dict, contract: dict) -> object:
        """根据解析后的 recipe + 契约返回一个 runner 对象。"""
        ...


@runtime_checkable
class ExporterProtocol(Protocol):
    """策略导出三入口之三（export）。"""

    def export(self, checkpoint: str, contract: dict, output: str) -> dict:
        """把 checkpoint 导出为 ONNX 等产物，返回元数据。"""
        ...


@runtime_checkable
class BackendAdapter(Protocol):
    """一个训练后端 adapter 的完整接口。

    实现方（如 mjlab / unilab）按该协议提供三入口 + 元信息，供控制面与
    worker 按 manifest 统一消费。实现可以是模块（module-level 函数）或类。
    """

    #: 后端唯一 ID，如 "native_mjlab" / "unilab" / "isaacgym"。
    backend_id: str
    #: 依赖的 Python 环境标签（用于 venv 隔离：mjlab-py312 / unilab-py311）。
    python_env: str
    #: 是否就绪（探测结果由 worker 填充）。
    available: bool

    @property
    def env(self) -> EnvFactoryProtocol:
        """环境构造器。"""
        ...

    @property
    def runner(self) -> RunnerProtocol:
        """训练循环构造器。"""
        ...

    @property
    def exporter(self) -> ExporterProtocol:
        """策略导出器。"""
        ...


@dataclass(frozen=True, slots=True)
class BackendDescriptor:
    """控制面可见的后端能力声明（manifest 层面，不含实现）。

    与 training_api 的 frameworks 列表对齐，供 UI 诚实标注可用/规划中。
    """

    id: str
    label: str
    python_env: str
    available: bool
    #: env/runner/exporter 三入口的模块路径（字符串延迟解析）。
    env_entrypoint: str = ""
    runner_entrypoint: str = ""
    exporter_entrypoint: str = ""
    #: 依赖特征（torch / warp / mujoco-warp 等），用于能力声明。
    requires: tuple[str, ...] = field(default_factory=tuple)
    #: 后端备注（如为何不可用）。
    note: str = ""


#: 内置后端的 manifest 声明表（唯一事实源）。
#: available=False 表示"规划中/未接入"，UI 据此诚实标注而不误当可用。
BACKEND_DESCRIPTORS: dict[str, BackendDescriptor] = {
    "native_mjlab": BackendDescriptor(
        id="native_mjlab",
        label="MJLab",
        python_env="mjlab-py312",
        available=True,
        env_entrypoint="adapters.mjlab.env_factory:build_env",
        runner_entrypoint="adapters.mjlab.constants:resolve_runner_class",
        exporter_entrypoint="adapters.mjlab.onnx_exporter:export_policy_to_onnx",
        requires=("torch", "warp", "mujoco-warp"),
        note="已验证；隔离 adapter 子进程，控制面不 import torch。",
    ),
    "unilab": BackendDescriptor(
        id="unilab",
        label="UniLab",
        python_env="unilab-py311",
        available=False,
        env_entrypoint="",
        runner_entrypoint="",
        exporter_entrypoint="",
        requires=("unilab",),
        note="规划中；按同 manifest 接入后置 available=True。",
    ),
    "isaacgym": BackendDescriptor(
        id="isaacgym",
        label="IsaacGym",
        python_env="isaacgym-py38",
        available=False,
        env_entrypoint="",
        runner_entrypoint="",
        exporter_entrypoint="",
        requires=("isaacgym",),
        note="规划中；预留。",
    ),
}


def get_backend_descriptor(backend_id: str) -> BackendDescriptor | None:
    """按 id 取后端能力声明；未知 id 返回 None。"""
    return BACKEND_DESCRIPTORS.get(backend_id)


def list_backend_descriptors() -> list[BackendDescriptor]:
    """列出全部后端能力声明（UI 框架选择消费）。"""
    return list(BACKEND_DESCRIPTORS.values())


def load_backend_adapter(
    descriptor: BackendDescriptor,
    *,
    env_entrypoint: str | None = None,
    runner_entrypoint: str | None = None,
    exporter_entrypoint: str | None = None,
) -> dict[str, Callable | None]:
    """按 manifest 的 entrypoint 字符串延迟解析后端三入口。

    返回 {"env": callable|None, "runner": callable|None, "exporter": callable|None}。
    解析在调用方子进程内执行（worker），因此 torch/mjlab 只在真正需要时
    被 import——控制面调用本函数可安全地在无训练栈环境得到 None 占位。

    任意环节解析失败仅置 None，不抛异常，由调用方按 need 判定缺失。
    """
    import importlib

    def _resolve(entrypoint: str) -> Callable | None:
        if not entrypoint:
            return None
        module_path, _, attr = entrypoint.partition(":")
        if not module_path or not attr:
            return None
        try:
            module = importlib.import_module(module_path)
            return getattr(module, attr, None)
        except Exception:  # 训练栈模块缺失 / 导入失败 → 占位 None
            return None

    return {
        "env": _resolve(env_entrypoint or descriptor.env_entrypoint),
        "runner": _resolve(runner_entrypoint or descriptor.runner_entrypoint),
        "exporter": _resolve(exporter_entrypoint or descriptor.exporter_entrypoint),
    }
