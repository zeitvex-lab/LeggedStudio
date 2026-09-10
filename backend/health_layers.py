"""A3：L0–L6 六层体检 —— 从硬件到最小训练逐层定位故障（fail-fast）。

任务清单 A3 的验收：**断 CUDA / 卸 mjlab / 空注册表**，各能定位到对应层，
并给出**中文原因与处置**。

层定义（与排期表一致）：

====  ==========  =====================================================
层    名称        判定
====  ==========  =====================================================
L0    GPU/CUDA    nvidia-smi 可用且能列出设备
L1    框架        适配器 venv 里 mjlab / torch / mujoco / warp 可导入形态存在
L2    任务注册    ``recipe_registry.list_tasks()`` 非空
L3    场景        默认机型的模型与场景资源存在（可构建 Scene）
L4    zero agent  动作恒 0 前向一步（需适配器进程，deep 才执行）
L5    random agent 随机动作前向一步（同上）
L6    最小训练    64 envs × 5 iters 冒烟（同上，E8 的冒烟门前置）
====  ==========  =====================================================

设计要点：

* **fail-fast**：遇到第一个失败层即停（后面的层标 ``blocked``）——因为下层结论
  在上层故障时不可信（没有 GPU 时测"随机代理"只会得到误导性失败）。
* **依赖注入**：GPU / 包 / 任务 / 场景的探测函数都可作为参数注入，
  使"断 CUDA / 卸 mjlab / 空注册表"可以**无真实硬件**地单测复现。
* L4–L6 需要真正拉起适配器进程（代价大），默认 ``skip`` 并给出如何执行的中文指引；
  ``deep=True`` 时委托 ``tools/validate_training_smoke.py``。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROBOT = "unitree_go2"
ADAPTER_VENV = ROOT / "adapters" / "mjlab" / ".venv"
SMOKE_TOOL = ROOT / "tools" / "validate_training_smoke.py"

__all__ = ["build_layer_report", "LAYER_NAMES"]

LAYER_NAMES = {
    "L0": "GPU / CUDA",
    "L1": "训练框架",
    "L2": "任务注册",
    "L3": "场景资源",
    "L4": "zero agent",
    "L5": "random agent",
    "L6": "最小训练",
}

# L1 检查的模块目录名（importlib 包名 → venv site-packages 下的目录名）
_FRAMEWORK_MODULES = ("mjlab", "torch", "mujoco", "warp")


def _layer(
    layer_id: str, status: str, reason: str, action: str, **extra: Any
) -> dict[str, Any]:
    return {"id": layer_id, "name": LAYER_NAMES[layer_id], "status": status,
            "reason": reason, "action": action, **extra}


def _site_dirs(venv: Path) -> list[Path]:
    return [
        venv / "Lib" / "site-packages",
        venv / "lib" / "python3.12" / "site-packages",
        venv / "lib" / "python3.13" / "site-packages",
    ]


def _module_installed(venv: Path, module: str) -> bool:
    for site in _site_dirs(venv):
        if (site / module).is_dir():
            return True
        if any(site.glob(f"{module}-*.dist-info")):
            return True
    return False


def _default_gpu_probe() -> dict[str, Any]:
    from adapters.mjlab.preflight import gpu_probe

    return gpu_probe()


def _default_tasks() -> list[str]:
    from adapters.mjlab.recipe_registry import list_tasks

    return list(list_tasks())


def _scene_ready(robot_id: str = DEFAULT_ROBOT) -> tuple[bool, str]:
    """L3：默认机型的模型与场景资源是否可构建 Scene。"""

    model = ROOT / "assets" / "robots" / robot_id / "model" / "robot.xml"
    if not model.is_file():
        return False, f"缺少机型模型 {model.relative_to(ROOT)}"
    scenes = ROOT / "assets" / "robots" / robot_id / "simulation"
    if not scenes.is_dir():
        return False, f"缺少机型场景目录 {scenes.relative_to(ROOT)}"
    return True, f"{robot_id} 模型与场景资源齐备"


def _run_smoke() -> dict[str, Any]:
    """L6 的 deep 执行：委托 E8 的冒烟工具（64 envs × 5 iters）。"""

    python = ADAPTER_VENV / "Scripts" / "python.exe"
    executable = python if python.is_file() else Path(sys.executable)
    try:
        result = subprocess.run(
            [str(executable), str(SMOKE_TOOL)],
            capture_output=True, text=True, timeout=1800, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "reason": f"冒烟进程启动失败：{exc}"}
    if result.returncode != 0:
        tail = (result.stdout or result.stderr or "").strip().splitlines()[-5:]
        return {"ok": False, "reason": "；".join(tail) or f"冒烟退出码 {result.returncode}"}
    return {"ok": True, "reason": "最小训练冒烟通过"}


def build_layer_report(
    *,
    deep: bool = False,
    gpu_probe: Callable[[], dict[str, Any]] | None = None,
    list_tasks: Callable[[], list[str]] | None = None,
    venv: Path | None = None,
    scene_check: Callable[[str], tuple[bool, str]] | None = None,
) -> dict[str, Any]:
    """产出 L0–L6 六层体检报告（fail-fast）。

    所有探测函数可注入：单测用它们复现"断 CUDA / 卸 mjlab / 空注册表"。
    """

    gpu = (gpu_probe or _default_gpu_probe)()
    tasks = (list_tasks or _default_tasks)()
    venv = venv or ADAPTER_VENV
    scene = (scene_check or _scene_ready)(DEFAULT_ROBOT)

    layers: list[dict[str, Any]] = []

    # ---- L0 GPU / CUDA ----
    devices = gpu.get("devices") or []
    if gpu.get("available") and devices:
        layers.append(_layer(
            "L0", "pass", f"检测到 {len(devices)} 块 GPU：{devices[0].get('name', '?')}",
            "无需处置",
            devices=devices,
        ))
    else:
        layers.append(_layer(
            "L0", "fail",
            f"未检测到可用 GPU/CUDA（{gpu.get('reason') or 'nvidia-smi 未返回设备'}）",
            "① 确认本机为 NVIDIA 显卡并安装最新驱动；② 若确无独显，训练将回退 CPU"
            "（速度慢几个量级，仅建议冒烟）；③ 桌面端可在启动器『配置环境』中重装"
            " CUDA 运行时",
        ))

    # ---- L1 框架 ----
    if layers[-1]["status"] != "pass":
        layers.append(_layer("L1", "blocked", "上层（GPU/CUDA）未通过，框架检查失去意义", "先解决 L0"))
    else:
        missing = [m for m in _FRAMEWORK_MODULES if not _module_installed(venv, m)]
        if missing:
            layers.append(_layer(
                "L1", "fail", f"适配器运行时缺少框架包：{'、'.join(missing)}",
                "在启动器点击『配置环境』重新供应运行时；或手动执行 "
                "`uv sync`（adapters/mjlab）后重试",
                venv=str(venv),
            ))
        else:
            layers.append(_layer(
                "L1", "pass",
                f"框架齐备：{'、'.join(_FRAMEWORK_MODULES)}（{venv.name}）", "无需处置",
            ))

    # ---- L2 任务注册 ----
    if layers[-1]["status"] != "pass":
        layers.append(_layer("L2", "blocked", "上层未通过，任务注册检查失去意义", "先解决上层"))
    elif not tasks:
        layers.append(_layer(
            "L2", "fail", "任务注册表为空：没有任何可训练技能",
            "检查 adapters/mjlab/recipe_registry.py 的任务定义是否被清空/导入失败；"
            "恢复注册或重新安装适配器",
        ))
    else:
        def _task_label(item: Any) -> str:
            if isinstance(item, dict):
                return str(item.get("id") or item.get("label") or item)
            return str(item)

        preview = "、".join(_task_label(item) for item in tasks[:3])
        layers.append(_layer(
            "L2", "pass", f"已注册 {len(tasks)} 个任务：{preview}{'…' if len(tasks) > 3 else ''}",
            "无需处置",
            count=len(tasks),
        ))

    # ---- L3 场景 ----
    if layers[-1]["status"] != "pass":
        layers.append(_layer("L3", "blocked", "上层未通过，场景检查失去意义", "先解决上层"))
    elif not scene[0]:
        layers.append(_layer(
            "L3", "fail", f"场景资源不完整：{scene[1]}",
            f"重新导入 {DEFAULT_ROBOT} 包（工作台 → 资产库 → 导入），或从内置包恢复 "
            "assets/robots 下的 model/ 与 simulation/ 目录",
        ))
    else:
        layers.append(_layer("L3", "pass", scene[1], "无需处置"))

    # ---- L4 / L5 / L6（需适配器进程，deep 才执行）----
    agent_layers = (
        ("L4", "zero agent", "动作恒 0 前向一步"),
        ("L5", "random agent", "随机动作前向一步"),
        ("L6", "最小训练", "64 envs × 5 iters 冒烟"),
    )
    blocked = layers[-1]["status"] != "pass"
    smoke: dict[str, Any] | None = None
    for layer_id, name, what in agent_layers:
        if blocked:
            layers.append(_layer(
                layer_id, "blocked", "上层未通过，运行级检查失去意义", "先解决上层",
            ))
            continue
        if not deep:
            layers.append(_layer(
                layer_id, "skip",
                f"{what}需要拉起适配器进程（代价大，默认不执行）",
                "在启动器执行『深度体检』，或运行 tools/validate_training_smoke.py",
            ))
            continue
        if layer_id == "L6":
            smoke = _run_smoke()
            layers.append(_layer(
                "L6", "pass" if smoke["ok"] else "fail", smoke["reason"],
                "无需处置" if smoke["ok"] else
                "按冒烟输出的最后几行定位；常见原因：显存不足（调小 num_envs）、"
                "观测维度与契约不符（回工作台核对）、任务注册缺项（回到 L2）",
            ))
        else:
            layers.append(_layer(
                layer_id, "skip",
                f"{what}由 L6 冒烟一并覆盖（冒烟内部先跑 zero/random 阶段）",
                "执行『深度体检』",
            ))

    first_failure = next(
        (layer["id"] for layer in layers if layer["status"] == "fail"), None
    )
    passed = sum(1 for layer in layers if layer["status"] == "pass")
    return {
        "schema_version": "health-layers-1.0",
        "deep": deep,
        "ready": first_failure is None,
        "first_failure": first_failure,
        "passed": passed,
        "total": len(layers),
        "layers": layers,
        "smoke": smoke,
    }
