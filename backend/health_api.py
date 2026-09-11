"""L0-L6 分层体检 API（T5.1，批次 5 / M6）。

知识库 Ch02 分层验证（报告 1 §9）：GPU → 框架导入 → 任务注册 → 场景构建 →
zero agent → random agent → 最小训练。默认只跑 L0-L3（秒级）；L4-L6 标
"深度诊断"按需执行（本轮实现 L0-L3 + L4 入口，L5/L6 沿用 validate_training_smoke
的 train 模式）。每层 ✅⚠❌ + 失败原因 + 中文修复建议。
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from adapters.mjlab.preflight import gpu_probe

router = APIRouter(prefix="/api/health", tags=["health"])

ROOT = Path(__file__).resolve().parents[1]


def _adapter_python() -> Path:
    """适配器 venv 的 python：Windows 为 Scripts/python.exe，POSIX 为 bin/python。"""
    venv = ROOT / "adapters" / "mjlab" / ".venv"
    for relative in (Path("Scripts") / "python.exe", Path("bin") / "python"):
        candidate = venv / relative
        if candidate.is_file():
            return candidate
    return venv / "Scripts" / "python.exe"


ADAPTER_PY = _adapter_python()


@router.get("/layers")
async def health_layers(deep: bool = False) -> dict:
    """A3：L0–L6 六层体检（GPU→框架→任务注册→场景→zero/random agent→最小训练）。

    fail-fast：第一个失败层之后的层标记 blocked；每层附中文原因与处置。
    ``deep=true`` 时执行 L6 最小训练冒烟（64 envs × 5 iters，代价大）。
    """

    from backend.health_layers import build_layer_report

    return build_layer_report(deep=deep)


def _layer(layer_id: str, name: str, status: str, summary: str, **extra: Any) -> dict:
    return {"layer": layer_id, "name": name, "status": status, "summary": summary, **extra}


def _fix_advice(layer_id: str) -> str:
    advice = {
        "L0": "如需 GPU 训练：确认 NVIDIA 驱动已安装（不需要 CUDA Toolkit），在启动器「配置运行环境」按 GPU profile 重装；纯 CPU 可先跑仿真与冒烟验证",
        "L1": "训练适配器环境损坏——删除 adapters/mjlab/.venv 后重新配置运行环境",
        "L2": "机器人包索引缺失——重启后端重建 package index",
        "L3": "模型文件损坏——重新导入或恢复出厂包",
    }
    return advice.get(layer_id, "查看控制台页日志定位")


@router.get("/preflight")
async def preflight(depth: str = "fast"):
    """depth=fast 只跑 L0-L3（秒级）；depth=deep 追加 L4（zero-agent 冒烟，分钟级）。"""

    started = time.time()
    layers: list[dict] = []

    # L0 硬件/GPU：无 GPU 只告警，不阻断（CPU 可做仿真与冒烟验证）
    try:
        gpu = gpu_probe()
        devices = gpu.get("devices") or []
        if gpu.get("available") and devices:
            layers.append(_layer(
                "L0", "GPU 与驱动", "pass",
                f"检测到 {len(devices)} 块 GPU：{devices[0].get('name', '?')}",
                detail=gpu,
            ))
        else:
            layers.append(_layer(
                "L0", "GPU 与驱动", "warn",
                f"未检测到 GPU/CUDA（{gpu.get('reason') or '无设备'}）——回退 CPU："
                "可做仿真与最小训练冒烟，正式训练建议使用 NVIDIA GPU",
                detail=gpu,
            ))
    except Exception as exc:  # noqa: BLE001
        layers.append(_layer("L0", "GPU 与驱动", "fail", f"GPU 探测失败: {exc}", fix=_fix_advice("L0")))

    # L1 框架导入（隔离 adapter venv 的 torch/mjlab 探针，不污染控制面）
    torch_ok = ADAPTER_PY.exists()
    if torch_ok:
        try:
            probe = subprocess.run(
                [str(ADAPTER_PY), "-c", "import torch, mjlab; print('ok')"],
                capture_output=True, text=True, timeout=300,
            )
            torch_ok = probe.returncode == 0 and probe.stdout.strip().endswith("ok")
        except (OSError, subprocess.TimeoutExpired):
            torch_ok = False
    layers.append(_layer(
        "L1", "训练框架导入", "pass" if torch_ok else "fail",
        "torch + mjlab 导入正常（隔离 venv）" if torch_ok else "隔离 venv 中 torch/mjlab 导入失败",
        fix=None if torch_ok else _fix_advice("L1"),
    ))

    # L2 任务注册（55 profiles 索引可读）
    profile_count = 0
    try:
        from backend.robot_packages import list_robot_packages

        profile_count = sum(len(r.get("training_profiles") or []) for r in list_robot_packages())
        layers.append(_layer(
            "L2", "任务注册", "pass" if profile_count else "warn",
            f"{profile_count} 个训练 profile 已注册",
        ))
    except Exception as exc:  # noqa: BLE001
        layers.append(_layer("L2", "任务注册", "fail", f"包索引读取失败: {exc}", fix=_fix_advice("L2")))

    # L3 场景构建（Go2 MJCF 编译）
    try:
        import mujoco

        model_path = ROOT / "assets" / "robots" / "unitree_go2" / "model" / "robot.xml"
        model = mujoco.MjModel.from_xml_path(str(model_path))
        layers.append(_layer(
            "L3", "场景构建", "pass",
            f"Go2 MJCF 编译通过（nq={model.nq}, nu={model.nu}）",
        ))
        del model
    except Exception as exc:  # noqa: BLE001
        layers.append(_layer("L3", "场景构建", "fail", f"Go2 场景编译失败: {exc}", fix=_fix_advice("L3")))

    # L4-L6：深度诊断按需（L4 = zero agent rollout；L5/L6 = train 模式冒烟）
    if depth == "deep":
        try:
            probe = subprocess.run(
                [str(ADAPTER_PY), "-u", str(ROOT / "tools" / "_smoke_one.py"),
                 str(ROOT / "assets" / "robots" / "unitree_go2"),
                 str(ROOT / "assets" / "robots" / "unitree_go2" / "training" / "source"),
                 "local_tasks.robot_profiles:flat_env_cfg", "-",
                 "16", "10"],
                capture_output=True, text=True, timeout=1800,
            )
            ok = '"status": "ok"' in (probe.stdout or "")
            layers.append(_layer(
                "L4", "zero agent rollout", "pass" if ok else "fail",
                "16 envs × 10 步 rollout 完成" if ok else (probe.stderr or "rollout 失败")[-300:],
            ))
        except (OSError, subprocess.TimeoutExpired) as exc:
            layers.append(_layer("L4", "zero agent rollout", "fail", str(exc)))
        layers.append(_layer(
            "L5/L6", "random agent / 最小训练", "warn",
            "使用 tools/validate_training_smoke.py --mode train（55 profiles 全量）或训练页冒烟档",
        ))

    overall = "pass"
    for status in ("fail", "warn"):
        if any(layer["status"] == status for layer in layers):
            overall = status
            break
    return {
        "success": True,
        "depth": depth,
        "overall": overall,
        "elapsed_s": round(time.time() - started, 2),
        "layers": layers,
    }


@router.get("/demo-cards")
async def demo_cards():
    """T5.4：demo 卡目录（29 ONNX 按机器人分组直达 Sim2Sim——新用户"哇"时刻入口）。

    数据源：各包 simulation/config.json 的 policies + demo_policies（数据驱动，
    无 per-robot 分支）；点击卡片 → /web/sim2sim/?robot=<id>&policy=<id>。
    """
    from backend.robot_packages import list_robot_packages

    cards = []
    for record in list_robot_packages():
        robot_id = str(record.get("robot_id"))
        root = Path(str((record.get("robot_package") or {}).get("package_root", "")))
        config_path = root / "simulation" / "config.json"
        if not config_path.exists():
            continue
        try:
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        for item in (config.get("policies") or []) + (config.get("demo_policies") or []):
            if not isinstance(item, dict) or not (item.get("path") or item.get("url")):
                continue
            url = str(item.get("url") or f"/api/simulation/browser-package/{robot_id}/{str(item['path']).replace(chr(92), '/')}")
            cards.append({
                "robot_id": robot_id,
                "family": record.get("family") or robot_id,
                "id": str(item.get("id") or Path(url).stem),
                "label": str(item.get("label") or item.get("id") or Path(url).stem),
                "url": url,
                "obs_dim": item.get("obs_dim"),
                "action_dim": item.get("action_dim"),
                "task_type": (item.get("contract") or {}).get("task_type"),
                "play_url": f"/web/sim2sim/index.html?robot={robot_id}&policy={item.get('id', '')}",
            })
    cards.sort(key=lambda item: (item["robot_id"], item["id"]))
    return {"success": True, "count": len(cards), "cards": cards}
