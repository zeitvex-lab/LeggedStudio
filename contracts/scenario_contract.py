"""Versioned scenario and training-recipe contracts.

These models are shared by native MJLab training and MuJoCo simulation
workflows.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from contracts.sensor_plugin_contract import (
    SAFE_ID_PATTERN,
    LatencySpec,
    NoiseSpec,
    command_provider_definition,
    command_provider_ids,
    plugin_definition,
    plugin_ids,
)
from contracts.simulation_run_contract import RecordingOptions, ScheduledEvent

#: 场景侧实例/事件标识：**复用**插件契约的安全 id 规则（同一份 pattern，不各写一遍）。
_SCENARIO_SAFE_ID_RE = re.compile(SAFE_ID_PATTERN)
_SCENARIO_SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

#: 1.2：新增 ``advanced`` 入口（v2 原生闭环）。**默认值仍是 1.1** —— 老场景文件与
#: 老调用方（``backend/api_complete.validate_scenario``、``backend/simulation_api``）
#: 的行为逐字不变，只有显式声明 1.2 的场景才允许带高级入口。
SCENARIO_CONTRACT_VERSION_1_2 = "scenario-contract-1.2"


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


# --------------------------------------------------------------------------------------
# scenario-contract-1.2：高级仿真入口（**请求**，不是值）
# --------------------------------------------------------------------------------------
#
# 为什么这些字段要新版本号而不是偷偷加在 1.1 上：1.1 的
# ``contracts/schema/scenario-contract-1.1.schema.json`` 已经落盘，被外部场景文件引用；
# 静默加字段会让"同一版本号的两种解释"出现（旧文件里没人写过 ``advanced``，
# 但新代码会假设它有默认行为）。默认 ``schema_version`` 仍是 ``1.1``，
# 只有显式写 ``1.2`` 的场景才能带高级入口。
#
# 单一真值的边界（**这一条最重要**）
# ---------------------------------
# 这里只允许出现"**我要什么**"：插件 id、实例标识、挂载外参、期望采样率、参数覆盖、
# 记录开关。**不允许**出现插件默认值的副本 —— 默认值与出处只在
# :mod:`contracts.sensor_plugin_contract` 一处，形状与预算只在
# :mod:`contracts.simulation_run_contract` 一处。因此：
#
# * ``config`` 的键必须是该插件**声明过**的参数，且不得直接写 ``sample_period_ticks``
#   （调度周期用 ``sample_hz`` 表达，由解析器按时间基换成整数 tick 并回报真实值）；
# * ``plugin_version`` 必须与 catalog 登记版本一致（不引用未登记的旧版本）；
# * 噪声/延迟直接复用插件契约的 :class:`~contracts.sensor_plugin_contract.NoiseSpec` /
#   :class:`~contracts.sensor_plugin_contract.LatencySpec`（不再造一份退化模型）；
# * 记录选项直接复用 :class:`~contracts.simulation_run_contract.RecordingOptions`
#   （预算默认值的唯一居所，四个数不在这里重复）。


class SensorInstanceRequest(BaseModel):
    """"我要一个这样的传感器实例"（解析器据此产出 :class:`SensorInstanceSpec`）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    instance_id: str
    plugin_id: str
    plugin_version: str
    target_kind: Literal["body", "site", "joint", "camera"] | None = None
    target: str | None = None
    pos: list[float] | None = None
    quat_wxyz: list[float] | None = None
    #: 期望采样率（Hz）。**故意不接受 tick**：tick 依赖时间基，而时间基是机器人包的事实。
    sample_hz: float | None = Field(default=None, gt=0.0, le=20_000.0)
    purpose: Literal["policy", "display", "evaluation"] = "display"
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    noise: NoiseSpec | None = None
    latency: LatencySpec | None = None
    record: bool | None = None
    record_outputs: list[str] | None = None
    record_png: bool | None = None
    sample_stride: int | None = Field(default=None, ge=1, le=10_000)

    @field_validator("instance_id")
    @classmethod
    def _instance_id(cls, value: str) -> str:
        if not _SCENARIO_SAFE_ID_RE.match(value):
            raise ValueError(
                f"instance_id={value!r} 不符合安全标识规则（小写字母开头，可含 _ . -，禁止路径分隔符）"
            )
        return value

    @field_validator("plugin_id")
    @classmethod
    def _plugin_id(cls, value: str) -> str:
        definition = plugin_definition(value)
        if definition is None:
            raise ValueError(
                f"未知传感器插件 {value!r}（catalog 未登记，不能用它写场景；已登记"
                f" {list(plugin_ids())}）"
            )
        if not definition.instantiable:
            raise ValueError(f"插件 {value} 是派生视图，不能单独实例化")
        return value

    @field_validator("plugin_version")
    @classmethod
    def _version_not_blank(cls, value: str) -> str:
        if not _SCENARIO_SEMVER_RE.match(value):
            raise ValueError(f"plugin_version={value!r} 必须是 x.y.z")
        return value

    @field_validator("config")
    @classmethod
    def _config_keys_are_declared(cls, value: dict[str, Any]) -> dict[str, Any]:
        # 需要 plugin_id 才能核对声明 → 在 model_validator 里做；这里只挡最明显的一条：
        # 直接写调度周期会造成"Hz 与 tick 谁作数"的两份真值。
        if "sample_period_ticks" in value:
            raise ValueError(
                "不得在场景里直接写 sample_period_ticks：那是解析后的 tick 值，"
                "请写 sample_hz（解析器按 contract 时间基换成整数 tick 并回报真实率）"
            )
        return value

    @model_validator(mode="after")
    def _cross_check(self) -> "SensorInstanceRequest":
        definition = plugin_definition(self.plugin_id)
        if definition is None:  # pragma: no cover - field_validator 已挡
            raise ValueError(f"未知传感器插件 {self.plugin_id!r}")
        if definition.version != self.plugin_version:
            raise ValueError(
                f"实例 {self.instance_id} 引用插件版本 {self.plugin_version}，"
                f"而 catalog 登记的是 {definition.version}（不允许引用未登记的旧版本）"
            )
        declared = {field.name for field in definition.config}
        unknown = sorted(set(self.config) - declared)
        if unknown:
            raise ValueError(
                f"实例 {self.instance_id}（{self.plugin_id}）含未声明参数 {unknown}"
                f"（可覆盖 {sorted(declared)}）—— 场景不得自造参数名"
            )
        if definition.requires_target and not self.target:
            raise ValueError(f"实例 {self.instance_id}（{self.plugin_id}）必须给 target")
        if not definition.mountable and (self.pos or self.quat_wxyz):
            raise ValueError(
                f"实例 {self.instance_id}（{self.plugin_id}）不是物理器件，不接受 pos/quat 外参"
            )
        for field_name, vector in (("pos", self.pos), ("quat_wxyz", self.quat_wxyz)):
            if vector is None:
                continue
            if any(item != item or item in (float("inf"), float("-inf")) for item in vector):
                raise ValueError(f"实例 {self.instance_id} 的 {field_name} 含非有限数值")
        if self.noise is not None and not definition.supports_noise:
            raise ValueError(f"实例 {self.instance_id}（{self.plugin_id}）不支持噪声")
        if self.latency is not None and not definition.supports_latency:
            raise ValueError(f"实例 {self.instance_id}（{self.plugin_id}）不支持延迟")
        if self.record_outputs is not None:
            outputs = {output.name for output in definition.outputs}
            stray = sorted(set(self.record_outputs) - outputs)
            if stray:
                raise ValueError(
                    f"实例 {self.instance_id} 要求记录未声明的输出 {stray}（可用 {sorted(outputs)}）"
                )
        # 和运行规格读**同一份声明**（``definition.outputs``）：这里只是把"永远解析不出
        # 来的场景"挡在门口，规则本身仍只住在 simulation_run_contract 那一处。
        if self.record_png and not any(
            output.payload_kind == "image_png" for output in definition.outputs
        ):
            raise ValueError(
                f"实例 {self.instance_id}（{self.plugin_id}）没有 PNG 输出"
                "（payload_kind=image_png），record_png 无意义"
            )
        return self


class CommandProviderRequest(BaseModel):
    """"我要在策略外加一个决策器"（B 类）。只改指令，不进观测。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str
    version: str
    input_instance_ids: list[str] = Field(min_length=1)
    config: dict[str, Any] = Field(default_factory=dict)
    source: Literal["scenario", "joystick", "evaluation"] = "scenario"

    @field_validator("provider_id")
    @classmethod
    def _provider(cls, value: str) -> str:
        if command_provider_definition(value) is None:
            raise ValueError(
                f"未知命令提供器 {value!r}（已登记 {list(command_provider_ids())}）"
            )
        return value

    @model_validator(mode="after")
    def _check(self) -> "CommandProviderRequest":
        definition = command_provider_definition(self.provider_id)
        if definition is None:  # pragma: no cover
            raise ValueError(f"未知命令提供器 {self.provider_id!r}")
        if definition.version != self.version:
            raise ValueError(
                f"命令提供器 {self.provider_id} 版本 {self.version} 与登记值"
                f" {definition.version} 不符"
            )
        ids = list(self.input_instance_ids)
        if len(ids) != len(set(ids)):
            raise ValueError(f"input_instance_ids 有重复：{ids}")
        declared = {field.name for field in definition.config}
        unknown = sorted(set(self.config) - declared)
        if unknown:
            raise ValueError(f"命令提供器 {self.provider_id} 含未声明参数 {unknown}")
        return self


class ScenarioEventRequest(BaseModel):
    """场景里**预排**的事件（epoch 由运行时决定，所以这里不带 ``expected_epoch``）。

    到运行时用 :meth:`to_scheduled_event` 变成权威形状 :class:`ScheduledEvent` ——
    事件只有一个形状，这里只是它的"场景侧投影"。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    type: Literal["velocity_command", "wrench", "sensor_fault", "policy_switch", "run_control"]
    at_tick: int = Field(ge=0)
    duration_ticks: int = Field(default=0, ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_id")
    @classmethod
    def _eid(cls, value: str) -> str:
        if not _SCENARIO_SAFE_ID_RE.match(value):
            raise ValueError(f"event_id={value!r} 不是安全标识")
        return value

    def to_scheduled_event(self, *, expected_epoch: int = 0) -> ScheduledEvent:
        """换成运行时权威事件（校验完全交给 :class:`ScheduledEvent`，不在此复制规则）。"""

        return ScheduledEvent(
            event_id=self.event_id,
            type=self.type,
            expected_epoch=expected_epoch,
            at_tick=self.at_tick,
            duration_ticks=self.duration_ticks,
            payload=dict(self.payload),
            source="scenario",
        )


class ScenarioAdvanced(BaseModel):
    """高级仿真入口（1.2）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    executor_id: Literal["native_mujoco"] = "native_mujoco"
    sensor_instances: list[SensorInstanceRequest] = Field(default_factory=list)
    command_provider: CommandProviderRequest | None = None
    events: list[ScenarioEventRequest] = Field(default_factory=list)
    recording: RecordingOptions | None = None
    #: 期望控制率（Hz）——只是**校验**：解析器用它核对"机器人包 contract 的分频是不是
    #: 场景作者以为的那个"。它**不产生**时间基（时间基的唯一来源是 ``contract.json``）。
    expect_control_hz: float | None = Field(default=None, gt=0.0, le=20_000.0)

    @model_validator(mode="after")
    def _check(self) -> "ScenarioAdvanced":
        ids = [item.instance_id for item in self.sensor_instances]
        if len(ids) != len(set(ids)):
            duplicates = sorted({item for item in ids if ids.count(item) > 1})
            raise ValueError(f"重复实例 instance_id={duplicates}（同类型可多实例，标识必须唯一）")
        event_ids = [item.event_id for item in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError(f"重复 event_id：{sorted(set(item for item in event_ids if event_ids.count(item) > 1))}")
        provider = self.command_provider
        if provider is not None:
            known = set(ids)
            missing = sorted(set(provider.input_instance_ids) - known)
            if missing:
                raise ValueError(
                    f"命令提供器输入实例 {missing} 未在 sensor_instances 里声明"
                    "（决策器不能引用不存在的传感器）"
                )
            by_id = {item.instance_id: item for item in self.sensor_instances}
            allowed = set(command_provider_definition(provider.provider_id).input_plugin_ids)
            for instance_id in provider.input_instance_ids:
                plugin_id = by_id[instance_id].plugin_id
                if plugin_id not in allowed:
                    raise ValueError(
                        f"命令提供器 {provider.provider_id} 不接受插件 {plugin_id} 的实例 "
                        f"{instance_id}（声明输入 {sorted(allowed)}）"
                    )
        return self


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
    # --- 1.2 高级仿真入口（v2 原生闭环：传感器实例 / 命令提供器 / 预排事件 / 记录选项）---
    advanced: ScenarioAdvanced | None = None

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        allowed = (
            "scenario-contract-1.0",
            "scenario-contract-1.1",
            SCENARIO_CONTRACT_VERSION_1_2,
        )
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

    @model_validator(mode="after")
    def validate_advanced_entry(self) -> "ScenarioContract":
        """1.2 入口的版本门与**防双真值**约束。

        1. 带 ``advanced`` 就必须显式写 ``scenario-contract-1.2``：旧场景文件不会因为
           代码升级而突然多出行为；
        2. 外部决策器（B 类）与 A 类分层互斥，且 ``command_source`` 不能同时说是策略给的；
        3. ``perception.depth_camera``（1.1 的深度请求）与 ``purpose=policy`` 的 depth
           实例（1.2）**不能同时存在** —— 两处都在描述"策略吃的那一路深度"，同时给出
           就是两份真值；纯显示用的深度实例可以共存。

        刻意**不做**的一件事：校验 ``events[].at_tick`` 是否超出 ``episode_length_s``。
        tick↔秒的换算需要物理率，而物理率只存在于机器人包的 ``contract.json``；
        在场景层做这个换算就会造出第二个频率真值。该检查归解析器
        （:mod:`backend.simulation_resolver`）。
        """
        advanced = self.advanced
        if advanced is None:
            return self
        if self.schema_version != SCENARIO_CONTRACT_VERSION_1_2:
            raise ValueError(
                f"advanced 入口需要 schema_version={SCENARIO_CONTRACT_VERSION_1_2!r}，"
                f"当前是 {self.schema_version!r}（旧场景请去掉 advanced 字段）"
            )
        provider = advanced.command_provider
        perception = self.perception
        if provider is not None:
            if perception is not None and perception.route == "obs":
                raise ValueError(
                    "perception.route=obs（A 类）与 command_provider 冲突：外部决策器只改指令，"
                    "而 A 类的感知在策略观测里 —— 请选一种分层"
                )
            if self.command_source == "policy":
                raise ValueError(
                    "带 command_provider 时 command_source 不能是 policy"
                    "（否则『最终指令是谁给的』有两份答案）"
                )
        policy_depth = [
            item
            for item in advanced.sensor_instances
            if item.plugin_id == "depth" and item.purpose == "policy"
        ]
        if policy_depth and perception is not None and perception.depth_camera is not None:
            raise ValueError(
                "perception.depth_camera（1.1 的深度请求）与 purpose=policy 的 depth 实例"
                f"（{[item.instance_id for item in policy_depth]}）同时存在：同一策略输入有两条"
                "来源声明。请用 advanced 实例表达（由解析器把参数绑到策略契约），"
                "或把实例 purpose 改为 display"
            )
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
