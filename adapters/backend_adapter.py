"""BackendAdapter Protocol：训练后端插件化的正式接口契约（对应优化清单 #3）。

背景：
    项目当前仅一个 mjlab adapter（`adapters/mjlab/`），入口靠 profile 的
    `entrypoints.env / entrypoints.runner` 字符串延迟加载。为支撑后续
    UniLab / RoboLab / IsaacGym 以同一 manifest 接入，这里把「训练后端」
    收敛为显式的 Protocol（三入口：env 环境构造 / runner 训练循环 /
    exporter 策略导出），并提供一个轻量注册表。

刻意设计：
    - 本模块**只含标准库**，不含 torch / mjlab / pydantic——控制面在无训练栈
      环境下也能导入本协议做框架能力声明与校验（维持"控制面永不 import
      训练栈"的隔离原则）。
    - 训练栈 worker 通过字符串延迟解析（`load_backend_adapter`）在子进程内
      按模块路径加载对应实现；控制面只需按 manifest 声明能力，不触碰实现。

参考：
    报告 4 §1B / §2 的 framework 同名符号延迟解析范式（robot_lab /
    unilab EnvFactory Protocol），以及报告 7 §3 异构子进程隔离。

K2 增补：**能力契约**（``BackendPlayCapabilities`` / 高度扫描 / 域随机化）
    上面的 ``BackendDescriptor`` 只说「有没有这个后端、三入口在哪」，没说
    「这个后端到底能做哪些事」。多后端最容易出的两类事故都在这层：

    1. **能力靠猜**：调用方以为"换个后端也一样"，而某后端的确定性回放 / 高度扫描 /
       域随机化其实没实现，于是静默降级成"碰巧能跑"，结论不可信；
    2. **能力漂移**：真实能力在文档和代码里各写一份，改了代码忘了文档。

    所以能力一律 **fail-closed**：未显式声明的能力按 ``unsupported`` 处理，
    取用即抛 :class:`CapabilityNotImplementedError`（**绝不回退**）；能力名拼错抛
    :class:`UnknownCapabilityError`（不能因为拼错就返回"不支持"然后被当正常分支走掉）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable


@runtime_checkable
class EnvFactoryProtocol(Protocol):
    """构造训练环境的三入口之一（environment）。"""

    def build(self, recipe: dict, contract: dict) -> object:
        """根据解析后的 recipe + 契约返回一个环境对象。"""
        ...


@runtime_checkable
class RunnerProtocol(Protocol):
    """构造训练循环的三入口之二（runner）。"""

    def build(self, recipe: dict, contract: dict) -> object:
        """根据解析后的 recipe + 契约返回一个 runner 对象。"""
        ...


@runtime_checkable
class ExporterProtocol(Protocol):
    """策略导出三入口之三（export）。"""

    def export(self, checkpoint: str, contract: dict, output: str) -> dict:
        """把 checkpoint 导出为 ONNX 等产物，返回元数据。"""
        ...


@runtime_checkable
class BackendAdapter(Protocol):
    """一个训练后端 adapter 的完整接口。

    实现方（如 mjlab / unilab）按该协议提供三入口 + 元信息，供控制面与
    worker 按 manifest 统一消费。实现可以是模块（module-level 函数）或类。
    """

    #: 后端唯一 ID，如 "native_mjlab" / "unilab" / "isaacgym"。
    backend_id: str
    #: 依赖的 Python 环境标签（用于 venv 隔离：mjlab-py312 / unilab-py311）。
    python_env: str
    #: 是否就绪（探测结果由 worker 填充）。
    available: bool

    @property
    def env(self) -> EnvFactoryProtocol:
        """环境构造器。"""
        ...

    @property
    def runner(self) -> RunnerProtocol:
        """训练循环构造器。"""
        ...

    @property
    def exporter(self) -> ExporterProtocol:
        """策略导出器。"""
        ...


@dataclass(frozen=True, slots=True)
class BackendDescriptor:
    """控制面可见的后端能力声明（manifest 层面，不含实现）。

    与 training_api 的 frameworks 列表对齐，供 UI 诚实标注可用/规划中。
    """

    id: str
    label: str
    python_env: str
    available: bool
    #: env/runner/exporter 三入口的模块路径（字符串延迟解析）。
    env_entrypoint: str = ""
    runner_entrypoint: str = ""
    exporter_entrypoint: str = ""
    #: 依赖特征（torch / warp / mujoco-warp 等），用于能力声明。
    requires: tuple[str, ...] = field(default_factory=tuple)
    #: 后端备注（如为何不可用）。
    note: str = ""

    def capabilities(self) -> "BackendCapabilities":
        """本后端的能力声明（K2）。

        未在 :data:`BACKEND_CAPABILITIES` 登记的后端返回**全 unsupported 的缺省声明**
        —— descriptor 说"有这个后端"不等于"它能做这些事"，缺省即不支持。
        """
        declared = BACKEND_CAPABILITIES.get(self.id)
        if declared is not None:
            return declared
        return BackendCapabilities(
            backend_id=self.id,
            display_name=self.label,
            engine="unknown",
            notes=self.note or "未登记能力声明（缺省：全部不支持）",
        )

    def require(self, capability: str) -> str:
        """要求本后端支持某能力；不支持即抛 :class:`CapabilityNotImplementedError`。"""
        return self.capabilities().require(capability)

    def supports(self, capability: str) -> bool:
        return self.capabilities().supports(capability)


#: 内置后端的 manifest 声明表（唯一事实源）。
#: available=False 表示"规划中/未接入"，UI 据此诚实标注而不误当可用。
BACKEND_DESCRIPTORS: dict[str, BackendDescriptor] = {
    "native_mjlab": BackendDescriptor(
        id="native_mjlab",
        label="MJLab",
        python_env="mjlab-py312",
        available=True,
        env_entrypoint="adapters.mjlab.env_factory:build_env",
        runner_entrypoint="adapters.mjlab.constants:resolve_runner_class",
        exporter_entrypoint="adapters.mjlab.onnx_exporter:export_policy_to_onnx",
        requires=("torch", "warp", "mujoco-warp"),
        note="已验证；隔离 adapter 子进程，控制面不 import torch。",
    ),
    "unilab": BackendDescriptor(
        id="unilab",
        label="UniLab",
        python_env="unilab-py311",
        available=False,
        env_entrypoint="",
        runner_entrypoint="",
        exporter_entrypoint="",
        requires=("unilab",),
        note="规划中；按同 manifest 接入后置 available=True。",
    ),
    "isaacgym": BackendDescriptor(
        id="isaacgym",
        label="IsaacGym",
        python_env="isaacgym-py38",
        available=False,
        env_entrypoint="",
        runner_entrypoint="",
        exporter_entrypoint="",
        requires=("isaacgym",),
        note="规划中；预留。",
    ),
}


def get_backend_descriptor(backend_id: str) -> BackendDescriptor | None:
    """按 id 取后端能力声明；未知 id 返回 None。"""
    return BACKEND_DESCRIPTORS.get(backend_id)


def list_backend_descriptors() -> list[BackendDescriptor]:
    """列出全部后端能力声明（UI 框架选择消费）。"""
    return list(BACKEND_DESCRIPTORS.values())


def load_backend_adapter(
    descriptor: BackendDescriptor,
    *,
    env_entrypoint: str | None = None,
    runner_entrypoint: str | None = None,
    exporter_entrypoint: str | None = None,
) -> dict[str, Callable | None]:
    """按 manifest 的 entrypoint 字符串延迟解析后端三入口。

    返回 {"env": callable|None, "runner": callable|None, "exporter": callable|None}。
    解析在调用方子进程内执行（worker），因此 torch/mjlab 只在真正需要时
    被 import——控制面调用本函数可安全地在无训练栈环境得到 None 占位。

    任意环节解析失败仅置 None，不抛异常，由调用方按 need 判定缺失。
    """
    import importlib

    def _resolve(entrypoint: str) -> Callable | None:
        if not entrypoint:
            return None
        module_path, _, attr = entrypoint.partition(":")
        if not module_path or not attr:
            return None
        try:
            module = importlib.import_module(module_path)
            return getattr(module, attr, None)
        except Exception:  # 训练栈模块缺失 / 导入失败 → 占位 None
            return None

    return {
        "env": _resolve(env_entrypoint or descriptor.env_entrypoint),
        "runner": _resolve(runner_entrypoint or descriptor.runner_entrypoint),
        "exporter": _resolve(exporter_entrypoint or descriptor.exporter_entrypoint),
    }


# ===========================================================================
# K2：能力契约（声明式 + 缺省 NotImplementedError）
# ===========================================================================
SUPPORTED = "supported"
PARTIAL = "partial"
UNSUPPORTED = "unsupported"
_LEVELS = (SUPPORTED, PARTIAL, UNSUPPORTED)

#: 已知能力目录：id → 中文说明。**白名单**——拼错能力名必须报错。
CAPABILITY_CATALOG: dict[str, str] = {
    "multi_env": "批量并行环境（同一进程内 N 个环境实例）",
    "deterministic_replay": "确定性回放：同一 seed/指令两次运行逐帧一致",
    "offscreen_render": "离屏渲染（无显示环境出图/出深度）",
    "height_scan": "高度扫描（地形采样点 → 高度场观测）",
    "depth_camera": "深度相机观测项（可进策略输入）",
    "domain_randomization": "域随机化（质量/摩擦/延迟/增益等参数扰动）",
    "terrain_generation": "地形生成（程序化地形 / 命名地形资产）",
    "onnx_export": "策略导出 ONNX（含契约快照与门禁）",
    "policy_acceptance": "策略验收（确定性回放 + 判据，产出 acceptance 报告）",
    "sim2sim_browser": "浏览器内 sim2sim（WASM + ONNX Runtime Web）",
    "mjcf_load": "MJCF 模型加载与 step",
    "usd_load": "USD 资产加载",
    "sensor_suite": "外部传感器套件（声明的传感器集合）",
    "contact_forces": "接触力/触点观测",
}


class UnknownCapabilityError(KeyError):
    """能力名或后端名不在登记表内（拼错 / 版本不匹配）。"""


class CapabilityNotImplementedError(NotImplementedError):
    """能力已知但该后端未声明支持——**不回退**，由调用方决定换后端还是关掉该功能。"""


def known_capabilities() -> tuple[str, ...]:
    """全部已知能力 id（排序，便于稳定输出与测试）。"""
    return tuple(sorted(CAPABILITY_CATALOG))


def _validate_capability(capability: str) -> str:
    if capability not in CAPABILITY_CATALOG:
        raise UnknownCapabilityError(
            f"未知能力 {capability!r}；已登记：{', '.join(known_capabilities())}"
        )
    return capability


@dataclass(frozen=True)
class PlayCapabilities:
    """「运行期播放/回放」相关能力。未列出的能力一律按 ``unsupported`` 处理。"""

    levels: dict[str, str] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)

    def level(self, capability: str) -> str:
        """取能力等级（未声明 = ``unsupported``；能力名未知 = 报错）。"""
        _validate_capability(capability)
        return self.levels.get(capability, UNSUPPORTED)

    def supports(self, capability: str) -> bool:
        return self.level(capability) == SUPPORTED

    def require(self, capability: str) -> str:
        """要求能力为 ``supported``；否则抛 :class:`CapabilityNotImplementedError`。"""
        level = self.level(capability)
        if level != SUPPORTED:
            note = self.notes.get(capability)
            detail = f"（{note}）" if note else ""
            raise CapabilityNotImplementedError(
                f"能力 {capability!r} 当前等级为 {level}{detail}；"
                "请显式开启该能力（换后端或补实现），而不是期待静默回退"
            )
        return level

    def declared(self) -> dict[str, dict[str, Any]]:
        """只列出**显式声明**的能力（等级 + 备注 + 说明），用于能力面板。"""
        return {
            capability: {
                "level": self.levels[capability],
                "note": self.notes.get(capability),
                "help": CAPABILITY_CATALOG[capability],
            }
            for capability in sorted(self.levels)
        }

    def to_dict(self) -> dict[str, Any]:
        return {"levels": dict(self.levels), "notes": dict(self.notes), "declared": self.declared()}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PlayCapabilities":
        levels = {str(key): str(value) for key, value in (payload.get("levels") or {}).items()}
        for capability, level in levels.items():
            _validate_capability(capability)
            if level not in _LEVELS:
                raise ValueError(f"能力 {capability!r} 的等级 {level!r} 不合法（可选 {_LEVELS}）")
        return cls(levels=levels, notes={str(k): str(v) for k, v in (payload.get("notes") or {}).items()})


@dataclass(frozen=True)
class HeightScannerCapabilities:
    """高度扫描能力：可用性 + 网格口径 + 备注（供观测维度校验引用）。"""

    available: bool = False
    backend: str | None = None
    grid: dict[str, Any] = field(default_factory=dict)
    notes: str | None = None

    def require(self) -> "HeightScannerCapabilities":
        if not self.available:
            raise CapabilityNotImplementedError(
                f"高度扫描未实现（后端 {self.backend or '未声明'}）：{self.notes or '无备注'}"
            )
        return self

    def to_dict(self) -> dict[str, Any]:
        return {"available": self.available, "backend": self.backend, "grid": dict(self.grid), "notes": self.notes}


@dataclass(frozen=True)
class DomainRandomizationCapabilities:
    """域随机化能力：支持的字段清单 + 备注。"""

    available: bool = False
    fields: tuple[str, ...] = ()
    notes: str | None = None

    def require(self) -> "DomainRandomizationCapabilities":
        if not self.available:
            raise CapabilityNotImplementedError(f"域随机化未实现：{self.notes or '无备注'}")
        return self

    def supports_field(self, name: str) -> bool:
        return self.available and name in self.fields

    def to_dict(self) -> dict[str, Any]:
        return {"available": self.available, "fields": list(self.fields), "notes": self.notes}


@dataclass(frozen=True)
class BackendCapabilities:
    """一个后端的完整能力声明（与 ``BackendDescriptor`` 同 id 对齐）。"""

    backend_id: str
    display_name: str
    engine: str
    play: PlayCapabilities = field(default_factory=PlayCapabilities)
    height_scanner: HeightScannerCapabilities = field(default_factory=HeightScannerCapabilities)
    domain_randomization: DomainRandomizationCapabilities = field(
        default_factory=DomainRandomizationCapabilities
    )
    evidence: tuple[str, ...] = ()
    notes: str | None = None

    def require(self, capability: str) -> str:
        """统一入口：高度扫描/域随机化走专用声明，其余落回 play 能力表。"""
        _validate_capability(capability)
        if capability == "height_scan":
            self.height_scanner.require()
            return SUPPORTED
        if capability == "domain_randomization":
            self.domain_randomization.require()
            return SUPPORTED
        return self.play.require(capability)

    def supports(self, capability: str) -> bool:
        try:
            self.require(capability)
        except CapabilityNotImplementedError:
            return False
        return True

    def report(self) -> dict[str, str]:
        """能力面板：全部已知能力的当前等级（未声明即 unsupported）。"""
        return {
            capability: (
                (SUPPORTED if self.supports(capability) else UNSUPPORTED)
                if capability in ("height_scan", "domain_randomization")
                else self.play.level(capability)
            )
            for capability in known_capabilities()
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "display_name": self.display_name,
            "engine": self.engine,
            "play": self.play.to_dict(),
            "height_scanner": self.height_scanner.to_dict(),
            "domain_randomization": self.domain_randomization.to_dict(),
            "report": self.report(),
            "evidence": list(self.evidence),
            "notes": self.notes,
        }


#: 能力声明表（与 BACKEND_DESCRIPTORS 同 id）。**证据见 evidence，不猜**：
#: 宁可保守记 partial，也不虚报 supported——调用方是按这份声明 fail-closed 的。
BACKEND_CAPABILITIES: dict[str, BackendCapabilities] = {
    "native_mjlab": BackendCapabilities(
        backend_id="native_mjlab",
        display_name="MJLab（MuJoCo Warp + PyTorch）",
        engine="mujoco_warp",
        play=PlayCapabilities(
            levels={
                "multi_env": SUPPORTED,
                "onnx_export": SUPPORTED,
                "policy_acceptance": SUPPORTED,
                "sim2sim_browser": SUPPORTED,
                "mjcf_load": SUPPORTED,
                "sensor_suite": PARTIAL,
                "deterministic_replay": PARTIAL,
                "offscreen_render": PARTIAL,
                "depth_camera": PARTIAL,
                "terrain_generation": PARTIAL,
                "contact_forces": PARTIAL,
                "domain_randomization": UNSUPPORTED,
                "usd_load": UNSUPPORTED,
            },
            notes={
                "deterministic_replay": "浏览器 sim2sim 有 deterministicReplay、训练侧有 replay_diff 数值回放；"
                                        "「两次逐帧一致」的门禁未落地（G2 未完成）",
                "offscreen_render": "控制面 backend/model_api.py 可渲染预览，依赖可用 GL 后端（MUJOCO_GL）；"
                                    "训练侧无渲染路径",
                "depth_camera": "00_resources/parkour_mjlab 有 PIE 深度任务口径、"
                                "backend/perception_observations.py 有观测项；适配层未声明相机传感器",
                "terrain_generation": "backend/terrain_gen/ 与 assets/maps/ 提供地形，训练 profile 有 terrain 字段；"
                                      "适配层未接线程序化地形",
                "sensor_suite": "backend/sensor_suite.py 声明传感器套件；适配层未消费",
                "contact_forces": "契约与观测项已具备，训练侧接线未逐项复核",
                "domain_randomization": "适配层无 DR 实现，训练 profile 也无 DR 字段（待 E 组重建时补）",
                "usd_load": "mjlab 走 MJCF；USD 属 Newton/Isaac 系资产格式",
            },
        ),
        height_scanner=HeightScannerCapabilities(
            available=False,
            backend="backend/height_scan.py",
            grid={"resolution": 187, "unit": "格"},
            notes="控制面有高度扫描几何实现（187 格），但训练侧未接线为可选能力——按 fail-closed 记不可用，"
                  "接线后改 available=True 并补证据",
        ),
        domain_randomization=DomainRandomizationCapabilities(
            available=False,
            notes="无 DR 实现（与 play.domain_randomization=unsupported 同源）",
        ),
        evidence=(
            "adapters/mjlab/env_factory.py（num_envs 批量环境）",
            "adapters/mjlab/onnx_exporter.py（ONNX 导出）",
            "adapters/mjlab/policy_acceptance.py（策略验收）",
            "adapters/mjlab/replay_diff.py（数值回放）",
            "web/sim2sim/（浏览器 sim2sim，47 条策略基线）",
            "backend/{height_scan,terrain_gen,sensor_suite}.py（控制面侧能力）",
        ),
        notes="MVP 唯一训练后端；等级按 2026-09-13 实测填写。",
    ),
    "unilab": BackendCapabilities(
        backend_id="unilab",
        display_name="UniLab（规划中）",
        engine="unilab",
        notes="未接入：不声明任何支持能力（descriptor 亦为 available=False）。",
    ),
    "isaacgym": BackendCapabilities(
        backend_id="isaacgym",
        display_name="IsaacGym（规划中）",
        engine="isaacgym",
        notes="未接入；IsaacLab 系上游能力见 00_resources，但本仓库无适配层，调用方拿到 unsupported。",
    ),
}


def backend_capabilities(backend_id: str) -> BackendCapabilities:
    """按 id 取后端能力声明；未登记即报错并列出已知后端（**不回退到 mjlab**）。"""
    if backend_id not in BACKEND_CAPABILITIES:
        raise UnknownCapabilityError(
            f"未登记的后端 {backend_id!r}；已知：{', '.join(sorted(BACKEND_CAPABILITIES))}"
        )
    return BACKEND_CAPABILITIES[backend_id]


def capability_matrix() -> dict[str, Any]:
    """后端 × 能力矩阵（全部已知能力 × 全部已登记后端），供报告/页面直接消费。"""
    return {
        "capabilities": {capability: CAPABILITY_CATALOG[capability] for capability in known_capabilities()},
        "backends": {
            backend_id: item.report() for backend_id, item in sorted(BACKEND_CAPABILITIES.items())
        },
    }


def adapter_selftest() -> dict[str, Any]:
    """离线自检：缺省不支持、未知能力名报错、partial 不放行、不回退。"""
    cases: list[dict[str, Any]] = []

    def case(name: str, ok: bool, detail: dict[str, Any]) -> None:
        cases.append({"name": name, "ok": bool(ok), **detail})

    mjlab = backend_capabilities("native_mjlab")

    case(
        "declared_capability_is_usable",
        mjlab.require("multi_env") == SUPPORTED,
        {"multi_env": mjlab.play.level("multi_env")},
    )

    height_blocked = False
    try:
        mjlab.require("height_scan")
    except CapabilityNotImplementedError:
        height_blocked = True
    case(
        "undeclared_capability_raises_not_implemented",
        height_blocked and mjlab.play.level("height_scan") == UNSUPPORTED,
        {"height_scan_level": mjlab.play.level("height_scan")},
    )

    partial_blocked = False
    try:
        mjlab.require("deterministic_replay")
    except CapabilityNotImplementedError as exc:
        partial_blocked = "deterministic_replay" in str(exc)
    case(
        "partial_capability_does_not_silently_pass",
        partial_blocked and mjlab.play.level("deterministic_replay") == PARTIAL,
        {"level": mjlab.play.level("deterministic_replay")},
    )

    name_blocked = False
    try:
        mjlab.play.level("quantum_replay")
    except UnknownCapabilityError:
        name_blocked = True
    case("unknown_capability_name_raises", name_blocked, {})

    backend_blocked = False
    try:
        backend_capabilities("no-such-engine")
    except UnknownCapabilityError:
        backend_blocked = True
    case("unknown_backend_raises", backend_blocked, {"known": sorted(BACKEND_CAPABILITIES)})

    case(
        "capability_table_matches_descriptor_table",
        set(BACKEND_CAPABILITIES) == set(BACKEND_DESCRIPTORS),
        {"descriptors": sorted(BACKEND_DESCRIPTORS), "capabilities": sorted(BACKEND_CAPABILITIES)},
    )

    matrix = capability_matrix()
    case(
        "matrix_covers_every_backend_and_capability",
        set(matrix["backends"]) == set(BACKEND_CAPABILITIES)
        and all(set(row) == set(known_capabilities()) for row in matrix["backends"].values()),
        {"backends": sorted(matrix["backends"]), "capability_count": len(matrix["capabilities"])},
    )

    round_trip = PlayCapabilities.from_dict(mjlab.play.to_dict())
    case(
        "play_capabilities_round_trip",
        round_trip.levels == mjlab.play.levels and round_trip.level("domain_randomization") == UNSUPPORTED,
        {"levels": round_trip.levels},
    )

    bad_level = False
    try:
        PlayCapabilities.from_dict({"levels": {"multi_env": "maybe"}})
    except ValueError:
        bad_level = True
    case("illegal_level_rejected", bad_level, {})

    dr_blocked = False
    try:
        mjlab.domain_randomization.require()
    except CapabilityNotImplementedError:
        dr_blocked = True
    case(
        "domain_randomization_fails_closed",
        dr_blocked and not mjlab.supports("domain_randomization"),
        {},
    )

    failures = [item["name"] for item in cases if not item["ok"]]
    return {
        "success": True,
        "backends": sorted(BACKEND_CAPABILITIES),
        "cases": cases,
        "verdict": "pass" if not failures else "fail",
        "failures": failures,
    }
