"""Versioned scenario and training-recipe contracts.

These models are shared by native MJLab training and MuJoCo simulation
workflows.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Waypoint(BaseModel):
    x: float
    y: float
    tolerance: float = Field(default=0.35, gt=0.0, le=5.0)


class DepthCameraSpec(BaseModel):
    """深度相机观测项（图像尺寸默认取 PIE 参考 106×60）。"""

    width: int = Field(default=106, gt=0, le=4096)
    height: int = Field(default=60, gt=0, le=4096)
    cutoff_m: float = Field(default=3.0, gt=0.0, le=100.0)
    update_interval: int = Field(default=5, ge=1, le=1000)


class PerceptionSpec(BaseModel):
    """感知观测项（scenario-contract-1.1 的 ``perception``）。

    **感知分层在这里落成字段（H24）**：``route`` 区分两条都算合格的路径——

    * ``obs``（A 类）：传感器**进策略观测**，策略本身吃感知（如 go2-parkour 的 depth）；
    * ``external``（B 类）：感知**在策略外**，RL 只负责运动（可以是本体感觉盲狗），
      由外挂传感器 + 规划/感知模块做目标判定与任务分段。

    ``mount`` 是「**传感器可外挂**」的落点：挂载点标识（``base`` / ``head`` /
    ``scene:<id>``——挂在场景里而非机器人上）。
    """

    heightfield: bool = False
    depth_camera: DepthCameraSpec | None = None
    foot_contact: bool = False
    route: Literal["obs", "external"] = "external"
    mount: str = Field(default="base", min_length=1)


class TerrainSpec(BaseModel):
    """地形（1.1 新增；ArenaX ``terrain_generator`` 三件套的直接映射）。"""

    kind: Literal["flat", "slope", "stairs", "noise", "obstacle_mix"] = "flat"
    elements: list[dict[str, Any]] = Field(default_factory=list)
    heightmap_png: str | None = None
    xml_path: str | None = None
    generator_params: dict[str, Any] = Field(default_factory=dict)


class TerminationSpec(BaseModel):
    """终止条件（1.1 新增）。"""

    fall_pitch: float | None = Field(default=None, gt=0.0)
    timeout: float | None = Field(default=None, gt=0.0)
    collision_count: int | None = Field(default=None, ge=0)
    out_of_bounds: float | None = Field(default=None, gt=0.0)


class AssessmentSpec(BaseModel):
    """评估口径（1.1 新增）——导航报告写回策略档案的判据。"""

    route_completion_min: float | None = Field(default=None, ge=0.0, le=1.0)
    tracking_error_max: float | None = Field(default=None, ge=0.0)
    stability: bool | None = None


class ScenarioContract(BaseModel):
    """场景契约（v1.1）。

    **为什么必须对齐 1.1**（2026-09-13 实测）：``contracts/schema/scenario-contract-1.1.schema.json``
    早就是高级仿真口径（terrain / termination / assessment / perception 四组字段），
    但本模型停留在 1.0 且没有这四组——而两个消费端（``backend/api_complete.validate_scenario``、
    ``backend/simulation_api``）都只用本模型做校验，**结果是高级仿真字段被静默丢弃**：
    写进场景的地形/终止/评估/感知在通过校验后就消失了。
    """

    schema_version: str = "scenario-contract-1.1"
    scenario_id: str = Field(pattern=r"^[a-z0-9_-]+$")
    map_id: str = "flat"
    mode: Literal["basic", "navigation"] = "basic"
    seed: int = 0
    episode_length_s: float = Field(default=60.0, gt=0.0, le=3600.0)
    waypoints: list[Waypoint] = Field(default_factory=list)
    command_limits: dict[str, float] = Field(default_factory=lambda: {"vx": 1.0, "vy": 1.0, "wz": 1.0})
    metrics: list[str] = Field(default_factory=lambda: ["reward", "distance", "route_completion"])
    # --- 1.1 高级仿真四组（H1：Mode / Sensors / CommandSource / Checks / Recorders）---
    terrain: TerrainSpec | None = None
    termination: TerminationSpec | None = None
    assessment: AssessmentSpec | None = None
    perception: PerceptionSpec | None = None
    # H3：命令来源。``planner`` = 外部规划输出 cmd_vel 复用 velocity 策略（不重训即可走完全程）
    command_source: Literal["policy", "planner", "perception", "script", "teleop"] = "policy"
    checks: list[str] = Field(default_factory=lambda: ["arrival", "route_completion"])
    recorders: list[str] = Field(default_factory=lambda: ["trajectory", "metrics"])

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        allowed = ("scenario-contract-1.0", "scenario-contract-1.1")
        if value not in allowed:
            raise ValueError(f"未知 scenario schema_version：{value!r}（允许 {list(allowed)}）")
        return value

    @field_validator("command_limits")
    @classmethod
    def validate_command_limits(cls, value: dict[str, float]) -> dict[str, float]:
        required = {"vx", "vy", "wz"}
        if not required.issubset(value):
            raise ValueError("command_limits must contain vx, vy and wz")
        if any(float(item) <= 0 for item in value.values()):
            raise ValueError("command limits must be positive")
        return {key: float(item) for key, item in value.items()}

    @model_validator(mode="after")
    def validate_perception_routing(self) -> "ScenarioContract":
        """把「感知分层」写成**契约约束**（fail-closed，而不是靠约定）。

        * ``route=obs``（A 类）⇒ 策略必须自己吃感知 ⇒ ``command_source=policy``；
        * ``command_source`` 为 ``planner`` / ``perception``（B 类的外部决策）⇒
          必须有航点，否则"导航"没有目标，跑了也判不出结果。
        """
        perception = self.perception
        if perception is not None and perception.route == "obs" and self.command_source != "policy":
            raise ValueError(
                "perception.route=obs（A 类：感知入观测）要求 command_source=policy，"
                f"当前为 {self.command_source!r}；感知在策略外请用 route=external"
            )
        if self.command_source in ("planner", "perception") and not self.waypoints:
            raise ValueError(f"command_source={self.command_source!r} 需要至少一个 waypoint")
        return self

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class TrainingRecipe(BaseModel):
    """Resolved task recipe shared by Web, CLI and adapter workers."""

    schema_version: str = "training-recipe-1.0"
    task_name: str = "forward_walk"
    algorithm: str = "PPO"
    backend: Literal["native_mjlab"] = "native_mjlab"
    reward_scales: dict[str, float] = Field(default_factory=dict)
    environment: dict[str, Any] = Field(default_factory=dict)
    algorithm_config: dict[str, Any] = Field(default_factory=dict)
    seed: int = 0

    @field_validator("algorithm")
    @classmethod
    def normalize_algorithm(cls, value: str) -> str:
        return value.upper()
