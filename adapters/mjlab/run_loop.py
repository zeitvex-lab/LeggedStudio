"""运行期调度循环（:mod:`contracts.runtime_interfaces` 生命周期的编排核心）。

每个**控制步**：``decimation`` 次物理子步 → 取观测 → 策略一步 → 施加动作 → 记录样本；
按 ``status_period`` 周期上报状态。观测构造与样本封装以**注入件**参与——本模块只钉
编排（子步/策略步/记录/状态的正确次序与计数），不臆造任何策略的观测语义；真实
per-policy 观测由传感器/观测适配器提供（后续切片），记录器由
:class:`adapters.mjlab.recorder.ChunkRecorder` 提供。

动作施加只做"裁剪到 ``model.nu`` 后写入 ``data.ctrl``"：位置/力矩/速度的语义由
执行器接口与契约增益决定（浏览器与桌面同源），循环不二次解释动作含义。
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

__all__ = ["NativeRunLoop"]


class NativeRunLoop:
    """把 (物理模型, 策略运行时, 记录器, 观测构造) 编排成一次可复现的运行。"""

    def __init__(
        self,
        *,
        model: Any,
        data: Any,
        runtime: Any,
        recorder: Any,
        obs_builder: Callable[[Any, Any, Any], Any],
        make_sample: Callable[[int, float, Any], tuple[Any, bytes]],
        decimation: int,
        control_steps: int,
        status_period: int = 0,
        actuator: Callable[[Any, Any, Any], None] | None = None,
    ) -> None:
        self._model = model
        self._data = data
        self._runtime = runtime
        self._recorder = recorder
        self._obs_builder = obs_builder
        self._make_sample = make_sample
        self._decimation = max(1, int(decimation))
        self._control_steps = max(0, int(control_steps))
        self._status_period = max(0, int(status_period))
        self._actuator = actuator
        self._input_names = tuple(binding.name for binding in runtime.declared_inputs)
        self._output_name = runtime.output_names[0] if runtime.output_names else None
        self._nu = int(getattr(model, "nu", 0) or 0)
        self._last_action: np.ndarray | None = None

    def run(self, *, seed: int = 0) -> dict:
        import mujoco

        self._runtime.reset(seed=int(seed))
        self._last_action = None
        for step in range(self._control_steps):
            # 顺序与桌面参考同源：先 obs→策略→施加，再跑 decimation 子步。
            # 若先子步后施加，每个控制步前 decimation 步会**无力矩**自由下落，
            # 首步扰动即足以让软增益策略失稳（实测 go2_rl_sdk_45 跌倒）。
            obs = self._obs_builder(self._model, self._data, self._last_action)
            obs2d = np.asarray(obs, dtype=np.float32).reshape(1, -1)
            feeds = {name: obs2d for name in self._input_names}
            outputs = self._runtime.step(feeds)
            action = np.asarray(outputs[self._output_name], dtype=np.float32).reshape(-1)
            self._last_action = action

            write = min(len(action), self._nu)

            for _ in range(self._decimation):
                # 执行器（PD）必须在**每个物理子步**重算力矩（桌面 500Hz 反馈）；
                # 若每控制步只算一次并保持，软增益策略会因 50Hz PD 失稳跌倒。
                if self._actuator is not None:
                    self._actuator(action, self._model, self._data)
                elif write:
                    self._data.ctrl[:write] = action[:write]
                mujoco.mj_step(self._model, self._data)

            sim_time = float(self._data.time)
            state = np.asarray([self._data.qpos[2]], dtype=np.float32) if self._data.qpos.size > 2 else np.zeros(1, dtype=np.float32)
            envelope, payload = self._make_sample(step, sim_time, state)
            self._recorder.accept_sample(envelope, payload)

            if self._status_period and (step + 1) % self._status_period == 0:
                self._recorder.accept_status(
                    {"tick": step, "sim_time": sim_time, "status": "running"}
                )

        return {"steps": self._control_steps, "sim_time": float(self._data.time)}
