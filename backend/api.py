"""
Legged Studio Backend - Enhanced API
集成 Contract、Asset Inventory 和工具
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pathlib import Path
from typing import Optional, List
import sys

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from contracts.models import AssetRecord, filter_assets
from contracts.utils.mass_estimator import classify_size_by_mass

app = FastAPI(
    title="Legged Studio API",
    description="足式机器人强化学习工作室后端",
    version="0.1.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# 基础端点
# ============================================================================

@app.get("/")
async def root():
    """根端点"""
    return {
        "name": "Legged Studio API",
        "version": "0.1.0",
        "phase": "Phase 0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "ok",
        "version": "0.1.0",
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "phase": "Phase 0"
    }


# ============================================================================
# Asset Inventory 端点
# ============================================================================

@app.get("/api/assets/summary")
async def get_assets_summary():
    """
    获取资产清单摘要

    返回：
        {
            "total": int,
            "by_size": {"S": int, "M": int, "L": int},
            "by_locomotion": {"P": int, "W": int},
            "families": List[str]
        }
    """
    try:
        # TODO: 从实际 inventory 加载
        # 这里返回模拟数据
        return {
            "total": 107,
            "by_size": {"S": 35, "M": 42, "L": 30},
            "by_locomotion": {"P": 67, "W": 40},
            "families": ["Go1", "Go2", "A1", "A2", "Aliengo", "ANYmal", "B1", "B2"],
            "note": "数据来自 QUADRUPED_ASSET_INVENTORY.json"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/assets/robots")
async def get_robots(
    size: Optional[str] = None,
    locomotion: Optional[str] = None,
    family: Optional[str] = None,
    usable_only: bool = True
):
    """
    查询机器人资产

    参数：
        size: S | M | L
        locomotion: P | W
        family: 机器人家族名
        usable_only: 仅返回可用的

    返回：
        List[AssetRecord]
    """
    try:
        # TODO: 从实际 inventory 加载并过滤
        # 这里返回模拟数据

        # 示例：Go2
        go2_example = {
            "family": "Go2",
            "size_class_by_mass": "M",
            "locomotion": "P",
            "readiness": "READY",
            "role": "PRESET_CANDIDATE",
            "usable": True,
            "mass_kg": 15.0,
            "urdf_path": "go2_description/urdf/go2.urdf",
            "note": "最合理的 MVP 主线"
        }

        return {
            "count": 1,
            "robots": [go2_example],
            "filters": {
                "size": size,
                "locomotion": locomotion,
                "family": family,
                "usable_only": usable_only
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/assets/robots/{family}")
async def get_robot_by_family(family: str):
    """
    按家族获取机器人详情

    参数：
        family: 机器人家族名（如 Go2, A1）
    """
    # TODO: 从实际 inventory 查询

    families_map = {
        "Go2": {
            "family": "Go2",
            "size": "M",
            "locomotion": "P",
            "mass_kg": 15.0,
            "readiness": "READY",
            "variants": ["Go2", "Go2W"],
            "description": "宇树 Go2，M 级点足，最合理的 MVP 主线"
        },
        "A1": {
            "family": "A1",
            "size": "M",
            "locomotion": "P",
            "mass_kg": 12.0,
            "readiness": "READY",
            "variants": ["A1"],
            "description": "宇树 A1，M 级点足"
        }
    }

    if family not in families_map:
        raise HTTPException(status_code=404, detail=f"Family '{family}' not found")

    return families_map[family]


# ============================================================================
# STL 工具端点
# ============================================================================

@app.post("/api/tools/stl/volume")
async def calculate_stl_volume(stl_path: str):
    """
    计算 STL 体积

    参数：
        stl_path: STL 文件路径

    返回：
        {
            "volume_m3": float,
            "stl_path": str
        }
    """
    try:
        from tools.stl_volume import calculate_volume_from_stl

        volume = calculate_volume_from_stl(stl_path)

        return {
            "volume_m3": volume,
            "stl_path": stl_path
        }

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"STL file not found: {stl_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tools/stl/estimate-mass")
async def estimate_mass_from_stl(
    stl_path: str,
    material: str = "abs_plastic",
    density: Optional[float] = None
):
    """
    估算质量

    参数：
        stl_path: STL 文件路径
        material: 材料类型
        density: 自定义密度（可选）
    """
    try:
        from tools.stl_volume import estimate_mass

        result = estimate_mass(
            stl_path,
            density=density if density else None,
            material=material if not density else None
        )

        # 添加尺寸分类
        size_class = classify_size_by_mass(result['mass_kg'])
        result['size_class'] = size_class

        return result

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"STL file not found: {stl_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Contract 端点
# ============================================================================

@app.get("/api/contracts/template")
async def get_contract_template():
    """
    获取 Contract 模板

    返回：
        RobotContract JSON Schema
    """
    from contracts.models import RobotContract

    return {
        "schema_version": "robot-contract-1.0",
        "json_schema": RobotContract.model_json_schema(),
        "example": {
            "schema_version": "robot-contract-1.0",
            "robot_id": "go2",
            "model_revision": "v1.0",
            "urdf_path": "go2_description/urdf/go2.urdf",
            "control_hz": 50,
            "physics_hz": 1000,
            "action_scale": 1.0,
            "default_pose": [0.0] * 12,
            "actuated_joint_names": ["FR_hip", "FR_thigh", "FR_calf", "FL_hip", "FL_thigh", "FL_calf",
                                     "RR_hip", "RR_thigh", "RR_calf", "RL_hip", "RL_thigh", "RL_calf"],
            "note": "示例 Contract"
        }
    }


@app.post("/api/contracts/validate")
async def validate_contract(contract_data: dict):
    """
    验证 Contract

    参数：
        contract_data: Contract JSON

    返回：
        {
            "valid": bool,
            "errors": List[str],
            "warnings": List[str]
        }
    """
    try:
        from contracts.models import RobotContract

        # 尝试加载
        contract = RobotContract(**contract_data)

        return {
            "valid": True,
            "errors": [],
            "warnings": [],
            "contract": contract.model_dump()
        }

    except Exception as e:
        return {
            "valid": False,
            "errors": [str(e)],
            "warnings": []
        }


# ============================================================================
# 系统信息端点
# ============================================================================

@app.get("/api/system/info")
async def get_system_info():
    """
    获取系统信息
    """
    import platform

    return {
        "platform": platform.system(),
        "platform_version": platform.version(),
        "python_version": sys.version,
        "architecture": platform.machine(),
        "node": platform.node(),
    }


@app.get("/api/system/environment")
async def get_environment_status():
    """
    获取环境状态
    """
    adapters_status = {}

    # 检查 MJLab adapter
    mjlab_venv = Path(__file__).parent.parent / "adapters" / "mjlab" / ".venv"
    adapters_status["mjlab"] = {
        "name": "MJLab Adapter",
        "venv_exists": mjlab_venv.exists(),
        "python_path": str(mjlab_venv / "Scripts" / "python.exe") if mjlab_venv.exists() else None,
        "status": "installed" if mjlab_venv.exists() else "not_installed"
    }

    return {
        "control_plane": {
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "status": "running"
        },
        "adapters": adapters_status
    }


# ============================================================================
# 错误处理
# ============================================================================

@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "Not Found", "detail": str(exc.detail)}
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "detail": str(exc)}
    )


# ============================================================================
# 启动
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("Legged Studio Backend - Enhanced API")
    print("=" * 60)
    print()
    print("📊 API 端点：")
    print("  - GET  /              根端点")
    print("  - GET  /health        健康检查")
    print("  - GET  /docs          Swagger 文档")
    print()
    print("📦 Asset Inventory：")
    print("  - GET  /api/assets/summary")
    print("  - GET  /api/assets/robots")
    print("  - GET  /api/assets/robots/{family}")
    print()
    print("🔧 STL 工具：")
    print("  - POST /api/tools/stl/volume")
    print("  - POST /api/tools/stl/estimate-mass")
    print()
    print("📋 Contract：")
    print("  - GET  /api/contracts/template")
    print("  - POST /api/contracts/validate")
    print()
    print("💻 系统：")
    print("  - GET  /api/system/info")
    print("  - GET  /api/system/environment")
    print()
    print("=" * 60)
    print("🚀 启动服务器...")
    print("=" * 60)

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8765,
        log_level="info"
    )
