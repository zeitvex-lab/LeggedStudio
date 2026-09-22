"""任务插件 HTTP 面（v2 高级仿真"任务即插件"的控制面）。

两个端点，刻意都很薄（**判据全在** `backend.task_plugins`，这里只做 HTTP 形状）：

* ``GET /api/task-plugins`` —— 列出注册表（含每条要哪些传感器、各自能力级、命令来源是否
  有执行器支持）⇒ 页面拿它直接渲染"选任务"下拉，不需要自己抄一份传感器需求；
* ``POST /api/task-plugins/{plugin_id}/instantiate`` —— 把插件**补齐到一份场景**上，
  返回 `scenario`（可直接喂仿真）+ `obs_items`（S2① 生成）+ `readiness`（能不能真跑）。

未知插件 id / 声明不合法一律 **400 带原话**（"接口说谎"的反面：拒绝要说清怎么改）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from contracts.task_plugin_contract import TaskPluginError

router = APIRouter(prefix="/api/task-plugins", tags=["task-plugins"])


class InstantiateTaskPluginRequest(BaseModel):
    """把任务插件实例化到一份**可选**基场景上（缺省从空白场景开始）。"""

    scenario: dict[str, Any] | None = Field(default=None, description="基场景（任务插件只补它声明的字段）")


@router.get("")
async def list_task_plugins() -> dict[str, Any]:
    """列出任务插件（含传感器需求与能力级——**诚实**到"能不能真跑"这一层）。"""

    from backend.task_plugins import list_task_plugins as _list

    try:
        plugins = _list()
    except TaskPluginError as exc:
        raise HTTPException(status_code=500, detail=f"任务插件注册表不合法：{exc}") from exc
    return {"success": True, "count": len(plugins), "plugins": plugins}


@router.post("/{plugin_id}/instantiate")
async def instantiate(plugin_id: str, request: InstantiateTaskPluginRequest) -> dict[str, Any]:
    """把插件补齐成可跑的场景（含 recipe 观测项）——**不落盘**，回载荷给调用方。"""

    from backend.task_plugins import instantiate_task_plugin

    try:
        return instantiate_task_plugin(plugin_id, scenario=request.scenario)
    except TaskPluginError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
