"""策略运行时（onnxruntime 实现 :class:`contracts.runtime_interfaces.PolicyRuntimeProtocol`）。

构造时注入 ``ResolvedRunSpec.policy_inputs``（带真实语义 kind/source 的绑定）；
:meth:`OnnxPolicyRuntime.load` 从**已核对摘要**的产物字节加载，并把每个声明绑定与
产物**实际输入**逐项对账（名称 + 形状 + dtype）。任何不符都抛
:class:`~contracts.runtime_interfaces.PolicyRuntimeError`——不广播、不近似、不静默
转换：那会把观测拼接错误变成一段"能跑但错"的动作，正是本模块要挡住的事故。

onnxruntime **只在** :meth:`load` 内导入，这样控制面可以安全引用本模块而不被迫
加载原生栈（与 :mod:`adapters.mjlab.native_probe` 同一边界约定）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from contracts import simulation_run_contract as rc
from contracts.runtime_interfaces import PolicyRuntimeError

__all__ = ["OnnxPolicyRuntime"]

#: 线协议 dtype（:data:`contracts.simulation_protocol.DTYPE_ITEMSIZE` 的键）→ numpy dtype。
_PROTOCOL_TO_NP: dict[str, Any] = {
    "f4": np.float32,
    "f8": np.float64,
    "i1": np.int8,
    "i2": np.int16,
    "i4": np.int32,
    "i8": np.int64,
    "u1": np.uint8,
    "u2": np.uint16,
    "u4": np.uint32,
    "u8": np.uint64,
    "b1": np.bool_,
}

#: onnxruntime 输入类型串 → 线协议 dtype（load 期对账用；未收录的码型一律视为不符）。
_ORT_TYPE_TO_PROTOCOL: dict[str, str] = {
    "tensor(float)": "f4",
    "tensor(double)": "f8",
    "tensor(int8)": "i1",
    "tensor(int16)": "i2",
    "tensor(int32)": "i4",
    "tensor(int64)": "i8",
    "tensor(uint8)": "u1",
    "tensor(uint16)": "u2",
    "tensor(uint32)": "u4",
    "tensor(uint64)": "u8",
    "tensor(bool)": "b1",
}


class OnnxPolicyRuntime:
    """onnxruntime 策略运行时（一个运行一份产物，可跨 epoch ``reset`` 复用）。"""

    def __init__(self, declared: Sequence[rc.PolicyInputBinding]) -> None:
        self._declared = tuple(declared)
        self._session: Any = None
        self._output_names: tuple[str, ...] = ()
        self._seed = 0

    @property
    def declared_inputs(self) -> tuple[rc.PolicyInputBinding, ...]:
        """注入的规格绑定原样回显（语义 kind/source 由规格给出，运行时不臆造）。"""

        return self._declared

    @property
    def output_names(self) -> tuple[str, ...]:
        return self._output_names

    def load(self, *, model_bytes: bytes) -> None:
        try:
            import onnxruntime as ort
        except ImportError as exc:  # pragma: no cover - 环境缺原生栈
            raise PolicyRuntimeError("runtime_unavailable", f"onnxruntime 不可用：{exc}") from exc
        try:
            session = ort.InferenceSession(model_bytes, providers=["CPUExecutionProvider"])
        except Exception as exc:  # noqa: BLE001 - 任何加载失败都记为 load_failed，不猜
            raise PolicyRuntimeError("load_failed", f"onnxruntime 加载产物失败：{exc}") from exc

        actual = {tensor.name: tensor for tensor in session.get_inputs()}
        for binding in self._declared:
            meta = actual.get(binding.name)
            if meta is None:
                raise PolicyRuntimeError(
                    "input_missing",
                    f"产物缺少声明输入 {binding.name!r}（实际输入 {sorted(actual)}）",
                )
            product_dtype = _ORT_TYPE_TO_PROTOCOL.get(meta.type)
            if product_dtype != binding.dtype:
                raise PolicyRuntimeError(
                    "dtype_mismatch",
                    f"输入 {binding.name} dtype 不符：声明 {binding.dtype}，产物 {meta.type}",
                )
            _check_declared_shape(binding.name, binding.tensor_shape, meta.shape)

        self._session = session
        self._output_names = tuple(tensor.name for tensor in session.get_outputs())

    def reset(self, *, seed: int) -> None:
        """每个 epoch 显式重置随机种子（循环状态清理随循环策略切片接入）。"""

        self._seed = int(seed)

    def step(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        if self._session is None:
            raise PolicyRuntimeError("not_loaded", "step 前必须先 load（或运行时已 dispose）")
        feeds: dict[str, Any] = {}
        for binding in self._declared:
            if binding.name not in inputs:
                raise PolicyRuntimeError("input_missing", f"step 缺输入 {binding.name!r}")
            expected_np = _PROTOCOL_TO_NP[binding.dtype]
            array = inputs[binding.name]
            if not isinstance(array, np.ndarray):
                array = np.asarray(array)
            if array.dtype != expected_np:
                raise PolicyRuntimeError(
                    "dtype_mismatch",
                    f"输入 {binding.name} dtype={array.dtype} 与声明 {binding.dtype} 不符（不静默转换）",
                )
            if array.shape != _concrete_shape(binding.tensor_shape, array.shape):
                raise PolicyRuntimeError(
                    "shape_mismatch",
                    f"输入 {binding.name} 形状 {tuple(array.shape)} 与声明 "
                    f"{tuple(binding.tensor_shape)} 不符（不广播）",
                )
            feeds[binding.name] = array
        try:
            outputs = self._session.run(None, feeds)
        except Exception as exc:  # noqa: BLE001 - 推理失败一律显式抛，不静默跳过
            raise PolicyRuntimeError("inference_failed", f"推理失败：{exc}") from exc
        return dict(zip(self._output_names, outputs))

    def dispose(self) -> None:
        """释放 session（幂等：可重复调用，之后 step 会明确报 not_loaded）。"""

        self._session = None
        self._output_names = ()


def _check_declared_shape(name: str, declared: Sequence[int], actual: Any) -> None:
    """load 期形状对账：``-1``（声明动态）与产物动态维都表示"任意"，逐维比其余。"""

    actual_dims = tuple(actual or ())
    if len(actual_dims) != len(declared):
        raise PolicyRuntimeError(
            "shape_mismatch",
            f"输入 {name} 维数不符：声明 {list(declared)}，产物 {list(actual_dims)}",
        )
    for want, got in zip(declared, actual_dims):
        if int(want) == -1 or not isinstance(got, int) or got <= 0:
            continue  # 任一侧动态 → 该维不判
        if int(want) != int(got):
            raise PolicyRuntimeError(
                "shape_mismatch",
                f"输入 {name} 形状不符：声明 {list(declared)}，产物 {list(actual_dims)}",
            )


def _concrete_shape(declared: Sequence[int], actual: tuple[int, ...]) -> tuple[int, ...]:
    """把声明里的 ``-1`` 用实际维填回，得到"应与实际相等"的具体形状（维数不符则原样返回）。"""

    if len(declared) != len(actual):
        return tuple(int(dim) for dim in declared)
    return tuple(int(act) if int(dim) == -1 else int(dim) for dim, act in zip(declared, actual))
