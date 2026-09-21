"""原生高级仿真的**真实运行时探测**（worker 侧）。

解析器（:mod:`backend.simulation_resolver`）不启动进程、也不导入 mujoco；它只消费
注入进来的探测结果。这里就是那个被注入的实现：它**真的**编译 MJCF、**真的**用
onnxruntime 加载策略并推理，然后如实报告每一项特征。

三条与契约同源的反冒充规则
--------------------------
1. **没探过就是没探过**：运行时导入失败 → ``probed=False``（reason=probe_failed），不猜。
2. **没核验的特征不写 supported**：探测只对它**实际执行过**核验的特征给
   ``supported``/``unsupported``；其余保持缺省（契约里等于 ``unknown``），
   于是"未实现"表现为阻断而不是放行。
3. **版本来自运行时**：mujoco/onnxruntime/python 版本取自真实模块，不硬编码。

mujoco 与 onnxruntime **只在** :func:`probe_native` 内部导入——这样控制面
（解析器）注入本函数时并不会被迫加载原生栈，符合"解析器不启动进程"的边界。
"""

from __future__ import annotations

import platform
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from contracts import simulation_run_contract as rc

__all__ = ["probe_native"]

#: onnxruntime 张量类型名 → numpy dtype（只用于按声明形状喂零观测跑一次真实推理）。
_ORT_TO_NP: dict[str, Any] = {
    "tensor(float)": np.float32,
    "tensor(float16)": np.float16,
    "tensor(double)": np.float64,
    "tensor(int64)": np.int64,
    "tensor(int32)": np.int32,
    "tensor(bool)": np.bool_,
}


def probe_native(draft: Mapping[str, Any]) -> rc.NativeProbeReport:
    """按草稿里的 ``required_features`` 做**真实**探测，返回契约类型的报告。

    草稿由解析器构造，至少携带 ``model_path``（已解析的 MJCF）与
    ``policy_onnx_path``（已认证的策略产物）——探测直接复用这些路径，不重复解析清单。
    """

    required = {str(name) for name in (draft.get("required_features") or ())}
    model_path = draft.get("model_path")
    onnx_path = draft.get("policy_onnx_path")

    try:
        import mujoco
    except Exception as exc:  # pragma: no cover - 环境缺原生栈时如实报告
        return rc.NativeProbeReport.not_probed(
            "probe_failed", details=f"mujoco 导入失败：{exc}"
        )
    try:
        import onnxruntime as ort
    except Exception as exc:  # pragma: no cover - 环境缺原生栈时如实报告
        return rc.NativeProbeReport.not_probed(
            "probe_failed", details=f"onnxruntime 导入失败：{exc}"
        )

    features: dict[str, str] = {}
    details: list[str] = []

    model = None
    if required & {"model_compile", "physics_substep", "policy_closed_loop"}:
        model = _probe_model_compile(mujoco, model_path, features, details)
        if "physics_substep" in required:
            _probe_physics_substep(mujoco, model, features, details)

    session = None
    if required & {"onnx_inference", "policy_closed_loop"}:
        session = _probe_onnx_inference(ort, onnx_path, features, details)

    if "policy_closed_loop" in required:
        _probe_closed_loop(session, features, details)

    if "episode_record" in required:
        _probe_episode_record(features, details)

    if not features:
        # 没有任何可核验特征：不是"探测通过"，如实报告未探测。
        return rc.NativeProbeReport.not_probed(
            "not_probed", details="草稿没有可核验的 required_features"
        )

    return rc.NativeProbeReport(
        probed=True,
        reason="probed",
        features=features,
        mujoco_version=str(getattr(mujoco, "__version__", "") or ""),
        onnxruntime_version=str(getattr(ort, "__version__", "") or ""),
        python_version=platform.python_version(),
        probed_at_unix=time.time(),
        details="；".join(details) if details else "真实运行时探测通过",
    )


def _probe_model_compile(
    mujoco: Any, model_path: Any, features: dict[str, str], details: list[str]
) -> Any:
    """实际编译 MJCF；返回 ``mjModel`` 或 ``None``（并如实标注 model_compile）。"""

    if not model_path:
        features["model_compile"] = "unsupported"
        details.append("model_compile：草稿缺 model_path")
        return None
    path = Path(str(model_path))
    if not path.is_file():
        features["model_compile"] = "unsupported"
        details.append(f"model_compile：模型文件不存在 {path}")
        return None
    try:
        model = mujoco.MjModel.from_xml_path(str(path))
    except Exception as exc:
        features["model_compile"] = "unsupported"
        details.append(f"model_compile：编译失败 {type(exc).__name__}: {exc}")
        return None
    features["model_compile"] = "supported"
    return model


def _probe_physics_substep(
    mujoco: Any, model: Any, features: dict[str, str], details: list[str]
) -> None:
    """在已编译模型上实际步进一次（``model`` 为 ``None`` 即无从步进）。"""

    if model is None:
        features["physics_substep"] = "unsupported"
        details.append("physics_substep：无已编译模型可步进")
        return
    try:
        data = mujoco.MjData(model)
        mujoco.mj_step(model, data)
        stepped = float(data.time)
    except Exception as exc:
        features["physics_substep"] = "unsupported"
        details.append(f"physics_substep：步进失败 {type(exc).__name__}: {exc}")
        return
    if not np.isfinite(stepped):
        features["physics_substep"] = "unsupported"
        details.append("physics_substep：步进后时间非有限")
        return
    features["physics_substep"] = "supported"


def _probe_onnx_inference(
    ort: Any, onnx_path: Any, features: dict[str, str], details: list[str]
) -> Any:
    """实际用 onnxruntime 加载策略产物；返回 session 或 ``None``。"""

    if not onnx_path:
        features["onnx_inference"] = "unsupported"
        details.append("onnx_inference：草稿缺 policy_onnx_path")
        return None
    path = Path(str(onnx_path))
    if not path.is_file():
        features["onnx_inference"] = "unsupported"
        details.append(f"onnx_inference：策略产物不存在 {path}")
        return None
    try:
        session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    except Exception as exc:
        features["onnx_inference"] = "unsupported"
        details.append(f"onnx_inference：加载失败 {type(exc).__name__}: {exc}")
        return None
    features["onnx_inference"] = "supported"
    return session


def _probe_closed_loop(
    session: Any, features: dict[str, str], details: list[str]
) -> None:
    """闭环能力 = onnx 能推理 **且** 物理能步进 **且** 一次真实推理产出有限动作。

    这是"能力"探测而非完整验收：它证明 obs→策略→动作这一段在本机真跑得通，
    而不是靠 profile 里写了什么词来推断（词形命中不算认证）。
    """

    if (
        session is None
        or features.get("onnx_inference") != "supported"
        or features.get("physics_substep") != "supported"
    ):
        features["policy_closed_loop"] = "unsupported"
        details.append("policy_closed_loop：onnx_inference 与 physics_substep 未同时具备")
        return
    try:
        feeds: dict[str, Any] = {}
        for tensor in session.get_inputs():
            shape = tuple(int(d) if isinstance(d, int) and d > 0 else 1 for d in tensor.shape)
            feeds[tensor.name] = np.zeros(shape, dtype=_ORT_TO_NP.get(tensor.type, np.float32))
        outputs = session.run(None, feeds)
        if not outputs:
            raise RuntimeError("推理没有输出")
        if not np.all(np.isfinite(np.asarray(outputs[0], dtype=np.float64))):
            raise RuntimeError("推理输出含非有限值")
    except Exception as exc:
        features["policy_closed_loop"] = "unsupported"
        details.append(f"policy_closed_loop：闭环推理失败 {type(exc).__name__}: {exc}")
        return
    features["policy_closed_loop"] = "supported"


def _probe_episode_record(features: dict[str, str], details: list[str]) -> None:
    """记录能力：跑记录子系统的存储原语自检（写/校验/读回一个 npz 块）。

    自检不依赖规格（探测早于规格构造），因此它证明的是"本机能把一个记录块
    落盘并校验读回"；完整清单/背压路径由 :class:`adapters.mjlab.recorder.ChunkRecorder`
    在运行期走，并各有其单元测试。
    """

    try:
        from .recorder import recorder_selftest

        ok = bool(recorder_selftest())
    except Exception as exc:  # noqa: BLE001 - 自检异常也只能如实报 unsupported
        ok = False
        details.append(f"episode_record：记录自检异常 {type(exc).__name__}: {exc}")
    features["episode_record"] = "supported" if ok else "unsupported"
    if not ok:
        details.append("episode_record：记录子系统存储原语自检未通过")
