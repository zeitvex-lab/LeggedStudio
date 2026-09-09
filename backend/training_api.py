"""
Training API
训练任务管理的 REST API

本文件由原 god file（~960 行）按「创建/监控/产物/健康/schema」拆分而来，
仅作为聚合入口：组合各子模块的 router，并 re-export 公共模型，保持
`backend.api_complete` 与 `backend.test_api_complete` 的导入路径不变。
"""

from fastapi import APIRouter

# 各职责子模块（拆分自原 god file，路由路径与响应结构不变）。
from backend.training.models import (
    CreateTrainingRequest,
    TrainingStatusResponse,
    CompareTrainingRequest,
)
from backend.training.schema import (
    router as schema_router,
    RECIPE_READONLY_NOTE,
    CONTRACT_READONLY_NOTE,
    ARCHIVED_ONLY_NOTE,
    EDITABLE_CREATE_KEYS,
)
from backend.training.create import router as create_router
from backend.training.monitor import router as monitor_router
from backend.training.artifacts import router as artifacts_router
from backend.training.events import router as events_router


router = APIRouter()
# 各子 router 已自带 /api/training 前缀，include 后路径保持一致。
router.include_router(create_router)
router.include_router(schema_router)
router.include_router(monitor_router)
router.include_router(artifacts_router)
router.include_router(events_router)


__all__ = [
    "router",
    "CreateTrainingRequest",
    "TrainingStatusResponse",
    "CompareTrainingRequest",
]
