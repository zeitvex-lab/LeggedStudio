"""部署包生成器（T3.3，批次 3 / M4）。

"一键生成 ≠ 一键上机"：本模块只生成部署物料，不直接发电机命令。
四件套（报告 10 §⑤ / 报告 2 §4 rl_sar 双层契约 + microduck publish 门）：

  1. deployment-contract.yaml —— 关节映射/控制频率/PD/armature/限位（JSON 是合法
     YAML 子集；注释指向真值源 contract_v3.json）
  2. fsm_safety_template.py —— PASSIVE→STAND→POLICY→RECOVER→ESTOP 安全状态机
     （安全链路独立于策略；急停最高优先；wheel 角色走速度指令）
  3. action_decoder_template.py —— 策略槽序 × reindex_from_model → 真实电机命令
     （position/torque/velocity 三模式；含单关节正弦波验证项——"训练关节序 ≠
     SDK 电机序"是最高频部署 bug，报告 2 §3）
  4. 人工确认清单.md —— 增益先降 50% / 急停最高优先 / 零点初始化 / 软限位一致

数据全部来自契约 v3（DENYLIST gate 已在导出侧把关一致性）。
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

GENERATED_HEADER = "# 本文件由 Legged Studio 部署包生成器产出（{ts}）；真值源：contract_v3.json\n"


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def deployment_contract_yaml(contract_v3: dict) -> str:
    """JSON 是合法 YAML 子集——机器可读、人可读、无 PyYAML 依赖。"""

    payload = {
        "schema_version": "deployment-contract-1.0",
        "generated_by": "legged-studio deploy packager",
        "robot_id": contract_v3.get("robot_id"),
        "control": contract_v3.get("control") or {},
        "action": {
            "joint_order": contract_v3.get("action", {}).get("joint_order"),
            "reindex_from_model": contract_v3.get("action", {}).get("reindex_from_model"),
            "action_scale": contract_v3.get("action", {}).get("action_scale"),
        },
        "actuator_profile": contract_v3.get("actuator_profile") or {},
        "default_pose": (contract_v3.get("joints") or {}).get("default_pose"),
        "notes": "关节映射/控制频率/PD/armature 全部来自契约 v3（rl_sar base.yaml 语义）——修改请回训练区，不要手改本文件",
    }
    header = (
        "# deployment contract（rl_sar 双层 YAML 契约语义）\n"
        + GENERATED_HEADER.format(ts=datetime.now().isoformat(timespec="seconds"))
        + "# JSON 是合法 YAML 子集；与 deployment_contract.json 内容一致\n"
    )
    return header + json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def deployment_contract_json(contract_v3: dict) -> str:
    payload = {
        "schema_version": "deployment-contract-1.0",
        "generated_by": "legged-studio deploy packager",
        "robot_id": contract_v3.get("robot_id"),
        "control": contract_v3.get("control") or {},
        "action": contract_v3.get("action") or {},
        "actuator_profile": contract_v3.get("actuator_profile") or {},
        "default_pose": (contract_v3.get("joints") or {}).get("default_pose"),
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


def fsm_template(contract_v3: dict) -> str:
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


def decoder_template(contract_v3: dict) -> str:
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


def generate_deploy_package(robot_id: str, *, degraded: bool = False) -> dict:
    """生成部署包 zip。返回 {path, files}。"""

    from backend.robot_presets import get_robot_preset

    preset = get_robot_preset(robot_id)
    root_value = str(((preset or {}).get("robot_package") or {}).get("package_root", ""))
    root = Path(root_value) if root_value else ROOT / "assets" / "robots" / robot_id
    if not root.exists():
        raise FileNotFoundError(f"robot package not found: {robot_id}")
    contract_v3 = _load_json(root / "contract_v3.json")
    if not contract_v3:
        raise ValueError(f"robot {robot_id} 缺少 contract_v3.json——先运行 tools/migrate_contract_v3.py")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = ROOT / "workspace" / "deploy"
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{robot_id}_deploy_{ts}.zip"

    joints_actuated = contract_v3.get("joints", {}).get("actuated", [])
    effort_scale = 0.8 if degraded else 1.0
    if degraded and effort_scale != 1.0:
        profile = dict(contract_v3.get("actuator_profile") or {})
        scaled_roles = {}
        for role, params in (profile.get("by_role") or {}).items():
            scaled = dict(params)
            if scaled.get("effort") is not None:
                scaled["effort"] = round(float(scaled["effort"]) * effort_scale, 4)
            scaled_roles[role] = scaled
        profile["by_role"] = scaled_roles
        profile["degraded"] = {"effort_scale": effort_scale, "note": "劣化参数档：摩擦 -20% 建议 + 力矩 ×0.8 跑稳再上真机"}
        contract_v3 = dict(contract_v3)
        contract_v3["actuator_profile"] = profile

    dc_payload = _strip_none({
        "schema_version": "deployment-contract-1.0",
        "robot_id": contract_v3.get("robot_id"),
        "control": contract_v3.get("control") or {},
        "action": {
            "joint_order": contract_v3.get("action", {}).get("joint_order"),
            "reindex_from_model": contract_v3.get("action", {}).get("reindex_from_model"),
            "action_scale": contract_v3.get("action", {}).get("action_scale"),
        },
        "actuator_profile": contract_v3.get("actuator_profile") or {},
        "default_pose": contract_v3.get("joints", {}).get("default_pose"),
        "joints_actuated": joints_actuated,
    })
    dc_py = (
        GENERATED_HEADER.format(ts=ts)
        + "CONTRACT = "
        + json.dumps(dc_payload, ensure_ascii=False, indent=2)
        + "\n"
    )

    files = {
        "deployment-contract.yaml": deployment_contract_yaml(contract_v3),
        "deployment_contract.json": json.dumps(dc_payload, ensure_ascii=False, indent=2) + "\n",
        "deployment_contract.py": dc_py,
        "fsm_safety_template.py": fsm_template(contract_v3),
        "action_decoder_template.py": decoder_template(contract_v3),
        "人工确认清单.md": CHECKLIST_TEMPLATE.format(ts=ts, robot_id=contract_v3.get("robot_id")),
    }
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return {"robot_id": robot_id, "path": str(zip_path), "files": list(files)}
