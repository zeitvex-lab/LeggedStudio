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


def offscreen_render_status() -> tuple[bool, str]:
    """当前进程是否真的能做离屏渲染，附一句可读的原因。

    给「要渲染」的调用方（单测、健康检查、预览端点）一个**显式前置判定**，
    避免把"环境不允许渲染"误报成"代码有 bug"。判定顺序与 MuJoCo 自身一致：
    ``MUJOCO_GL=disabled`` 是显式关闭；否则看后端能否提供 ``GLContext``。

    Returns:
        ``(可用?, 原因或后端名)``
    """
    backend = ensure_headless_gl() or os.environ.get("MUJOCO_GL") or "unset"
    if backend == "disabled":
        return False, "MUJOCO_GL=disabled：当前环境显式关闭了离屏渲染"
    try:
        from mujoco.rendering.classic import gl_context
    except Exception as exc:  # pragma: no cover - 导入失败本身即结论
        return False, f"无法导入 MuJoCo GL 后端：{exc}"
    if not hasattr(gl_context, "GLContext"):
        return False, f"离屏后端 {backend!r} 不可用（MuJoCo 未提供 GLContext）"
    return True, backend


def render_error_hint(exc: BaseException) -> str:
    """把离屏渲染失败翻译成可操作的中文提示（不改动原始错误信息）。"""
    message = str(exc)
    if "GLContext" in message or "MUJOCO_GL" in message or "OpenGL" in message:
        return (
            f"{message}（离屏渲染后端不可用：无显示环境下需可用的 libEGL 或 libOSMesa，"
            "或显式设置 MUJOCO_GL=egl|osmesa；用 MUJOCO_GL=disabled 会关闭渲染）"
        )
    return message
