"""mjswan 四输入 RNN（robust / vanilla / facet）"**站得住但不走**"的逐因素排查探针。

## 为什么要这个工具（而不是继续拍脑袋）

§P-1 的 #2/#3 卡在"链路跑通、能站住、但命令响应极弱"（vx=0.3→0.006 m、vx=1.0→0.087 m、
vx=2.0→0.318 m 后摔）。已排除的假设（`is_init` 语义 / 输出索引 / 采样 vs 均值 / 初始姿态 /
张量 rank）留着 3 类**未逐项 A/B** 的自由度；而"差一步"型的口径错误**不会抛异常**，
只会表现为"策略像没听见命令"——即本缺陷的形状。所以做成一键探针：

* 每个变体只动**一处**（一因素一测），跑同一命令、同一时长，输出**前进距离 / 存活 / 倾角**；
* 基线必须复现已知症状（否则探针本身有问题，先修探针）；
* 结论只认"哪一处改动让策略真的走起来"，不认"看起来更像"。

真值来源（都在快照内，**只读、不落库**）：
* `00_resources/mjswan/examples/demo/main.py`（官方 demo 配置：`JointPositionActionCfg(
  scale=0.5, stiffness=25.0, damping=0.5)`、`control_dt=0.02`、`in_keys/out_keys`、
  `history_steps=(0,1,2)`、`velocity_cmd(3) + velocity_command_padding(13 零)`）；
* `…/assets/unitree_go2/{robust,vanilla,facet}.onnx|.json`（产物自带 `policy_joint_names`
  与 `default_joint_pos`）。

用法：
    python tools/probe_mjswan_variants.py                       # 全部变体
    python tools/probe_mjswan_variants.py --variants cmd_raw,gains_demo --seconds 8
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "adapters" / "mjlab" / "policy_acceptance.py"
DEFAULT_ASSETS = ROOT / "00_resources" / "mjswan" / "examples" / "demo" / "assets" / "unitree_go2"
PACKAGE = ROOT / "assets" / "robots" / "unitree_go2"
#: 探针合成契约时借用的**已有**策略条目（拿到该包已核对的 control/actuator 真值，不另抄一份）。
TEMPLATE_POLICY_ID = "go2-moe-cts"


def load_engine():
    spec = importlib.util.spec_from_file_location("policy_acceptance_for_probe", ENGINE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_entry(engine, assets: Path, onnx: str) -> dict[str, Any]:
    """合成一条**只在内存里**的策略条目（仓库零副作用）——真值取自产物 JSON + 官方 demo。"""
    # `utf-8-sig`：**有 BOM 的 JSON 读之前先 strip**（仓库口径，见 backend/test_jsonio_single_source.py）
    meta = json.loads((assets / f"{Path(onnx).stem}.json").read_text(encoding="utf-8-sig"))
    names = [str(n) for n in meta["policy_joint_names"]]
    defaults = [float(v) for v in meta["default_joint_pos"]]
    sim_cfg = json.loads((PACKAGE / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
    template = next(e for e in sim_cfg["policies"] if e.get("id") == TEMPLATE_POLICY_ID)
    entry = json.loads(json.dumps(template))          # 深拷贝模板（含包级 control/actuator 真值）
    entry["id"] = f"probe-{Path(onnx).stem}"
    entry["label"] = f"probe {onnx}"
    entry["obs_dim"] = 117
    entry["action_dim"] = len(names)
    # 包内（= 模型 MJCF 的）关节序：观测侧的候选顺序之一（见 `obs_model_order` 变体）
    entry["_probe_model_joint_order"] = list(template["contract"].get("action_joint_order") or [])
    contract = entry["contract"]
    contract.update({
        "observation_kind": "go2_mjswan_velocity",
        "obs_dim": 117,
        "action_dim": len(names),
        "action_joint_order": names,
        "default_joint_angles": dict(zip(names, defaults)),
        # 官方 demo：`JointPositionActionCfg(scale=0.5, stiffness=25.0, damping=0.5)`
        "action_scale": 0.5,
        "control": {"stiffness": {"": 25.0}, "damping": {"": 0.5}},
        # `command_` 槽 = `velocity_cmd` 原值（mjswan 的 `generated_commands` 不做缩放）+ 13 零
        "cmd_scale": [1.0, 1.0, 1.0],
        "onnx_slots": {"inputs": ["actor", "is_init", "adapt_hx", "command_"]},
        "history_len": 1,
    })
    return entry


def _history_class(engine, *, frame_order: str, interleave_order: str, terms=None):
    """按变体生成 actor 历史打包类（默认＝现实现：逐 term、每帧 新→旧、交错内 新→旧）。"""

    class _VariantHistory(engine._MjswanActorHistory):
        @property
        def array(self) -> np.ndarray:
            frames = self._frames if frame_order == "newest_first" else list(reversed(self._frames))
            chunks: list[float] = []
            offset = 0
            for _name, dim, interleaved in (terms or engine._MJSWAN_ACTOR_TERMS):
                width = dim or self._action_dim
                if interleaved:
                    order = frames if interleave_order == "newest_first" else list(reversed(frames))
                    for j in range(width):
                        for frame in order:
                            chunks.append(float(frame[offset + j]))
                else:
                    for frame in frames:
                        chunks.extend(float(v) for v in frame[offset:offset + width])
                offset += width
            return np.asarray(chunks, dtype=np.float32)

    return _VariantHistory


#: 变体 → 只动一处。键名与 `apply_variant` 对应。
VARIANTS: dict[str, dict[str, Any]] = {
    "baseline": {},
    # 命令槽：上游 `generated_commands` 给**原值**；若契约里带着 go2 惯用的 [2,2,0.25] 就会错
    "cmd_raw": {"cmd_scale": [1.0, 1.0, 1.0]},
    # 动作口径
    "action_scale_0.5": {"action_scale": 0.5},
    "action_scale_0.25": {"action_scale": 0.25},
    "no_default_offset": {"no_default_offset": True},
    # 增益（官方 demo：kp=25 / kd=0.5 全关节一致）
    "gains_demo": {"stiffness": {"": 25.0}, "damping": {"": 0.5}},
    # 历史口径（两类方向各自可 A/B）
    "hist_oldest_first": {"frame_order": "oldest_first"},
    "hist_interleave_oldest_first": {"interleave_order": "oldest_first"},
    # **观测关节序 vs 动作关节序**：产物 JSON 的 `policy_joint_names` 是 **type-major**
    # （全部 hip → thigh → calf），而包内 MJCF 的动作序是 **leg-major**（每条腿 3 关节相邻）。
    # 若 mjswan 运行时的观测用**模型序**、动作才用 policy 序，则两者不同 ⇒ 观测里 12 个关节
    # 落到别的槽（策略看到错姿态 ⇒ 输出"安全"的定常动作 ⇒ 站得住但不走）。
    "obs_model_order": {"obs_joint_order": "model"},
    # **闭环保守不动点**：站住 ⇒ 观测恒定 ⇒ 动作恒定 ⇒ 继续站住。这一族策略是 RNN，
    # 内部没有"自走起来的时钟"（13 个 oscillator 槽上游也是零占位）⇒ 若出生态正好落在
    # 静止不动点上，它会一直站着。给一点**初始前进速度**看它是否随即进入步态：若能，
    # 说明"不走"是**出生态/固定点**问题（部署侧），不是这份移植规格错。
    "push_0.5": {"push_vx": 0.5},
    "push_1.0": {"push_vx": 1.0},
    # **模型保真度**：用官方 demo 自带的 `go2.xml`/`scene.xml`（就是它 trace env 的那份）
    # 跑同一个 onnx。这一条把"控制回路/观测口径"与"包内模型保真度"彻底分开。
    "mjswan_model": {"model_dir": None},   # 由 main 填成 --assets 目录（避免硬编码路径）
    # **出生态**：官方 `go2.xml` 的 keyframe `home` 是 **z=0.27 / 每腿 [0, 0.9, −1.8]**
    # （unitree 蹲姿），而包内初高是 **0.445**、且我们主动把关节对到**策略默认姿**
    # （hip ±0.1 / thigh 0.7 / calf −1.5）。两者差 17.5 cm ⇒ 出生即"从空中落下"
    # （trace 首拍 |dq|max=10 rad/s），RNN 的自适应隐状态被这一下冲坏、随后收敛到
    # "站住不动"的定点。这三条把**高度**与**姿态**两个因素分开测：
    "init_h027_keyframe": {"init_z": 0.27, "init_pose": "keyframe"},
    "init_h027_default": {"init_z": 0.27, "init_pose": "policy_default"},
    "init_h035_default": {"init_z": 0.35, "init_pose": "policy_default"},
    "init_h044_default": {"init_z": 0.44, "init_pose": "policy_default"},   # = 现状
    # **actor 内 term 顺序**：main.py 的 dict 序（gravity, q, dq, action）与"按名排序"
    # （joint_pos, joint_vel, prev_actions, projected_gravity）差一个整体循环位移。
    # 若运行时会排序（dict→JSON→sorted 之类的实现细节），我们的 117 就是"错位一整个段"。
    "term_order_alpha": {"terms": "alpha"},
    # **增益量级**：trace 显示关节被重力拉出 0.25 rad 的稳态误差（kp=25 ⇒ τ≈6 N·m），
    # 即"腿撑住但软"。若策略其实是按更高刚度训练的（或 mjswan 的 stiffness 与 XML 增益
    # 是**叠加**关系），提高 kp 应当能把定点从"站住"推成"走"。扫一遍看有无单调趋势。
    "gains_kp50": {"stiffness": {"": 50.0}},
    "gains_kp100": {"stiffness": {"": 100.0}},
    "gains_legged_gym": {"stiffness": {"hip": 20.0, "thigh": 20.0, "calf": 40.0},
                          "damping": {"hip": 0.5, "thigh": 0.5, "calf": 1.0}},
}


def apply_variant(engine, contract, variant: dict[str, Any], onnx: str, assets: Path,
                  entry: dict[str, Any] | None = None):
    """把变体落到契约/历史类上，返回本次要用的历史类。"""
    if "cmd_scale" in variant:
        contract.cmd_scale = list(variant["cmd_scale"])
    if "action_scale" in variant:
        contract.action_scales = [float(variant["action_scale"])] * contract.action_dim
    if variant.get("no_default_offset"):
        contract.default_for = lambda name: 0.0  # noqa: ARG005 —— 变体：目标 = action×scale
    for key in ("stiffness", "damping"):
        if key in variant:
            setattr(contract, key, variant[key])
    if "init_z" in variant or "init_pose" in variant:
        original_spawn2 = engine.spawn_default
        z = float(variant.get("init_z", 0.0))
        pose = str(variant.get("init_pose", "policy_default"))
        # 官方 keyframe 的每腿姿态（顺序无关：按**名字后缀**落值）
        keyframe = {"hip": 0.0, "thigh": 0.9, "calf": -1.8}

        def _spawn3(contract, model, data, obs, _orig=original_spawn2, _z=z, _pose=pose):
            _orig(contract, model, data, obs)
            import mujoco as _mj
            if _z:
                data.qpos[2] = _z
            if _pose == "keyframe":
                for name in contract.action_joint_order:
                    for suffix, value in keyframe.items():
                        if name.lower().endswith(f"{suffix}_joint"):
                            data.qpos[obs.jadr[name][0]] = value
            _mj.mj_forward(model, data)

        engine.spawn_default = _spawn3
    if variant.get("push_vx"):
        original_spawn = engine.spawn_default
        push = float(variant["push_vx"])

        def _spawn(contract, model, data, obs, _orig=original_spawn, _v=push):
            _orig(contract, model, data, obs)
            data.qvel[0] = _v            # 世界系 x 方向初速（机身朝 +x）
            import mujoco as _mj
            _mj.mj_forward(model, data)

        engine.spawn_default = _spawn
    if variant.get("obs_joint_order") == "model":
        model_order = list((entry or {}).get("_probe_model_joint_order") or [])
        assert model_order, "缺少包内（模型）关节序，无法跑 obs_model_order 变体"

        def _frame(obs, _order=model_order):
            q = obs.data.qpos[3:7]
            out = [float(v) for v in engine.projected_gravity(q)]
            out += [float(obs.data.qpos[obs.jadr[n][0]] - obs.contract.default_for(n)) for n in _order]
            out += [float(obs.data.qvel[obs.jadr[n][1]]) for n in _order]
            out += [float(v) for v in obs.last_action]
            return np.asarray(out, dtype=np.float32)

        engine._mjswan_actor_frame = _frame              # 观测用模型序；动作仍按 policy 序
        # 注意：默认角按**名字**取，与顺序无关；故这里只换顺序，不换数值来源。
    terms = None
    if variant.get("terms") == "alpha":
        by_name = {name: (name, dim, inter) for name, dim, inter in engine._MJSWAN_ACTOR_TERMS}
        terms = [by_name[k] for k in sorted(by_name)]     # joint_pos, joint_vel, prev_actions, projected_gravity
    return _history_class(
        engine,
        frame_order=variant.get("frame_order", "newest_first"),
        interleave_order=variant.get("interleave_order", "newest_first"),
        terms=terms,
    )


def command_sensitivity(engine, sess, entry, slots, onnx: str, assets: Path) -> int:
    """**命令灵敏度**：静态姿态 + 固定 actor 历史，只改 `command_` 槽，看网络输出动多少。

    这是把"策略不走"二分的最快一刀：
      · 输出随命令**明显变化** ⇒ 命令槽与其位置都是对的，问题在**动力学/观测**那一侧；
      · 输出几乎不动 ⇒ 槽位/顺序/缩放错了（网络没听见命令）——继续 A/B 该槽。
    """
    import mujoco

    sim_cfg = json.loads((PACKAGE / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
    in_names = [str(i.name) for i in sess.get_inputs()]
    print(f"命令灵敏度（{onnx}）：静态姿态下只改命令槽，看输出动多少")
    print("-" * 86)
    print(f"{'command_ 前 3 维':<28}{'|a| 均值':>10}{'|Δa| vs 零命令':>16}   动作前 4 维")
    rows: list[np.ndarray] = []
    for cmd in ([0.0, 0.0, 0.0], [0.5, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]):
        contract = engine.PackageContract(PACKAGE, entry)
        contract.motion_loader = None
        model = engine.load_package_model(PACKAGE, sim_cfg, None,
                                         scene_rel=contract.contract.get("scene_path"))
        model.opt.timestep = 1.0 / float(contract.physics_hz)
        data = mujoco.MjData(model)
        obs = engine.ObsBuilder(contract, model, data)
        engine.spawn_default(contract, model, data, obs)
        for name in contract.action_joint_order:
            data.qpos[obs.jadr[name][0]] = contract.default_for(name)
        mujoco.mj_forward(model, data)
        obs.last_action = np.zeros(contract.action_dim, dtype=np.float32)
        history = engine._MjswanActorHistory(3 + 3 * contract.action_dim, contract.action_dim)
        history.append(engine._mjswan_actor_frame(obs))
        values = {
            "actor": history.array.reshape(1, -1),
            "is_init": np.asarray([True], dtype=bool),
            "adapt_hx": np.zeros((1, engine._MJSWAN_RECURRENT_DIM), dtype=np.float32),
            "command_": np.concatenate(
                [np.asarray(cmd, dtype=np.float32), np.zeros(engine._MJSWAN_COMMAND_PAD, dtype=np.float32)]
            ).reshape(1, -1),
        }
        outs = sess.run(None, {in_names[i]: values[slot] for i, slot in enumerate(slots)})
        action = np.asarray(outs[engine._MJSWAN_ACTION_OUTPUT], dtype=np.float32).reshape(-1)
        rows.append(action)
        delta = float(np.linalg.norm(action - rows[0])) if len(rows) > 1 else 0.0
        print(f"{str(cmd):<28}{float(np.abs(action).mean()):>10.4f}{delta:>16.4f}   "
              f"{np.round(action[:4], 3).tolist()}")
    print("-" * 86)
    spread = float(np.max([np.linalg.norm(a - rows[0]) for a in rows[1:]])) if len(rows) > 1 else 0.0
    if spread > 0.5:
        print(f"⇒ 输出随命令**明显变化**（最大 |Δa|={spread:.3f}）：命令槽与位置是对的，"
              f"问题不在「没听见命令」，往**动力学/观测历史**那一侧查。")
    else:
        print(f"⇒ 输出几乎不随命令变（最大 |Δa|={spread:.3f}）：网络没听见命令 ⇒ 先查 "
              f"`command_` 槽的内容/顺序/缩放（探针的 cmd_* 变体正是干这个的）。")
    return 0


def trace_rollout(engine, sess, entry, slots, onnx: str, args) -> int:
    """逐拍取数：**动作多大 / 关节跟不跟得上 / 轮子转不转 / 走没走**。

    "站得住但不走"的定位必须看这四件事的**同时**读数：动作大而关节跟不上 ⇒ 增益/限幅；
    关节跟得上而机身不动 ⇒ 接触/几何；动作本来就小 ⇒ 观测或回路。
    """
    import mujoco

    sim_cfg = json.loads((PACKAGE / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
    contract = engine.PackageContract(PACKAGE, entry)
    contract.motion_loader = None
    model = engine.load_package_model(PACKAGE, sim_cfg, None,
                                     scene_rel=contract.contract.get("scene_path"))
    model.opt.timestep = 1.0 / float(contract.physics_hz)
    data = mujoco.MjData(model)
    obs = engine.ObsBuilder(contract, model, data)
    order = contract.action_joint_order
    rows: list[str] = []

    def on_step(step, model, data, obs, action, forward):
        if step % 25:
            return
        target = np.array([float(action[i]) * contract.action_scales[i] + contract.default_for(n)
                           for i, n in enumerate(order)])
        q = np.array([float(data.qpos[obs.jadr[n][0]]) for n in order])
        tau = np.array([float(data.ctrl[engine.actuator_for_joint(model, n)]) for n in order])
        rows.append(
            f"t={step * engine._MJSWAN_CONTROL_DT:5.2f}s  x={forward:6.3f}  z={data.qpos[2]:5.3f}  "
            f"|a|={float(np.abs(action).mean()):.3f}  跟踪|q−target|max={float(np.abs(q - target).max()):.3f}  "
            f"|τ|max={float(np.abs(tau).max()):6.2f}  |dq|max={float(np.abs(data.qvel[6:]).max()):5.2f}"
        )

    metrics = engine.run_mjswan_policy(
        sess, contract, model, data, obs, [args.vx, 0.0, 0.0], args.seconds, 0,
        slots=slots, on_step=on_step,
    )
    print(f"逐拍trace（{onnx}  vx={args.vx:g}）：")
    print("\n".join(rows[:40]))
    print(f"metrics: {json.dumps({k: metrics[k] for k in ('forward_max_m', 'survival_ratio', 'tilt_max_deg', 'height_min')}, ensure_ascii=False)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="mjswan 四输入 RNN 逐因素排查探针")
    parser.add_argument("--onnx", default="robust.onnx", help="产物名（robust/vanilla/facet）")
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument("--vx", type=float, default=1.0)
    parser.add_argument("--variants", default=",".join(VARIANTS))
    parser.add_argument("--mode", choices=("rollout", "sensitivity", "trace", "all"), default="rollout")
    args = parser.parse_args()

    import mujoco
    import onnxruntime as ort

    engine = load_engine()
    onnx_path = args.assets / args.onnx
    if not onnx_path.is_file():
        print(f"[probe] 找不到产物：{onnx_path}", file=sys.stderr)
        return 2
    sim_cfg = json.loads((PACKAGE / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
    entry = make_entry(engine, args.assets, args.onnx)
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    slots = tuple(entry["contract"]["onnx_slots"]["inputs"])

    if args.mode in ("sensitivity", "all"):
        code = command_sensitivity(engine, sess, entry, slots, args.onnx, args.assets)
        if args.mode == "sensitivity":
            return code
        print()
    if args.mode in ("trace", "all"):
        code = trace_rollout(engine, sess, entry, slots, args.onnx, args)
        if args.mode == "trace":
            return code
        print()

    print(f"探针：{args.onnx}  vx={args.vx:g}  {args.seconds:g}s  "
          f"（官方 demo 真值：scale=0.5 / kp=25 / kd=0.5 / cmd 原值 + 13 零）")
    print("-" * 86)
    print(f"{'变体':<30}{'前进(m)':>10}{'存活':>8}{'倾角max':>10}{'终点基高':>10}  结论")
    original_frame = engine._mjswan_actor_frame
    original_history = engine._MjswanActorHistory
    original_spawn = engine.spawn_default
    VARIANTS["mjswan_model"]["model_dir"] = str(args.assets)   # 官方 demo 自带的模型目录
    for name in [v.strip() for v in args.variants.split(",") if v.strip()]:
        if name not in VARIANTS:
            print(f"{name:<30} 未知变体（可用：{', '.join(VARIANTS)}）")
            continue
        variant = VARIANTS[name]
        # 变体之间必须**互相隔离**：上一轮打过补丁的帧函数/历史类先还原，否则后一个变体会
        # 叠在前一个上，读数看着像"都差不多"（实测第一轮就是这么被糊住的）。
        engine._mjswan_actor_frame = original_frame
        engine._MjswanActorHistory = original_history
        engine.spawn_default = original_spawn
        contract = engine.PackageContract(PACKAGE, entry)
        contract.motion_loader = None
        history_cls = apply_variant(engine, contract, variant, args.onnx, args.assets, entry)
        engine._MjswanActorHistory = history_cls          # 变体只在探针里生效
        if variant.get("model_dir"):
            # 用**官方 demo 自己的**模型/场景跑（mjswan 的 trace env 就是 `go2.xml`）：
            # 若"同一份策略 + 官方模型"能走、换回包内模型就不走 ⇒ 症结在**模型保真度**
            # （armature / frictionloss / damping / 几何），不在控制回路与观测口径。
            model = mujoco.MjModel.from_xml_path(str(Path(variant["model_dir"]) / "scene.xml"))
        else:
            model = engine.load_package_model(PACKAGE, sim_cfg, None,
                                             scene_rel=contract.contract.get("scene_path"))
        model.opt.timestep = 1.0 / float(contract.physics_hz)
        data = mujoco.MjData(model)
        obs = engine.ObsBuilder(contract, model, data)
        metrics = engine.run_mjswan_policy(
            sess, contract, model, data, obs, [args.vx, 0.0, 0.0], args.seconds, 0, slots=slots,
        )
        ok = (not metrics["fell"]) and metrics["forward_max_m"] >= 0.3
        print(f"{name:<30}{metrics['forward_max_m']:>10.3f}"
              f"{metrics['survival_ratio']:>8.2f}{metrics['tilt_max_deg']:>10.1f}"
              f"{metrics.get('height_steady', float('nan')) or float('nan'):>10.3f}"
              f"  {'✓ 走起来了' if ok else ''}")
    print("-" * 86)
    print("读法：基线应复现\"站得住但不走\"；哪个变体的前进距离跳到米级，那一处口径就是真因。")
    print("注意：本工具**不改仓库任何文件**（条目只在内存里合成），产物也不入库。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
