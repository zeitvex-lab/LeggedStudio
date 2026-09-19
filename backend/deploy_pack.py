"""部署包生成器（T3.3，批次 3 / M4）。

"一键生成 ≠ 一键上机"：本模块只生成部署物料，不直接发电机命令。
四件套（报告 10 §⑤ / 报告 2 §4 rl_sar 双层契约 + microduck publish 门）：

  1. deployment-contract.yaml —— 关节映射/控制频率/PD/armature/限位（JSON 是合法
     YAML 子集；注释指向真值源 contract.json）
  2. fsm_safety_template.py —— PASSIVE→STAND→POLICY→RECOVER→ESTOP 安全状态机
     （安全链路独立于策略；急停最高优先；wheel 角色走速度指令）
  3. action_decoder_template.py —— 策略槽序 × reindex_from_model → 真实电机命令
     （position/torque/velocity 三模式；含单关节正弦波验证项——"训练关节序 ≠
     SDK 电机序"是最高频部署 bug，报告 2 §3）
  4. 人工确认清单.md —— 增益先降 50% / 急停最高优先 / 零点初始化 / 软限位一致

数据全部来自契约真值（DENYLIST gate 已在导出侧把关一致性）。
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.jsonio import read_json  # JSON 读取唯一实现

ROOT = Path(__file__).resolve().parents[1]

GENERATED_HEADER = "# 本文件由 Legged Studio 部署包生成器产出（{ts}）；真值源：contract.json\n"


def _load_json(path: Path) -> dict | None:
    """读一份 JSON 对象；缺失 / 坏内容 / 非对象一律 ``None``（实现见 ``backend.jsonio``）。"""

    return read_json(path, default=None, require=dict)

# 包定位已收口到 ``backend.package_locator``（本模块按名 re-export，保持既有 import 可用）：
# 部署域曾与仿真域各实现一遍"包根从哪来"，规则还不同（``zex_w`` 在仿真域 200、在这里 404）。
# 本域只保留**域特有前置**（契约真值存在 / 策略文件存在），定位规则不再各说各话。
from backend.package_locator import RobotPackageNotFound, resolve_package_root  # noqa: E402


def deployment_contract_yaml(contract_truth: dict) -> str:
    """JSON 是合法 YAML 子集——机器可读、人可读、无 PyYAML 依赖。"""

    payload = {
        "schema_version": "deployment-contract-1.0",
        "generated_by": "legged-studio deploy packager",
        "robot_id": contract_truth.get("robot_id"),
        "control": contract_truth.get("control") or {},
        "action": {
            "joint_order": contract_truth.get("action", {}).get("joint_order"),
            "reindex_from_model": contract_truth.get("action", {}).get("reindex_from_model"),
            "action_scale": contract_truth.get("action", {}).get("action_scale"),
        },
        "actuator_profile": contract_truth.get("actuator_profile") or {},
        "default_pose": (contract_truth.get("joints") or {}).get("default_pose"),
        "notes": "关节映射/控制频率/PD/armature 全部来自契约真值（rl_sar base.yaml 语义）——修改请回训练区，不要手改本文件",
    }
    header = (
        "# deployment contract（rl_sar 双层 YAML 契约语义）\n"
        + GENERATED_HEADER.format(ts=datetime.now().isoformat(timespec="seconds"))
        + "# JSON 是合法 YAML 子集；与 deployment_contract.json 内容一致\n"
    )
    return header + json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def deployment_contract_json(contract_truth: dict) -> str:
    payload = {
        "schema_version": "deployment-contract-1.0",
        "generated_by": "legged-studio deploy packager",
        "robot_id": contract_truth.get("robot_id"),
        "control": contract_truth.get("control") or {},
        "action": contract_truth.get("action") or {},
        "actuator_profile": contract_truth.get("actuator_profile") or {},
        "default_pose": (contract_truth.get("joints") or {}).get("default_pose"),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


FSM_TEMPLATE = '''"""通用安全状态机模板（Legged Studio 生成）。

PASSIVE → STAND → POLICY → RECOVER → ESTOP
安全链路独立于策略：action clip ≠ 急停；急停为最高优先级。
wheel 角色关节在 STAND/POLICY 中使用速度指令（mode 来自 deployment contract）。

接入点（机器人特化处，参考 rl_sar fsm 分层）：
  - read_remote_stop() / read_keyboard_stop()：接目标平台的急停信号
  - read_imu()/read_joint_states()：接 SDK 状态
  - send_motor_commands(...)：接 SDK 电机接口（Unitree SDK2 / ROS2 / 其他）
  - STANDUP_POSE 可按机器人默认站姿覆盖
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Optional

import deployment_contract as dc


class State(Enum):
    PASSIVE = "PASSIVE"
    STAND = "STAND"
    POLICY = "POLICY"
    RECOVER = "RECOVER"
    ESTOP = "ESTOP"


STANDUP_POSE = list(dc.CONTRACT.get("default_pose") or [])


class RobotSafetyFSM:
    def __init__(self, command_timeout_s: float = 0.5) -> None:
        self.state = State.PASSIVE
        self.command_timeout_s = command_timeout_s
        self.last_command_ts: Optional[float] = None

    # ---- 安全输入（接入点） ----
    def estop_requested(self) -> bool:
        """急停：遥控/键盘/看门狗任一触发即真。永远最高优先。"""
        return False

    def policy_alive(self) -> bool:
        """命令超时看门狗：策略推理超时即假。"""
        if self.last_command_ts is None:
            return False
        return (time.monotonic() - self.last_command_ts) <= self.command_timeout_s

    # ---- 主循环 ----
    def tick(self, policy_action=None):
        """每控制周期调用一次；返回电机命令或 None（被动阻尼）。"""
        if self.estop_requested():
            self.state = State.ESTOP
            return self._estop_commands()

        if self.state == State.ESTOP:
            return self._estop_commands()

        if self.state == State.PASSIVE:
            if self._posture_safe_for_standup():
                self.state = State.STAND
            return self._damping_commands()

        if self.state == State.STAND:
            if not self._posture_safe():
                self.state = State.RECOVER
                return self._damping_commands()
            if policy_action is not None and self.policy_alive():
                self.state = State.POLICY
                self.last_command_ts = time.monotonic()
                return self._policy_commands(policy_action)
            return self._stand_commands()

        if self.state == State.POLICY:
            if not self._posture_safe():
                self.state = State.RECOVER
                return self._damping_commands()
            if policy_action is None or not self.policy_alive():
                self.state = State.STAND
                return self._stand_commands()
            self.last_command_ts = time.monotonic()
            return self._policy_commands(policy_action)

        if self.state == State.RECOVER:
            if self._posture_safe():
                self.state = State.PASSIVE
            return self._damping_commands()

        return self._damping_commands()

    # ---- 保护与输出（按 deployment contract 生成增益/限幅） ----
    def _posture_safe_for_standup(self) -> bool:
        return True  # TODO：接姿态检查（sdk_deploy 官方曾注释 PostureUnsafeCheck——实机必须重新启用）

    def _posture_safe(self) -> bool:
        return True  # TODO：俯仰/横滚越限即返回 False

    def _damping_commands(self):
        return {"mode": "damping"}

    def _estop_commands(self):
        return {"mode": "estop"}

    def _stand_commands(self):
        return {"mode": "position", "target": list(STANDUP_POSE)}

    def _policy_commands(self, action):
        return {"mode": "policy", "action": list(action)}
'''


def fsm_template(contract_truth: dict) -> str:
    header = GENERATED_HEADER.format(ts=datetime.now().isoformat(timespec="seconds"))
    return header + FSM_TEMPLATE


DECODER_TEMPLATE = '''"""动作解码层模板（Legged Studio 生成）。

策略 12/16/29 维关节动作 → 真实 SDK 电机命令：
  motor_cmd = decode(policy_output, obs_stamp)
  - reindex_from_model：模型序 → 契约槽序（训练关节序 ≠ SDK 电机序是最高频 bug）
  - action_scale / default_pose：动作语义还原（q_target = default + scale * action）
  - mode: position → PD；torque → 力矩限幅；velocity（wheel）→ 速度指令
上线前先跑 single_joint_sine_test()：逐关节正弦波核对电机序与方向。
"""

from __future__ import annotations

import math
import deployment_contract as dc


def _expand_params() -> dict:
    """default < by_role < by_joint 三级合并（与控制面 role_resolver 同规则）。"""
    profile = dc.CONTRACT.get("actuator_profile") or {}
    default = profile.get("default") or {}
    by_role = profile.get("by_role") or {}
    by_joint = profile.get("by_joint") or {}
    roles = {}
    for entry in dc.CONTRACT.get("joints_actuated", []):
        roles[entry["name"]] = entry["role"]
    merged = {}
    for name, role in roles.items():
        params = dict(default)
        params.update(by_role.get(role) or {})
        params.update(by_joint.get(name) or {})
        merged[name] = params
    return merged


CONTRACT = dc.CONTRACT
JOINT_ORDER = list(CONTRACT["action"]["joint_order"])
REINDEX = CONTRACT["action"].get("reindex_from_model")
ACTION_SCALE = float(CONTRACT["action"].get("action_scale") or 0.25)
DEFAULT_POSE = list(CONTRACT.get("default_pose") or [0.0] * len(JOINT_ORDER))
PARAMS = _expand_params()


def decode(policy_output):
    """策略输出（模型序）→ {joint_name: 命令}（契约序，含模式与限幅）。"""
    actions = list(policy_output)
    if REINDEX is not None:
        # 模型序 → 契约序：contract_slot[i] = model[reindex[i]]
        if sorted(REINDEX) != list(range(len(JOINT_ORDER))):
            raise ValueError("reindex_from_model 不是合法置换——检查部署契约")
        if len(actions) != len(REINDEX):
            raise ValueError(f"策略输出维度 {len(actions)} != 模型序维度 {len(REINDEX)}")
        actions = [actions[i] for i in REINDEX]
    if len(actions) != len(JOINT_ORDER):
        raise ValueError(f"策略输出维度 {len(actions)} != joint_order {len(JOINT_ORDER)}")

    commands = {}
    for name, delta in zip(JOINT_ORDER, actions):
        params = PARAMS.get(name) or {}
        mode = str(params.get("mode") or "position")
        effort = float(params.get("effort") or 40.0)
        q_target = DEFAULT_POSE[JOINT_ORDER.index(name)] + ACTION_SCALE * float(delta) if mode != "velocity" else float(delta)
        commands[name] = {"mode": mode, "target": q_target, "effort_limit": effort,
                          "kp": params.get("stiffness"), "kd": params.get("damping")}
    return commands


def single_joint_sine_test(duration_s: float = 3.0, freq_hz: float = 1.0, send=None):
    """上线前自检：逐关节正弦波，肉眼/日志核对每个电机只动该动的那一个。

    send(joint_name, target) 由目标平台适配层提供（None 时仅打印）。
    """
    for name in JOINT_ORDER:
        steps = int(duration_s * float(CONTRACT["control"]["control_hz"]))
        for k in range(steps):
            target = DEFAULT_POSE[JOINT_ORDER.index(name)] + 0.2 * math.sin(2 * math.pi * freq_hz * k / steps)
            if send is None:
                print(f"[sine] {name} -> {target:.3f}")
            else:
                send(name, target)
'''


def decoder_template(contract_truth: dict) -> str:
    header = GENERATED_HEADER.format(ts=datetime.now().isoformat(timespec="seconds"))
    # 模板 import deployment_contract —— 附带 joints_actuated 供角色展开
    return header + DECODER_TEMPLATE


CHECKLIST_TEMPLATE = """# 人工确认清单（一键生成 ≠ 一键上机）

> 生成时间：{ts} ｜ 机器人：{robot_id}
> 依据：报告 2（Sim2Real 链路）与报告 10 部署区约定——D3+ 必须人工确认。

## 上电前
- [ ] **增益先降 50%**：将 deployment contract 中的 kp/kd 减半后先行验证，再逐步恢复
- [ ] **急停最高优先**：急停链路（遥控/键盘/看门狗）独立于策略并已实测
- [ ] **零点初始化**：电机零点与契约 default_pose 一致；M20 类多圈关节需标定流程
- [ ] **软限位 = 机械极限**：joint_limits 与结构限位核对（尤其 HipY/Knee）

## 上线自检
- [ ] `single_joint_sine_test()`：逐关节正弦波核对电机序与方向（最高频 bug）
- [ ] `reindex_from_model` 已按部署契约核对（训练关节序 ≠ SDK 电机序）
- [ ] 站立姿态保持 30s 无漂移（PD 收敛）
- [ ] 命令超时看门狗生效（断开策略 → 自动回 STAND）

## 分级上机（D0 → D6）
- [ ] D2 台架：悬空执行器正弦扫频 + 温升/堵转保护提示
- [ ] D3 低增益着地静态 → D4 系留/围栏受限动态 → D5 自由动态 → D6 全功能
- [ ] 每级通过后才进下一级；任何异常回退上一级并记录日志
"""


def _strip_none(value: Any) -> Any:
    """剔除 None（null），保证 json.dumps 产物可直接作为 Python 字面量。"""

    if isinstance(value, dict):
        return {k: _strip_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_strip_none(v) for v in value if v is not None]
    return value


D2_BENCH_TEMPLATE = '''# D2 台架测试（空载执行器正弦扫频 + 温升/堵转保护）
# 对应优化清单 #12：部署页"台架模式"导出档。悬空（不落地）验证每个执行器
# 只动该动的那一个、方向正确、无异常温升/堵转，是 Sim2Real 的 D2 级检查。
#
# 运行：接入目标平台适配层后单关节扫频，或直接本文件作为独立测试脚本。
#     from deployment_contract import CONTRACT
#     from d2_bench_test import run_bench_scan
#     run_bench_scan(CONTRACT, duration_s=3.0, freq_hz=1.0)

import math
import time


def run_bench_scan(contract, duration_s: float = 3.0, freq_hz: float = 1.0, send=None):
    """逐关节正弦扫频。

    send(joint_index, target) 由目标平台适配层提供（None 时仅打印）。
    观察点：
      - 每个电机只动该动的那一个（关节序/方向核对，最高频 bug）；
      - 长时间扫频后温升正常、无堵转；
      - 遇到异常立即调用 estop。
    """
    action = contract.get(\"action\") or {}
    joint_order = action.get(\"joint_order\") or []
    default_pose = contract.get(\"default_pose\") or [0.0] * len(joint_order)
    scale = action.get(\"action_scale\") or 0.25
    control = contract.get(\"control\") or {}
    control_hz = control.get(\"control_hz\") or 50
    steps = int(duration_s * control_hz)

    print(f\"[bench] D2 台架扫频 over {len(joint_order)} joints, {duration_s}s @ {freq_hz}Hz\")
    for joint_idx in range(len(joint_order)):
        base = default_pose[joint_idx] if joint_idx < len(default_pose) else 0.0
        for k in range(steps):
            phase = 2 * math.pi * freq_hz * k / steps
            target = base + scale * math.sin(phase)
            if send is None:
                print(f\"[bench] {joint_order[joint_idx]} -> {target:.4f}\")
            else:
                send(joint_idx, target)
            time.sleep(1.0 / control_hz)
        print(f\"[bench] joint {joint_order[joint_idx]} 扫频完成——核对方向/无堵转\")
    print(\"[bench] D2 台架扫频完成——温升正常则视为通过（D2 级）\")
'''

def generate_deploy_package(
    robot_id: str, *,
    degraded: bool = False,
    target_platform: str = "unitree_sdk2",
    bench_mode: bool = False,
    out_dir: Path | str | None = None,
    policy_onnx: str | Path | None = None,
) -> dict:
    """生成部署包 zip。返回 ``{robot_id, path, files, target_platform, bench_mode}``。

    ``out_dir`` 缺省落 ``<仓库>/workspace/deploy``（与 Web 的
    ``POST /api/deploy/package`` 同一落点）；CLI 的 ``deploy package --out <目录>``
    传入自定目录（测试 / CI 把产物放进临时目录，不污染真实 workspace）。

    ``policy_onnx``：可选，随包携带策略 ONNX（打进包内 ``policy.onnx``）。
    **给了路径而文件不存在时 fail-closed 报错**——"以为带上了策略"比不带更危险。

    打包逻辑本身只有这一份（单一真值）：``POST /api/deploy/package`` 与 CLI
    ``deploy package`` 都调这里，不各自再写一套打包/追加逻辑。
    """

    root = resolve_package_root(robot_id)
    contract_truth = _load_json(root / "contract.json")
    if not contract_truth:
        raise ValueError(f"robot {robot_id} 缺少 contract.json——先运行 tools/migrate_contract.py")

    # 输入校验全部前置：**不通过就不落任何产物（连输出目录都不建）**——"失败留半个包"
    # 比"失败没包"更难排查（调用方会以为这是上一次的产物）。产出目录只在输入合格后创建。
    onnx_path: Path | None = None
    if policy_onnx is not None:
        onnx_path = Path(policy_onnx)
        if not onnx_path.is_file():
            raise FileNotFoundError(f"policy onnx not found: {onnx_path}")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(out_dir) if out_dir else ROOT / "workspace" / "deploy"
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{robot_id}_deploy_{ts}.zip"

    joints_actuated = contract_truth.get("joints", {}).get("actuated", [])
    effort_scale = 0.8 if degraded else 1.0
    if degraded and effort_scale != 1.0:
        profile = dict(contract_truth.get("actuator_profile") or {})
        scaled_roles = {}
        for role, params in (profile.get("by_role") or {}).items():
            scaled = dict(params)
            if scaled.get("effort") is not None:
                scaled["effort"] = round(float(scaled["effort"]) * effort_scale, 4)
            scaled_roles[role] = scaled
        profile["by_role"] = scaled_roles
        profile["degraded"] = {"effort_scale": effort_scale, "note": "劣化参数档：摩擦 -20% 建议 + 力矩 ×0.8 跑稳再上真机"}
        contract_truth = dict(contract_truth)
        contract_truth["actuator_profile"] = profile

    dc_payload = _strip_none({
        "schema_version": "deployment-contract-1.0",
        "robot_id": contract_truth.get("robot_id"),
        "control": contract_truth.get("control") or {},
        "action": {
            "joint_order": contract_truth.get("action", {}).get("joint_order"),
            "reindex_from_model": contract_truth.get("action", {}).get("reindex_from_model"),
            "action_scale": contract_truth.get("action", {}).get("action_scale"),
        },
        "actuator_profile": contract_truth.get("actuator_profile") or {},
        "default_pose": contract_truth.get("joints", {}).get("default_pose"),
        "joints_actuated": joints_actuated,
    })
    dc_py = (
        GENERATED_HEADER.format(ts=ts)
        + "CONTRACT = "
        + json.dumps(dc_payload, ensure_ascii=False, indent=2)
        + "\n"
    )

    files = {
        "deployment-contract.yaml": deployment_contract_yaml(contract_truth),
        "deployment_contract.json": json.dumps(dc_payload, ensure_ascii=False, indent=2) + "\n",
        "deployment_contract.py": dc_py,
        "fsm_safety_template.py": fsm_template(contract_truth),
        "action_decoder_template.py": decoder_template(contract_truth),
        "platform_adapter.py": platform_adapter(target_platform),
        "人工确认清单.md": CHECKLIST_TEMPLATE.format(ts=ts, robot_id=contract_truth.get("robot_id")),
    }
    if bench_mode:
        files["d2_bench_test.py"] = D2_BENCH_TEMPLATE

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
        if onnx_path is not None:
            zf.write(onnx_path, "policy.onnx")

    listed = list(files) + (["policy.onnx"] if onnx_path is not None else [])
    return {"robot_id": robot_id, "path": str(zip_path), "files": listed, "target_platform": target_platform, "bench_mode": bench_mode}


def deploy_gate_report(robot_id: str) -> dict:
    """部署前契约一致性快检（包内 v3 vs v2）：
    ``{robot_id, package_root, ok, blockers, warnings, disposition, entries, context}``。

    ``GET /api/deploy/gate/{robot_id}`` 与 CLI ``deploy gate`` 都调这里（**同一处实现**）。
    边界：真正的强校验在**导出侧**（训练快照 vs 当前契约）；这里只核对包内两版契约的层间一致性。

    失败语义（调用方各自映射措辞，不各自判条件）：

    - 包不存在 → :class:`RobotPackageNotFound`（API 404 / CLI 退出码 1）；
    - 包在但两版契约缺任一 → ``ValueError``（"包内契约不全"属数据问题，不是"包不在"）；
    - 两版契约都在 → ``compare_contracts`` 的裁决结果，**不一致就是 deny**（不编造通过）。
    """

    from backend.export_gate import compare_contracts

    root = resolve_package_root(robot_id)
    contract = _load_json(root / "contract.json")
    legacy = _load_json(root / "contract_legacy_v2.json")
    missing = [name for name, value in (("contract.json", contract), ("contract_legacy_v2.json", legacy)) if not value]
    if missing:
        raise ValueError(f"包内契约不全（缺 {' / '.join(missing)}）：{root}")
    return {"robot_id": robot_id, "package_root": str(root), **compare_contracts(contract, legacy)}


# ===== 目标平台模板实例化（T5.x 部署模板） =====
#
# 部署包四件套里的 FSM 与解码层此前只带"接 Unitree SDK2 / ROS2 / 其他"的占位注释，
# 不产出真实实现。这里按所选平台实例化一个 platform_adapter，把 SDK 状态读取、
# 急停信号、电机命令发送这些"接入点"落成可运行的骨架代码。
# 安全边界不变：只生成物料与骨架，不直接发电机命令（一键生成 ≠ 一键上机）。

PLATFORM_LABELS = {
    "unitree_sdk2": "Unitree SDK2（DDS LowCmd/LowState）",
    "ros2": "ROS2（rclpy 话题：JointState 状态发布 / Float64MultiArray 命令订阅）",
}

UNITTREE_SDK2_ADAPTER = '''
"""Unitree SDK2 平台适配层（Legged Studio 生成骨架）。

通过 unitree_sdk2py 的 DDS 接口收发 LowCmd / LowState。
- send_motor_commands(): 把 ROBOT SAFETY FSM 产出的命令包发布到 rt/lowcmd。
- read_states(): 从 rt/lowstate 读取关节角度、电机状态与 IMU。
- read_remote_stop(): 从遥控/上位机急停信号（unitree 手柄或看门狗）读急停。

上线前必须核对：关节序（reindex）、力矩限幅、SDK 版本与电机 id 映射。
"""

from __future__ import annotations

from typing import Optional

try:
    import numpy as np
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber, ChannelPublisher
    from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowCmd_, LowState_
except Exception as _exc:  # pragma: no cover - 目标机上才有 SDK
    np = None
    ChannelFactoryInitialize = ChannelSubscriber = ChannelPublisher = None
    LowCmd_ = LowState_ = None


class UnitreeSDK2Adapter:
    """将 FSM/解码层的通用命令包映射到 Unitree SDK2 LowCmd。"""

    def __init__(self, n_motors: int, dt: float = 0.02) -> None:
        self.n_motors = int(n_motors)
        self.dt = dt
        self._pub = None
        self._state_sub = None
        self._last_state: Optional["LowState_"] = None
        if ChannelFactoryInitialize is not None:
            ChannelFactoryInitialize(0, "lo")
            self._pub = ChannelPublisher("rt/lowcmd", LowCmd_)
            self._state_sub = ChannelSubscriber("rt/lowstate", LowState_)
            self._state_sub.Init(lambda msg: setattr(self, "_last_state", msg))

    def send_motor_commands(self, commands: dict) -> None:
        """commands: {joint_name: {mode, target, effort_limit, kp, kd}}。"""
        if self._pub is None or LowCmd_ is None:
            return
        cmd = LowCmd_()
        cmd.mode_pr = [0] * self.n_motors
        cmd.mode_mx = [0] * self.n_motors
        for name, spec in commands.items():
            index = int(spec.get("joint_index", 0))
            mode = str(spec.get("mode") or "position")
            if mode == "velocity":
                cmd.mode_mx[index] = 1  # 速度模式
                cmd.tau_mx[index] = float(spec.get("effort_limit") or 0.0)
                cmd.qd_mx[index] = float(spec.get("target") or 0.0)
            elif mode == "estop":
                # 急停：零速 + 零力矩，保持软限位（真实急停需硬件断开）
                cmd.mode_mx[index] = 0
                cmd.tau_mx[index] = 0.0
                cmd.qd_mx[index] = 0.0
            else:  # position / policy 位置指令
                cmd.mode_pr[index] = 1
                cmd.q_pr[index] = float(spec.get("target") or 0.0)
                cmd.kp_pr[index] = float(spec.get("kp") or 40.0)
                cmd.kd_pr[index] = float(spec.get("kd") or 2.0)
                cmd.tau_pr[index] = float(spec.get("effort_limit") or 40.0)
        self._pub.write(cmd)

    def read_states(self):
        """返回 {joint_name: {q, dq, tau}}（按部署契约关节序）。"""
        if self._last_state is None or LowState_ is None:
            return {}
        state = self._last_state
        names = getattr(state, "name", None) or []

    def read_remote_stop(self) -> bool:
        """急停优先：这里返回 False（未接遥控急停）；上线前必须接真信号。"""
        return False


__all__ = ["UnitreeSDK2Adapter"]
'''

ROS2_ADAPTER = '''
"""ROS2 平台适配层（Legged Studio 生成骨架）。

用 rclpy 话题接入：
- 订阅 sensor_msgs/JointState：读关节角度/速度（状态）。
- 发布 std_msgs/Float64MultiArray 到 /legged_studio/joint_commands：发电机命令。
急停可订阅 std_msgs/Bool 到 /legged_studio/estop。
"""

from __future__ import annotations

from typing import Optional

try:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import JointState
    from std_msgs.msg import Float64MultiArray, MultiArrayDimension, Bool
except Exception as _exc:  # pragma: no cover - 目标机才有 ROS2
    rclpy = None
    Node = JointState = Float64MultiArray = MultiArrayDimension = Bool = None


class ROS2Adapter(Node):
    def __init__(self, joint_names: list[str]) -> None:
        if rclpy is None:
            raise RuntimeError("ROS2（rclpy）未安装——目标平台需先 source 环境")
        super().__init__("legged_studio_deploy")
        self.joint_names = list(joint_names)
        self._cmd_pub = self.create_publisher(Float64MultiArray, "/legged_studio/joint_commands", 10)
        self._estop_sub = self.create_subscription(Bool, "/legged_studio/estop", self._on_estop, 10)
        self._estop = False

    def _on_estop(self, msg) -> None:
        self._estop = bool(msg.data)

    def send_motor_commands(self, commands: dict) -> None:
        msg = Float64MultiArray()
        msg.layout.dim.append(MultiArrayDimension(label="joint", size=len(self.joint_names), stride=1))
        # 按 joint_order 输出 target（模式字段在部署契约/解码层已归一）
        msg.data = [float(commands.get(name, {}).get("target", 0.0)) for name in self.joint_names]
        self._cmd_pub.publish(msg)

    def read_remote_stop(self) -> bool:
        return self._estop


__all__ = ["ROS2Adapter"]
'''


PLATFORM_ADAPTERS = {
    "unitree_sdk2": UNITTREE_SDK2_ADAPTER,
    "ros2": ROS2_ADAPTER,
}


def platform_adapter(platform: str) -> str:
    """返回所选平台的适配层骨架代码；未知平台回退到通用注释。"""
    label = PLATFORM_LABELS.get(platform, platform)
    header = GENERATED_HEADER.format(ts=datetime.now().isoformat(timespec="seconds"))
    body = PLATFORM_ADAPTERS.get(platform)
    if body is None:
        body = f'"""通用平台适配层（{label}）。\n\n请按目标平台的电机接口实现 send_motor_commands / read_states / read_remote_stop。\n"""\n'
    return header + body
