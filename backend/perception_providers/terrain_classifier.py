"""地形/台阶分类 provider（首个真实 provider，route=external）。

**吃**：187 维高度扫描（`backend/height_scan.py` 的网格契约：x 主序 `ix*11+iy`、
机身系 x 前 y 左、`value = base_z - terrain_z`、米、未缩放）。
**吐**：`terrain_class / confidence / metrics / action / stable`（结构见注册表清单）。

分类是**阈值型**的（不是学习型），理由有两条：
1. 阈值判定可解释、可测（合成地形能精确构造期望类别），适合先把"感知 → 切换"链路跑通；
2. 阈值与动作映射都放在 `registry/perception_providers/index.json`（数字是数据），
   标了 `calibration=pending`——**没有真实地形回归标定前不许当验收判据**。

去抖：连续 `stable_readings` 次同类才对外切换（`stable=true`）；抖动期内保留上一次稳定类别，
避免"动作跟着噪声抖"。这条来自参考实践：`nav_route_sim2sim_check.py` 的 `stable_cycles` 同理。
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from backend.height_scan import GRID_SHAPE, GRID_SPACING_M, MEASURED_POINTS_X, MEASURED_POINTS_Y

TERRAIN_CLASSES = ("flat", "slope_up", "slope_down", "stair_up", "stair_down", "rough", "obstacle")


def _grid(height_scan: Sequence[float]) -> list[list[float]]:
    """187 → 17×11（`grid[ix][iy]`，与 height_scan 的 x 主序一致）。"""
    values = [float(v) for v in height_scan]
    if len(values) != GRID_SHAPE[0] * GRID_SHAPE[1]:
        raise ValueError(f"高度扫描必须是 {GRID_SHAPE[0] * GRID_SHAPE[1]} 维（得到 {len(values)}）")
    return [[values[ix * GRID_SHAPE[1] + iy] for iy in range(GRID_SHAPE[1])] for ix in range(GRID_SHAPE[0])]


def forward_corridor(params: dict[str, Any]) -> tuple[list[int], list[int]]:
    """前向走廊的格子范围 `(ix 列表, iy 列表)`（由注册表参数决定，不在代码里写死）。"""
    x_min = float(params["forward_min_m"])
    x_max = float(params["forward_max_m"])
    half_width = float(params["half_width_m"])
    ix = [i for i, x in enumerate(MEASURED_POINTS_X) if x_min <= x <= x_max]
    iy = [i for i, y in enumerate(MEASURED_POINTS_Y) if abs(y) <= half_width]
    if not ix or not iy:
        raise ValueError("前向走廊为空：检查 forward_min_m/forward_max_m/half_width_m 参数")
    return ix, iy


def terrain_metrics(height_scan: Sequence[float], params: dict[str, Any]) -> dict[str, float]:
    """走廊内的三个几何量 + 前向总分差。

    * ``max_step_signed_m``：相邻 ``x`` 单元间最大的**带符号**高度差；
      高度扫描的取值是 ``base_z - terrain_z``，所以**前方地形变高 ⇒ 该值为负**
      （负 = 上台阶/上坡方向，正 = 下台阶方向）；
    * ``slope_deg``：沿 ``x`` 的中位梯度换算成角度（上坡为正）；
    * ``roughness_m``：扣除前向线性趋势后的残差标准差（是否像"平面/斜坡"）；
    * ``forward_drop_m``：走廊最远列与最近列的高度差（带上坡正号）。
    """
    grid = _grid(height_scan)
    ix, iy = forward_corridor(params)

    # 相邻列（x 方向）之间的带符号差
    max_step_signed = 0.0
    gradients: list[float] = []
    for i in range(len(ix) - 1):
        for j in iy:
            delta = grid[ix[i + 1]][j] - grid[ix[i]][j]
            if abs(delta) > abs(max_step_signed):
                max_step_signed = delta
            # value 随地形升高而减小 ⇒ 地形梯度 = -Δvalue/Δx
            gradients.append(-delta / GRID_SPACING_M)
    gradients.sort()

    def median(values: list[float]) -> float:
        if not values:
            return 0.0
        middle = len(values) // 2
        return values[middle] if len(values) % 2 else 0.5 * (values[middle - 1] + values[middle])

    gradient = median(gradients)
    slope_deg = math.degrees(math.atan(gradient))

    # 残差：走廊内每个点相对"最近列 + 前向线性趋势"的偏差
    base_column = [grid[ix[0]][j] for j in iy]
    base_mean = sum(base_column) / len(base_column)
    residuals: list[float] = []
    for i, column_index in enumerate(ix):
        expected = base_mean - gradient * MEASURED_POINTS_X[column_index]
        for j in iy:
            residuals.append(grid[column_index][j] - expected)
    mean_residual = sum(residuals) / len(residuals)
    variance = sum((value - mean_residual) ** 2 for value in residuals) / len(residuals)
    roughness = math.sqrt(variance)

    near = sum(grid[ix[0]][j] for j in iy) / len(iy)
    far = sum(grid[ix[-1]][j] for j in iy) / len(iy)
    return {
        "max_step_signed_m": round(max_step_signed, 6),
        "max_step_m": round(abs(max_step_signed), 6),
        "step_is_uphill": max_step_signed < 0.0,
        "slope_deg": round(slope_deg, 4),
        "gradient": round(gradient, 6),
        "roughness_m": round(roughness, 6),
        "forward_drop_m": round(near - far, 6),
    }


def classify_terrain(metrics: dict[str, float], params: dict[str, Any]) -> tuple[str, float]:
    """阈值判定 + 置信度（0..1）。

    优先级：**obstacle → stair → rough → slope → flat**。

    ``rough`` 排在 ``slope`` 之前是刻意的：非平面地形上，"坡度"这个一阶量本来就不可信
    （残差大 ⇒ 平面模型不成立），此时报 ``rough`` 比报一个方向可疑的坡度更有用——切换动作
    也不一样（粗糙地形降速 vs 上/下坡保守）。链条上它仍是"保守优先"。"""
    step = float(metrics["max_step_m"])
    slope = float(metrics["slope_deg"])
    roughness = float(metrics["roughness_m"])
    uphill = bool(metrics["step_is_uphill"]) or slope > 0

    step_min = float(params["step_min_m"])
    step_max = float(params["step_max_m"])
    slope_min = float(params["slope_min_deg"])
    slope_max = float(params["slope_max_deg"])
    rough_std = float(params["rough_std_m"])
    margin_m = float(params["confidence_margin_m"])
    margin_deg = float(params["confidence_margin_deg"])

    def confidence(distance: float, scale: float) -> float:
        return round(max(0.0, min(1.0, distance / scale)) if scale > 0 else 0.0, 4)

    if step >= step_max or abs(slope) >= slope_max:
        worst = max(step / step_max if step_max else 0.0, abs(slope) / slope_max if slope_max else 0.0)
        return "obstacle", round(max(0.5, min(1.0, worst)), 4)
    if step >= step_min:
        cls = "stair_up" if uphill else "stair_down"
        return cls, confidence(step - step_min, margin_m)
    if roughness > rough_std:
        return "rough", confidence(roughness - rough_std, rough_std)
    if abs(slope) >= slope_min:
        cls = "slope_up" if slope > 0 else "slope_down"
        return cls, confidence(abs(slope) - slope_min, margin_deg)
    # 离"像台阶/像斜坡"的边界有多远，决定"平地"的置信度
    near_step = max(0.0, step_min - step) / (margin_m or 1.0)
    near_slope = max(0.0, slope_min - abs(slope)) / (margin_deg or 1.0)
    return "flat", confidence(min(near_step, near_slope), 1.0)


class TerrainClassifier:
    """provider 实现（生命周期形状：init / update / on_reset）。"""

    provider_id = "terrain_classifier"

    def init(self, params: dict[str, Any]) -> None:
        required = (
            "forward_min_m", "forward_max_m", "half_width_m", "step_min_m", "step_max_m",
            "slope_min_deg", "slope_max_deg", "rough_std_m", "stable_readings",
            "confidence_margin_m", "confidence_margin_deg", "actions",
        )
        missing = [key for key in required if key not in params]
        if missing:
            raise ValueError(f"terrain_classifier 缺参数 {missing}（阈值只有注册表一处真值）")
        self.params = dict(params)
        self.on_reset()

    def on_reset(self) -> None:
        self._stable_class: str | None = None
        self._candidate: str | None = None
        self._candidate_count = 0
        self._readings = 0
        self._last_reading: dict[str, Any] | None = None

    def update(self, reading: Any, time_s: float = 0.0) -> dict[str, Any]:
        """吃一帧高度扫描（187 维列表或 ``{"height_scan": [...]}``），吐结构化判定。"""
        scan = reading.get("height_scan") if isinstance(reading, dict) else reading
        if scan is None:
            raise ValueError("terrain_classifier 需要 height_scan（187 维列表或 {'height_scan': [...]}）")
        metrics = terrain_metrics(scan, self.params)
        raw_class, confidence = classify_terrain(metrics, self.params)
        self._readings += 1

        if raw_class == self._candidate:
            self._candidate_count += 1
        else:
            self._candidate = raw_class
            self._candidate_count = 1
        needed = max(1, int(self.params["stable_readings"]))
        stable = self._candidate_count >= needed
        if stable:
            self._stable_class = raw_class

        effective = self._stable_class or raw_class
        action = dict((self.params.get("actions") or {}).get(effective) or {})
        self._last_reading = {
            "terrain_class": effective,
            "raw_class": raw_class,
            "confidence": confidence,
            "stable": stable,
            "candidate_count": self._candidate_count,
            "required_readings": needed,
            "metrics": metrics,
            "action": action,
            "sensor": "heightfield",
            "provider_id": self.provider_id,
            "readings": self._readings,
            "time_s": float(time_s),
        }
        return dict(self._last_reading)

    @property
    def last_reading(self) -> dict[str, Any] | None:
        return dict(self._last_reading) if self._last_reading else None
