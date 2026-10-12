"""CLI 离线命令的仓内定位助手（自 scripts/legged_studio_cli.py 拆分，2026-10-12；函数体零改动）。

workspace 根解析与 run 状态读取（backend.paths 同一口径）。
"""

from __future__ import annotations

import json
from pathlib import Path



def _workspace_root(workspace: str | None) -> Path:
    """workspace 根：``--workspace`` 参数 > 环境变量 > 仓库 ``workspace/``（唯一实现见 ``backend/paths.py``）。

    ``--workspace`` 分支也做 ``resolve()``：否则同一个 ``--workspace ws`` 会以相对/绝对两种
    形态出现在"环境变量里的值"与"下游模块解析出的值"之间，前缀判断与缓存键随之失配。
    """

    if workspace:
        return Path(workspace).expanduser().resolve()
    from backend.paths import workspace_root

    return workspace_root()


def _run_status(run_dir: Path, fallback: str) -> str:
    """读 ``status.json`` 的 ``status`` 字段；缺失/不可解析时回退 run.json 自带的 status（如实，不编造）。"""

    try:
        payload = json.loads((run_dir / "status.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return fallback
    value = payload.get("status") if isinstance(payload, dict) else None
    return str(value) if value else fallback
