"""感知闭环的 HTTP 面（S6）：provider 清单 + 地形判定与切换决定。

两个入口：

* ``GET  /api/perception/providers``        —— provider 清单（权威注册表的内容 + 自检）；
* ``POST /api/perception/terrain/evaluate`` —— 按场景 + 位姿做地形判定，并给出切换决定。

**为什么用"场景 + 位姿"而不是上传点云**：浏览器侧 vendored 的 MuJoCo WASM 没有确证导出
射线接口，拿不到机载高度扫描；而服务端有**唯一实现**的高度扫描构造器
（`backend/height_scan.py`）与地形数据（`backend/perception_scene.py`）。浏览器只上传位姿，
判定与切换仍只有一处实现——不会因为端不同而口径漂移。

**fail-closed**：未知场景 / 无法复现的场景直接报错（不按平地处理），
返回值里带 `reproducible` 与 `source`，让调用方能把"依据是什么"显示出来。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.perception_providers import PerceptionProviderError, provider_selftest, provider_specs
from backend.perception_scene import SceneTerrainError, height_scan_at
from backend.skill_switch import plan_switch

router = APIRouter(prefix="/api/perception", tags=["perception"])

DEFAULT_BASE_LIMITS = {"vx": 0.9, "vy": 0.5, "wz": 0.85}


class TerrainEvaluateRequest(BaseModel):
    """按场景与位姿求地形判定（浏览器导航闭环用）。"""

    scene_id: str = Field(description="场景 id：flat 或 workspace/scenes/<id> 下已生成的场景")
    base_xy: list[float] = Field(default_factory=lambda: [0.0, 0.0], min_length=2, max_length=2)
    base_z: float = Field(default=0.45, description="机身高度（米），用于 value = base_z - terrain_z")
    base_yaw: float = 0.0
    base_limits: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_BASE_LIMITS))
    available_policies: list[str] = Field(default_factory=list)
    provider_id: str = "terrain_classifier"


class RenderDetectRequest(BaseModel):
    """渲染一帧 + 几何检测 + 位姿反解（"这套框到底对不对"的可视化入口）。"""

    scene_xml: str | None = Field(
        default=None,
        description="MJCF 文本；留空则用内置自检场景（深色地面 + 白色标签 + 正对相机）",
    )
    camera: str = Field(default="front", description="MJCF 里声明的相机名——**渲染与投影都用它**")
    tag_body: str = Field(default="tag", description="标签所在的 body 名")
    tag_size_m: float = Field(default=0.16, gt=0.0, description="标签物理边长（米）")
    width: int = Field(default=320, ge=64, le=1280)
    height: int = Field(default=240, ge=64, le=720)
    sigma_px: float = Field(default=0.0, ge=0.0, description="检测像素噪声标准差")
    bias_px: float = Field(default=0.0, description="检测系统性像素偏移")
    drop_frame_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    drop_corner_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    seed: int = Field(default=0, description="固定种子 ⇒ 同参数必复现（回归可当门禁）")
    include_image: bool = Field(default=True, description="是否返回 base64 PNG（关掉可只看几何与框）")


@router.post("/render/detect")
async def render_detect(request: RenderDetectRequest) -> dict[str, Any]:
    """渲染一帧 → **几何检测**（带声明式噪声）→ 位姿反解，返回 PNG 与**可对齐的框**。

    对齐的前提是"渲染与投影走同一台 MJCF 相机"（``backend/perception_pipeline.py``）——
    用 ``mjv_defaultFreeCamera`` 自动取景的那套渲染**没有内参**，框画不准。

    **边界**：检测由 ``backend/synthetic_detector.py`` 提供，是「几何 + 声明式噪声」的
    **检测器模型**，**不是图像识别**；响应里 ``image_based=false`` 明确标注，免得被当成视觉能力。

    渲染不可用（无离屏 GL）时返回 ``success=false`` + 原因而**不是 500**：
    那是环境能力问题，不该表现成接口故障。
    """
    import random

    from backend.gl_env import render_error_hint
    from backend.perception_pipeline import SELFTEST_SCENE, ensure_render_backend, render_and_detect
    from backend.synthetic_detector import DetectionNoise

    ensure_render_backend()
    try:
        import mujoco
    except Exception as exc:  # pragma: no cover - mujoco 缺失属环境问题
        raise HTTPException(status_code=503, detail=f"MuJoCo 不可用：{exc}") from exc

    try:
        model = mujoco.MjModel.from_xml_string(request.scene_xml or SELFTEST_SCENE)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"MJCF 编译失败：{exc}") from exc

    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    camera_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, request.camera)
    tag_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, request.tag_body)
    if camera_id < 0:
        raise HTTPException(status_code=400, detail=f"场景里没有名为 {request.camera} 的相机")
    if tag_id < 0:
        raise HTTPException(status_code=400, detail=f"场景里没有名为 {request.tag_body} 的 body")

    try:
        result = render_and_detect(
            model,
            data,
            camera_id=camera_id,
            tag_body_id=tag_id,
            tag_size_m=request.tag_size_m,
            width=request.width,
            height=request.height,
            noise=DetectionNoise(
                sigma_px=request.sigma_px,
                bias_px=request.bias_px,
                drop_frame_rate=request.drop_frame_rate,
                drop_corner_rate=request.drop_corner_rate,
            ),
            rng=random.Random(request.seed),
        )
    except BaseException as exc:
        return {"success": False, "error": render_error_hint(exc), "image_based": False}

    if not request.include_image:
        result.pop("image_png_base64", None)
    return {"success": True, **result}


@router.get("/providers")
async def perception_providers() -> dict[str, Any]:
    """感知 provider 权威清单（含自检与未登记文件诊断）。"""
    try:
        specs = [spec.to_dict() for spec in provider_specs()]
    except PerceptionProviderError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": True, "count": len(specs), "providers": specs, "selftest": provider_selftest()}


class TagEvaluateRequest(BaseModel):
    """按**检测器输出的角点**求标签位姿与停靠伺服（图像检测需可选依赖，本入口不收图像）。"""

    corners_px: list[list[float]] = Field(min_length=4, max_length=4)
    tag_id: str | None = None
    undistorted: bool = False
    camera_profile_id: str | None = Field(default=None, description="覆盖注册表默认档位（标定口径）")
    tag_size_m: float | None = Field(default=None, gt=0.0)
    provider_id: str = "tag_detector"


@router.post("/tag/evaluate")
async def evaluate_tag_endpoint(request: TagEvaluateRequest) -> dict[str, Any]:
    """标签位姿 + 停靠判定 + 伺服指令（几何与判据都复用唯一实现）。"""
    from backend.perception_providers import resolve_provider, provider_spec

    try:
        spec = provider_spec(request.provider_id)
    except PerceptionProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    params = dict(spec.params)
    if request.camera_profile_id:
        params["camera_profile_id"] = request.camera_profile_id
    if request.tag_size_m is not None:
        params["tag_size_m"] = float(request.tag_size_m)
    try:
        provider = resolve_provider(request.provider_id)
        provider.init(params)
        provider.on_reset()
        reading = provider.update(
            {"tag_id": request.tag_id, "corners_px": request.corners_px, "undistorted": request.undistorted},
            0.0,
        )
    except (PerceptionProviderError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "success": True,
        "reading": reading,
        "note": (
            "输入是**检测器输出的角点**（不是图像）：本次环境未装图像检测依赖，"
            "该 provider 只做「角点 → 位姿 → 停靠判定 → 伺服指令」；停靠容差取 H10 视觉停靠真值。"
        ),
    }


@router.post("/terrain/evaluate")
async def evaluate_terrain_endpoint(request: TerrainEvaluateRequest) -> dict[str, Any]:
    """地形判定 + 切换决定（服务端唯一实现：provider + skill_switch）。"""
    try:
        scan, scene_meta = height_scan_at(
            request.scene_id, request.base_xy, base_z=request.base_z, base_yaw=request.base_yaw
        )
    except SceneTerrainError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        from backend.perception_providers import resolve_provider

        provider = resolve_provider(request.provider_id)
    except PerceptionProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    reading = provider.update(scan, 0.0)
    switch = plan_switch(
        reading.get("action"),
        base_limits=request.base_limits,
        available_policies=request.available_policies,
    )
    return {
        "success": True,
        "scene": scene_meta,
        "reading": reading,
        "switch": switch,
        "height_scan_points": len(scan),
        "note": (
            "依据 = 场景地形数据 + 上传的位姿（**不是机载射线/深度**）；"
            "机载感知留给原生链路。空场景高度场不可复现时会报错而不是按平地处理。"
        ),
    }
