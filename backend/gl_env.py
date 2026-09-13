"""离屏渲染后端的选址（MuJoCo ``MUJOCO_GL``）。

**为什么需要这个模块**：MuJoCo 的离屏渲染后端由环境变量 ``MUJOCO_GL`` 决定，并且
只在 ``import mujoco`` 时解析一次（``mujoco.rendering.classic.gl_context`` 的模块级
逻辑）。在没有 ``DISPLAY`` 的容器 / CI 里，MuJoCo 的默认探测会失败，随后
``mujoco.Renderer(...)`` 抛：

    module 'mujoco.rendering.classic.gl_context' has no attribute 'GLContext'

这正是 ``backend/test_model_api.py::test_mjcf_has_real_render_preview`` 在门禁里
失败的原因（手工设 ``MUJOCO_GL=egl`` 即通过）。修法必须是**在任何 mujoco 导入之前**
把后端定下来，所以本模块被 ``backend/__init__.py`` 在最早的时机调用。

策略（幂等，尊重外部口径）：

1. 已显式设置 ``MUJOCO_GL`` → 一律不动（CI / 用户的显式选择优先）；
2. 非 Linux，或 Linux 但存在 ``DISPLAY`` → 不动（桌面形态用平台默认）；
3. Linux 且无 ``DISPLAY`` → 选 ``egl``；``libEGL`` 不可用时退回 ``osmesa``；
   两者都没有 → 保持不动，让调用方自己拿到原始的失败信息。
"""

from __future__ import annotations

import ctypes.util
import os
import sys

#: 选中的后端名（``get_selected_backend()`` 的口径与 ``MUJOCO_GL`` 一致）
_CANDIDATES: tuple[tuple[str, str], ...] = (("egl", "EGL"), ("osmesa", "OSMesa"))


def ensure_headless_gl() -> str | None:
    """在无显示环境下为 MuJoCo 选定一个可用的离屏渲染后端。

    Returns:
        被采纳的后端名（``"egl"`` / ``"osmesa"``），或 ``None`` 表示未改动环境。
    """
    existing = os.environ.get("MUJOCO_GL")
    if existing:
        return existing
    if sys.platform != "linux" or os.environ.get("DISPLAY"):
        return None
    for backend, library in _CANDIDATES:
        if ctypes.util.find_library(library):
            os.environ["MUJOCO_GL"] = backend
            return backend
    return None


#: 探针结果的进程级缓存（同进程后端不会变；``refresh=True`` 可强制重测）
_PROBE_CACHE: tuple[bool, str] | None = None

#: 探针用的最小可渲染场景：只要"能建上下文并出帧"，不关心画了什么
_PROBE_SCENE = """
<mujoco>
  <worldbody><body name="probe"><geom type="sphere" size="0.1"/></body></worldbody>
</mujoco>
"""


def _probe_offscreen_render(backend: str) -> tuple[bool, str]:
    """真的建一次 ``mujoco.Renderer`` 并渲染一帧；失败即环境结论。"""
    try:
        import mujoco
    except Exception as exc:  # pragma: no cover - 导入失败本身即结论
        return False, f"无法导入 mujoco：{exc}"
    try:
        model = mujoco.MjModel.from_xml_string(_PROBE_SCENE)
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        renderer = mujoco.Renderer(model, height=16, width=16)
        try:
            renderer.update_scene(data)
            renderer.render()
        finally:
            renderer.close()
    except BaseException as exc:  # GL 失败类型五花八门（RuntimeError / OSError / 平台库缺失）
        return False, f"离屏后端 {backend!r} 实测不可用（{type(exc).__name__}: {exc}）"
    return True, backend


def offscreen_render_status(refresh: bool = False) -> tuple[bool, str]:
    """当前进程是否真的能做离屏渲染，附一句可读的原因。

    给「要渲染」的调用方（单测、健康检查、预览端点）一个**显式前置判定**，
    避免把"环境不允许渲染"误报成"代码有 bug"。

    **为什么必须实测而不是看属性**（2026-09-13 CI 实测教训）：旧版只检查
    ``mujoco.rendering.classic.gl_context`` 有没有 ``GLContext`` 属性——在没有
    libEGL / libOSMesa 的容器（CI 的 ``python:3.12`` 镜像）里，该模块**能导入、
    属性也在**，于是判定"可用"，直到真正 ``mjr_makeContext`` 才抛
    ``an OpenGL platform library has not been loaded into this process``。
    结果：单测的 skip 守卫失效 → 把环境问题报成代码失败。现在改为**建一次真实
    渲染上下文并渲染一帧**（16×16 的小模型），拿到的是同一件事的**实测结论**。

    Returns:
        ``(可用?, 原因或后端名)``
    """
    global _PROBE_CACHE
    if _PROBE_CACHE is not None and not refresh:
        return _PROBE_CACHE
    backend = ensure_headless_gl() or os.environ.get("MUJOCO_GL") or "unset"
    if backend == "disabled":
        _PROBE_CACHE = (False, "MUJOCO_GL=disabled：当前环境显式关闭了离屏渲染")
        return _PROBE_CACHE
    _PROBE_CACHE = _probe_offscreen_render(backend)
    return _PROBE_CACHE


def render_error_hint(exc: BaseException) -> str:
    """把离屏渲染失败翻译成可操作的中文提示（不改动原始错误信息）。"""
    message = str(exc)
    if "GLContext" in message or "MUJOCO_GL" in message or "OpenGL" in message:
        return (
            f"{message}（离屏渲染后端不可用：无显示环境下需可用的 libEGL 或 libOSMesa，"
            "或显式设置 MUJOCO_GL=egl|osmesa；用 MUJOCO_GL=disabled 会关闭渲染）"
        )
    return message
