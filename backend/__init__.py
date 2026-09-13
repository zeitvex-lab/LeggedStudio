"""Legged Studio control-plane backend."""

from .gl_env import ensure_headless_gl

# 必须在任何 ``import mujoco`` 之前确定离屏渲染后端（MuJoCo 只在导入时解析一次
# ``MUJOCO_GL``）。放在包初始化里是刻意的：凡是 ``backend.*`` 的入口（API 进程、
# 单测、CLI）都会先经过这里。幂等，且不覆盖外部显式设置。
ensure_headless_gl()
