#!/usr/bin/env python3
"""obs_crosscheck.py — **同状态观测对拍**：验收器（Python）↔ 浏览器观测构建器（Node）。

**为什么需要它**（2026-09-22 一场血案的直接产物）：浏览器与验收器是**两套独立实现**，
"差一步"的缺陷**不抛异常、不改任何读数**，只在特定姿态暴露——用户报的"机器人转到 180°
左右必然抽风"就是浏览器侧 `captureImuSample` 对自由关节 `qvel[3:6]`（**本就是机体系角速度**）
多做了一次 `Rᵀ`（双重旋转）：yaw≈0 处 R≈I 完全看不出来，yaw→180° 时水平两轴翻号 ⇒
姿态反馈变正反馈 ⇒ 乱动失衡。当时把它抓住的唯一手段就是本工具的做法：
**同一份 qpos/qvel 喂给两条实现，逐段比观测**。

口径（刻意的选择，别改）：
  · 状态在**真 MuJoCo** 里造：默认 **yaw=180° + 小滚转/俯仰（4°/3°）**，带非零体速度与关节
    偏移。**为什么要给滚转/俯仰**：差一步的缺陷在 yaw≈0 且姿态直立时几乎不可见（实测同一
    缺陷：yaw=0 直立 Δ≈1e-8 也测不出来；带上 4°/3° 后 yaw=0 就有 Δ≈1.8e-2、到 yaw=180°
    放大到 Δ≈0.98）——所以状态要"站得歪 + 转得大"，任何 yaw 下都能现形；
  · 浏览器侧**不启浏览器**：Node 直接加载 `web/sim2sim/obs/observation_builders.js`，
    IMU 走 `web/sim2sim/utils.js::imuSampleFromQpos`（运行时真路径）——不另写一份仿真品；
  · 判据在 Python 侧算，两边各自只出自己的真值，工具不引入第三份实现。

**门禁资格（已实测）**：把 2026-09-22 那处缺陷临时注入回去 → 本工具 `exit=1` 并指名
`IMU.angular max|Δ|=9.85e-01`；还原后 `exit=0`。即它**真的能抓**，不是"跑完总是绿"。

退出码：`0` 一致 · `1` 不一致（超容差）· `2` 环境缺失或本 kind 不适用（fail-closed）

用法：
    python3 tools/obs_crosscheck.py                      # 默认 go2-rlsar-robotlab @ yaw=180°
    python3 tools/obs_crosscheck.py --yaw-deg 0          # 对照：yaw=0（此处两者本应恒等）
    python3 tools/obs_crosscheck.py --policy go2-loco-45
    python3 tools/obs_crosscheck.py --keep               # 保留中间 JSON 供排查
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: 通例段（**定位提示**，不是判据）：绝大多数 kind 的前 9 维是 ang_vel / gravity / cmd。
#: 判据只有一条 —— 逐维 max|Δ| ≤ tol。段名写在这里只是让人一眼看出"错在哪个语义段"。
#: 无声明式规格时的**兜底**段名（按 rl_sdk 顺序写死的那份）。
#: 注意它只对"ang_vel 在前"的布局成立——对 `cmd` 在前或带相位的 kind 会**贴错段名**
#: （实测：注入反例时差异被标在 `ang_vel` 段上），故有规格时一律走 `segments_for()`。
COMMON_SEGMENTS = (("ang_vel", 0, 3), ("gravity", 3, 6), ("cmd", 6, 9))


def segments_for(contract: dict, action_dim: int | None = None, command_dims: int = 3) -> tuple:
    """**按声明式规格生成段名** `(label, lo, hi)`；无规格则回落 `COMMON_SEGMENTS`。

    段名带缩放（如 `cmd×[2.0, 2.0, 0.25]`）—— 对拍输出从此是**自解释**的：读者不用再去
    翻解释器就知道每一段的语义与缩放，也不用猜"0-3 到底是不是 ang_vel"。
    """
    layout = (contract or {}).get("observation_layout")
    if not layout:
        return COMMON_SEGMENTS
    fixed = {"gravity": 3, "euler": 3, "phase_sin": 1, "phase_cos": 1}
    out, lo = [], 0
    for seg in layout:
        source = str((seg or {}).get("source") or "")
        if source in fixed:
            width = fixed[source]
        elif source == "cmd":
            width = int((seg or {}).get("width") or command_dims)
        else:
            width = int((seg or {}).get("width") or action_dim or 0)
        scale = (seg or {}).get("scale", 1.0)
        label = source if scale in (1, 1.0) else f"{source}×{scale}"
        out.append((label, lo, lo + width))
        lo += width
    return tuple(out)


def load_engine():
    """加载验收器引擎（与 tools/sim2sim_headless.py 同一实现，见那里的说明）。"""
    spec = importlib.util.spec_from_file_location(
        "sim2sim_headless", ROOT / "tools" / "sim2sim_headless.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        return module.load_engine()
    except ImportError as exc:  # mujoco / onnxruntime 缺失
        print(f"[crosscheck] 环境缺失：{exc}", file=sys.stderr)
        raise SystemExit(2)


def _name_id_map(model, kind: str) -> dict[str, int]:
    """`{名字: id}`（按 MuJoCo 的 id 序）——给浏览器侧的 `mj_name2id` 当索引表。"""
    import mujoco

    obj = mujoco.mjtObj.mjOBJ_JOINT if kind == "joint" else mujoco.mjtObj.mjOBJ_BODY
    count = int(model.njnt) if kind == "joint" else int(model.nbody)
    out: dict[str, int] = {}
    for i in range(count):
        name = mujoco.mj_id2name(model, obj, i)
        if name:
            out[str(name)] = i
    return out


def build_state(engine, package_dir: Path, sim_cfg: dict, entry: dict, yaw_deg: float) -> tuple[dict, dict]:
    """造一个"大角度 + 非零速度 + 关节偏移"的状态，返回 (给 Node 的状态包, 本侧参考观测)。"""
    import mujoco
    import numpy as np

    contract = engine.PackageContract(package_dir, entry)
    contract.motion_loader = None
    if contract.observation_kind in getattr(engine, "_DEFERRED_KINDS", set()):
        print(f"[crosscheck] kind={contract.observation_kind} 需 MotionLoader/复合命令，本工具不适用（不是缺陷）",
              file=sys.stderr)
        raise SystemExit(2)
    model = engine.load_package_model(package_dir, sim_cfg, None, scene_rel=contract.contract.get("scene_path"))
    model.opt.timestep = 1.0 / contract.physics_hz
    data = mujoco.MjData(model)
    obs = engine.ObsBuilder(contract, model, data)
    engine.spawn_default(contract, model, data, obs)

    # ── 状态：按 yaw 造姿态（含小滚转/俯仰，让 R 既不是单位阵也不是纯偏航）──────────
    quat = np.zeros(4, dtype=np.float64)
    mujoco.mju_euler2Quat(quat, np.radians(np.array([4.0, -3.0, float(yaw_deg)])), "xyz")
    data.qpos[3:7] = quat
    rot = np.zeros(9, dtype=np.float64)
    mujoco.mju_quat2Mat(rot, quat)
    rot = rot.reshape(3, 3)
    v_body = np.array([0.6, 0.2, 0.0])          # 机体系线速度 → 世界系写进 qvel[0:3]
    omega_body = np.array([0.3, -0.5, 0.2])     # 机体系角速度 → 直接进 qvel[3:6]
    data.qvel[0:3] = rot @ v_body
    data.qvel[3:6] = omega_body

    order = contract.action_joint_order
    joints = []
    for i, name in enumerate(order):
        qa, da = obs.jadr[name]
        data.qpos[qa] = contract.default_for(name) + 0.05 * ((i % 3) - 1)
        data.qvel[da] = 0.1 * i - 0.4
        joints.append({"name": name, "q": float(data.qpos[qa]), "dq": float(data.qvel[da]),
                       # **真地址**：`qpos = [pos, quat, 关节…]` 只在"机器人本体是第一个自由关节"
                       # 时成立。wuji_hand 就不成立（唯一的自由关节是**立方体**，手指关节在
                       # qpos[0..19]）⇒ 工具原先按 `7+i` 造/读 qpos，读 `qpos[3:7]` 当四元数，
                       # 全是假的（IMU 段立刻红）。
                       "qpos_adr": int(qa), "dof_adr": int(da),
                       "default": float(contract.default_for(name))})
    mujoco.mj_forward(model, data)

    # 策略内部状态：**原始**（弧度）动作目标 —— 浏览器 `sim.targetDofPos` 就是原始值，
    # 由 builder 自己归一化；验收器的 `wuji_target` 存的是**归一化后**的值，故这里用
    # **引擎自己的** `_wuji_normalize_positions` 换算过去（不在此另写公式），
    # 并让目标 ≠ 当前姿态（否则 qpos_error 段两侧同为 0，等于没测）。
    if hasattr(obs, "wuji_target"):
        raw_target = np.array([float(data.qpos[obs.jadr[n][0]]) + 0.1 for n in order], dtype=np.float64)
        obs.wuji_target = engine._wuji_normalize_positions(model, order, raw_target)
    else:
        raw_target = np.zeros(len(order), dtype=np.float64)

    obs.last_action = np.zeros(contract.action_dim, dtype=np.float32)
    cmd = np.array([0.6, 0.0, 0.0], dtype=np.float32)
    own = np.asarray(obs.build(cmd), dtype=np.float64).reshape(-1)
    # **历史口径**：验收器的 `build()` 直接给出**叠好历史**的整向量（如 270 = 6×45），
    # 而浏览器侧被驱动的是 **builder 单帧**（叠帧在 `app.js::packObsHistoryByTerm`，
    # Node 侧没驱动那一层）⇒ 直接比会得到"270 vs 45"的**假红**。故有历史时只比**当前帧**，
    # 由 `engine.packed_current_frame` 按**与打包同一张段表**定位（不在这里另写一份切法）。
    #
    # **2026-09-22 订正（尺子自己也会错，别只怀疑被测物）**：本工具原先把"当前帧"一律
    # 取 `packed[:obs_dim]`——对 frame-major 成立，对 **term-major（缺省布局）不成立**：
    # 后者当前帧**分散在每段的末槽**，切出来是"第 0 段的历史 + 第 1 段的历史"，于是
    # 5 条 `go2_rl_sdk_45` 族策略（go2-moe-cts / kaiwu 四条）被**误报**不一致
    # （实测两侧逐维一致 5.96e-08）。现在一律走 `packed_current_frame`。
    history_len = int(contract.history_len or 1)
    frame_width = int(contract.obs_dim or own.shape[0])
    layout = str(getattr(contract, "history_layout", "") or "")
    compare_basis = "整向量"
    if history_len > 1 and own.shape[0] == frame_width * history_len:
        own = np.asarray(engine.packed_current_frame(contract, own), dtype=np.float64)
        compare_basis = (f"当前帧（{layout or 'term-major（缺省段表）'}，"
                         f"另 {history_len - 1} 帧历史不在此层）")

    # IMU 诊断段的可比性：它假定**浮动基座在 qpos[0:7]**（`pos(3)+quat(4)`）。某些机型的
    # 自由关节不在 0 位（wuji_hand 唯一自由关节是立方体、手指关节排在前面）——那种情况下
    # `qpos[3:7]` 根本不是四元数，两侧各按各自的公式解读同一坨垃圾，比较**没有意义**。
    # 如实标"不适用"，不要把它算成红（也不要点着它说"两份实现差一步"）。
    free_at_zero = any(
        model.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE and int(model.jnt_qposadr[j]) == 0
        for j in range(int(model.njnt))
    )
    imu_reason = "" if free_at_zero else (
        "本机型 qpos[0:7] 不是浮动基座（没有位于 0 位的自由关节）⇒ "
        "浏览器与验收器对 qpos[3:7] 的解读都无物理意义，IMU 段不参与判定"
    )

    state = {
        "contract": {
            "observation_kind": contract.observation_kind,
            "obs_dim": int(contract.obs_dim or own.shape[0]),
            "action_dim": int(contract.action_dim),
            "history_len": int(contract.history_len or 1),
            # 声明式布局规格：对拍工具的段名/宽度也由它派生（不再按 rl_sdk 顺序写死）。
            "observation_layout": contract.contract.get("observation_layout"),
            "command_dims": int(contract.command_dims or 3),
            "decimation": int(contract.decimation or 1),
            "physics_hz": float(contract.physics_hz),
            # 浏览器 `CONFIG.simulationDt` 的**同源真值**：后端 API 的 `control.sim_dt`
            # ＝ 1/physics_hz（`backend/simulation_api.py`），不是控制步长。缺它会静默
            # 影响相位钟类布局（实测 `g1_mjlab_velocity_98` ⇒ `Math.sin(NaN)`）。
            "simulation_dt": (1.0 / float(contract.physics_hz)) if contract.physics_hz else 0.005,
            "gait_period_s": float(getattr(contract, "gait_period", 0.0) or 0.0),
            "default_joint_angles": {},
            # 角色/控制模式：浏览器侧 `applyActuatorContract(contract, control, order)`
            # 的**同一组输入**（策略契约字段原样带过去，解析在 JS 侧共用函数里做）。
            # 缺了它们，"轮位清零"那类分支会在对拍里被当成 position 处理 ⇒ **假红**
            # （2026-09-22 实测 m20/b2w 两条 `go2w_rl_sdk_57`：Δ=5.000e-02）。
            "actuator_roles": contract.contract.get("actuator_roles"),
            "control_modes": contract.contract.get("control_modes"),
        },
        # 机器人级控制模式：后端 API 的 `control.control_modes` 取自同一处
        # （`simulation/config.json` 的 `control_modes`，见 backend/simulation_api.py）。
        "control_modes": {"robot": sim_cfg.get("control_modes") or {}},
        "scales": {
            "ang_vel": float(contract.ang_vel_scale),
            "dof_pos": float(contract.dof_pos_scale),
            "dof_vel": float(contract.dof_vel_scale),
            "command": [float(v) for v in contract.cmd_scale],
        },
        "cmd": [float(v) for v in cmd],
        "action": [float(v) for v in obs.last_action],
        # ── 模型态：浏览器侧那几只读 `sim.model` / `sim.data` 的 builder（wuji-reorient 等）
        #    需要有**真模型**才能算对：关节 id（软限位归一化）、body id（立方体/手掌位姿）。
        #    这里把 MuJoCo 的真值原样搬过去（不是"再算一遍"，是"同一份输入"）——不搬的
        #    后果实测过：wuji 的 [40..48] 9 维在浏览器侧全是 NaN（`xpos[-3]`），而对拍的
        #    报告只会说"不一致"，看着像实现问题。
        "mujoco": {
            "njnt": int(model.njnt),
            "nbody": int(model.nbody),
            "joint_ids": _name_id_map(model, "joint"),
            "body_ids": _name_id_map(model, "body"),
            # 软限位（`mjlab soft_joint_pos_limit_factor=0.9` 在两侧各自的实现里乘）
            "jnt_range": [[float(model.jnt_range[j, 0]), float(model.jnt_range[j, 1])]
                          for j in range(int(model.njnt))],
            "xpos": [float(v) for v in np.asarray(data.xpos).reshape(-1)],
            "xquat": [float(v) for v in np.asarray(data.xquat).reshape(-1)],
        },
        # 策略内部状态（两侧必须"同一状态"才可比）：**原始**动作目标（qpos_error 用，语义
        # 同浏览器 `sim.targetDofPos`＝弧度原值）与目标朝向状态机的当前 goal。缺 goal 时
        # 浏览器侧会**随机**采样 ⇒ 不可比（不是不一致）。
        "policy_state": {
            "target_dof_pos_raw": [float(v) for v in raw_target],
            "goal_quat": [float(v) for v in np.asarray(
                getattr(obs, "wuji_goal_quat", np.array((1.0, 0.0, 0.0, 0.0))), dtype=np.float64).reshape(-1)],
        },
        # 浏览器侧 `input.imuAxisSigns` 默认 [1,1,1]（契约里没有该字段），两侧同号
        "imu_axis_signs": {"angular": [1, 1, 1], "gravity": [1, 1, 1]},
        "imu_comparable": {"ok": free_at_zero, "reason": imu_reason},
        "state": {
            # **整条 qpos/qvel 原样搬过去**（不做"pos+quat+关节"的布局假设）：不同机型的
            # 自由关节位置不同（wuji_hand 唯一自由关节是立方体、手指关节排在前面），
            # 让浏览器侧自己按 `qpos_adr/dof_adr` 取值才是同一状态。
            "nq": int(model.nq),
            "nv": int(model.nv),
            "qpos": [float(v) for v in np.asarray(data.qpos).reshape(-1)],
            "qvel": [float(v) for v in np.asarray(data.qvel).reshape(-1)],
            "quat_wxyz": [float(v) for v in data.qpos[3:7]],
            "qvel_head": [float(v) for v in data.qvel[0:6]],
            "joints": joints,
        },
    }
    reference = {
        "obs": [float(v) for v in own],
        "compare_basis": compare_basis,
        "imu": {
            "angular": [float(v) for v in data.qvel[3:6]],
            "linear": [float(v) for v in (rot.T @ data.qvel[0:3])],
            "gravity": [float(v) for v in engine.projected_gravity(data.qpos[3:7])],
            "rpy": [float(v) for v in engine.quat_to_euler_xyz(data.qpos[3:7])],
        },
    }
    return state, reference


def run_browser_side(state: dict, keep_path: Path | None) -> dict:
    node = shutil.which("node")
    if not node:
        print("[crosscheck] 环境缺失：找不到 node（浏览器侧观测构建器需要 Node 运行）", file=sys.stderr)
        raise SystemExit(2)
    if keep_path is None:
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        handle.write(json.dumps(state))
        handle.close()
        state_path = Path(handle.name)
    else:
        state_path = keep_path
        state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    completed = subprocess.run(
        [node, str(ROOT / "tools" / "obs_crosscheck.mjs"), str(state_path)],
        capture_output=True, text=True, encoding="utf-8", timeout=180,
    )
    if completed.returncode != 0 and not completed.stdout.strip():
        print(f"[crosscheck] 浏览器侧执行失败（exit {completed.returncode}）：\n{completed.stderr[-2000:]}",
              file=sys.stderr)
        raise SystemExit(2)
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    if not payload.get("ok"):
        print(f"[crosscheck] 浏览器侧报错：{payload.get('error')}", file=sys.stderr)
        raise SystemExit(2)
    return payload


def compare(tag: str, mine: list[float], theirs: list[float], tol: float) -> tuple[float, str]:
    """逐维比对，返回 (max|Δ|, 最差维描述)。长度不等直接判失败。

    **NaN 单列**：浏览器侧观测是 Float32Array，`JSON.stringify` 把 NaN/Infinity 写成
    `null` ⇒ 到这边就是 `None`。原先直接 `float(None)` 抛 `TypeError`（工具自己崩，
    报告里只剩一段 traceback，看不出"是谁、第几维、什么值"）——而 NaN 恰恰**必须**
    报出来：它意味着构建器吃到了缺输入（实测 `g1_mjlab_velocity_98` 就是相位钟的
    `simulationDt` 没喂 ⇒ `Math.sin(NaN)`）。现在：非有限值单独成句、指名维号，
    并且**优先于**数值差报告（有 NaN 时"最大差"没有意义）。
    """
    if len(mine) != len(theirs):
        return math.inf, f"长度不一致：验收器 {len(mine)} vs 浏览器 {len(theirs)}"
    nonfinite = [i for i, b in enumerate(theirs)
                 if b is None or not math.isfinite(float(b))]
    if nonfinite:
        head = ", ".join(f"[{i}]={theirs[i]!r}" for i in nonfinite[:8])
        more = f"（共 {len(nonfinite)} 维）" if len(nonfinite) > 8 else ""
        return math.inf, (f"{tag} 浏览器侧出现**非有限值**（NaN/Inf，JSON 里是 null）：{head}{more}"
                          f" ⇒ 构建器吃到了缺输入，先查状态包里该喂的字段（不是「两份实现差一步」）")
    worst_nonfinite = [i for i, a in enumerate(mine)
                       if a is None or not math.isfinite(float(a))]
    if worst_nonfinite:
        head = ", ".join(f"[{i}]={mine[i]!r}" for i in worst_nonfinite[:8])
        return math.inf, f"{tag} 验收器侧出现**非有限值**：{head}（先查验收器，不是浏览器）"
    worst, at = 0.0, -1
    for i, (a, b) in enumerate(zip(mine, theirs)):
        delta = abs(float(a) - float(b))
        if delta > worst:
            worst, at = delta, i
    detail = f"[{at}] 验收器 {mine[at]:+.6f} vs 浏览器 {theirs[at]:+.6f}" if at >= 0 else "—"
    return worst, f"{tag} 最差维 {detail}"


def check_one(engine, robot: str, policy: str, yaw_deg: float, tol: float,
              keep: Path | None = None, quiet: bool = False) -> tuple[int, str]:
    """对拍**一条**策略，返回 `(退出码, 一句话结论)`。quiet=批量模式（只打一行）。"""
    package_dir = ROOT / "assets" / "robots" / robot
    if not (package_dir / "simulation" / "config.json").is_file():
        print(f"[crosscheck] 找不到机型包：{package_dir}", file=sys.stderr)
        return 2, "找不到机型包"
    sim_cfg = json.loads((package_dir / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
    entry = next((e for e in (sim_cfg.get("policies") or []) if e.get("id") == policy), None)
    if entry is None:
        print(f"[crosscheck] {robot} 里没有策略 id={policy}", file=sys.stderr)
        return 2, "没有该策略"
    # 声明为**不可仿真**的策略（`sim_ready:false` + `sim_blocker`）本来就没有浏览器
    # builder —— 如实报"不适用"，不要让它以"浏览器拒绝"的形态冒充一条红（也不是绿）。
    if entry.get("sim_ready") is False:
        reason = str(entry.get("sim_blocker") or "未写 sim_blocker")
        if not quiet:
            print("=" * 74)
            print(f"同状态观测对拍：{robot} / {policy}")
            print(f"  ⏭ 声明 `sim_ready:false`，浏览器侧没有 builder，本工具不适用：{reason}")
        return 2, f"声明 sim_ready:false（{reason[:48]}…）"

    try:
        state, reference = build_state(engine, package_dir, sim_cfg, entry, yaw_deg)
    except SystemExit as exc:                       # 需 MotionLoader/复合命令 ⇒ 本工具不适用
        return int(exc.code or 2), "需 MotionLoader/复合命令，本工具不适用"
    except ValueError as exc:
        # 验收器侧没有该 kind 的布局（如产物-only 声明的 `kind='unknown'`）⇒ **不是**
        # "两份实现不一致"，而是"这条策略没有可比的那一层"。如实报"不适用"（退出码 2），
        # 既不伪装成绿，也不把它算成红。
        return 2, f"验收器没有该布局（{exc}）"
    try:
        browser = run_browser_side(state, keep)
    except SystemExit as exc:
        # 浏览器侧**主动拒绝**（如某 kind 没有 builder）⇒ 同上按"不适用"处理，
        # 不能让一条不适用把批量跑打断（原先 SystemExit 会直接结束 --all 的循环）。
        return int(exc.code or 2), "浏览器侧拒绝（没有该 kind 的 builder）"

    kind = state["contract"]["observation_kind"]
    if not quiet:
        print("=" * 74)
        print(f"同状态观测对拍：{robot} / {policy}")
        print(f"  kind={kind}  obs={state['contract']['obs_dim']}  history={state['contract']['history_len']}"
              f"  yaw={yaw_deg:g}°  容差={tol:g}")
        print(f"  对比基准：{reference.get('compare_basis') or '整向量'}")
        print("-" * 74)

    failures: list[str] = []
    imu_info = state.get("imu_comparable") or {"ok": True, "reason": ""}
    if not quiet:
        print("① IMU 采样（喂进观测的那一组；浏览器 = utils.js::imuSampleFromQpos）")
    if not imu_info.get("ok"):
        # 不可比 ⇒ **不参与判定**（既不算红，也不能算绿：如实说"没测这一段"）。
        if not quiet:
            print(f"  [SKIP] 不适用：{imu_info.get('reason')}")
    else:
        for name in ("angular", "linear", "gravity", "rpy"):
            worst, detail = compare(name, reference["imu"][name], browser["imu"][name], tol)
            flag = "OK  " if worst <= tol else "FAIL"
            if not quiet:
                print(f"  [{flag}] {name:<8} max|Δ|={worst:.3e}   {detail}")
            if worst > tol:
                failures.append(f"IMU.{name}: max|Δ|={worst:.3e}（{detail}）")

    obs_worst, obs_detail = compare("obs", reference["obs"], browser["obs"], tol)
    if not quiet:
        print("② 整条观测（逐维；段名按通例标注，仅作定位提示）")
        for name, lo, hi in segments_for(state["contract"],
                                         action_dim=state["contract"]["action_dim"],
                                         command_dims=state["contract"]["command_dims"]):
            if hi > len(reference["obs"]):
                continue
            seg_worst, _ = compare(name, reference["obs"][lo:hi], browser["obs"][lo:hi], tol)
            print(f"  [{'OK  ' if seg_worst <= tol else 'FAIL'}] {name:<8} max|Δ|={seg_worst:.3e}")
        print(f"  [{'OK  ' if obs_worst <= tol else 'FAIL'}] 全向量   max|Δ|={obs_worst:.3e}")
    if obs_worst > tol:
        failures.append(f"obs: max|Δ|={obs_worst:.3e}（{obs_detail}）")

    if failures:
        if not quiet:
            print("-" * 74)
            print(f"✗ 两份实现**不一致** {len(failures)} 处：")
            for item in failures:
                print(f"  - {item}")
            print("  ⇒ 浏览器与验收器差一步（历史上正是这类缺陷造成\"转 180° 抽风\"）")
        return 1, f"max|Δ|={obs_worst:.3e}（{obs_detail}）"
    if not quiet:
        print("-" * 74)
        print("✓ 一致：同一状态、同一条观测，两份实现逐维相同")
    return 0, f"max|Δ|={obs_worst:.3e}"


def _all_targets() -> list[tuple[str, str]]:
    """全部"机型 / 策略"对（只含声明了 `policies` 的包，按名字排序 ⇒ 输出可比对）。"""
    targets: list[tuple[str, str]] = []
    for config_path in sorted((ROOT / "assets" / "robots").glob("*/simulation/config.json")):
        robot = config_path.parents[1].name
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        for entry in cfg.get("policies") or []:
            if isinstance(entry, dict) and entry.get("id"):
                targets.append((robot, str(entry["id"])))
    return targets


def main() -> int:
    parser = argparse.ArgumentParser(description="同状态观测对拍（验收器 ↔ 浏览器观测构建器）")
    parser.add_argument("--robot", default="unitree_go2")
    parser.add_argument("--policy", default="go2-rlsar-robotlab")
    parser.add_argument("--all", action="store_true",
                        help="遍历所有机型的全部声明策略（每条一行；有红即退出码 1）——"
                             "**门禁用法**：新增/改动任何观测布局实现后都该跑一遍")
    parser.add_argument("--yaw-deg", type=float, default=180.0, help="机身 yaw（默认 180°：两份实现差异最大的地方）")
    parser.add_argument("--tol", type=float, default=1e-5, help="逐维容差（两侧都是 Float32，~1e-7 量级是表示误差）")
    parser.add_argument("--keep", type=Path, default=None, help="保留中间 JSON 到此路径（排查用）")
    args = parser.parse_args()

    engine = load_engine()
    if not args.all:
        code, _ = check_one(engine, args.robot, args.policy, args.yaw_deg, args.tol, args.keep)
        return code

    counts = {"ok": 0, "fail": 0, "skip": 0}
    reds: list[str] = []
    print(f"全量对拍：{len(_all_targets())} 条声明策略（容差 {args.tol:g}，yaw {args.yaw_deg:g}°）")
    print("-" * 74)
    for robot, policy in _all_targets():
        code, note = check_one(engine, robot, policy, args.yaw_deg, args.tol, None, quiet=True)
        if code == 0:
            counts["ok"] += 1
            mark = "OK  "
        elif code == 2:
            counts["skip"] += 1
            mark = "SKIP"
        else:
            counts["fail"] += 1
            mark = "FAIL"
            reds.append(f"{robot}/{policy}：{note}")
        print(f"[{mark}] {robot}/{policy:<34} {note}")
    print("-" * 74)
    print(f"汇总：{counts['ok']} 一致 / {counts['fail']} 不一致 / {counts['skip']} 不适用"
          f"（共 {sum(counts.values())} 条）")
    for item in reds:
        print(f"  ✗ {item}")
    return 1 if counts["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
