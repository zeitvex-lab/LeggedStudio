"""v2 高级仿真的**运行规格解析器**：把「用户意图」决议成不可变 :class:`ResolvedRunSpec`。

本模块**只做解析**，因此有三条边界（都是刻意的，不是待办）：

* **不启动进程**：原生 worker 的探测由后续运行管理器负责（它才有子进程）。这里的
  :data:`RunProbe` 是一个**明确类型的可注入边界**，默认实现如实报告「未探测」。
* **不写 API 路由**：只产出 :class:`contracts.simulation_run_contract.ResolveResponse`
  等模型；HTTP 形状由路由层原样序列化。
* **不写物理循环**：传感器/策略/记录器的实现在别处，这里只核对声明。

三条反冒充规则（本模块存在的主要理由）
--------------------------------------
1. **未探测 ≠ 可运行**。:class:`ResolvedRunSpec` 在类型层就要求已完成的
   :class:`~contracts.simulation_run_contract.NativeProbeReport`，所以「先放行、跑不通再说」
   在这里写不出来。缺探测一律变成 ``native_probe_missing`` 阻断项，``ok=False`` 且
   **不返回半份规格**。
2. **词形命中不算认证**。策略是否吃深度，唯一依据是**实际读到的 ONNX 图输入**
   （名字 + dtype + 形状），``metadata_source="onnx_file"``。
   :mod:`backend.perception_binding` 的 profile 扫描（``declaration_source="scan"``）
   在这里只降级成一条 warning，绝不进入 ``verified_by``。
3. **时间基不算出来的、只抄契约**。``physics_hz`` / ``decimation`` 唯一来自机器人包
   ``contract.json``（:func:`contracts.physics_binding.physics_facts`` 的
   ``source=="contract"``）。``legacy_config`` / ``missing`` 一律阻断 —— 否则 PIE 的
   隐式 200Hz 会作为第二真值回来。

失败一律是 :class:`~contracts.simulation_run_contract.ResolutionBlocker` 结构化列表，
调用方按 ``code`` 分支，不需要读中文文本。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import backend.robot_packages as robot_packages
from contracts import sensor_plugin_contract as plugin_contract
from contracts import simulation_run_contract as rc
from contracts.physics_binding import physics_facts
from contracts.scenario_contract import ScenarioContract
from contracts.simulation_protocol import DTYPE_ITEMSIZE, protocol_limits
from contracts.validator import canonical_sha256, normalized_sha256

__all__ = [
    "RESOLVER_VERSION",
    "ONNX_ELEMENT_TYPE_TO_PROTOCOL",
    "MAIN_OBS_INPUT_NAMES",
    "AUX_PRODUCED_BY_BINDINGS",
    "DEPTH_CALIBRATION_KEYS",
    "MODEL_ASSET_FALLBACK",
    "OnnxArtifactMetadata",
    "PolicyMetadataReader",
    "ProbeContext",
    "RunProbe",
    "read_onnx_artifact_metadata",
    "unavailable_native_probe",
    "RunResolver",
    "resolve_run",
    "verify_assets",
    "run_catalog",
]

#: 解析器自身的版本。**独立于** :data:`contracts.simulation_run_contract.NATIVE_RUNTIME_VERSION`
#: ——它描述「谁做的决议」，不冒称执行器版本（旧 ``server_mujoco`` 没有策略闭环）。
RESOLVER_VERSION = "sim-resolver-1.0"

#: 包内没有 ``robot_package.json`` 描述时的模型兜底路径（与 ``package_for_contract`` 同一默认）。
MODEL_ASSET_FALLBACK = "model/robot.xml"

#: 主观测输入的常见名字。**名字只用来挑出「哪一路是本体观测」**，其形状/dtype 一律取
#: ONNX 实测；宽度含义（proprio 还是 history）由 ``obs_dim`` 的除法决定，不看词。
#: 表里的每一项都对应一个真实产物用过的输入名（``proprio``=go2-pie-parkour、
#: ``observation``=go2-lainlab-trot）；没出现过的名字一律不预判，未命中就阻断。
MAIN_OBS_INPUT_NAMES = (
    "obs",
    "observation",
    "observations",
    "actor_obs",
    "policy_obs",
    "actor_states",
    "proprio",
    # mjswan 导出器给主观测槽起的名（`examples/demo` 的 unitree_go2 产物实测：四个输入
    # `l_kwargs_policy_[1,117]` / `arg1[1]bool` / `l_kwargs_adapt_hx_[1,128]` /
    # `l_kwargs_command_[1,16]`，槽表顺序由包的 `contract.onnx_slots` 声明）。
    "l_kwargs_policy_",
)

#: ONNX ``TensorProto.elem_type`` → 线协议 dtype（唯一表）。**故意不收录** f2/bf16/complex：
#: 线协议没有这些码型，遇到就当「读不出可认证的元数据」，而不是就近取一个近似 dtype。
ONNX_ELEMENT_TYPE_TO_PROTOCOL: dict[int, str] = {
    1: "f4",   # FLOAT
    2: "u1",   # UINT8
    3: "i1",   # INT8
    4: "u2",   # UINT16
    5: "i2",   # INT16
    6: "i4",   # INT32
    7: "i8",   # INT64
    9: "b1",   # BOOL
    11: "f8",  # DOUBLE
    12: "u4",  # UINT32
    13: "u8",  # UINT64
}

#: 包内声明 ``aux_inputs[].produced_by`` → ``(观测类别, 数据来源)``。
#: 键的取值来自既有声明（``external:history_buffer`` 等）；**未登记的 produced_by 不猜**，
#: 直接阻断报「无法确定该输入的来源」——把未知项当 ``external`` 放行就是静默错绑。
AUX_PRODUCED_BY_BINDINGS: dict[str, tuple[str, str]] = {
    "external:depth_camera": ("depth", "sensor"),
    "external:history_buffer": ("history", "history_buffer"),
    "external:recurrent_state": ("memory", "recurrent_state"),
    "external:base_command": ("command", "command"),
    "external:command": ("command", "command"),
    # mjswan 四输入链的 `is_init`（bool 标量：该步是否 episode 首帧）。它既不是观测也不是
    # 命令，而是**随 episode 边界变化的运行态标志** —— 与 `adapt_hx` 同属"运行时自己填"的槽
    # （上游 `RUNTIME_INPUT_SLOTS = {is_init, adapt_hx, time_step}`）。
    "external:is_init": ("memory", "is_init"),
}

#: 策略契约 ``contract.depth_camera`` → 深度插件参数名。标定四项**只有这一处**从策略契约
#: 流向传感器实例（``update_steps`` 单独处理：它的单位是控制步，要乘 decimation 才是 tick）。
DEPTH_CALIBRATION_KEYS: dict[str, str] = {
    "min_m": "min_range",
    "max_m": "max_range",
    "crop": "crop_width",
    "history": "history_frames",
    "raw_width": "width",
    "height": "height",
    "fovy_deg": "fovy_deg",
}


# --------------------------------------------------------------------------------------
# 注入边界（可测试、可替换，但类型严格）
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class OnnxArtifactMetadata:
    """从**实际文件**读出的产物元数据（读不出就是 ``None``，没有「部分读出」）。"""

    inputs: tuple[rc.OnnxTensorMeta, ...]
    outputs: tuple[rc.OnnxTensorMeta, ...]
    reader: str


#: ``path -> metadata | None``。``None`` = 读不到（onnx 未安装 / 文件损坏 / 码型不支持）。
PolicyMetadataReader = Callable[[Path], OnnxArtifactMetadata | None]

#: 探测期能看到的**草稿**（决议尚未完成，所以拿不到 :class:`ResolvedRunSpec`：
#: 规格的构造本身要求已有探测报告 —— 用草稿映射避免「先有鸡还是先有蛋」）。
ProbeContext = Mapping[str, Any]

#: 解析期的原生探测边界。worker 侧真正实现的类型是
#: :data:`contracts.runtime_interfaces.NativeProbe`（入参是已决议规格），两者**不能混用**。
RunProbe = Callable[[ProbeContext], rc.NativeProbeReport]


def unavailable_native_probe(context: ProbeContext) -> rc.NativeProbeReport:
    """默认探测实现：**如实报告「没探过」**。

    它不抛异常（抛异常会让调用方倾向「捕获后继续」），也不返回 ``None``
    （``None`` 会被写成「没有信息 = 不判断」）—— 返回一份类型完整的未探测报告，
    于是阻断项是**证据**而不是猜测。
    """

    del context  # 默认实现什么都不测，因此也什么都不看
    return rc.NativeProbeReport.not_probed(
        "not_implemented",
        details="backend/simulation_resolver 不启动进程；worker 探测由运行管理器注入",
    )


def _onnx_tensor_metas(value_infos: Sequence[Any]) -> tuple[rc.OnnxTensorMeta, ...] | None:
    """把 ONNX ``ValueInfo`` 列表转成协议张量描述；任一项解释不了就整体返回 ``None``。

    **整体失败**是刻意的：一份「三个输入认得、一个猜的」元数据比读不到更危险
    （猜错的那个通常正是深度/记忆这类拼接易错的输入）。
    """

    items: list[rc.OnnxTensorMeta] = []
    for info in value_infos:
        try:
            tensor_type = info.type.tensor_type
            dtype = ONNX_ELEMENT_TYPE_TO_PROTOCOL.get(int(tensor_type.elem_type))
        except (AttributeError, TypeError, ValueError):
            return None
        if dtype is None:
            return None
        dims: list[int] = []
        shape = getattr(tensor_type, "shape", None)
        for dim in (getattr(shape, "dim", ()) or ()):
            if getattr(dim, "dim_param", ""):  # 符号维（"batch" 等）→ 动态
                dims.append(-1)
            else:
                try:
                    dims.append(int(dim.dim_value))
                except (TypeError, ValueError):
                    return None
        name = str(getattr(info, "name", "") or "").strip()
        if not name:
            return None
        items.append(rc.OnnxTensorMeta(name=name, dtype=dtype, shape=tuple(dims)))
    return tuple(items) if items else None


def read_onnx_artifact_metadata(path: Path) -> OnnxArtifactMetadata | None:
    """读取产物实际元数据（只读模型头，不解析权重）。读不到返回 ``None``。"""

    try:
        import onnx
    except ImportError:
        return None
    try:
        model = onnx.load(str(path), load_external_data=False)
    except Exception:  # noqa: BLE001 - 任何解析失败都只能记为「读不到」，不能猜
        return None
    inputs = _onnx_tensor_metas(list(model.graph.input))
    outputs = _onnx_tensor_metas(list(model.graph.output))
    if not inputs or not outputs:
        return None
    return OnnxArtifactMetadata(
        inputs=inputs,
        outputs=outputs,
        reader=f"onnx/{getattr(onnx, '__version__', 'unknown')}",
    )


def _file_digest(path: Path) -> str | None:
    """资产摘要：委托 :func:`contracts.validator.normalized_sha256`（**唯一**实现处）。"""

    try:
        return normalized_sha256(path.read_bytes())
    except OSError:
        return None


def _repo_relative(path: Path, repo_root: Path | None = None) -> str:
    """仓库相对 posix 路径。仓库外的资产**不登记**（返回空串由调用方阻断）。

    ``repo_root`` 只为「把整棵树搬到别处」的调用方存在（测试用自己的临时仓库根、
    以及未来的可移植安装包）；默认仍是 :data:`backend.robot_packages.ROOT` ——
    路径口径始终**只有一种**（仓库相对），不搞第二套。
    """

    base = Path(repo_root) if repo_root is not None else robot_packages.ROOT
    resolved = path.resolve()
    try:
        return resolved.relative_to(base.resolve()).as_posix()
    except ValueError:
        return ""


def _product(dims: Sequence[int]) -> int:
    total = 1
    for dim in dims:
        if int(dim) < 0:
            return -1  # 动态维：元素数不可知
        total *= int(dim)
    return total


def _static_product(dims: Sequence[int]) -> int:
    """忽略**至多一个**动态维（ONNX 的符号批维）后的元素数；两个以上未知维 → ``-1`` 不可知。

    为什么不能直接用 :func:`_product`：真实导出常见 ``[-1, 470]``，按 ``_product`` 会得到
    ``-1``，于是「历史帧数」这种本该算得出的量也算不出 —— 但批维未知**不影响**每样本元素数，
    所以这里只放过一个未知维，多于一律不可知（不做「猜一个批大小」的事）。
    """

    unknown = [dim for dim in dims if int(dim) < 0]
    if len(unknown) > 1:
        return -1
    total = 1
    for dim in dims:
        if int(dim) > 0:
            total *= int(dim)
    return total


def _truncate(text: str, limit: int = 700) -> str:
    clean = " ".join(str(text).split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"


def _error_detail(exc: Exception) -> str:
    """从 ``ValidationError`` 里取**第一条**可读错误（多条时截断会让诊断更难对齐）。"""

    errors = getattr(exc, "errors", None)
    if callable(errors):
        try:
            items = errors()
        except Exception:  # noqa: BLE001 - 摘要失败退回 str(exc)
            items = []
        if items:
            first = items[0]
            location = ".".join(str(part) for part in (first.get("loc") or ())) or "?"
            return f"{location}: {first.get('msg') or first}"
    return _truncate(str(exc))


# --------------------------------------------------------------------------------------
# 阻断收集
# --------------------------------------------------------------------------------------


@dataclass
class _Findings:
    """一次决议收集到的阻断项与告警（告警**不**阻断，但会随响应返回给前端）。"""

    blockers: list[rc.ResolutionBlocker] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return bool(self.blockers)

    def block(
        self,
        code: Any,
        subject: str,
        detail: str,
        *,
        remedy: str = "",
        field_name: str | None = None,
    ) -> None:
        self.blockers.append(
            rc.ResolutionBlocker(
                code=code,  # type: ignore[arg-type]
                subject=subject,
                detail=_truncate(detail, 900),
                remedy=_truncate(remedy, 500),
                field=field_name,
            )
        )

    def warn(self, text: str) -> None:
        self.warnings.append(_truncate(text, 500))


# --------------------------------------------------------------------------------------
# 包事实
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PackageFacts:
    """一个机器人包里被解析器读到的事实（**只读**，不写盘、不改包）。"""

    robot_id: str
    root: Path
    descriptor: dict[str, Any]
    sim_config: dict[str, Any]
    policies: dict[str, dict[str, Any]]

    def model_rel_path(self) -> str:
        model = self.descriptor.get("model")
        if isinstance(model, Mapping):
            value = str(model.get("path") or "").strip()
            if value:
                return value.replace("\\", "/")
        return MODEL_ASSET_FALLBACK

    def policy_entry(self, policy_id: str) -> dict[str, Any] | None:
        entry = self.policies.get(policy_id)
        return entry if isinstance(entry, Mapping) else None


def _load_package(
    robot_id: str, findings: _Findings, root: Path | None = None
) -> PackageFacts | None:
    """解析包根与必需文件；缺件即阻断（**不回落到内置默认包**）。

    ``root`` 是给调用方的显式覆盖（运行管理器已知生效包根；测试用自己的夹具包）。
    留空时才走 :func:`backend.robot_packages.robot_package_root` 的单一解析规则 ——
    解析器不自造第二套「去哪儿找包」的逻辑。
    """

    if root is None:
        known = {str(item.get("package_id") or "") for item in robot_packages.list_robot_packages()}
        if known and robot_id not in known:
            findings.block(
                "unknown_robot",
                robot_id,
                f"机器人包索引里没有 {robot_id!r}（已登记 {sorted(k for k in known if k)}）",
                remedy="导入该机器人包，或改用已登记的 package_id",
            )
            return None
        package_root: Path = robot_packages.robot_package_root(robot_id)
    else:
        package_root = Path(root)
    root = package_root
    if not root.is_dir():
        findings.block(
            "package_missing",
            robot_id,
            f"机器人包目录不存在：{root}",
            remedy="确认 assets/robots/<package_id> 或 workspace 导入目录存在",
        )
        return None
    descriptor = robot_packages._read_json(root / "robot_package.json")
    sim_config = robot_packages._read_json(root / "simulation" / "config.json")
    if not sim_config:
        findings.block(
            "asset_missing",
            f"{robot_id}:simulation/config.json",
            "包内没有可读的 simulation/config.json，策略声明无从核对",
            remedy="补齐该包的仿真配置（解析器不猜策略清单）",
        )
        return None
    policies: dict[str, dict[str, Any]] = {}
    for section in ("policies", "demo_policies"):
        for entry in sim_config.get(section) or []:
            if not isinstance(entry, Mapping):
                continue
            identifier = str(entry.get("id") or "").strip()
            if not identifier:
                continue
            if identifier in policies:
                # 两处都登记同一个 id 时，「用哪一条」不可知；先阻断，不让解析器投票。
                findings.block(
                    "scenario_invalid",
                    f"{robot_id}:{identifier}",
                    "策略 id 在 policies 与 demo_policies 中重复登记，声明冲突",
                    remedy="删掉其中一份声明（一个策略一个身份）",
                    field_name=f"policies[{identifier}]",
                )
                return None
            policies[identifier] = dict(entry)
    return PackageFacts(
        robot_id=robot_id, root=root, descriptor=descriptor, sim_config=sim_config, policies=policies
    )


def _time_base(package: PackageFacts, findings: _Findings) -> rc.RunTimeBase | None:
    """时间基**只能**来自 ``contract.json``（``physics_facts`` 的 ``source`` 是权威标记）。"""

    facts = physics_facts(package.root)
    source = str(facts.get("source") or "missing")
    if source != "contract":
        code = "time_base_missing" if source == "missing" else "time_base_not_contract"
        findings.block(
            code,  # type: ignore[arg-type]
            package.robot_id,
            f"物理事实来源={source!r}；运行规格只接受 contract.json 的 control 段"
            "（legacy_config 会制造第二个频率真值，例如把 PIE 的隐式 200Hz 当物理事实）",
            remedy=f"在 {package.root / 'contract.json'} 的 control 里声明 "
            "control_hz/physics_hz/decimation",
            field_name="control",
        )
        return None
    physics_hz = facts.get("physics_hz")
    decimation = facts.get("decimation")
    control_hz = facts.get("control_hz")
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in (physics_hz, decimation)):
        findings.block(
            "time_base_missing",
            package.robot_id,
            f"contract.json 的 physics_hz/decimation 必须是整数，实为 {physics_hz!r}/{decimation!r}",
            remedy="补齐整数物理率与分频（tick 是整数，非整数率无法对齐 tick）",
            field_name="control",
        )
        return None
    try:
        base = rc.RunTimeBase(
            physics_hz=int(physics_hz),
            control_decimation=int(decimation),
            source="contract",
        )
    except ValueError as exc:
        findings.block(
            "time_base_not_contract",
            package.robot_id,
            f"contract.json 的时间基不自洽：{_error_detail(exc)}",
            remedy="physics_hz 必须能被 decimation 整除",
            field_name="control",
        )
        return None
    if control_hz is not None and abs(float(control_hz) - base.control_hz) > 1e-9:
        findings.block(
            "time_base_not_contract",
            package.robot_id,
            f"contract.json 同时给了 control_hz={control_hz} 与 physics_hz/decimation="
            f"{base.control_hz}，两者不一致（两个真值必须先在包里对齐）",
            remedy="删除 control_hz 或把它改成 physics_hz/decimation 的商",
            field_name="control.control_hz",
        )
        return None
    return base


def _declared_onnx_path(package: PackageFacts, entry: Mapping[str, Any]) -> Path | None:
    """按既有三种声明形式（包内相对 / 浏览器包 URL / web 静态目录）实测解析产物文件。"""

    from backend.policy_artifacts import resolve_declared_onnx  # 解析规则唯一实现处

    return resolve_declared_onnx(package.root, entry.get("path") or "", entry.get("url") or "")


def _profile_for_policy(package: PackageFacts, policy_id: str) -> tuple[dict[str, Any] | None, str | None]:
    from backend.perception_binding import load_profile_for_policy  # profile 查找唯一实现处

    return load_profile_for_policy(package.root, package.sim_config, policy_id)



# --------------------------------------------------------------------------------------
# 策略产物与观测绑定
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _ResolvedPolicy:
    """一条已认证的策略决议（产物字节 + 实际元数据 + 声明块）。"""

    policy_id: str
    entry: dict[str, Any]
    contract: dict[str, Any]
    onnx_path: Path
    relative_path: str
    package_root: str
    sha256: str
    metadata: OnnxArtifactMetadata
    obs_dim: int
    profile: dict[str, Any] | None
    profile_id: str | None

    @property
    def depth_calibration(self) -> dict[str, Any]:
        block = self.contract.get("depth_camera")
        return dict(block) if isinstance(block, Mapping) else {}

    def aux_map(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for item in self.entry.get("aux_inputs") or []:
            if isinstance(item, Mapping) and str(item.get("name") or ""):
                out[str(item["name"])] = dict(item)
        return out


def _resolve_policy(
    package: PackageFacts,
    policy_id: str,
    findings: _Findings,
    read_metadata: PolicyMetadataReader,
    repo_root: Path | None = None,
) -> _ResolvedPolicy | None:
    entry = package.policy_entry(policy_id)
    if entry is None:
        findings.block(
            "unknown_policy",
            policy_id,
            f"机器人包 {package.robot_id} 的 policies/demo_policies 里没有该策略"
            f"（已登记 {sorted(package.policies)}）",
            remedy="选择包里存在的策略 id，或把策略装进该包",
        )
        return None
    onnx_path = _declared_onnx_path(package, entry)
    if onnx_path is None:
        findings.block(
            "asset_missing",
            policy_id,
            f"策略声明的 ONNX 文件实测不存在（path={entry.get('path')!r} url={entry.get('url')!r}）",
            remedy="补齐产物文件，或修正包内声明指向真实文件",
            field_name="path",
        )
        return None
    digest = _file_digest(onnx_path)
    if digest is None:
        findings.block(
            "asset_missing",
            policy_id,
            f"无法读取策略产物字节以计算摘要：{onnx_path}",
            remedy="检查文件可读权限（无摘要就无法在运行创建后发现资产漂移）",
        )
        return None
    relative = _repo_relative(onnx_path, repo_root)
    if not relative:
        findings.block(
            "path_escape",
            policy_id,
            f"策略产物在仓库之外：{onnx_path}（运行规格只登记仓库相对路径）",
            remedy="把产物放进机器人包目录",
        )
        return None
    metadata = read_metadata(onnx_path)
    if metadata is None:
        findings.block(
            "policy_metadata_unverified",
            policy_id,
            f"读不出 {relative} 的实际输入/输出元数据（onnx 不可用、文件不可解析，"
            "或含线协议不支持的码型）。配置里写了形状、或按名字猜都不算认证",
            remedy="安装 onnx 可读的产物；或修正导出（只允许线协议 dtype 表内的码型）",
        )
        return None
    contract_block = entry.get("contract") if isinstance(entry.get("contract"), Mapping) else {}
    obs_dim_raw = entry.get("obs_dim") or (contract_block or {}).get("obs_dim")
    try:
        obs_dim = int(obs_dim_raw)
    except (TypeError, ValueError):
        obs_dim = 0
    if obs_dim < 1:
        findings.block(
            "policy_input_mismatch",
            policy_id,
            f"包内声明的 obs_dim={obs_dim_raw!r} 不是正整数，无法解释产物观测宽度"
            "（proprio 与 history 的区分靠 obs_dim 做除法，不做词形猜测）",
            remedy="在包声明里补正确的 obs_dim",
            field_name="obs_dim",
        )
        return None
    profile, profile_id = _profile_for_policy(package, policy_id)
    return _ResolvedPolicy(
        policy_id=policy_id,
        entry=dict(entry),
        contract=dict(contract_block or {}),
        onnx_path=onnx_path,
        relative_path=relative,
        package_root=str(package.root),
        sha256=digest,
        metadata=metadata,
        obs_dim=obs_dim,
        profile=profile,
        profile_id=profile_id,
    )


def _expected_policy_tensor_shape(config: Mapping[str, Any]) -> tuple[int, ...] | None:
    """深度插件「策略实际吃的那一路」的应有形状 ``(history, height, width-2*crop)``。

    这条算式是 106/86 事故的**唯一**防线：ONNX 实测形状是权威，插件参数是声明，
    两者必须逐项相等（动态维除外）。返回 ``None`` 表示参数不足以判定。
    """

    try:
        width = int(config["width"])
        height = int(config["height"])
        crop = int(config["crop_width"])
        frames = int(config["history_frames"])
    except (KeyError, TypeError, ValueError):
        return None
    cropped = width - 2 * crop
    if cropped <= 0 or height <= 0 or frames <= 0:
        return (-1,)
    return (frames, height, cropped)


def _resolve_instances(
    package: PackageFacts,
    advanced: Any,
    time_base: rc.RunTimeBase,
    policy: _ResolvedPolicy | None,
    findings: _Findings,
) -> tuple[tuple[rc.SensorInstanceSpec, ...], list[tuple[str, str]]]:
    """场景请求 → 已决议实例（完整参数集 + 每个参数的出处）＋挂载位姿出处清单。"""

    requests = list(getattr(advanced, "sensor_instances", None) or [])
    mount_authority: list[tuple[str, str]] = []
    if not requests:
        return (), mount_authority
    depth_calib = policy.depth_calibration if policy else {}
    instances: list[rc.SensorInstanceSpec] = []
    seen: set[str] = set()
    for request in requests:
        identifier = str(getattr(request, "instance_id", "") or "?")
        plugin_id = str(getattr(request, "plugin_id", "") or "")
        if identifier in seen:
            findings.block(
                "duplicate_instance",
                identifier,
                f"instance_id={identifier!r} 在场景里出现多次（同类型可多实例，但标识必须唯一）",
                remedy="给第二个实例换一个唯一 instance_id",
                field_name=f"advanced.sensor_instances[{identifier}].instance_id",
            )
            continue
        seen.add(identifier)
        definition = plugin_contract.plugin_definition(plugin_id)
        if definition is None:
            findings.block(
                "unknown_plugin",
                f"{identifier}:{plugin_id}",
                f"插件 {plugin_id!r} 未登记（catalog：{list(plugin_contract.plugin_ids())}）",
                remedy="改用已登记插件，或先在 contracts/sensor_plugin_contract.py 声明它",
                field_name=f"advanced.sensor_instances[{identifier}].plugin_id",
            )
            continue
        if not definition.instantiable:
            findings.block(
                "unknown_plugin",
                f"{identifier}:{plugin_id}",
                f"插件 {plugin_id} 是派生视图（instantiable=False），不能直接实例化",
                remedy="实例化它的源插件并声明用途",
            )
            continue
        if not bool(getattr(request, "enabled", True)):
            # 关掉的实例不进规格：它既不该被采集，也不该参与「策略需要哪路传感器」的判定
            continue
        requested_version = str(getattr(request, "plugin_version", "") or "")
        if requested_version and requested_version != definition.version:
            findings.block(
                "unknown_plugin",
                f"{identifier}:{plugin_id}",
                f"场景要求插件 {plugin_id} 版本 {requested_version}，catalog 里只有 "
                f"{definition.version}（版本不同的参数集不兼容，不能当同一个插件用）",
                remedy=f"把 plugin_version 改成 {definition.version}，或补齐该版本的声明",
                field_name=f"advanced.sensor_instances[{identifier}].plugin_version",
            )
            continue
        if definition.requires_target and not str(getattr(request, "target", "") or "").strip():
            findings.block(
                "sensor_calibration_missing",
                identifier,
                f"实例 {identifier}（{plugin_id}）必须有 target：射线/相机要挂在具体 "
                "site/body/camera 上，解析器不猜模型里的名字",
                remedy="在 advanced.sensor_instances[].target 填 MJCF 里的 site 名",
                field_name=f"advanced.sensor_instances[{identifier}].target",
            )
            continue

        overrides: dict[str, Any] = {}
        authority: dict[str, str] = {}
        # 1) 深度标定：权威是**策略契约**（插件声明故意不给默认值，就是为了不让两处不同真值）
        if plugin_id == "depth" and depth_calib:
            for declared_key, param in DEPTH_CALIBRATION_KEYS.items():
                if declared_key not in depth_calib:
                    continue
                value = depth_calib[declared_key]
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    overrides[param] = int(value) if param in _DEPTH_INT_PARAMS else float(value)
                    authority[param] = f"policy_contract:{policy.policy_id}.depth_camera.{declared_key}"
        # 2) 场景显式覆盖（与策略契约同时给出时必须相等）
        for key, value in (getattr(request, "config", None) or {}).items():
            param = str(key)
            if param in overrides and overrides[param] != value:
                findings.block(
                    "policy_input_mismatch",
                    identifier,
                    f"参数 {param}：场景给 {value!r}，策略契约给 {overrides[param]!r}"
                    "（两处都声明且不是一致的值，就是双真值；解析器不投票）",
                    remedy="删掉场景里的这一项，或把两处改成同一个值",
                    field_name=f"advanced.sensor_instances[{identifier}].config.{param}",
                )
                continue
            overrides[param] = value
            authority[param] = f"scenario.advanced.sensor_instances[{identifier}].config.{param}"
        # 3) 采样周期：请求给 Hz → 换整数 tick；否则用策略契约的 update_steps
        period, period_source = _resolve_sample_period(
            request, definition, time_base, depth_calib, policy, findings, identifier
        )
        if period is None:
            if period_source != _PLUGIN_DEFAULT_PERIOD:
                continue  # 已经记录过阻断项的路径（无权威来源 / 非整数 tick / 双真值）
            # 插件声明自己有默认周期：**不**写覆盖值，交给 ``resolve_config`` 填默认，
            # 出处由插件声明自己给出。这里不能把实例丢掉 —— 用户要了这个传感器。
        else:
            overrides["sample_period_ticks"] = period
            authority["sample_period_ticks"] = period_source
        # 4) 挂载位姿：场景优先，缺则取策略契约的 pos/quat
        pos, quat, pose_sources = _resolve_mount(
            request, plugin_id, depth_calib, policy, findings, identifier
        )
        if pos is None:
            continue
        try:
            config, provenance = definition.resolve_config(overrides)
        except Exception as exc:  # SensorDeclarationError / ValueError
            findings.block(
                "scenario_invalid",
                identifier,
                f"插件 {plugin_id} 参数解析失败：{_error_detail(exc)}",
                remedy="补齐该插件的必填参数（标定类参数无默认值是刻意的）",
                field_name=f"advanced.sensor_instances[{identifier}].config",
            )
            continue
        for key in config:
            if provenance.get(key, "").startswith("override:"):
                provenance[key] = authority.get(key, provenance[key])
        # 挂载位姿的出处**不进**实例参数出处表（那张表与 config 严格同键集，由契约把住），
        # 而是登记到规格级 :class:`ParamProvenance`：位姿不是插件参数，是场景/契约给的装法。
        for pose_field, pose_text in pose_sources.items():
            mount_authority.append((f"mount[{identifier}].{pose_field}", pose_text))
        record = _record_options(request, definition, config)
        try:
            instances.append(
                rc.SensorInstanceSpec(
                    instance_id=identifier,
                    plugin_id=plugin_id,
                    plugin_version=definition.version,
                    target_kind=getattr(request, "target_kind", None),
                    target=str(getattr(request, "target", "") or "") or None,
                    pos=pos,  # type: ignore[arg-type]
                    quat_wxyz=quat,  # type: ignore[arg-type]
                    noise=getattr(request, "noise", None) or plugin_contract.NoiseSpec(),
                    latency=getattr(request, "latency", None) or plugin_contract.LatencySpec(),
                    config=config,
                    config_provenance=provenance,
                    capability_level=definition.capability_level,
                    record=record,
                )
            )
        except ValueError as exc:
            findings.block(
                "scenario_invalid",
                identifier,
                f"实例决议不成立：{_error_detail(exc)}",
                remedy="按报错指出的一项修正场景声明（参数集必须完整且合法）",
                field_name=f"advanced.sensor_instances[{identifier}]",
            )
    if findings.failed:
        return (), []
    return tuple(instances), mount_authority


_DEPTH_INT_PARAMS = frozenset({"width", "height", "crop_width", "history_frames"})

#: 哨兵：采样周期「本轮不覆盖，用插件声明里的默认值」。必须与"算不出来（已阻断）"用的
#: ``None`` 区分开 —— 否则调用方会把用户要的那个实例整个丢掉（静默少一路传感器，
#: 比报错更难查）。
_PLUGIN_DEFAULT_PERIOD = "__plugin_default__"


def _resolve_sample_period(
    request: Any,
    definition: plugin_contract.SensorPluginDefinition,
    time_base: rc.RunTimeBase,
    depth_calib: Mapping[str, Any],
    policy: _ResolvedPolicy | None,
    findings: _Findings,
    identifier: str,
) -> tuple[int | None, str]:
    """采样周期的**唯一**换算处：Hz / update_steps → 整数物理 tick。"""

    requested_hz = getattr(request, "sample_hz", None)
    field = definition.config_field("sample_period_ticks")
    steps = depth_calib.get("update_steps") if isinstance(depth_calib, Mapping) else None
    if requested_hz:
        hz = float(requested_hz)
        raw_ticks = time_base.physics_hz / hz
        ticks = int(round(raw_ticks))
        if ticks < 1 or abs(raw_ticks - ticks) > 1e-6:
            findings.block(
                "scenario_invalid",
                identifier,
                f"sample_hz={hz} 在 physics_hz={time_base.physics_hz} 下不是整数 tick"
                f"（实为 {raw_ticks:.6f}）—— tick 是整数，否则相位会随时间漂移",
                remedy="改成物理率的整数分频（如 500Hz 下取 10/25/50Hz）",
                field_name=f"advanced.sensor_instances[{identifier}].sample_hz",
            )
            return None, ""
        if steps is not None:
            contract_ticks = time_base.ticks_for_control_steps(int(steps))
            if contract_ticks != ticks:
                findings.block(
                    "policy_input_mismatch",
                    identifier,
                    f"场景要求每 {ticks} tick 采一次，而策略契约 depth_camera.update_steps="
                    f"{steps}（={contract_ticks} tick）不符：采样率属于策略契约，不是请求者的意见",
                    remedy="删除场景里的 sample_hz（交给策略契约），或改成一致的值",
                    field_name=f"advanced.sensor_instances[{identifier}].sample_hz",
                )
                return None, ""
        return ticks, f"scenario_override:sample_hz={hz}@physics_hz={time_base.physics_hz}"
    if steps is not None and str(getattr(policy, "policy_id", "") or ""):
        return time_base.ticks_for_control_steps(
            int(steps),
        ), f"policy_contract:{policy.policy_id}.depth_camera.update_steps×decimation"
    if field is not None and field.default is not None:
        return None, _PLUGIN_DEFAULT_PERIOD  # 交给插件默认值（出处由插件声明自己给出）
    findings.block(
        "sensor_calibration_missing",
        identifier,
        f"插件 {definition.plugin_id} 的 sample_period_ticks 无默认值，而场景未给 sample_hz、"
        "策略契约也没有 update_steps（无权威来源时解析器不编一个采样率）",
        remedy="在场景实例里写 sample_hz，或在策略契约里声明 update_steps",
        field_name=f"advanced.sensor_instances[{identifier}].sample_hz",
    )
    return None, ""


def _resolve_mount(
    request: Any,
    plugin_id: str,
    depth_calib: Mapping[str, Any],
    policy: _ResolvedPolicy | None,
    findings: _Findings,
    identifier: str,
) -> tuple[tuple[float, float, float] | None, tuple[float, float, float, float], dict[str, str]]:
    """挂载位姿：场景显式 > 策略契约；两处都给且不一致 → 阻断（不做数值投票）。"""

    pos_raw = getattr(request, "pos", None)
    quat_raw = getattr(request, "quat_wxyz", None)
    sources: dict[str, str] = {}
    if pos_raw is None and plugin_id == "depth" and depth_calib.get("pos"):
        pos_raw = list(depth_calib["pos"])
        sources["pos"] = f"policy_contract:{getattr(policy, 'policy_id', '?')}.depth_camera.pos"
    if quat_raw is None and plugin_id == "depth" and depth_calib.get("quat"):
        quat_raw = list(depth_calib["quat"])
        sources["quat_wxyz"] = (
            f"policy_contract:{getattr(policy, 'policy_id', '?')}.depth_camera.quat（wxyz 口径）"
        )
    pos = tuple(float(item) for item in pos_raw) if pos_raw else (0.0, 0.0, 0.0)
    quat = tuple(float(item) for item in quat_raw) if quat_raw else (1.0, 0.0, 0.0, 0.0)
    if len(pos) != 3:
        findings.block(
            "scenario_invalid",
            identifier,
            f"pos 必须是 3 元组，实为 {list(pos)}",
            remedy="按米、MuJoCo z-up 右手系给相机/器件位置",
            field_name=f"advanced.sensor_instances[{identifier}].pos",
        )
        return None, (1.0, 0.0, 0.0, 0.0), {}
    if len(quat) != 4:
        findings.block(
            "scenario_invalid",
            identifier,
            f"quat_wxyz 必须是 4 元组（w 在前），实为 {list(quat)}",
            remedy="按 wxyz 顺序给四元数；xyzw 请就地换算，不要在协议里混两种口径",
            field_name=f"advanced.sensor_instances[{identifier}].quat_wxyz",
        )
        return None, (1.0, 0.0, 0.0, 0.0), {}
    return pos, quat, sources  # type: ignore[return-value]


def _record_options(
    request: Any,
    definition: plugin_contract.SensorPluginDefinition,
    config: Mapping[str, Any],
) -> rc.InstanceRecordOptions:
    """记录选项决议：默认只记「策略实际吃的那一路」，避免把每个中间量都写盘。"""

    purpose = str(getattr(request, "purpose", "display") or "display")
    explicit = getattr(request, "record", None)
    record = bool(purpose == "policy") if explicit is None else bool(explicit)
    outputs = list(getattr(request, "record_outputs", None) or [])
    if not outputs and record:
        if definition.policy_output:
            outputs = [definition.policy_output]
        else:
            tensors = [output.name for output in definition.outputs if output.payload_kind == "tensor"]
            outputs = tensors[:1] if len(tensors) == 1 else []
    return rc.InstanceRecordOptions(
        record=record,
        outputs=tuple(dict.fromkeys(outputs)),
        record_png=bool(getattr(request, "record_png", None) or False),
        sample_stride=int(getattr(request, "sample_stride", None) or 1),
    )


def _output_elements(
    definition: plugin_contract.SensorPluginDefinition,
    output_name: str,
    config: Mapping[str, Any],
) -> int | None:
    """一个输出的元素数（动态形状按实例参数解算；解算不出返回 ``None`` = 不计入预算）。"""

    output = next((item for item in definition.outputs if item.name == output_name), None)
    if output is None or output.payload_kind != "tensor":
        return None
    if not output.is_dynamic():
        return output.element_count()
    if definition.plugin_id == "depth" and output_name == "policy_tensor":
        expected = _expected_policy_tensor_shape(config)
        if expected is None or expected == (-1,):
            return None
        return _product(expected)
    return None


def _resolve_bindings(
    policy: _ResolvedPolicy | None,
    instances: Sequence[rc.SensorInstanceSpec],
    findings: _Findings,
) -> tuple[rc.PolicyInputBinding, ...]:
    """把 ONNX **实际输入**逐项对账成观测绑定（A 类吃传感器的实现处）。"""

    if policy is None:
        return ()
    aux = policy.aux_map()
    matched_aux: set[str] = set()
    bindings: list[rc.PolicyInputBinding] = []
    evidence_reader = policy.metadata.reader
    main_taken = False
    for tensor in policy.metadata.inputs:
        declared = aux.get(tensor.name)
        if declared is None:
            if tensor.name in MAIN_OBS_INPUT_NAMES and not main_taken:
                main_taken = True
                try:
                    bindings.append(_state_binding(policy, tensor, evidence_reader))
                except _Unbindable as exc:
                    findings.block(
                        "policy_input_mismatch",
                        policy.policy_id,
                        f"主观测输入 {exc.name} 的元素数 {exc.product} 既不等于 obs_dim"
                        f"={policy.obs_dim} 也不是它的整数倍（本体状态这一路解释不了，"
                        "就不能靠猜把它拼进去）",
                        remedy="核对包声明的 obs_dim 与导出观测宽度是否同源",
                    )
                continue
            if tensor.name in MAIN_OBS_INPUT_NAMES:
                findings.block(
                    "policy_input_mismatch",
                    policy.policy_id,
                    f"产物里出现两个主观测输入（{tensor.name} 已被占用）—— 无法确定哪一路是本体状态",
                    remedy="导出侧只留一路主观测，或在 aux_inputs 里显式声明 produced_by",
                )
                continue
            findings.block(
                "policy_input_mismatch",
                policy.policy_id,
                f"产物输入 {tensor.name} 既不是已声明的主观测，也不在 aux_inputs 里"
                f"（实际输入 {[item.name for item in policy.metadata.inputs]}）：不知道它从哪来就不能绑"
                f"；生效包目录 = {policy.package_root}（workspace 导入的副本可能落后于 "
                "assets/robots/<id>，声明要补在**生效**的那份里）",
                remedy="在生效包的该策略条目里为它写 aux_inputs.produced_by，或修正导出输入名",
                field_name=f"aux_inputs[{tensor.name}]",
            )
            continue
        matched_aux.add(tensor.name)
        produced_by = str(declared.get("produced_by") or "")
        mapping = AUX_PRODUCED_BY_BINDINGS.get(produced_by)
        if mapping is None:
            findings.block(
                "policy_input_mismatch",
                policy.policy_id,
                f"输入 {tensor.name} 的 produced_by={produced_by!r} 不在登记表里"
                f"（已登记 {sorted(AUX_PRODUCED_BY_BINDINGS)}）—— 未登记的来源一律阻断，"
                "当成 external 放行就是把拼接错误藏进默认行为",
                remedy="在 backend/simulation_resolver.AUX_PRODUCED_BY_BINDINGS 里登记并核对语义",
                field_name=f"aux_inputs[{tensor.name}].produced_by",
            )
            continue
        declared_shape = [int(dim) for dim in (declared.get("shape") or [])]
        actual_product = _static_product(tensor.shape)
        declared_product = _product(declared_shape)
        if actual_product > 0 and declared_product > 0 and actual_product != declared_product:
            findings.block(
                "policy_input_mismatch",
                policy.policy_id,
                f"输入 {tensor.name} 声明形状 {declared_shape}（{declared_product} 元素）与产物实测"
                f" {list(tensor.shape)}（{actual_product} 元素）不符",
                remedy="以产物为准更新包声明（或重新导出产物）",
                field_name=f"aux_inputs[{tensor.name}].shape",
            )
            continue
        kind, source = mapping
        if source == "sensor":
            instance = _pick_policy_sensor(kind, instances, findings, policy)
            if instance is None:
                continue
            definition = plugin_contract.plugin_definition(instance.plugin_id)
            expected = _expected_policy_tensor_shape(instance.config)
            if definition is not None and expected is not None:
                # 去掉最前面的批维（实数 1 或符号 -1），剩下的必须逐维等于算式结果
                actual = tuple(
                    dim
                    for index, dim in enumerate(tensor.shape)
                    if not (index == 0 and dim in (1, -1))
                )
                if len(actual) == len(expected):
                    for want, got in zip(expected, actual):
                        if want == -1 or got == -1:
                            break
                        if want != got:
                            findings.block(
                                "policy_input_mismatch",
                                policy.policy_id,
                                f"深度策略张量应为 {list(expected)}（history/height/宽-2×crop），"
                                f"产物实测 {list(actual)} —— 106 与 86 这类裁剪宽度错配正是这样产生的",
                                remedy="核对策略契约 depth_camera 的 raw_width/crop 与产物导出参数",
                                field_name=f"aux_inputs[{tensor.name}]",
                            )
                            break
            bindings.append(
                rc.PolicyInputBinding(
                    name=tensor.name,
                    kind=kind,  # type: ignore[arg-type]
                    tensor_shape=tensor.shape,
                    dtype=tensor.dtype,
                    source="sensor",
                    instance_id=instance.instance_id,
                    output=definition.policy_output if definition else None,
                    sample_period_ticks=instance.sample_period_ticks,
                    verified=True,
                    verified_by="onnx_metadata",
                    evidence=(
                        f"{policy.relative_path}#input {tensor.name}: dtype={tensor.dtype}"
                        f" shape={list(tensor.shape)} read_by={evidence_reader}"
                    ),
                )
            )
            continue
        frames = 1
        if source == "history_buffer":
            if actual_product % policy.obs_dim:
                findings.block(
                    "policy_input_mismatch",
                    policy.policy_id,
                    f"历史输入 {tensor.name} 元素数 {actual_product} 不是 obs_dim={policy.obs_dim} 的整数倍"
                    "（帧数算不出来就说明宽度口径不一致）",
                    remedy="核对 obs_dim 与导出的历史堆叠顺序",
                )
                continue
            frames = max(1, int(actual_product // policy.obs_dim))
        bindings.append(
            rc.PolicyInputBinding(
                name=tensor.name,
                kind=kind,  # type: ignore[arg-type]
                tensor_shape=tensor.shape,
                dtype=tensor.dtype,
                source=source,  # type: ignore[arg-type]
                history_frames=frames,
                transform="stack" if frames > 1 else "none",
                verified=True,
                verified_by="onnx_metadata",
                evidence=(
                    f"{policy.relative_path}#input {tensor.name}: dtype={tensor.dtype}"
                    f" shape={list(tensor.shape)} read_by={evidence_reader}"
                ),
            )
        )
    for name in sorted(set(aux) - matched_aux):
        findings.block(
            "policy_input_mismatch",
            policy.policy_id,
            f"包声明了输入 {name}，但产物实际输入里没有它"
            f"（实测 {[item.name for item in policy.metadata.inputs]}）—— 声明与产物已经分叉",
            remedy="更新包声明或重新导出，使两者一致",
            field_name=f"aux_inputs[{name}]",
        )
    return tuple(bindings)


def _state_binding(
    policy: _ResolvedPolicy, tensor: rc.OnnxTensorMeta, evidence_reader: str
) -> rc.PolicyInputBinding:
    """主观测输入的解释：元素数 == obs_dim → proprio；== obs_dim×N → 帧历史。"""

    product = _static_product(tensor.shape)
    frames = 1
    if product > 0 and product % policy.obs_dim == 0:
        frames = max(1, int(product // policy.obs_dim))
    elif product > 0 and product > policy.obs_dim:
        frames = -1  # 除不尽：交给下面的阻断分支
    if frames == 1 and product == policy.obs_dim:
        return rc.PolicyInputBinding(
            name=tensor.name,
            kind="proprio",
            tensor_shape=tensor.shape,
            dtype=tensor.dtype,
            source="state",
            verified=True,
            verified_by="onnx_metadata",
            evidence=(
                f"{policy.relative_path}#input {tensor.name}: dtype={tensor.dtype}"
                f" shape={list(tensor.shape)} = obs_dim×1 read_by={evidence_reader}"
            ),
        )
    if frames > 1:
        return rc.PolicyInputBinding(
            name=tensor.name,
            kind="history",
            tensor_shape=tensor.shape,
            dtype=tensor.dtype,
            source="history_buffer",
            history_frames=frames,
            transform="stack",
            verified=True,
            verified_by="onnx_metadata",
            evidence=(
                f"{policy.relative_path}#input {tensor.name}: dtype={tensor.dtype}"
                f" shape={list(tensor.shape)} = obs_dim×{frames} read_by={evidence_reader}"
            ),
        )
    raise _Unbindable(tensor.name, product)


class _Unbindable(Exception):
    """主观测宽度无法用 obs_dim 解释（由调用方转成阻断项，不用异常控制常规流程之外的路径）。"""

    def __init__(self, name: str, product: int) -> None:
        super().__init__(name)
        self.name = name
        self.product = product


def _pick_policy_sensor(
    kind: str,
    instances: Sequence[rc.SensorInstanceSpec],
    findings: _Findings,
    policy: _ResolvedPolicy,
) -> rc.SensorInstanceSpec | None:
    """挑「喂给策略的那一路传感器」：按插件类别 + purpose=policy 唯一确定，多义即阻断。"""

    wanted = _KIND_TO_PLUGIN.get(kind)
    if wanted is None:
        findings.block(
            "policy_input_mismatch",
            policy.policy_id,
            f"观测类别 {kind!r} 没有对应的可实例化插件",
            remedy="先在插件契约里登记该类别的来源",
        )
        return None
    candidates = [
        instance for instance in instances if instance.plugin_id == wanted
    ]
    if not candidates:
        findings.block(
            "perception_binding_missing",
            policy.policy_id,
            f"策略实际输入需要 {kind}（插件 {wanted}），但场景没有声明该插件的实例："
            "A 类策略吃传感器，传感器必须由场景声明并决议（词形命中不算，这里要的是实例）",
            remedy="在 scenario.advanced.sensor_instances 里加一个 purpose=policy 的实例",
        )
        return None
    if len(candidates) > 1:
        findings.block(
            "policy_input_mismatch",
            policy.policy_id,
            f"有 {len(candidates)} 个 {wanted} 实例"
            f"（{[item.instance_id for item in candidates]}）而策略输入只有一路 {kind}：绑哪个不可知",
            remedy="只保留一个 purpose=policy 的该类型实例，其余改为 display/evaluation",
        )
        return None
    return candidates[0]


#: 观测类别 → 提供它的插件（唯一映射；新增类别必须在这里登记，否则阻断）
_KIND_TO_PLUGIN: dict[str, str] = {"depth": "depth"}


def _check_perception_binding(
    scenario: ScenarioContract,
    policy: _ResolvedPolicy | None,
    instances: Sequence[rc.SensorInstanceSpec],
    findings: _Findings,
) -> None:
    """复用既有实现做 A 类感知校验，但**只把它当辅助证据**。"""

    from backend.perception_binding import check_perception_binding  # A 类感知校验唯一实现处

    if policy is None:
        return
    verdict = check_perception_binding(
        scenario.perception,
        policy.profile,
        policy_id=policy.policy_id,
        profile_id=policy.profile_id,
    )
    if verdict.get("declaration_source") == "scan":
        findings.warn(
            "策略 profile 的感知声明来自词形扫描（不是 perception_items 显式声明）："
            "它不构成认证，认证依据只有 ONNX 实际输入元数据"
        )
    if not verdict.get("ok", True):
        findings.block(
            "perception_binding_missing",
            policy.policy_id,
            str(verdict.get("reason") or "A 类感知与策略 profile 不匹配")
            + f"；已声明 {verdict.get('declared')}",
            remedy="；".join(str(step) for step in (verdict.get("fix") or [])[:2]),
            field_name="perception",
        )
        return
    # ``perception.depth_camera``（1.1 的显示/请求口径）与已决议实例的关系：**不制造假阻断**。
    # 策略到底需不需要深度，权威依据是产物实际输入（上面已按它绑过），不是场景里写了这个字段。
    declared_camera = getattr(scenario.perception, "depth_camera", None)
    if declared_camera is None:
        return
    depth_instances = [item for item in instances if item.plugin_id == "depth"]
    if not depth_instances:
        findings.warn(
            "场景写了 perception.depth_camera（1.1 口径）但没有深度实例：v2 运行只按 "
            "advanced.sensor_instances 采集，1.1 字段不产生任何采集器"
        )
        return
    for instance in depth_instances:
        for key in ("width", "height"):
            want = getattr(declared_camera, key, None)
            got = instance.config.get(key)
            if want is not None and got is not None and int(want) != int(got):
                findings.warn(
                    f"perception.depth_camera.{key}={want} 与实例 {instance.instance_id}"
                    f" 决议出的 {got} 不一致：显示口径与采集口径各说各话（策略侧只有实例值有效）"
                )


# --------------------------------------------------------------------------------------
# 资产 / 能力 / 记录预算
# --------------------------------------------------------------------------------------


def _resolve_assets(
    package: PackageFacts,
    scenario: ScenarioContract,
    policy: _ResolvedPolicy | None,
    profile_id: str | None,
    findings: _Findings,
    repo_root: Path | None = None,
) -> tuple[rc.AssetRef, ...]:
    """登记**实际必需**的文件（存在 + 摘要）。缺件即阻断，不做「大概齐」。"""

    base = Path(repo_root) if repo_root is not None else robot_packages.ROOT
    assets: list[rc.AssetRef] = []

    def add(kind: str, path: Path, *, robot_id: str | None = None) -> None:
        relative = _repo_relative(path, base)
        if not relative:
            findings.block(
                "path_escape",
                f"{kind}:{path.name}",
                f"资产在仓库之外，无法登记为包内相对路径：{path}",
                remedy="把资产放进机器人包目录",
            )
            return
        digest = _file_digest(path)
        if digest is None:
            findings.block(
                "asset_missing",
                f"{kind}:{relative}",
                f"必需资产读不到：{relative}",
                remedy="恢复该文件或修正包内声明指向真实文件",
            )
            return
        try:
            assets.append(
                rc.AssetRef(
                    kind=kind,  # type: ignore[arg-type]
                    path=relative,
                    sha256=digest,
                    size_bytes=path.stat().st_size,
                    robot_id=robot_id,
                )
            )
        except ValueError as exc:
            findings.block(
                "spec_invalid",
                f"{kind}:{relative}",
                f"资产登记失败：{_error_detail(exc)}",
                remedy="修正路径（必须是仓库相对 posix 路径，不含 .. 与盘符）",
            )

    model_path = package.root / package.model_rel_path()
    if not model_path.is_file():
        findings.block(
            "asset_missing",
            f"{package.robot_id}:model",
            f"机器人模型不存在：{package.model_rel_path()}（相对 {package.root}）",
            remedy="补齐 MJCF，或在 robot_package.json 的 model.path 指向真实文件",
        )
    else:
        add("model_xml", model_path, robot_id=package.robot_id)
    contract_path = package.root / "contract.json"
    if contract_path.is_file():
        add("robot_contract", contract_path, robot_id=package.robot_id)
    if policy is not None:
        add("policy_onnx", policy.onnx_path, robot_id=package.robot_id)
    if profile_id:
        profile_path = package.root / "training" / "profiles" / f"{profile_id}.json"
        if profile_path.is_file():
            add("training_profile", profile_path, robot_id=package.robot_id)
    if str(scenario.map_id or "flat") != "flat":
        scene = base / "assets" / "maps" / f"{scenario.map_id}.xml"
        if scene.is_file():
            add("scene_xml", scene)
        else:
            findings.block(
                "asset_missing",
                f"map:{scenario.map_id}",
                f"场景地图文件不存在：assets/maps/{scenario.map_id}.xml",
                remedy="选择已登记的 map_id，或补齐地图",
                field_name="map_id",
            )
    terrain_scene = (policy.contract if policy else {}).get("scene_path")
    if isinstance(terrain_scene, str) and terrain_scene.strip():
        path = package.root / terrain_scene.strip().lstrip("./").replace("\\", "/")
        if path.is_file():
            add("terrain_heightmap", path, robot_id=package.robot_id)
        else:
            findings.block(
                "asset_missing",
                f"{getattr(policy, 'policy_id', '?')}:scene_path",
                f"策略契约声明的地形场景缺失：{terrain_scene}",
                remedy="补齐场景文件，或修正策略契约的 scene_path",
            )
    return tuple(assets)


def _required_features(plugin_ids: Sequence[str], provider_id: str | None) -> tuple[str, ...]:
    """探测需求表（与 :meth:`rc.ResolvedRunSpec.required_engine_features` 同规则）。

    两处都必须算一遍是有原因的：规格构造**之前**就要问 probe，而那时还没有规格。
    漂移风险由 :meth:`RunResolver._check_features_agree` 在构造后立刻核对（不一致即阻断）。
    """

    wanted = set(rc.PROBE_FEATURES_REQUIRED)
    if provider_id:
        wanted.update({"event_injection", "raycast"})
        wanted.update(plugin_contract.provider_required_capabilities(provider_id))
    for plugin_id in plugin_ids:
        wanted.update(plugin_contract.required_capabilities(plugin_id))
    return tuple(sorted(wanted))


def _check_features_agree(spec: rc.ResolvedRunSpec, features: Sequence[str], findings: _Findings) -> None:
    if tuple(spec.required_engine_features()) != tuple(sorted(set(features))):
        findings.block(
            "spec_invalid",
            spec.spec_digest[:12] or "spec",
            "解析器算出的探测需求与规格算出的不一致（两处实现漂移了）："
            f"resolver={sorted(set(features))} spec={list(spec.required_engine_features())}",
            remedy="修 resolver 的需求表，使其与 ResolvedRunSpec.required_engine_features 一致",
        )


def _probe_capabilities(
    draft: dict[str, Any],
    probe: RunProbe,
    features: Sequence[str],
    plugin_levels: dict[str, str],
    findings: _Findings,
) -> rc.Capabilities | None:
    """消费**注入进来的**探测结果；未探测/缺实现一律阻断，不降级放行。"""

    report = probe(draft)
    if not isinstance(report, rc.NativeProbeReport):
        findings.block(
            "native_probe_missing",
            str(draft.get("robot_id") or "?"),
            f"probe 返回了 {type(report).__name__} 而不是 NativeProbeReport —— "
            "自定义报告类型等于绕过 fail-closed 检查",
            remedy="返回 contracts.simulation_run_contract.NativeProbeReport 实例",
        )
        return None
    if not report.probed:
        findings.block(
            "native_probe_missing",
            str(draft.get("robot_id") or "?"),
            f"原生能力探测未完成（reason={report.reason}）：{report.details or '无更多细节'}。"
            "未探测不等于可运行，解析器不会产出规格",
            remedy="由运行管理器调用 worker 探测后重试（新原生能力有独立版本标识）",
        )
        return None
    missing = [feature for feature in features if not report.is_supported(feature)]
    if missing:
        findings.block(
            "native_feature_unsupported",
            report.executor_id,
            "原生运行时未确认支持："
            + ", ".join(f"{feature}={report.state_of(feature)}" for feature in missing)
            + "（unknown 与 unsupported 同样阻断；mujoco="
            + str(report.mujoco_version)
            + " onnxruntime="
            + str(report.onnxruntime_version)
            + "）",
            remedy="实现该能力后重新探测；不要在生产路径上伪造报告",
        )
        return None
    entries = [
        rc.CapabilityEntry(
            name=feature,
            level="available",
            # 证据里**不带时间戳**：能力快照参与 spec_digest，掺入 probed_at_unix 会让
            # 「同一份决议」每次算出不同摘要，稳定 hash 就没了。
            evidence=(
                f"probe:{report.native_runtime_version}"
                f";mujoco={report.mujoco_version or 'unknown'}"
                f";state={report.state_of(feature)}"
            ),
        )
        for feature in sorted(set(features))
    ]
    for plugin_id, level in sorted(plugin_levels.items()):
        entries.append(
            rc.CapabilityEntry(
                name=f"plugin:{plugin_id}",
                level=level,
                note="级别来自插件声明（解析器不许就地升级）",
            )
        )
    return rc.Capabilities(probed=True, probe=report, entries=tuple(entries))


def _check_recording(
    recording: rc.RecordingOptions,
    instances: Sequence[rc.SensorInstanceSpec],
    time_base: rc.RunTimeBase,
    duration_s: float,
    findings: _Findings,
) -> None:
    """记录预算的**算术**检查：单个样本进不了队列、或整段跑不满时长，都不该等到运行中才发现。"""

    largest_sample = 0
    bytes_per_second = 0.0
    for instance in instances:
        if not instance.record.record:
            continue
        definition = plugin_contract.plugin_definition(instance.plugin_id)
        if definition is None:
            continue
        names = instance.record.outputs or tuple(
            output.name for output in definition.outputs if output.payload_kind == "tensor"
        )
        sample_bytes = 0
        for name in names:
            elements = _output_elements(definition, str(name), instance.config)
            output = next((item for item in definition.outputs if item.name == name), None)
            if elements is None or output is None or output.dtype is None:
                continue
            sample_bytes += elements * DTYPE_ITEMSIZE[output.dtype]
        if not sample_bytes:
            continue
        largest_sample = max(largest_sample, sample_bytes)
        rate = time_base.hz_for_period_ticks(instance.sample_period_ticks)
        bytes_per_second += sample_bytes * rate / max(1, instance.record.sample_stride)
    if largest_sample > recording.queue_budget_bytes:
        findings.block(
            "recording_budget_unsafe",
            "recording.queue_budget_bytes",
            f"单个样本 {largest_sample} 字节 > 队列预算 {recording.queue_budget_bytes}："
            "队列永远装不下一次完整写入，背压会在第一个 tick 卡死",
            remedy="加大 queue_budget_bytes，或降低该实例的分辨率/采样率",
            field_name="recording.queue_budget_bytes",
        )
    projected = bytes_per_second * float(duration_s)
    if projected > recording.per_run_budget_bytes:
        findings.block(
            "recording_budget_unsafe",
            "recording.per_run_budget_bytes",
            f"预计写入 {int(projected)} 字节 > 单运行预算 "
            f"{recording.per_run_budget_bytes}（{bytes_per_second / 1048576:.2f} MiB/s × "
            f"{duration_s:.1f}s）。默认策略是不自动删除，所以只会中途停住",
            remedy="缩短 duration、降低记录分辨率，或显式提高 per_run_budget_bytes",
            field_name="recording.per_run_budget_bytes",
        )
    if bytes_per_second:
        findings.warn(
            f"记录速率估计 {bytes_per_second / 1048576:.2f} MiB/s（只计已启用记录的实例）"
        )


# --------------------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------------------


class RunResolver:
    """把一次 resolve 请求决议成 :class:`contracts.simulation_run_contract.ResolveResponse`。

    两个可注入边界（都是**明确类型**，不是随手传的回调）：

    * :data:`RunProbe` —— 原生能力探测。默认 :func:`unavailable_native_probe` 如实回答
      「没探过」，于是产出阻断项而不是放行；运行管理器接管后传入 worker 探测实现。
    * :data:`PolicyMetadataReader` —— 策略产物元数据读取。默认
      :func:`read_onnx_artifact_metadata`（真读文件）。测试里换成假实现时，
      假的也只是「文件内容」，不是「认证结论」：``verified_by`` 恒为 ``onnx_metadata``。
    """

    def __init__(
        self,
        *,
        probe: RunProbe | None = None,
        metadata_reader: PolicyMetadataReader | None = None,
        package_root: Path | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self._probe: RunProbe = probe if probe is not None else unavailable_native_probe
        self._read_metadata: PolicyMetadataReader = (
            metadata_reader if metadata_reader is not None else read_onnx_artifact_metadata
        )
        #: 生效包根 / 仓库根：**默认沿用既有解析工具**，只在测试与可移植安装里覆盖。
        self._package_root = Path(package_root) if package_root is not None else None
        self._repo_root = Path(repo_root) if repo_root is not None else None

    # ---- 失败/成功出口 ------------------------------------------------------

    @staticmethod
    def _failure(
        findings: _Findings, capabilities: rc.Capabilities | None = None
    ) -> rc.ResolveResponse:
        """失败出口：**永远不给半份规格**。"""

        return rc.ResolveResponse(
            ok=False,
            spec=None,
            spec_digest=None,
            blockers=tuple(findings.blockers),
            warnings=tuple(findings.warnings),
            capabilities=capabilities,
            protocol=protocol_limits(),
        )

    @staticmethod
    def _success(spec: rc.ResolvedRunSpec, findings: _Findings) -> rc.ResolveResponse:
        return rc.ResolveResponse(
            ok=True,
            spec=spec,
            spec_digest=spec.spec_digest,
            blockers=(),
            warnings=tuple(findings.warnings),
            capabilities=spec.capabilities,
            protocol=protocol_limits(),
        )

    # ---- 主入口 -------------------------------------------------------------

    def resolve(self, request: rc.ResolveRequest | Mapping[str, Any]) -> rc.ResolveResponse:
        """执行一次决议（无副作用：不写盘、不起进程、不改任何资产）。"""

        findings = _Findings()

        try:
            req = (
                request
                if isinstance(request, rc.ResolveRequest)
                else rc.ResolveRequest.model_validate(request)
            )
        except ValueError as exc:
            findings.block(
                "scenario_invalid",
                "resolve_request",
                f"resolve 请求本身不合法：{_error_detail(exc)}",
                remedy="按 contracts.simulation_run_contract.ResolveRequest 的形状重发",
            )
            return self._failure(findings)

        options = req.options
        robot_id = str(options.robot_id or "").strip()
        if not robot_id:
            findings.block(
                "unknown_robot",
                "<未指定>",
                "resolve 请求没有 robot_id：v2 运行不接受内置默认机器人（那会让包边界变得含糊）",
                remedy="在 options.robot_id 填机器人包的 package_id",
                field_name="options.robot_id",
            )
            return self._failure(findings)

        package = _load_package(robot_id, findings, self._package_root)
        if package is None:
            return self._failure(findings)

        time_base = _time_base(package, findings)
        if time_base is None:
            return self._failure(findings)

        try:
            scenario = ScenarioContract.model_validate(req.scenario)
        except ValueError as exc:
            findings.block(
                "scenario_invalid",
                str(req.scenario.get("scenario_id") if isinstance(req.scenario, Mapping) else "?")
                or "?",
                f"场景契约不通过：{_error_detail(exc)}",
                remedy="按 contracts/scenario_contract.py 的形状修正场景（1.2 高级字段需显式写 schema_version）",
            )
            return self._failure(findings)

        expected_hz = scenario.advanced.expect_control_hz if scenario.advanced is not None else None
        if expected_hz is not None and expected_hz != time_base.control_hz:
            findings.block(
                "scenario_invalid",
                scenario.scenario_id,
                f"场景期望控制率 {expected_hz:g} Hz，但机器人契约为 {time_base.control_hz:g} Hz；"
                "期望值只用于核对，不能覆盖 contract 时间基",
                remedy="核对所选机器人包，或修正 advanced.expect_control_hz",
                field_name="advanced.expect_control_hz",
            )
            return self._failure(findings)

        policy_id = str(options.policy_id or "").strip() or None
        policy = (
            _resolve_policy(package, policy_id, findings, self._read_metadata, self._repo_root)
            if policy_id
            else None
        )
        if policy_id and policy is None:
            return self._failure(findings)

        instances, mount_authority = _resolve_instances(
            package, scenario.advanced, time_base, policy, findings
        )
        bindings = _resolve_bindings(policy, instances, findings)
        _check_perception_binding(scenario, policy, instances, findings)
        if findings.failed:
            return self._failure(findings)

        events, event_note = self._resolve_events(scenario, findings)
        provider = self._resolve_provider(scenario, instances, findings)
        assets = _resolve_assets(
            package,
            scenario,
            policy,
            policy.profile_id if policy else None,
            findings,
            self._repo_root,
        )
        recording = self._resolve_recording(options, scenario, findings)
        if findings.failed:
            return self._failure(findings)

        seed, seed_source = self._pick(options.seed, scenario.seed, "resolve_options.seed", "scenario.seed", findings)
        duration, duration_source = self._pick(
            options.duration_s,
            getattr(scenario, "episode_length_s", None),
            "resolve_options.duration_s",
            "scenario.episode_length_s",
            findings,
        )
        if duration is None or float(duration) <= 0.0:
            findings.block(
                "scenario_invalid",
                scenario.scenario_id,
                "既没有 options.duration_s 也没有 scenario.episode_length_s：运行时长无权威来源，"
                "而记录预算、事件时刻、收尾 tick 全都依赖它",
                remedy="在场景里写 episode_length_s，或在 resolve 请求里写 duration_s",
                field_name="options.duration_s",
            )
            duration = 0.0
        else:
            duration = float(duration)
        seed = int(seed) if seed is not None else 0

        plugin_levels = self._plugin_levels(instances)
        features = _required_features([item.plugin_id for item in instances], provider.provider_id if provider else None)
        if not options.require_probe:
            # ``require_probe=False`` 的语义在 :class:`contracts.simulation_run_contract.ResolveOptions`
            # 里已经写死：只做声明层校验，**同样不产出规格**（规格在类型层就要求已完成的探测
            # 报告）。这里把它落实成"连 worker 都不问"，否则这个开关是个假承诺。
            findings.block(
                "native_probe_missing",
                package.robot_id,
                "options.require_probe=False：本次只核对声明，未调用 worker 探测，因此没有能力报告；"
                "无报告不会降级放行，而是与「未探测」同样阻断（规格构造不出来）",
                remedy="要创建运行请去掉 require_probe=False（或置 True）以触发真实探测",
                field_name="options.require_probe",
            )
            return self._failure(findings)
        draft: dict[str, Any] = {
            "robot_id": package.robot_id,
            "package_root": str(package.root),
            "policy_id": policy_id,
            # 探测端复用解析器**已解析**的产物绝对路径，不必再解析一遍清单（DRY）；
            # 未选策略时为 None，探测据此把 onnx_inference 如实标为 unsupported。
            "model_path": str(package.root / package.model_rel_path()),
            "policy_onnx_path": str(policy.onnx_path) if policy else None,
            "time_base": time_base.as_dict(),
            "plugin_ids": sorted({item.plugin_id for item in instances}),
            "provider_id": provider.provider_id if provider else None,
            "required_features": list(features),
            "duration_s": duration,
            "resolver_version": RESOLVER_VERSION,
            "run_contract_version": rc.RUN_CONTRACT_VERSION,
        }
        capabilities = _probe_capabilities(draft, self._probe, features, plugin_levels, findings)
        if capabilities is None:
            return self._failure(findings)
        if findings.failed:
            return self._failure(findings)

        if recording is not None:
            _check_recording(recording, instances, time_base, duration, findings)
        if findings.failed:
            return self._failure(findings)

        provenance = self._provenance(
            package=package,
            time_base=time_base,
            scenario=scenario,
            policy=policy,
            instances=instances,
            assets=assets,
            mount_authority=mount_authority,
            bindings=bindings,
            provider=provider,
            recording=recording,
            capabilities=capabilities,
            features=features,
            seed_source=seed_source,
            duration_source=duration_source,
            seed=seed,
            duration=duration,
            event_count=len(events),
        )
        values: dict[str, Any] = {
            "robot_id": package.robot_id,
            "policy_id": policy_id,
            "scenario_id": scenario.scenario_id,
            "scenario_schema_version": scenario.schema_version,
            "scenario_digest": canonical_sha256(scenario.to_payload()),
            "time_base": time_base,
            "duration_s": duration,
            "seed": seed,
            "assets": assets,
            "sensor_instances": instances,
            "policy_artifact": self._policy_artifact_ref(policy),
            "policy_inputs": bindings,
            "command_provider": provider,
            "recording": recording or rc.RecordingOptions(),
            "units": rc.Units(),
            "capabilities": capabilities,
            "provenance": provenance,
            "notes": self._notes(scenario, policy, events, event_note),
        }
        try:
            spec = rc.ResolvedRunSpec.with_digest(**values)
        except ValueError as exc:
            findings.block(
                "spec_invalid",
                scenario.scenario_id,
                f"运行规格构造失败（决议内部不自洽）：{_error_detail(exc)}",
                remedy="按报错回到对应声明处修正；解析器不会绕过校验产出一份退化的规格",
            )
            return self._failure(findings)
        _check_features_agree(spec, features, findings)
        if findings.failed:
            return self._failure(findings)
        return self._success(spec, findings)

    # ---- 子步骤 -------------------------------------------------------------

    @staticmethod
    def _pick(
        override: Any,
        declared: Any,
        override_source: str,
        declared_source: str,
        findings: _Findings,
    ) -> tuple[Any, str]:
        """请求级覆盖 **优先于** 场景声明；两者同时给出且不同 → 告警（不静默投票）。"""

        if override is not None and declared is not None:
            if override != declared:
                findings.warn(
                    f"{override_source}={override} 覆盖了 {declared_source}={declared}"
                    "（两处都写了同一件事，以请求为准；请删掉其中一处以免误读）"
                )
            return override, override_source
        if override is not None:
            return override, override_source
        if declared is not None:
            return declared, declared_source
        return None, ""

    def _resolve_events(
        self, scenario: ScenarioContract, findings: _Findings
    ) -> tuple[tuple[rc.ScheduledEvent, ...], str]:
        """把场景里的排程事件**验证成合法形状**（规格不含事件，见下面的说明）。

        刻意不把事件塞进 :class:`ResolvedRunSpec`：它是「运行能不能跑」的决议，而事件是
        运行期的输入；把两者混进一份摘要会让「改一个事件时刻」变成「重新解析整个运行」。
        因此这里只做类型/边界校验，并由调用方在运行创建后经
        ``POST /api/simulation/v2/runs/{run_id}/events`` 按序投递。
        """

        advanced = getattr(scenario, "advanced", None)
        requests = list(getattr(advanced, "events", None) or [])
        events: list[rc.ScheduledEvent] = []
        for item in requests:
            try:
                events.append(item.to_scheduled_event(expected_epoch=0))
            except ValueError as exc:
                findings.block(
                    "scenario_invalid",
                    str(getattr(item, "event_id", "?") or "?"),
                    f"排程事件不合法：{_error_detail(exc)}",
                    remedy="按 contracts.simulation_run_contract.ScheduledEvent 的口径修正",
                    field_name=f"advanced.events[{getattr(item, 'event_id', '?')}]",
                )
        note = f"场景声明事件 {len(events)} 条，由 /events 端点在运行创建后投递"
        return tuple(events), note

    def _resolve_provider(
        self,
        scenario: ScenarioContract,
        instances: Sequence[rc.SensorInstanceSpec],
        findings: _Findings,
    ) -> rc.CommandProviderSpec | None:
        """外置决策器（B 类：LiDAR 只改指令）的决议：默认值/出处一律委托插件契约。"""

        advanced = getattr(scenario, "advanced", None)
        request = getattr(advanced, "command_provider", None)
        if request is None:
            return None
        provider_id = str(getattr(request, "provider_id", "") or "")
        if plugin_contract.command_provider_definition(provider_id) is None:
            findings.block(
                "unknown_provider",
                provider_id or "<未指定>",
                f"命令提供器 {provider_id!r} 未登记"
                f"（已登记 {list(plugin_contract.command_provider_ids())}）",
                remedy="先在 contracts/sensor_plugin_contract.py 声明它，再在场景里引用",
                field_name="advanced.command_provider.provider_id",
            )
            return None
        known = {item.instance_id for item in instances}
        wanted = tuple(str(item) for item in (getattr(request, "input_instance_ids", None) or []))
        unknown = sorted(set(wanted) - known)
        if unknown:
            findings.block(
                "scenario_invalid",
                provider_id,
                f"命令提供器输入实例 {unknown} 不在已决议实例里（已决议 {sorted(known)}）："
                "外挂决策器只能看见真实存在的传感器",
                remedy="先在 advanced.sensor_instances 声明该实例，或从输入清单里删掉它",
                field_name="advanced.command_provider.input_instance_ids",
            )
            return None
        try:
            return rc.command_provider_spec_from(
                provider_id,
                input_instances=wanted,
                overrides=dict(getattr(request, "config", None) or {}),
                source=str(getattr(request, "source", "scenario") or "scenario"),
            )
        except ValueError as exc:
            findings.block(
                "scenario_invalid",
                provider_id,
                f"命令提供器参数解析失败：{_error_detail(exc)}",
                remedy="按该提供器声明的参数集修正（未知参数名会被直接拒绝）",
                field_name="advanced.command_provider.config",
            )
            return None

    @staticmethod
    def _resolve_recording(
        options: rc.ResolveOptions, scenario: ScenarioContract, findings: _Findings
    ) -> rc.RecordingOptions:
        """记录选项：请求 > 场景 > 契约默认（预算默认值只有 :class:`RecordingOptions` 一份）。"""

        declared = getattr(getattr(scenario, "advanced", None), "recording", None)
        chosen = options.recording if options.recording is not None else declared
        if options.recording is not None and declared is not None and options.recording != declared:
            findings.warn(
                "options.recording 与 advanced.recording 同时给出且不同：以 options 为准"
                "（预算属于本次请求的意图，不写回场景）"
            )
        return chosen or rc.RecordingOptions()

    @staticmethod
    def _plugin_levels(
        instances: Sequence[rc.SensorInstanceSpec],
    ) -> dict[str, str]:
        """能力级别**只从声明抄**（无采集器的插件永远是 registered，解析器无权升级）。"""

        levels: dict[str, str] = {}
        for instance in instances:
            definition = plugin_contract.plugin_definition(instance.plugin_id)
            if definition is not None:
                levels[instance.plugin_id] = definition.capability_level
        return levels

    @staticmethod
    def _policy_artifact_ref(
        policy: _ResolvedPolicy | None,
    ) -> rc.PolicyArtifactRef | None:
        if policy is None:
            return None
        return rc.PolicyArtifactRef(
            relative_path=policy.relative_path,
            sha256=policy.sha256,
            metadata_source="onnx_file",
            metadata_verified=True,
            inputs=policy.metadata.inputs,
            outputs=policy.metadata.outputs,
        )

    @staticmethod
    def _notes(
        scenario: ScenarioContract,
        policy: _ResolvedPolicy | None,
        events: Sequence[rc.ScheduledEvent],
        event_note: str,
    ) -> tuple[str, ...]:
        """规格备注：**必须逐项可复算**（备注参与摘要，所以这里不放时间戳、不放告警）。"""

        notes = [
            f"resolver={RESOLVER_VERSION}",
            f"scenario={scenario.scenario_id}@{scenario.schema_version}",
            f"events={len(events)}",
        ]
        if policy is not None:
            notes.append(f"profile={policy.profile_id or 'none'}")
            notes.append(f"obs_dim={policy.obs_dim}")
        if event_note:
            notes.append("events_via=POST /runs/{run_id}/events")
        return tuple(notes)

    @staticmethod
    def _provenance(
        *,
        package: PackageFacts,
        time_base: rc.RunTimeBase,
        scenario: ScenarioContract,
        policy: _ResolvedPolicy | None,
        instances: Sequence[rc.SensorInstanceSpec],
        assets: Sequence[rc.AssetRef],
        mount_authority: Sequence[tuple[str, str]],
        bindings: Sequence[rc.PolicyInputBinding],
        provider: rc.CommandProviderSpec | None,
        recording: rc.RecordingOptions | None,
        capabilities: rc.Capabilities,
        features: Sequence[str],
        seed_source: str,
        duration_source: str,
        seed: int,
        duration: float,
        event_count: int,
    ) -> tuple[rc.ParamProvenance, ...]:
        """规格级出处清单：12 个类别一个不缺（契约把住），每项都说得出**具体**来源。"""

        report = capabilities.probe
        entries: list[rc.ParamProvenance] = [
            rc.ParamProvenance(
                name="robot_id",
                category="robot_id",
                source="resolve_options.robot_id",
                value=package.robot_id,
                detail=f"包根 {package.root.name}",
            ),
            rc.ParamProvenance(
                name="policy_id",
                category="policy_id",
                source="resolve_options.policy_id"
                if policy is not None
                else "resolve_options.policy_id 未提供（本次运行无策略闭环）",
                value=policy.policy_id if policy else None,
            ),
            rc.ParamProvenance(
                name="time_base",
                category="time_base",
                source=f"{package.robot_id}:contract.json#control",
                value=time_base.as_dict(),
                detail="physics_hz/decimation 只来自契约；legacy_config 会被直接阻断",
            ),
            rc.ParamProvenance(
                name="seed", category="seed", source=seed_source or "unspecified_default_0", value=seed
            ),
            rc.ParamProvenance(
                name="duration_s",
                category="duration",
                source=duration_source or "unspecified",
                value=duration,
            ),
            rc.ParamProvenance(
                name="assets",
                category="assets",
                source="resolver:normalized_sha256(文件字节)",
                value=[f"{asset.kind}:{asset.path}" for asset in assets],
                detail="创建运行时必须用 verify_assets() 重算，发现 resolve 之后的资产变化",
            ),
            rc.ParamProvenance(
                name="sensor_instances",
                category="sensor_instances",
                source="scenario.advanced.sensor_instances + contracts/sensor_plugin_contract.py 声明",
                value=[item.instance_id for item in instances],
                detail="每个参数的出处在实例自己的 config_provenance 里（一一对应）",
            ),
            rc.ParamProvenance(
                name="policy_inputs",
                category="policy_inputs",
                source=f"onnx_file:{policy.relative_path}" if policy else "none（无策略）",
                value=[item.name for item in bindings],
                detail="verified_by 只有 onnx_metadata 一种：词形命中不算认证",
            ),
            rc.ParamProvenance(
                name="command_provider",
                category="command_provider",
                source="scenario.advanced.command_provider"
                if provider is not None
                else "scenario.advanced.command_provider 未声明（本次运行不启用外挂决策器）",
                value=provider.provider_id if provider else None,
            ),
            rc.ParamProvenance(
                name="recording",
                category="recording",
                source="resolve_options.recording"
                if recording is not None
                else "contracts.simulation_run_contract.RecordingOptions 默认预算",
                value=recording.budget_dict() if recording else None,
                detail="auto_delete=False：预算不足时停下并报状态，不悄悄删数据",
            ),
            rc.ParamProvenance(
                name="scenario",
                category="scenario",
                source=f"scenario:{scenario.scenario_id}@{scenario.schema_version}",
                detail=f"排程事件 {event_count} 条（不进摘要，经 /events 投递）",
            ),
            rc.ParamProvenance(
                name="runtime",
                category="runtime",
                source=f"resolver:{RESOLVER_VERSION};probe:{report.native_runtime_version if report else 'none'}",
                value=list(features),
                detail="探测报告原文见 capabilities.probe（含 mujoco/onnxruntime 版本）",
            ),
        ]
        for name, source in mount_authority:
            entries.append(
                rc.ParamProvenance(name=name, category="sensor_instances", source=source)
            )
        return tuple(entries)


# --------------------------------------------------------------------------------------
# 模块级入口（路由/运行管理器唯一该用的东西）
# --------------------------------------------------------------------------------------


def resolve_run(
    request: rc.ResolveRequest | Mapping[str, Any],
    *,
    probe: RunProbe | None = None,
    metadata_reader: PolicyMetadataReader | None = None,
    package_root: Path | None = None,
    repo_root: Path | None = None,
) -> rc.ResolveResponse:
    """一次性决议（无状态调用；重复调用同一请求应得到同一摘要，见 ``verify_assets``）。"""

    return RunResolver(
        probe=probe,
        metadata_reader=metadata_reader,
        package_root=package_root,
        repo_root=repo_root,
    ).resolve(request)


def verify_assets(
    spec: rc.ResolvedRunSpec, *, root: Path | None = None
) -> tuple[rc.ResolutionBlocker, ...]:
    """**重算**规格里每个资产的摘要（防 resolve 之后资产被改动）。

    运行管理器在 ``POST /runs`` 里必须调用它：只信客户端传来的 ``spec_digest``
    等于相信客户端不会指着一个被换掉的模型说「这是同一份决议」。
    """

    base = Path(root) if root is not None else robot_packages.ROOT
    blockers: list[rc.ResolutionBlocker] = []
    if not spec.digest_matches():
        blockers.append(
            rc.ResolutionBlocker(
                code="spec_invalid",
                subject=spec.spec_digest[:12] or "<无摘要>",
                detail="spec_digest 与按内容重算的结果不符（规格被改过，或不是经 with_digest 构造的）",
                remedy="丢弃这份规格，重新 resolve",
            )
        )
    seen: set[str] = set()
    for asset in spec.assets:
        key = f"{asset.kind}:{asset.path}"
        if key in seen:
            blockers.append(
                rc.ResolutionBlocker(
                    code="spec_invalid",
                    subject=key,
                    detail="资产在同一份规格里登记了两次",
                    remedy="去重（一个 kind 指向一个文件）",
                )
            )
            continue
        seen.add(key)
        path = base / asset.path
        if not path.is_file():
            blockers.append(
                rc.ResolutionBlocker(
                    code="asset_missing",
                    subject=key,
                    detail=f"resolve 时存在的资产现在没了：{asset.path}",
                    remedy="恢复文件，或重新 resolve 以绑定当前资产集",
                )
            )
            continue
        digest = _file_digest(path)
        if digest != asset.sha256:
            blockers.append(
                rc.ResolutionBlocker(
                    code="asset_digest_mismatch",
                    subject=key,
                    detail=f"资产字节变了：登记 {asset.sha256}，实测 {digest or '<读不出>'}",
                    remedy="重新 resolve 获取新规格；不要用旧摘要创建运行",
                )
            )
    return tuple(blockers)


def run_catalog(
    probe_report: rc.NativeProbeReport | None = None,
) -> rc.RunCatalogResponse:
    """``GET /api/simulation/v2/catalog`` 的响应体（**所有枚举/默认值的唯一出口**）。

    插件与命令提供器的清单直接来自 :mod:`contracts.sensor_plugin_contract`；
    这里不复制任何参数默认值，浏览器因此没有第二套可漂移的 catalog。
    """

    return rc.RunCatalogResponse(
        executors=(rc.ExecutorInfo(),),
        sensor_plugins=plugin_contract.plugin_catalog_payload(),
        protocol=protocol_limits(),
        stream=rc.ws_stream_contract(),
        units=rc.Units().as_dict(),
        recording_defaults=rc.RecordingOptions().budget_dict(),
        probe=probe_report,
    )
