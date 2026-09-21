"""传感器**插件声明**与**命令提供器声明**（v2 高级仿真的单一真值）。

为什么这些声明住在 ``contracts/`` 而不是 ``backend/``
----------------------------------------------------
插件声明要同时被四方消费：控制面的 catalog（HTTP）、浏览器坞（面板与默认参数）、
原生 worker（要实现适配器的插件）、记录器（要知道该记哪些输出）。任何一方自己抄一份
默认值，就会出现"UI 上写着 240 线、worker 实际打 128 线"这类**只能在线上发现**的错误。
所以本模块是**唯一**一份声明，``backend/sensor_suite.py`` 只做导出适配（不抄数值）。

与 :mod:`backend.sensor_suite` 的分工（不是重复）
------------------------------------------------
``sensor_suite`` 携的是 **MATRiX v1.0.13 硬件套件预设**（外部出处的逐字复制，
"这台机器人出厂装了哪些器件"）；本模块携的是 **原生运行时可实例化的插件契约**
（"一个插件有哪些输出、能吃哪些参数、默认值凭什么、现在到底能不能跑"）。
两者的交汇点在 :func:`backend.sensor_suite.plugin_catalog_v2`，它委托到这里。

诚实边界（**最重要的一条**）
--------------------------
:data:`CAPABILITY_LEVELS` 是四级，**不许跳级宣称**：

``registered``
    声明存在（本模块里有定义），实现未知 —— **当前所有插件都停在这里**，
    因为原生 MuJoCo 采集器尚未实现/探测。
``implemented``
    代码里有适配器实现（可导入、可调用），但未在目标运行时验证。
``available``
    在**本次探测到的**运行时里能跑通（probe 支撑）。
``verified``
    有可核对的证据（回归基线 / 对拍记录），必须同时给 ``verified_evidence``。

因此 :class:`SensorPluginDefinition` 默认 ``capability_level="registered"``，
且校验器**禁止**在无证据时写 ``verified`` —— 把"文档里画了"说成"能跑"是本项目明确拒绝的口径。
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from contracts.simulation_protocol import DTYPE_ITEMSIZE

__all__ = [
    "CAPABILITY_LEVELS",
    "COMMAND_PROVIDERS",
    "CONFIG_KINDS",
    "CommandProviderDefinition",
    "ConfigFieldSpec",
    "LatencySpec",
    "NoiseSpec",
    "PATTERN_KINDS",
    "PAYLOAD_KINDS",
    "PLUGIN_CONTRACT_VERSION",
    "PLUGIN_DEFINITIONS",
    "PLUGIN_ENGINE_REQUIREMENTS",
    "PROVIDER_ENGINE_REQUIREMENTS",
    "ProviderDecision",
    "ProviderDecisionError",
    "SAFE_ID_PATTERN",
    "SOURCE_KINDS",
    "SensorOutputSpec",
    "SensorDeclarationError",
    "SensorPluginDefinition",
    "UI_PANELS",
    "capability_level_of",
    "command_provider_definition",
    "command_provider_ids",
    "plugin_catalog_payload",
    "plugin_definition",
    "plugin_ids",
    "protocol_dtype_ok",
    "provider_required_capabilities",
    "required_capabilities",
]

#: 本声明文档自身的版本（与线协议版本 :data:`contracts.simulation_protocol.PROTOCOL_VERSION` 无关）。
PLUGIN_CONTRACT_VERSION = "sim-sensor-plugin-1.0"

#: 安全的实例/插件标识：小写、可含 ``_ . -``，**禁止** ``/`` ``\`` ``..``（路径 ID 同源规则）。
SAFE_ID_PATTERN = r"^[a-z0-9][a-z0-9_.-]{0,63}$"
_SAFE_ID_RE = re.compile(SAFE_ID_PATTERN)

#: 样本来源语义（用户要求"来源 truth/measurement/estimate"必须显式）。
#: ``truth``  = 直接从 ``qpos/qvel`` 读，无噪声、无渲染；
#: ``measurement`` = 器件量测（可加噪声/延迟/丢点），策略实际吃到的就是这一路；
#: ``estimate``  = 外部估计管线输出（如里程计积分），自带漂移。
SOURCE_KINDS: tuple[str, ...] = ("truth", "measurement", "estimate")

#: 能力四级（**顺序即升级顺序**，不得跳级宣称）。
CAPABILITY_LEVELS: tuple[str, ...] = ("registered", "implemented", "available", "verified")

#: 配置参数允许的取值种类（浏览器据此渲染控件，worker 据此校验）。
CONFIG_KINDS: tuple[str, ...] = (
    "float",
    "int",
    "bool",
    "str",
    "choice",
    "float_list",
    "str_list",
)

#: 输出载荷种类。``tensor`` 走 ``application/octet-stream``；``image_png`` 走 ``image/png``；
#: ``cloud``/``graph`` 目前**没有实现**，声明出来只为避免"点云塞进 tensor 假装对齐"。
PAYLOAD_KINDS: tuple[str, ...] = ("tensor", "image_png", "cloud", "graph")

#: 面板归属（与 ``web/sim2sim/sensors/sensor_catalog.js`` 的 ``kind`` 同名同义）。
UI_PANELS: tuple[str, ...] = ("readout", "rays", "camera", "contact", "canvas")

#: 采样 pattern（与 ``PATTERN_KINDS`` 及 mjlab ``raycast_sensor`` 的 PatternCfg 对齐）。
PATTERN_KINDS: tuple[str, ...] = ("point", "grid", "ring", "pinhole", "fan")


class SensorDeclarationError(ValueError):
    """插件声明本身不合法（默认值越界、输出形状矛盾、无证据却宣称 verified 等）。"""


class ProviderDecisionError(ValueError):
    """命令提供器的决策记录不合法（缺输入引用、命令维度不符等）。"""


def _check_safe_id(value: str, *, what: str) -> str:
    if not _SAFE_ID_RE.match(value):
        raise SensorDeclarationError(
            f"{what}={value!r} 不符合安全标识规则 {SAFE_ID_PATTERN}（禁止路径分隔符与 '..'）"
        )
    return value


def protocol_dtype_ok(dtype: str) -> bool:
    """``dtype`` 是否是线协议认识的元素类型（委托 :mod:`contracts.simulation_protocol`）。"""

    return dtype in DTYPE_ITEMSIZE


# --------------------------------------------------------------------------------------
# 配置参数（默认值的**唯一**居所）
# --------------------------------------------------------------------------------------


class ConfigFieldSpec(BaseModel):
    """一个可配置参数：类型、单位、取值范围、**默认值及其出处**。

    ``default=None`` + ``required=True`` 表示"**这里故意不给默认值**" —— 该参数必须由
    更权威的来源提供（策略契约、机器人包、场景文件）。给它编一个默认值，就等于
    在契约里伪造一次标定。出处写在 ``provenance`` 里，供解析器原样转成参数来源记录。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    kind: Literal[
        "float", "int", "bool", "str", "choice", "float_list", "str_list"
    ]
    unit: str | None = None
    default: Any = None
    required: bool = False
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] | None = None
    provenance: str = ""
    description: str = ""

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]{0,31}$", value):
            raise SensorDeclarationError(f"参数名不合法：{value!r}")
        return value

    @field_validator("provenance", "description")
    @classmethod
    def _text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _consistency(self) -> "ConfigFieldSpec":
        if self.kind == "choice" and not self.choices:
            raise SensorDeclarationError(f"参数 {self.name}: kind=choice 必须给 choices")
        if self.kind != "choice" and self.choices:
            raise SensorDeclarationError(f"参数 {self.name}: 非 choice 不得带 choices")
        if self.required and self.default is not None:
            raise SensorDeclarationError(
                f"参数 {self.name}: required=True 意味着默认值必须由权威来源给出，此处必须为 None"
            )
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise SensorDeclarationError(f"参数 {self.name}: minimum 大于 maximum")
        if self.default is not None:
            self.accepts(self.default)
        return self

    def accepts(self, value: Any) -> None:
        """校验一个覆盖值是否属于本参数（违规抛 :class:`SensorDeclarationError`）。"""

        if value is None:
            if self.required:
                raise SensorDeclarationError(f"参数 {self.name} 必填（无默认值）")
            return
        if self.kind in ("float_list", "str_list"):
            if not isinstance(value, (list, tuple)) or not value:
                raise SensorDeclarationError(f"参数 {self.name} 必须是非空列表")
            item_kind = "float" if self.kind == "float_list" else "str"
            for item in value:
                self._accept_scalar(item, item_kind)
            return
        self._accept_scalar(value, self.kind)

    def _accept_scalar(self, value: Any, kind: str) -> None:
        if kind == "bool":
            if not isinstance(value, bool):
                raise SensorDeclarationError(f"参数 {self.name} 需要布尔值，实为 {value!r}")
            return
        if kind == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise SensorDeclarationError(f"参数 {self.name} 需要整数，实为 {value!r}")
            self._accept_range(float(value))
            return
        if kind == "float":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise SensorDeclarationError(f"参数 {self.name} 需要数值，实为 {value!r}")
            if value != value or value in (float("inf"), float("-inf")):
                raise SensorDeclarationError(f"参数 {self.name} 不接受非有限数值")
            self._accept_range(float(value))
            return
        if kind == "str":
            if not isinstance(value, str) or not value:
                raise SensorDeclarationError(f"参数 {self.name} 需要非空字符串，实为 {value!r}")
            return
        if kind == "choice":
            if value not in (self.choices or ()):
                raise SensorDeclarationError(
                    f"参数 {self.name}={value!r} 不在允许值 {list(self.choices or ())}"
                )

    def _accept_range(self, value: float) -> None:
        if self.minimum is not None and value < self.minimum:
            raise SensorDeclarationError(f"参数 {self.name}={value} 小于下限 {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            raise SensorDeclarationError(f"参数 {self.name}={value} 大于上限 {self.maximum}")


# --------------------------------------------------------------------------------------
# 退化模型（噪声 / 延迟）
# --------------------------------------------------------------------------------------


class NoiseSpec(BaseModel):
    """量测退化模型。**默认 ``kind="none"`` = 理想传感器**，必须显式开启才有噪声。

    ``rng_stream`` 决定随机流归属：``instance`` = 每个实例一条可复现流（多实例互不干扰），
    ``run`` = 全运行共享一条（复现更快，但实例之间会互相影响 —— 需要显式选择）。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["none", "gaussian", "uniform_bias", "dropout"] = "none"
    sigma: float = Field(default=0.0, ge=0.0)
    bias: float = Field(default=0.0, allow_inf_nan=False)
    dropout_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    rng_stream: Literal["instance", "run"] = "instance"

    @model_validator(mode="after")
    def _check(self) -> "NoiseSpec":
        if self.kind == "none" and (self.sigma or self.bias or self.dropout_rate):
            raise ValueError("kind=none 的噪声模型不得携带非零参数（要么关掉，要么换类型）")
        if self.kind == "gaussian" and self.sigma <= 0.0:
            raise ValueError("kind=gaussian 需要 sigma > 0")
        if self.kind == "uniform_bias" and self.bias == 0.0:
            raise ValueError("kind=uniform_bias 需要 bias != 0")
        if self.kind == "dropout" and self.dropout_rate <= 0.0:
            raise ValueError("kind=dropout 需要 dropout_rate > 0")
        return self


class LatencySpec(BaseModel):
    """延迟模型，单位一律是**物理 tick**（不是秒 —— 秒要由时间基换算，换算只在一处做）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["none", "fixed", "jitter"] = "none"
    ticks: int = Field(default=0, ge=0)
    jitter_ticks: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _check(self) -> "LatencySpec":
        if self.kind == "none" and (self.ticks or self.jitter_ticks):
            raise ValueError("kind=none 的延迟模型不得携带 tick")
        if self.kind == "fixed" and self.ticks <= 0:
            raise ValueError("kind=fixed 需要 ticks > 0")
        if self.kind == "jitter" and self.jitter_ticks <= 0:
            raise ValueError("kind=jitter 需要 jitter_ticks > 0")
        return self


# --------------------------------------------------------------------------------------
# 输出与插件定义
# --------------------------------------------------------------------------------------


class SensorOutputSpec(BaseModel):
    """插件的一个输出（**一个插件可以有多个输出**，各自单位/坐标系/来源不同）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    payload_kind: Literal["tensor", "image_png", "cloud", "graph"] = "tensor"
    dtype: str | None = None
    dims: tuple[int, ...] | None = None
    unit: str | None = None
    reference_frame: str = "sensor"
    source: Literal["truth", "measurement", "estimate"] = "measurement"
    description: str = ""

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]{0,31}$", value):
            raise SensorDeclarationError(f"输出名不合法：{value!r}")
        return value

    @model_validator(mode="after")
    def _check(self) -> "SensorOutputSpec":
        if self.payload_kind == "tensor":
            if self.dtype not in DTYPE_ITEMSIZE:
                raise SensorDeclarationError(
                    f"输出 {self.name}: dtype={self.dtype!r} 不在线协议表里 {sorted(DTYPE_ITEMSIZE)}"
                )
            if not self.dims or any(dim < 0 for dim in self.dims):
                raise SensorDeclarationError(
                    f"输出 {self.name}: tensor 需要非负整数 dims（0 = 动态维，由实例参数决定；"
                    "解析器必须把它绑成具体元素数，见 :meth:`SensorOutputSpec.is_dynamic`）"
                )
            if not self.unit:
                raise SensorDeclarationError(f"输出 {self.name}: tensor 必须声明单位")
        elif self.payload_kind == "image_png":
            if self.dtype is not None or self.dims is not None:
                raise SensorDeclarationError(
                    f"输出 {self.name}: image_png 的形状由图像自身决定，不得声明 dtype/dims"
                )
        elif self.payload_kind in ("cloud", "graph"):
            if self.unit:
                raise SensorDeclarationError(
                    f"输出 {self.name}: {self.payload_kind} 载荷暂无单位口径（未实现，不要假装有）"
                )
        return self

    def element_count(self) -> int | None:
        """张量元素数（``dims`` 含 0 维占位时返回 ``None`` = 形状由实例决定）。"""

        if self.dims is None:
            return None
        if 0 in self.dims:
            return None
        total = 1
        for dim in self.dims:
            total *= int(dim)
        return total

    def is_dynamic(self) -> bool:
        """``dims`` 里出现 0 维 = 形状取决于实例参数（如射线数、网格边长）。"""

        return bool(self.dims) and 0 in (self.dims or ())


class ConfiguredDeclaration(BaseModel):
    """带一组可配置参数的声明公共基类（插件与命令提供器共用同一套逻辑）。

    收口的理由是**默认值与出处只实现一次**：两处各写一份 ``resolve_config``，
    迟早会有一份忘了拒绝未知参数、或忘了查交叉约束（如 ``stop_m < resume_m``）。
    ``ordering`` 就是交叉约束的载体：``(较小者, 较大者)`` 必须在最终参数里严格递增。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    config: tuple[ConfigFieldSpec, ...] = ()
    ordering: tuple[tuple[str, str], ...] = ()

    @model_validator(mode="after")
    def _check_config(self) -> "ConfiguredDeclaration":
        names = [field.name for field in self.config]
        if len(names) != len(set(names)):
            raise SensorDeclarationError(f"{self.declaration_label} 参数名重复：{names}")
        for lesser, greater in self.ordering:
            if lesser not in names or greater not in names:
                raise SensorDeclarationError(
                    f"{self.declaration_label} 交叉约束引用了未声明参数：{lesser} < {greater}"
                )
        return self

    @property
    def declaration_label(self) -> str:
        identifier = getattr(self, "plugin_id", None) or getattr(self, "provider_id", "?")
        return f"{type(self).__name__}({identifier})"

    def config_field(self, name: str) -> ConfigFieldSpec | None:
        return next((field for field in self.config if field.name == name), None)

    def default_config(self) -> dict[str, Any]:
        """默认参数（必填项**不出现**在这里 —— 不编造值）。"""

        return {field.name: field.default for field in self.config if field.default is not None}

    def required_config(self) -> tuple[str, ...]:
        """必须由权威来源（策略契约 / 机器人包 / 实例显式参数）提供的参数名。"""

        return tuple(field.name for field in self.config if field.required)

    def resolve_config(
        self, overrides: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """把覆盖值套到默认值上，返回 ``(最终参数, 每个参数的出处)``。

        出处字符串让"这个 240 是插件默认还是场景覆盖"变成可核对的事实，而不是靠读代码顺序猜。
        未知参数名、越界值、违反交叉约束的取值一律拒绝（fail-closed）。
        """

        provided = dict(overrides or {})
        values: dict[str, Any] = {}
        provenance: dict[str, str] = {}
        for field in self.config:
            if field.name in provided:
                value = provided.pop(field.name)
                field.accepts(value)
                values[field.name] = value
                provenance[field.name] = f"override:{field.name}"
            elif field.default is not None:
                values[field.name] = field.default
                provenance[field.name] = (
                    field.provenance or f"default:{self.declaration_label}"
                )
            elif field.required:
                raise SensorDeclarationError(
                    f"{self.declaration_label} 参数 {field.name} 必填且无默认值"
                    f"（应由 {field.provenance or '权威来源'} 提供）"
                )
        if provided:
            raise SensorDeclarationError(
                f"{self.declaration_label} 未知参数：{sorted(provided)}"
                f"（已声明 {sorted(field.name for field in self.config)}）"
            )
        for lesser, greater in self.ordering:
            if float(values[lesser]) >= float(values[greater]):
                raise SensorDeclarationError(
                    f"{self.declaration_label} 要求 {lesser} < {greater}，"
                    f"实为 {values[lesser]} / {values[greater]}"
                )
        return values, provenance


class SensorPluginDefinition(ConfiguredDeclaration):
    """一个可实例化插件的完整声明。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plugin_id: str
    version: str
    display_name: str
    sensor_class: Literal["proprioceptive", "exteroceptive"]
    ui_panel: Literal["readout", "rays", "camera", "contact", "canvas"]
    pattern: Literal["point", "grid", "ring", "pinhole", "fan"] | None = None
    onboard: bool = False
    mountable: bool = True
    instantiable: bool = True
    derived_from: str | None = None
    outputs: tuple[SensorOutputSpec, ...]
    supports_noise: bool = True
    supports_latency: bool = True
    requires_target: bool = False
    #: 该插件里「给策略吃的那一路」输出名（None = 无策略输出口，或只用于显示/评测）。
    #: 为什么必须由**声明**给出：深度插件同时有 ``depth_raw`` / ``depth_optical_z`` /
    #: ``policy_tensor`` 三路张量，让解析器按形状或名字去「猜哪一路是策略输入」，
    #: 就是把绑定错误藏进默认行为（106 与 86 的历史事故）。声明处只在这里。
    policy_output: str | None = None
    capability_level: Literal["registered", "implemented", "available", "verified"] = "registered"
    verified_evidence: str | None = None
    upstream: str = ""
    notes: str = ""

    @field_validator("plugin_id")
    @classmethod
    def _pid(cls, value: str) -> str:
        return _check_safe_id(value, what="plugin_id")

    @field_validator("version")
    @classmethod
    def _version(cls, value: str) -> str:
        if not re.match(r"^[0-9]+\.[0-9]+\.[0-9]+$", value):
            raise SensorDeclarationError(f"插件 version 必须是 x.y.z，实为 {value!r}")
        return value

    @model_validator(mode="after")
    def _check(self) -> "SensorPluginDefinition":
        names = [output.name for output in self.outputs]
        if len(names) != len(set(names)):
            raise SensorDeclarationError(f"插件 {self.plugin_id} 输出名重复：{names}")
        if not self.outputs:
            raise SensorDeclarationError(f"插件 {self.plugin_id} 没有任何输出声明")
        if self.capability_level == "verified" and not self.verified_evidence:
            raise SensorDeclarationError(
                f"插件 {self.plugin_id} 宣称 verified 但没有 verified_evidence —— 拒绝"
            )
        if self.derived_from and self.instantiable:
            raise SensorDeclarationError(
                f"派生视图 {self.plugin_id}（derived_from={self.derived_from}）不得可实例化"
            )
        # ``derived_from`` 指向的插件是否存在，由注册表构建完成后的
        # :func:`_assert_derived_targets` 统一核对 —— 构造本条时目标可能还没进注册表，
        # 顺序依赖不该变成隐式规则。
        if self.pattern not in PATTERN_KINDS and self.pattern is not None:
            raise SensorDeclarationError(f"插件 {self.plugin_id} pattern 未知：{self.pattern!r}")
        if self.policy_output is not None:
            target = next(
                (output for output in self.outputs if output.name == self.policy_output), None
            )
            if target is None:
                raise SensorDeclarationError(
                    f"插件 {self.plugin_id} 的 policy_output={self.policy_output!r} 不在已声明"
                    f"输出 {names} 里（引用不存在的输出比不声明更危险）"
                )
            if target.payload_kind != "tensor":
                raise SensorDeclarationError(
                    f"policy_output 必须是张量输出，{self.policy_output} 是"
                    f" {target.payload_kind}"
                )
        return self

    # 默认值与解析（``default_config`` / ``required_config`` / ``resolve_config``）
    # 继承自 :class:`ConfiguredDeclaration` —— **只有一份实现**。

    def as_catalog_entry(self) -> dict[str, Any]:
        """HTTP catalog 的一条（浏览器直接消费，不再自己抄默认值）。"""

        return {
            "plugin_id": self.plugin_id,
            "version": self.version,
            "display_name": self.display_name,
            "class": self.sensor_class,
            "ui_panel": self.ui_panel,
            "pattern": self.pattern,
            "onboard": self.onboard,
            "mountable": self.mountable,
            "instantiable": self.instantiable,
            "derived_from": self.derived_from,
            "capability_level": self.capability_level,
            "verified_evidence": self.verified_evidence,
            "supports_noise": self.supports_noise,
            "supports_latency": self.supports_latency,
            "requires_target": self.requires_target,
            "policy_output": self.policy_output,
            "upstream": self.upstream,
            "notes": self.notes,
            "defaults": self.default_config(),
            "required": list(self.required_config()),
            "config": [field.model_dump(mode="json") for field in self.config],
            "outputs": [output.model_dump(mode="json") for output in self.outputs],
        }


# --------------------------------------------------------------------------------------
# 命令提供器（B 类：感知在策略外，只修改指令）
# --------------------------------------------------------------------------------------


class CommandProviderDefinition(ConfiguredDeclaration):
    """一个外部决策器的声明（输入来自哪些插件、输出什么指令、参数默认值与出处）。

    **B 类的边界**：命令提供器只修改指令，不进观测、不改策略权重 —— 这是"外置 LiDAR 决策
    只改速度指令"这条约束在契约里的落点。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str
    version: str
    display_name: str
    command_dims: int = Field(default=3, ge=1, le=3)
    input_plugin_ids: tuple[str, ...] = ()
    capability_level: Literal["registered", "implemented", "available", "verified"] = "registered"
    verified_evidence: str | None = None
    notes: str = ""

    @field_validator("provider_id")
    @classmethod
    def _pid(cls, value: str) -> str:
        return _check_safe_id(value, what="provider_id")

    @field_validator("version")
    @classmethod
    def _version(cls, value: str) -> str:
        if not re.match(r"^[0-9]+\.[0-9]+\.[0-9]+$", value):
            raise SensorDeclarationError(f"命令提供器 version 必须是 x.y.z，实为 {value!r}")
        return value

    @model_validator(mode="after")
    def _check(self) -> "CommandProviderDefinition":
        if self.capability_level == "verified" and not self.verified_evidence:
            raise SensorDeclarationError(
                f"命令提供器 {self.provider_id} 宣称 verified 但没有证据 —— 拒绝"
            )
        for plugin_id in self.input_plugin_ids:
            if plugin_id not in PLUGIN_DEFINITIONS:
                raise SensorDeclarationError(
                    f"命令提供器 {self.provider_id} 引用未知插件 {plugin_id!r}"
                )
        return self

    # ``resolve_config`` / ``default_config`` / ``required_config`` 继承基类（只有一份实现）。

    def as_catalog_entry(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "version": self.version,
            "display_name": self.display_name,
            "command_dims": self.command_dims,
            "input_plugin_ids": list(self.input_plugin_ids),
            "capability_level": self.capability_level,
            "verified_evidence": self.verified_evidence,
            "notes": self.notes,
            "defaults": self.default_config(),
            "required": list(self.required_config()),
            "ordering": [list(pair) for pair in self.ordering],
            "config": [field.model_dump(mode="json") for field in self.config],
        }


class ProviderDecision(BaseModel):
    """命令提供器一次决策的**唯一**记录形状（进事件流与记录，供事后复盘"为什么停下"）。

    ``source_command`` 是上游（teleop/script/planner）给的原始指令，``final_command`` 是
    本提供器裁决后真正下发给策略/控制的指令 —— 两者都记，否则"为什么明明给了 0.6 只走 0.2"
    在事后无法回答。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = PLUGIN_CONTRACT_VERSION
    run_id: str
    epoch: int = Field(ge=0)
    tick: int = Field(ge=0)
    provider_id: str
    provider_version: str
    request_seq: int = Field(ge=0)
    source_command: tuple[float, ...]
    final_command: tuple[float, ...]
    reason: Literal[
        "ok",
        "decelerating",
        "stop_obstacle",
        "stale_sample",
        "no_sample",
        "sensor_fault",
        "unsupported_lateral_command",
    ]
    input_instance_id: str | None = None
    input_sample_seq: int | None = Field(default=None, ge=0)
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("run_id", "provider_id", "input_instance_id")
    @classmethod
    def _ids(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _check_safe_id(value, what="ProviderDecision id")

    def __init__(self, **data: Any) -> None:
        # 领域规则在 **pydantic 之外**跑：`model_validator` 里抛出的 ValueError 子类会被
        # pydantic v2 包成 ValidationError——调用方 `except ProviderDecisionError` 于是
        # 永远接不住，域错误类型就成了装饰。字段类型/范围仍交给 pydantic，两条判据
        # 各管一段（类型 vs 语义）。
        super().__init__(**data)
        self._check_domain_rules()

    def _check_domain_rules(self) -> None:
        for name in ("source_command", "final_command"):
            values = getattr(self, name)
            if len(values) != self.command_dims_ok():
                raise ProviderDecisionError(
                    f"{name} 长度 {len(values)} 与 command_dims 不一致"
                )
            if any(item != item or item in (float("inf"), float("-inf")) for item in values):
                raise ProviderDecisionError(f"{name} 含非有限数值")
        if self.reason in ("stale_sample", "no_sample", "sensor_fault"):
            # 这三条都是"传感器那一路出了问题"，必须能指回是哪个实例、哪一次采样，
            # 否则故障无法归因（"雷达好像不准"不是可核对的证据）。
            if self.input_instance_id is None:
                raise ProviderDecisionError(
                    f"reason={self.reason} 必须带 input_instance_id（故障要能指回实例）"
                )
            if self.input_sample_seq is None:
                raise ProviderDecisionError(
                    f"reason={self.reason} 必须带 input_sample_seq（样本引用不能缺）"
                )

    def command_dims_ok(self) -> int:
        definition = COMMAND_PROVIDERS.get(self.provider_id)
        return definition.command_dims if definition else len(self.source_command)


# --------------------------------------------------------------------------------------
# 注册表（构造顺序无关的存在性核对在构建完成后统一做）
# --------------------------------------------------------------------------------------


def _sample_period_field(
    *,
    default: int | None,
    required: bool = False,
    provenance: str = "",
    maximum: float = 100_000.0,
) -> ConfigFieldSpec:
    return ConfigFieldSpec(
        name="sample_period_ticks",
        kind="int",
        unit="physics_tick",
        default=default,
        required=required,
        minimum=1.0,
        maximum=maximum,
        provenance=provenance,
        description="每 N 个物理 tick 采一次；1 = 物理率。tick 是整数，秒由时间基换算。",
    )


def _build_plugins() -> dict[str, SensorPluginDefinition]:
    catalog: dict[str, SensorPluginDefinition] = {}

    def add(definition: SensorPluginDefinition) -> None:
        catalog[definition.plugin_id] = definition

    add(
        SensorPluginDefinition(
            plugin_id="imu",
            version="1.0.0",
            display_name="IMU",
            sensor_class="proprioceptive",
            ui_panel="readout",
            onboard=True,
            upstream="mjlab/sensor/builtin_sensor.py（本体状态直读）；噪声结构参考 newton/_src/sensors/sensor_imu.py",
            notes="姿态/速度是 truth，角速度与比力是 measurement（器件路）。策略吃的是后者。",
            outputs=(
                SensorOutputSpec(
                    name="orientation_quat_wxyz",
                    dtype="f4",
                    dims=(4,),
                    unit="quat_wxyz",
                    reference_frame="world",
                    source="truth",
                    description="挂载 site 相对世界的姿态，四元数顺序 **wxyz**（MuJoCo/mjlab 口径）",
                ),
                SensorOutputSpec(
                    name="angular_velocity",
                    dtype="f4",
                    dims=(3,),
                    unit="rad/s",
                    reference_frame="sensor",
                    source="measurement",
                ),
                SensorOutputSpec(
                    name="specific_force",
                    dtype="f4",
                    dims=(3,),
                    unit="m/s^2",
                    reference_frame="sensor",
                    source="measurement",
                    description="加速度计读到的比力（含重力投影），不是世界系线加速度",
                ),
            ),
            config=(
                _sample_period_field(
                    default=1,
                    provenance="physics_rate：IMU 与物理率同步（500 Hz 包即 500 Hz）",
                ),
                ConfigFieldSpec(
                    name="gyro_noise_sigma",
                    kind="float",
                    unit="rad/s",
                    default=0.0,
                    minimum=0.0,
                    provenance="默认理想器件；噪声必须显式开启",
                ),
                ConfigFieldSpec(
                    name="accel_noise_sigma",
                    kind="float",
                    unit="m/s^2",
                    default=0.0,
                    minimum=0.0,
                    provenance="默认理想器件；噪声必须显式开启",
                ),
            ),
        )
    )

    add(
        SensorPluginDefinition(
            plugin_id="odom",
            version="1.0.0",
            display_name="全局里程计 odom",
            sensor_class="proprioceptive",
            ui_panel="readout",
            onboard=False,
            mountable=False,
            requires_target=False,
            upstream="newton/_src/sensors/sensor_frame_transform.py；外部定位实见 00_resources/g1-mujoco-ros2-nav-sim",
            notes="世界系位姿属**外部估计管线输出**，本体并不知道 ⇒ 全局定位是开放问题，默认关。",
            outputs=(
                SensorOutputSpec(
                    name="pose_position",
                    dtype="f4",
                    dims=(3,),
                    unit="m",
                    reference_frame="world",
                    source="estimate",
                ),
                SensorOutputSpec(
                    name="pose_quat_wxyz",
                    dtype="f4",
                    dims=(4,),
                    unit="quat_wxyz",
                    reference_frame="world",
                    source="estimate",
                ),
            ),
            config=(
                _sample_period_field(
                    default=5,
                    provenance="MATRiX v1.0.13 UeSim/.../config.json 的 Odom 100 Hz（500 Hz 物理率下 = 5 tick）",
                ),
            ),
        )
    )

    add(
        SensorPluginDefinition(
            plugin_id="foot_contact",
            version="1.0.0",
            display_name="足底接触",
            sensor_class="proprioceptive",
            ui_panel="contact",
            onboard=False,
            mountable=False,
            supports_latency=False,
            requires_target=True,
            upstream="mjlab/sensor/contact_sensor.py；genesis-world sensors/contact_force",
            notes="需要 MuJoCo 碰撞检测与力传感器；接触开关是 truth，力是 measurement。",
            outputs=(
                SensorOutputSpec(
                    name="found",
                    dtype="b1",
                    dims=(0,),
                    unit="1",
                    reference_frame="target",
                    source="truth",
                    description="每个目标 site 是否接触（dims 含 0 = 元素数由实例的 targets 决定）",
                ),
                SensorOutputSpec(
                    name="force",
                    dtype="f4",
                    dims=(0, 3),
                    unit="N",
                    reference_frame="world",
                    source="measurement",
                ),
            ),
            config=(
                _sample_period_field(default=1, provenance="physics_rate：接触每个物理子步都可能变化"),
                ConfigFieldSpec(
                    name="force_threshold",
                    kind="float",
                    unit="N",
                    default=1.0,
                    minimum=0.0,
                    provenance="browser:sensor_catalog.js 与训练栈 contact_sensor 阈值同量级",
                    description="超过该力算 found=True",
                ),
            ),
        )
    )

    add(
        SensorPluginDefinition(
            plugin_id="rangefinder",
            version="1.0.0",
            display_name="单点测距",
            sensor_class="exteroceptive",
            ui_panel="rays",
            pattern="point",
            requires_target=True,
            upstream="mjlab raycast_sensor 的 point 用法；量测退化参考 robosuite demo_sensor_corruption",
            outputs=(
                SensorOutputSpec(
                    name="range",
                    dtype="f4",
                    dims=(1,),
                    unit="m",
                    reference_frame="sensor",
                    source="measurement",
                    description="无命中时输出 max_range 且 validity=no_hit（不输出 0，0 会被当成贴脸障碍）",
                ),
            ),
            config=(
                _sample_period_field(default=None, required=True, provenance="实例显式参数（无权威默认值可抄）"),
                ConfigFieldSpec(
                    name="max_range",
                    kind="float",
                    unit="m",
                    default=12.0,
                    minimum=0.05,
                    maximum=1000.0,
                    provenance="browser:sensor_catalog.js 的 lidar maxDist=12（同类射线器件共用）",
                ),
            ),
        )
    )

    add(
        SensorPluginDefinition(
            plugin_id="height",
            version="1.0.0",
            display_name="高度扫描（雷达）",
            sensor_class="exteroceptive",
            ui_panel="rays",
            pattern="grid",
            requires_target=True,
            upstream="mjlab GridPatternCfg + backend/height_scan.py 的 187 网格契约",
            notes="网格契约（17×11、x0=-0.8、y0=-0.5、x 主序）来自 backend/height_scan.py，本处不重抄数值。",
            outputs=(
                SensorOutputSpec(
                    name="heights",
                    dtype="f4",
                    dims=(187,),
                    unit="m",
                    reference_frame="body",
                    source="measurement",
                    description="base_z - terrain_z，x 主序 index = i_x*11 + i_y；无命中单元填 max_range",
                ),
            ),
            config=(
                _sample_period_field(default=None, required=True, provenance="实例显式参数（A 类策略须由观测声明决定）"),
                ConfigFieldSpec(
                    name="max_range",
                    kind="float",
                    unit="m",
                    default=10.0,
                    minimum=0.05,
                    maximum=1000.0,
                    provenance="browser:sensor_catalog.js 的 grid 默认射程口径",
                ),
            ),
        )
    )

    add(
        SensorPluginDefinition(
            plugin_id="lidar",
            version="1.0.0",
            display_name="LiDAR（水平扇扫）",
            sensor_class="exteroceptive",
            ui_panel="rays",
            pattern="fan",
            requires_target=True,
            upstream="mjlab RingPatternCfg 的单环展开；MJCF 挂法参考 mujoco_3d_lidar 插件",
            notes="点云载荷（cloud）**未实现**：只有 ranges 这一路张量可用。",
            outputs=(
                SensorOutputSpec(
                    name="ranges",
                    dtype="f4",
                    dims=(0,),
                    unit="m",
                    reference_frame="sensor",
                    source="measurement",
                    description="元素数 = count（实例参数）；无命中填 max_range",
                ),
                SensorOutputSpec(
                    name="points",
                    payload_kind="cloud",
                    reference_frame="world",
                    source="measurement",
                    description="世界系点云 —— 声明存在但**无实现**（capability_level=registered），不要用",
                ),
            ),
            config=(
                _sample_period_field(default=None, required=True, provenance="实例显式参数（B 类外挂决策器决定其速率）"),
                ConfigFieldSpec(
                    name="count",
                    kind="int",
                    unit="ray",
                    default=240,
                    minimum=1.0,
                    maximum=4096.0,
                    provenance="browser:sensor_catalog.js patternParams.count",
                ),
                ConfigFieldSpec(
                    name="max_range",
                    kind="float",
                    unit="m",
                    default=12.0,
                    minimum=0.05,
                    maximum=1000.0,
                    provenance="browser:sensor_catalog.js patternParams.maxDist",
                ),
                ConfigFieldSpec(
                    name="fov_deg",
                    kind="float",
                    unit="deg",
                    default=360.0,
                    minimum=1.0,
                    maximum=360.0,
                    provenance="browser:sensor_catalog.js 的 fan 全环（360°）默认",
                ),
            ),
        )
    )

    add(
        SensorPluginDefinition(
            plugin_id="lidar_height_scan",
            version="1.0.0",
            display_name="雷达高度扫描（LiDAR 派生）",
            sensor_class="exteroceptive",
            ui_panel="rays",
            pattern="grid",
            onboard=False,
            mountable=False,
            instantiable=False,
            derived_from="lidar",
            upstream="backend/height_scan.py::point_cloud_to_heights（min_z_per_cell）",
            notes="**派生视图，不占开关**：随 lidar 一起出现，独立开关会让人误以为是另一个器件。",
            outputs=(
                SensorOutputSpec(
                    name="heights",
                    dtype="f4",
                    dims=(187,),
                    unit="m",
                    reference_frame="body",
                    source="estimate",
                    description="base_z - min_z（每格聚合），空单元**留空**而不是编一个高度",
                ),
            ),
        )
    )

    add(
        SensorPluginDefinition(
            plugin_id="depth",
            version="1.0.0",
            display_name="深度相机",
            sensor_class="exteroceptive",
            ui_panel="camera",
            pattern="pinhole",
            requires_target=True,
            policy_output="policy_tensor",
            upstream="mjlab/sensor/raycast_sensor.py::PinholeCameraPatternCfg + camera_sensor；后处理对齐 parkour_mjlab mdp/observations.py::camera_depth",
            notes=(
                "A 类（go2-pie-parkour）的唯一感知入口。**标定四项（min/max/crop/history/update_steps）"
                "故意不给默认值**：它们属于策略契约（机器人包 contract.depth_camera），"
                "在契约里编一份就等于允许两处不同真值。浏览器预览的 106×60/fovy66 是**显示口径**，"
                "策略实际吃的是裁剪后 60×86 与 fovy 56.485 —— 差异常由此产生，故参数来源必须显式。"
            ),
            outputs=(
                SensorOutputSpec(
                    name="depth_raw",
                    dtype="f4",
                    dims=(0, 0),
                    unit="m",
                    reference_frame="sensor",
                    source="measurement",
                    description="沿射线几何的最近命中距离；无命中 = max_range（dims=(0,0) 表示由实例参数决定）",
                ),
                SensorOutputSpec(
                    name="depth_optical_z",
                    dtype="f4",
                    dims=(0, 0),
                    unit="m",
                    reference_frame="optical",
                    source="measurement",
                    description="光机系 z 分量（针孔投影后的平面深度）",
                ),
                SensorOutputSpec(
                    name="policy_tensor",
                    dtype="f4",
                    dims=(0, 0, 0),
                    unit="normalized",
                    reference_frame="optical",
                    source="measurement",
                    description="裁剪+归一化+历史堆叠后、策略实际吃的张量；形状与标定由解析器按策略契约绑定",
                ),
                SensorOutputSpec(
                    name="image",
                    payload_kind="image_png",
                    reference_frame="sensor",
                    source="measurement",
                    description="可视化深度帧（无损 PNG；记录里禁止有损压缩）",
                ),
            ),
            config=(
                _sample_period_field(
                    default=None,
                    required=True,
                    provenance="policy_contract:depth_camera.update_steps（单位=控制步，需乘 decimation）",
                ),
                ConfigFieldSpec(
                    name="width",
                    kind="int",
                    unit="px",
                    default=106,
                    minimum=1.0,
                    maximum=4096.0,
                    provenance="browser:sensor_catalog.js patternParams.width（原始宽度）",
                    description="原始成像宽度；策略张量用 crop 后的宽度",
                ),
                ConfigFieldSpec(
                    name="height",
                    kind="int",
                    unit="px",
                    default=60,
                    minimum=1.0,
                    maximum=4096.0,
                    provenance="browser:sensor_catalog.js patternParams.height",
                ),
                ConfigFieldSpec(
                    name="fovy_deg",
                    kind="float",
                    unit="deg",
                    default=66.0,
                    minimum=1.0,
                    maximum=179.0,
                    provenance="browser:sensor_catalog.js patternParams.fovy（**显示口径**；策略绑定实例必须覆盖为契约值 56.485）",
                ),
                ConfigFieldSpec(
                    name="min_range",
                    kind="float",
                    unit="m",
                    required=True,
                    minimum=0.0,
                    maximum=100.0,
                    provenance="policy_contract:depth_camera.min_m",
                    description="近端裁剪。无默认值：标定缺失必须阻断，不能编一个数继续跑",
                ),
                ConfigFieldSpec(
                    name="max_range",
                    kind="float",
                    unit="m",
                    required=True,
                    minimum=0.05,
                    maximum=1000.0,
                    provenance="policy_contract:depth_camera.max_m（cutoff_distance）",
                ),
                ConfigFieldSpec(
                    name="crop_width",
                    kind="int",
                    unit="px",
                    required=True,
                    minimum=0.0,
                    maximum=4096.0,
                    provenance="policy_contract:depth_camera.crop",
                    description="左右各裁掉的像素数（106 → 86 就是这么来的）",
                ),
                ConfigFieldSpec(
                    name="history_frames",
                    kind="int",
                    unit="frame",
                    required=True,
                    minimum=1.0,
                    maximum=64.0,
                    provenance="policy_contract:depth_camera.history",
                ),
                ConfigFieldSpec(
                    name="normalize",
                    kind="choice",
                    choices=("none", "min_max"),
                    default="min_max",
                    provenance="policy_contract:depth_camera 归一化（(d-min)/(max-min) 并截断）",
                ),
            ),
        )
    )

    add(
        SensorPluginDefinition(
            plugin_id="rgb",
            version="1.0.0",
            display_name="RGB 相机",
            sensor_class="exteroceptive",
            ui_panel="camera",
            pattern="pinhole",
            supports_noise=False,
            requires_target=True,
            upstream="mjlab camera_sensor（MuJoCo 离屏渲染）；浏览器预览是 three.js，**与训练栈不同源**",
            notes="原生离屏渲染是否可用取决于 probe（offscreen_render 特征）；未探测不放行。",
            outputs=(
                SensorOutputSpec(
                    name="image",
                    payload_kind="image_png",
                    reference_frame="sensor",
                    source="measurement",
                    description="无损 PNG 帧（记录必须无损，与深度同一条纪律）",
                ),
            ),
            config=(
                _sample_period_field(default=None, required=True, provenance="实例显式参数"),
                ConfigFieldSpec(
                    name="width",
                    kind="int",
                    unit="px",
                    default=160,
                    minimum=1.0,
                    maximum=8192.0,
                    provenance="browser:sensor_catalog.js patternParams.width（预览口径）",
                ),
                ConfigFieldSpec(
                    name="height",
                    kind="int",
                    unit="px",
                    default=120,
                    minimum=1.0,
                    maximum=8192.0,
                    provenance="browser:sensor_catalog.js patternParams.height（预览口径）",
                ),
            ),
        )
    )

    return catalog


PLUGIN_DEFINITIONS: dict[str, SensorPluginDefinition] = _build_plugins()


def _assert_derived_targets(
    catalog: dict[str, SensorPluginDefinition],
) -> None:
    """派生视图指向的插件必须真的存在（构建完成后核对，与构造顺序无关）。"""

    for plugin_id, definition in catalog.items():
        target = definition.derived_from
        if target is None:
            continue
        if target == plugin_id:
            raise SensorDeclarationError(f"插件 {plugin_id} 不能派生自自身")
        if target not in catalog:
            raise SensorDeclarationError(
                f"派生视图 {plugin_id} 指向未知插件 {target!r}（已知 {sorted(catalog)}）"
            )
        if not catalog[target].instantiable:
            raise SensorDeclarationError(
                f"派生视图 {plugin_id} 不能派生自另一个派生视图 {target!r}"
            )


_assert_derived_targets(PLUGIN_DEFINITIONS)


def _build_providers() -> dict[str, CommandProviderDefinition]:
    gate = CommandProviderDefinition(
        provider_id="lidar_velocity_gate",
        version="1.0.0",
        display_name="LiDAR 速度门（B 类外挂决策）",
        command_dims=3,
        input_plugin_ids=("lidar",),
        capability_level="registered",
        # 滞回三段的顺序是**语义要求**（stop < resume < decelerate），不是调参偏好；
        # 写成交叉约束后，任何一侧覆盖参数把它破坏掉都会在 resolve_config 里被拒。
        ordering=(("stop_m", "resume_m"), ("resume_m", "decelerate_m")),
        notes=(
            "B 类（go2-lainlab-trot）用外置 LiDAR **只修改指令**，不进观测、不重训策略。"
            "横向指令当前不裁决（扇区外的障碍只减速/停车），故 reason 有 unsupported_lateral_command。"
        ),
        config=(
            ConfigFieldSpec(
                name="sector_half_angle_deg",
                kind="float",
                unit="deg",
                default=20.0,
                minimum=0.0,
                maximum=180.0,
                provenance="本声明（前进方向扇区）；实例可覆盖",
            ),
            ConfigFieldSpec(
                name="decelerate_m",
                kind="float",
                unit="m",
                default=1.5,
                minimum=0.05,
                maximum=1000.0,
                provenance="本声明：进入该距离开始线性减速",
            ),
            ConfigFieldSpec(
                name="stop_m",
                kind="float",
                unit="m",
                default=0.8,
                minimum=0.0,
                maximum=1000.0,
                provenance="本声明：进入该距离指令清零",
            ),
            ConfigFieldSpec(
                name="resume_m",
                kind="float",
                unit="m",
                default=1.0,
                minimum=0.0,
                maximum=1000.0,
                provenance="本声明：滞回恢复距离（必须 > stop_m，见下方校验）",
            ),
            ConfigFieldSpec(
                name="max_sample_age_s",
                kind="float",
                unit="s",
                default=0.2,
                minimum=0.0,
                maximum=10.0,
                provenance="本声明：样本过期阈值，过期即 stale_sample（不允许用旧点云继续放行）",
            ),
        ),
    )
    return {gate.provider_id: gate}


COMMAND_PROVIDERS: dict[str, CommandProviderDefinition] = _build_providers()


# --------------------------------------------------------------------------------------
# 查询入口
# --------------------------------------------------------------------------------------


def plugin_ids(*, instantiable_only: bool = True) -> tuple[str, ...]:
    """已声明插件 id（默认只列可实例化的，派生视图另算）。"""

    return tuple(
        sorted(
            plugin_id
            for plugin_id, definition in PLUGIN_DEFINITIONS.items()
            if not (instantiable_only and not definition.instantiable)
        )
    )


def plugin_definition(plugin_id: str) -> SensorPluginDefinition | None:
    return PLUGIN_DEFINITIONS.get(plugin_id)


def capability_level_of(plugin_id: str) -> str | None:
    """``None`` = 未知插件（调用方必须阻断，不能当成 ``registered`` 继续）。"""

    definition = PLUGIN_DEFINITIONS.get(plugin_id)
    return definition.capability_level if definition else None


def command_provider_ids() -> tuple[str, ...]:
    return tuple(sorted(COMMAND_PROVIDERS))


def command_provider_definition(provider_id: str) -> CommandProviderDefinition | None:
    return COMMAND_PROVIDERS.get(provider_id)


# --------------------------------------------------------------------------------------
# 引擎能力要求（声明级）
# --------------------------------------------------------------------------------------


#: 每个插件**原理上**需要引擎提供的原生能力。特征名与探测词表一致（
#: :data:`contracts.simulation_run_contract.PROBE_FEATURES`，由消费方核对拼写，
#: 因为本模块不能反向导入运行契约）。
#:
#: 这不是第二套"能力等级"：等级回答"做到哪一步了"，这里回答"要跑起来得有什么"。
#: 适配器实现后 :func:`contracts.runtime_interfaces.SensorAdapterProtocol.prepare`
#: 返回同一份要求，运行管理器把两者对齐 —— 声明有、探测没有 = 阻断；探测有、声明没提 = 忽略。
PLUGIN_ENGINE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "imu": ("model_compile", "physics_substep", "imu_bias"),
    "odom": ("model_compile", "physics_substep"),
    "foot_contact": ("model_compile", "physics_substep", "contact_force"),
    "rangefinder": ("model_compile", "raycast"),
    "height": ("model_compile", "raycast", "height_field_collision"),
    "lidar": ("model_compile", "raycast", "mesh_collision"),
    "lidar_height_scan": ("model_compile", "raycast", "mesh_collision"),
    "depth": ("model_compile", "raycast", "depth_raycast", "height_field_collision"),
    "rgb": ("model_compile", "offscreen_render"),
}

#: 命令提供器的引擎要求（它不碰物理，只需要事件注入路径把改后的指令送进去）。
PROVIDER_ENGINE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "lidar_velocity_gate": ("model_compile", "physics_substep", "event_injection"),
}


def required_capabilities(plugin_id: str) -> tuple[str, ...]:
    """插件所需引擎能力。未知插件抛错（fail-closed：拼错 id 不能变成"什么都不需要"）。"""

    try:
        return PLUGIN_ENGINE_REQUIREMENTS[plugin_id]
    except KeyError as error:
        raise SensorDeclarationError(f"未知传感器插件 {plugin_id!r}，无从判断能力要求") from error


def provider_required_capabilities(provider_id: str) -> tuple[str, ...]:
    try:
        return PROVIDER_ENGINE_REQUIREMENTS[provider_id]
    except KeyError as error:
        raise SensorDeclarationError(f"未知命令提供器 {provider_id!r}") from error


def plugin_catalog_payload() -> dict[str, Any]:
    """完整插件 catalog（HTTP ``/api/simulation/v2/catalog`` 的 ``sensor_plugins`` 字段）。"""

    return {
        "schema_version": PLUGIN_CONTRACT_VERSION,
        "capability_levels": list(CAPABILITY_LEVELS),
        "source_kinds": list(SOURCE_KINDS),
        "ui_panels": list(UI_PANELS),
        "pattern_kinds": list(PATTERN_KINDS),
        "payload_kinds": list(PAYLOAD_KINDS),
        "config_kinds": list(CONFIG_KINDS),
        "dtype_itemsize": dict(DTYPE_ITEMSIZE),
        "engine_requirements": {
            plugin_id: list(features) for plugin_id, features in sorted(PLUGIN_ENGINE_REQUIREMENTS.items())
        },
        "sensors": [
            PLUGIN_DEFINITIONS[plugin_id].as_catalog_entry() for plugin_id in plugin_ids(instantiable_only=False)
        ],
        "command_providers": [
            COMMAND_PROVIDERS[provider_id].as_catalog_entry() for provider_id in command_provider_ids()
        ],
    }


# 声明级自检已在模型校验器与 :func:`_assert_derived_targets` 里完成：模块能导入成功
# 就说明"没有证据却升级能力等级""派生指向未知插件"这类矛盾不存在（比等到首个请求
# 才 500 更早暴露）。
