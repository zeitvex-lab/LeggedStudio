"""**任务插件**声明（v2 高级仿真的"任务即插件"层）。

## 它解决什么

高级仿真里"跑一个需要传感器的任务"此前是三件事各写一遍：**声明用哪些传感器**（场景
`perception`）、**从传感器生成哪些观测项**（recipe，S2① 已自动化）、**用哪些判据判成败**
（`criteria`/`assessment`）。结果是"深度跑酷"这类任务每换一个页面/会话就要人肉重配一遍，
**漏一项就静默降级**（页面照跑、策略吃不到深度——正是本仓最怕的那类假绿）。

任务插件把这三件事收成**一份声明**：`sensors`（要哪些插件、用它们的哪个输出）+
`perception`（场景里那几个开关）+ `checks`/`recorders`/`task_type`（判据与记录）。
`backend/task_plugins.instantiate()` 据此**自动把场景补齐**，并由
`perception_binding.generate_recipe_obs_items()` 生成 recipe 观测项（**委托，不另写一套**）。

## 真值来源（本模块**不抄**任何 id 或输出名）

* 传感器插件 id 与它们各自的输出名一律取自 :mod:`contracts.sensor_plugin_contract`
  （v2 高级仿真的单一真值）——写错的 id/输出在这里就 **fail-closed**，
  而不是等到仿真里"深度一直是零"才发现；
* 场景字段取自 :class:`contracts.scenario_contract.ScenarioContract` 的 `perception`。

## 诚实边界（与传感器插件契约同一条纪律）

`capability_level` 不许跳级：当前**所有**传感器插件都停在 `registered`（原生采集器未实现/
未探测）。所以任务插件的 `readiness` 里 **`ok` 只表示"声明可实例化"**，
`verified=False` 并附原因——**不许因为"插件里画了"就说这个任务能跑**。
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from contracts import sensor_plugin_contract as sensors

__all__ = [
    "TaskPerceptionPatch",
    "TaskPlugin",
    "TaskPluginError",
    "TaskSensorRequirement",
    "TASK_PLUGIN_SCHEMA",
    "validate_task_plugin_payload",
]

TASK_PLUGIN_SCHEMA = "task-plugin-1.0"

#: 场景契约里**已知会被消费**的判据/记录器取值（诚实标注用，**不是白名单**——
#: 场景契约本身不闭集，这里只用来回答"我声明的这几项今天到底有没有人执行"）。
CONSUMED_CHECKS = ("arrival", "route_completion")
CONSUMED_RECORDERS = ("trajectory", "metrics")

#: 与传感器插件契约同一套安全 id（拒路径分隔符 / 空串 / 大写空格）。
SAFE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class TaskPluginError(ValueError):
    """任务插件声明不合法（未知传感器 / 未知输出 / 缺证据）。**一律 fail-closed。**"""


def _check_safe_id(value: str, *, what: str) -> str:
    text = str(value or "")
    if not SAFE_ID_PATTERN.match(text):
        raise TaskPluginError(f"{what} {text!r} 不是合法 id（小写字母/数字/下划线/连字符，≤64 字符）")
    return text


class TaskSensorRequirement(BaseModel):
    """任务对**某个传感器插件**的依赖：要它的哪些输出（空 = 该插件的全部输出）。"""

    model_config = ConfigDict(extra="forbid")

    plugin_id: str
    outputs: list[str] = Field(default_factory=list)
    required: bool = True

    @field_validator("plugin_id")
    @classmethod
    def _safe(cls, value: str) -> str:
        return _check_safe_id(value, what="传感器的 plugin_id")

    @model_validator(mode="after")
    def _known_plugin_and_outputs(self) -> "TaskSensorRequirement":
        known = sensors.plugin_ids(instantiable_only=False)
        if self.plugin_id not in known:
            raise TaskPluginError(
                f"未知传感器插件 {self.plugin_id!r}（可用：{', '.join(known)}）——"
                f"id 抄错会让「声明了却拿不到数据」这类假绿溜过去"
            )
        definition = sensors.plugin_definition(self.plugin_id)
        declared = {str(getattr(out, "name", "")) for out in (getattr(definition, "outputs", None) or [])}
        for name in self.outputs:
            if declared and name not in declared:
                raise TaskPluginError(
                    f"传感器 {self.plugin_id!r} 没有输出 {name!r}（它有：{', '.join(sorted(declared))}）"
                )
        return self


class TaskPerceptionPatch(BaseModel):
    """任务要**自动填进场景**的 `perception` 字段（`None` = 不碰）。

    只保留 `PerceptionSpec` 里与"任务需要什么传感器"直接相关的四项；其余场景字段
    一律留给场景作者（任务插件不是场景的第二个真相）。
    """

    model_config = ConfigDict(extra="forbid")

    heightfield: bool | None = None
    depth_camera: dict[str, Any] | None = None
    foot_contact: bool | None = None
    route: Literal["obs", "external"] | None = None


class TaskPlugin(BaseModel):
    """一个任务插件（声明式；`registry/task_plugins/*.json` 逐条落盘）。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = TASK_PLUGIN_SCHEMA
    plugin_id: str
    label: str = Field(min_length=1)
    description: str = ""
    version: str = "1.0"
    #: 任务族名（与 `tools/sim2sim_headless.py::DEFAULT_CRITERIA` 的键同词表；缺省不挂判据）
    task_type: str | None = None
    #: **为什么这个任务需要这些传感器**——不许空口（"因为上游 XX 任务的 actor 吃 YY"）
    evidence: str = Field(min_length=1)
    sensors: list[TaskSensorRequirement] = Field(min_length=1)
    perception: TaskPerceptionPatch = Field(default_factory=TaskPerceptionPatch)
    #: 要自动填进场景 `command_source` 的取值（`None` = 不碰）。词表与场景契约同源。
    command_source: Literal["policy", "planner", "perception", "script", "teleop"] | None = None
    #: 场景判据名。**今天真的被消费的只有 `arrival` / `route_completion`**（场景契约默认值），
    #: 其余取值会写进场景但没人执行 —— 故这里与场景契约一样不做闭集校验，改由
    #: `backend/task_plugins.instantiate()` 在 readiness 里**如实标注"声明了但不被执行"**。
    checks: list[str] = Field(default_factory=list)
    recorders: list[str] = Field(default_factory=list)

    @field_validator("plugin_id")
    @classmethod
    def _safe(cls, value: str) -> str:
        return _check_safe_id(value, what="任务插件 id")

    @field_validator("schema_version")
    @classmethod
    def _schema(cls, value: str) -> str:
        if value != TASK_PLUGIN_SCHEMA:
            raise TaskPluginError(f"schema_version 必须是 {TASK_PLUGIN_SCHEMA!r}，得到 {value!r}")
        return value

    @model_validator(mode="after")
    def _obs_route_needs_a_feeding_sensor(self) -> "TaskPlugin":
        """`route="obs"`（A 类：策略吃感知）必须有**至少一个**传感器进观测。

        否则就是"宣称感知进观测、其实一根数据线都没接"——本仓最不接受的假绿。
        """
        if self.perception.route == "obs" and not any(req.required for req in self.sensors):
            raise TaskPluginError(
                f"{self.plugin_id}: perception.route='obs' 表示感知进策略观测，但没有任何必需传感器"
            )
        return self


def validate_task_plugin_payload(payload: Any) -> TaskPlugin:
    """从 dict 载入并校验（**唯一入口**：registry 加载与 API 入参都走它）。

    pydantic 的 `ValidationError` 在这里**归一成 `TaskPluginError`**：调用方（registry
    加载 / HTTP 入参 / CLI）只需要认一种异常，且消息里带着"可用 id 有哪些"这种可修信息。
    """

    from pydantic import ValidationError

    if isinstance(payload, TaskPlugin):
        return payload
    if not isinstance(payload, dict):
        raise TaskPluginError(f"任务插件声明必须是 JSON 对象，得到 {type(payload).__name__}")
    try:
        return TaskPlugin(**payload)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in err.get('loc') or [])}: {err.get('msg')}" for err in exc.errors()
        )
        raise TaskPluginError(f"任务插件声明不合法：{details}") from exc
