"""L1：无头 frame log 产出端 —— 把"逐帧日志"从浏览器控制台搬进可自动跑的引擎。

## 用法（**在适配器 venv 里跑**，需要 mujoco/onnxruntime）

    $LEGGED_STUDIO_MJLAB_VENV/bin/python adapters/mjlab/frame_log.py \
        --package assets/robots/zex-w \
        --policy simulation/policies/<policy_id>.onnx \
        --cmd 0.4,0,0 --seed 7 --steps 100 --out /tmp/frame-log-a.json

产出与 `web/sim2sim/app.js` 的 `frameLog` **同形**：

    {"head": {...}, "frames": [{"t", "stepIndex", "obs", "action", "ctrlBefore",
                                "targetsPos", "targetsVel", "actuatorIds"}]}

`adapters/mjlab/replay_determinism.compare_frame_logs()` / `tools/replay_gate.py` 直接吃，
无需任何转换。

## 为什么必须有它（L1 的已登记缺口）

此前 frame log 的**唯一**产出路径是浏览器控制台（`__sim2simDebug.startFrameLog()` →
人工复制 JSON），于是三件事同时卡住：

* 确定性回放门禁（G2）拿不到两份**可自动比较**的日志 —— 只能靠人开浏览器跑两遍；
* B12 的 **R2（复现"用"：重跑评测得同一分数）只能标 `blocked`**；
* **L3**（seed / 域随机化进日志）没有承载体。

## 与 B0（`tools/sim2sim_headless.py`）的分工

两者**同源不同责**，都建在 `policy_acceptance` 的契约驱动观测/执行语义上：

* B0 = **聚合判据**：这条策略站不站得住、能不能完成速度跟踪/模仿/特技（出"通过/失败"）；
* 本模块 = **逐帧日志**：把每一控制步的 obs / action / 目标原样落盘，供**确定性对拍**与复现证据 ——
  R2 要的"两次跑逐帧一致"，聚合指标说不了。

## 口径与诚实边界

* **不另写一套仿真**：直接复用验收同源原语（`policy_acceptance` 的
  `PackageContract` / `ObsBuilder` / `spawn_default` / `actuate`），与浏览器、桌面验收同链路；
* `spawn_default` 是**确定性重置**（默认姿态 + 契约初始高度），本路径**不做域随机化** ⇒
  日志头如实写 `randomization.applied = false`（**DR 属训练侧 L3 的缺口，不在验收路径假装有**）；
* `seed` 照实写进日志头（`head.seed`）：它现在约束的是"本身带随机量的验收模式"
  （如 Wuji 重定向的随机目标朝向，见 `policy_acceptance.run_wuji_reorient`）——
  一旦 L3 把 DR 接进来，这里就是**现成的承载体**；
* 日志头带**适配器环境快照**（python / mujoco / onnxruntime / numpy 版本 + 策略 sha256）：
  跨机对账时"环境不同"要看得见，而不是变成一个说不清的数字差。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from policy_acceptance import (  # noqa: E402
    ObsBuilder,
    PackageContract,
    actuate,
    actuator_for_joint,
    load_package_model,
    spawn_default,
)

FRAME_LOG_SCHEMA = "frame-log-1.0"
ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def resolve_policy_entry(sim_config: dict[str, Any], policy_id: str | None) -> dict[str, Any]:
    policies = sim_config.get("policies") or []
    if not policies:
        raise SystemExit("simulation/config.json 里没有 policies[]，无法确定要跑哪条策略")
    if policy_id is None:
        return dict(policies[0])
    for entry in policies:
        if str(entry.get("id")) == policy_id:
            return dict(entry)
    raise SystemExit(f"包内没有策略 {policy_id!r}；可用：{[p.get('id') for p in policies]}")


def resolve_policy(
    package_dir: Path, entry: dict[str, Any], explicit: str | None,
) -> tuple[Path, str | None, dict[str, Any]]:
    """解析要跑的策略文件 —— **复用后端同一解析器**（`policy_artifacts.policy_blob_path`，B10）。

    为什么不在这里另写一套规则：策略条目可能**只留 `id`**（源路径与 hash 在 `policies/index.json`），
    "id → 文件"的映射只能有**一个**真值源 —— 浏览器 URL、验收脚本、本产出端都走它。
    本文件初版按 `path/onnx` 字段猜，结果 zex-w 这类"只留 id"的包一条都解析不出来
    （也正是"名字是 A、跑的是 B"这类静默错标的温床）。

    返回 ``(文件路径, 声明的包内相对路径)``；``--policy`` 显式指定时用它，但声明路径仍如实返回，
    由调用方判断"跑的是不是声明的那一个"。
    """

    sys.path.insert(0, str(ROOT))
    from backend.policy_artifacts import policy_blob_path

    declared = policy_blob_path(entry, robot_dir=package_dir)
    declared_rel: str | None = None
    if declared is not None:
        try:
            declared_rel = declared.resolve().relative_to(package_dir.resolve()).as_posix()
        except ValueError:
            declared_rel = None

    if explicit:
        candidate = Path(explicit)
        path = (candidate if candidate.is_absolute() else package_dir / candidate).resolve()
        mode = "explicit"
    elif declared is not None:
        path = declared.resolve()
        mode = "declared_or_index"
    else:
        raise SystemExit(
            f"解析不到策略文件（条目 id={entry.get('id')!r}）：策略声明里没有可用路径，"
            "出库索引也没有对应条目 —— 请用 --policy 显式指定"
        )
    if not path.is_file():
        raise SystemExit(f"策略文件不存在：{path}")
    try:
        inside = path.relative_to(package_dir.resolve()).as_posix()
    except ValueError:
        inside = None
    return path, declared_rel, {"mode": mode, "inside_package": inside is not None, "in_package_path": inside}


def _adapter_snapshot() -> dict[str, Any]:
    """适配器环境快照（跨机对账时"环境不同"必须看得见）。"""

    import mujoco
    import onnxruntime

    return {
        "python": platform.python_version(),
        "mujoco": mujoco.__version__,
        "onnxruntime": onnxruntime.__version__,
        "numpy": np.__version__,
    }


def produce_frame_log(
    *,
    package_dir: Path | str,
    policy: str | None = None,
    policy_id: str | None = None,
    cmd: tuple[float, ...] | list[float] = (0.4, 0.0, 0.0),
    seed: int = 7,
    steps: int = 100,
    domain_rand: bool = False,
    dr_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """跑一条策略 ``steps`` 个**控制步**，返回与浏览器同形的 frame log。

    帧的采样时刻与浏览器一致：**先 build 观测、再记帧、再施加动作、再推进物理** ——
    于是 `stepIndex` 从 0 起（第 0 帧 = 重置后的初始观测），与 `app.js` 的
    `Math.floor(sim.counter / controlDecimation)` 同口径，`replay_diff.py` 的对齐规则照样适用。
    """

    import mujoco
    import onnxruntime

    package_dir = Path(package_dir).expanduser().resolve()
    sim_path = package_dir / "simulation" / "config.json"
    if not sim_path.is_file():
        raise SystemExit(f"包内缺 simulation/config.json：{package_dir}")
    sim_config = json.loads(sim_path.read_text(encoding="utf-8-sig"))

    entry = resolve_policy_entry(sim_config, policy_id)
    policy_path, declared_path, resolution = resolve_policy(package_dir, entry, policy)
    # 如实标注：显式 --policy 指定的文件未必就是该条策略条目声明的那个 —— 若不一致，
    # 头里的 policy.id 记 None 并保留 declared_path，避免"名字是 A、跑的是 B"这种静默错标。
    bound = declared_path is not None and (package_dir / declared_path).resolve() == policy_path
    policy_id_actual = entry.get("id") if bound else None
    contract = PackageContract(package_dir, entry)

    model = load_package_model(package_dir, sim_config)
    model.opt.timestep = 1.0 / contract.physics_hz
    data = mujoco.MjData(model)
    obs_builder = ObsBuilder(contract, model, data)
    session = onnxruntime.InferenceSession(str(policy_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name

    # 确定性起手（与浏览器 resetSimulation 同口径）：重置 → 默认姿态 → 清零策略内部状态。
    spawn_default(contract, model, data, obs_builder)
    obs_builder.phase_s = 0.0
    obs_builder.last_action[:] = 0
    obs_builder.history = []

    # L3：域随机化（默认**关**）。开了才用 seed 采样 —— 于是 `replay_gate --seed-probe`
    # 会从"换 seed 结果不变"翻成"结果不同"，这条探测就是 L3 的验收判据。
    import domain_randomization as dr

    rng = np.random.default_rng(int(seed))
    dr_terms = dr.terms_from_config(dr_config)
    dr_reports: list[dict[str, Any]] = []
    dr_interval: dict[str, float] = {}
    dr_backup: dict[str, Any] = {}   # 出厂值备份（由调用方持有：scale 类算子不能基于上次结果连乘）
    if domain_rand:
        dr_reports.append(dr.apply(model, data, rng, terms=dr_terms, mode="startup", backup=dr_backup))
        dr_reports.append(dr.apply(model, data, rng, terms=dr_terms, mode="reset", backup=dr_backup))

    cmd_arr = np.asarray(cmd, dtype=np.float32)
    actuator_ids = [actuator_for_joint(model, name) for name in contract.action_joint_order]
    frames: list[dict[str, Any]] = []
    for step in range(int(steps)):
        observation = obs_builder.build(cmd_arr)
        ctrl_before = np.asarray(data.ctrl, dtype=np.float64).copy()
        raw = session.run(None, {input_name: observation})[0][0]
        action = np.asarray(raw, dtype=np.float32)[: contract.action_dim]

        frames.append({
            "t": round(float(data.time), 6),
            "stepIndex": step,
            "obs_dim": int(observation.shape[-1]),
            "obs": observation[0].tolist(),
            "action": action.tolist(),
            "ctrlBefore": ctrl_before.tolist(),
            # 控制器"被告知的目标"（两种执行器接口同义：PD 目标位 / 速度执行器目标速），
            # 与浏览器 frame 的 targetsPos/targetsVel/actuatorIds 字段对齐。
            "targetsPos": [float(action[i] * contract.action_scales[i] + contract.default_for(name))
                           for i, name in enumerate(contract.action_joint_order)],
            "targetsVel": [float(action[i] * contract.velocity_scale) if contract.is_velocity_joint(name) else 0.0
                           for i, name in enumerate(contract.action_joint_order)],
            "actuatorIds": actuator_ids,
        })

        obs_builder.last_action = action.astype(np.float32)
        actuate(contract, model, data, obs_builder, obs_builder.last_action)
        for _ in range(contract.decimation):
            mujoco.mj_step(model, data)
        if domain_rand:
            # interval 类（推力）：到点再来一次
            dr_reports.append(dr.apply(model, data, rng, terms=dr_terms, mode="interval",
                                       now_s=float(data.time), last_interval=dr_interval,
                                       backup=dr_backup))

    head = {
        "schema": FRAME_LOG_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "producer": _repo_relative(Path(__file__)),
        "seed": int(seed),
        "cmd": [float(value) for value in cmd_arr],
        "steps": int(steps),
        "recorded": len(frames),
        "package": _repo_relative(package_dir),
        "robot_id": str(entry.get("robot_id") or package_dir.name),
        "policy": {
            "id": policy_id_actual,
            "declared_path": declared_path or None,
            "path": _repo_relative(policy_path),
            "sha256": _sha256(policy_path),
            # **包外解析必须看得见**：在本机（有仓库）跑 Bundle 时，索引可能把策略解析到
            # 仓库里的同名文件 —— 那样"这份 Bundle 在干净机器上可复现"就是假的。
            # R2 的判据要求 inside_package=true，否则按 blocked 处理（见 backend/reproduce.py）。
            "resolution": resolution,
        },
        "physics": {
            "physics_hz": contract.physics_hz,
            "decimation": contract.decimation,
            "step_dt": contract.step_dt,
            "actuator_interface": contract.actuator_interface,
        },
        "observation": {
            "kind": contract.observation_kind,
            "obs_dim": int(contract.obs_dim or (frames[0]["obs_dim"] if frames else 0)),
            "action_dim": contract.action_dim,
        },
        "randomization": {
            "applied": bool(domain_rand),
            "seed": int(seed),
            "terms": [term.name for term in dr_terms] if domain_rand else [],
            "reports": dr_reports,
            "summary": [dr.summarise(item) for item in dr_reports] if domain_rand else [],
            "note": (
                "本次**开了**域随机化（L3 E1–E8）：模型/初始状态按 seed 采样，换 seed 结果应当不同。"
                if domain_rand else
                "本次**没开**域随机化（默认关）：spawn_default 是确定性重置，换 seed 结果不变 —— "
                "这是正常状态，但也说明「同 seed 同 DR」这句话在关闭时是空转的；"
                "开它用 `--domain-rand`（或包内 `domain_randomization` 声明）。"
            ),
        },
        "adapter": _adapter_snapshot(),
    }
    return {"head": head, "frames": frames}


def write_frame_log(path: Path | str, payload: dict[str, Any]) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(
        description="无头 frame log 产出端（L1）：跑一条策略并记录逐帧日志，与浏览器 frameLog 同形",
    )
    parser.add_argument("--package", required=True, help="机器人包目录（如 assets/robots/zex-w）")
    parser.add_argument("--policy", default=None, help="策略 onnx（包内相对路径或绝对路径；默认取策略条目声明的 path）")
    parser.add_argument("--policy-id", default=None, help="simulation/config.json 里的策略 id（默认取第一条）")
    parser.add_argument("--cmd", default="0.4,0,0", help="速度指令 vx,vy,wz")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--steps", type=int, default=100, help="控制步数（默认 100）")
    parser.add_argument("--domain-rand", action="store_true",
                        help="开启域随机化（L3 E1–E8）：按 --seed 采样摩擦/armature/质量/质心/推力/初始高度")
    parser.add_argument("--out", required=True, help="输出 JSON 路径")
    args = parser.parse_args()

    payload = produce_frame_log(
        package_dir=args.package,
        policy=args.policy,
        policy_id=args.policy_id,
        cmd=tuple(float(x) for x in args.cmd.split(",")),
        seed=args.seed,
        steps=args.steps,
        domain_rand=args.domain_rand,
    )
    target = write_frame_log(args.out, payload)
    head = payload["head"]
    print(f"frame log 已写出：{target}")
    policy_label = head["policy"]["id"] or f"未绑定条目（文件 {Path(head['policy']['path']).name}）"
    print(f"  包 {head['package']} / 策略 {policy_label}（{head['policy']['sha256'][:12]}…）")
    print(f"  帧 {head['recorded']} 条（stepIndex 0..{head['recorded'] - 1}）/ obs_dim {head['observation']['obs_dim']}")
    randomization = head["randomization"]
    print(f"  seed {head['seed']} / 物理 {head['physics']['physics_hz']} Hz × {head['physics']['decimation']}"
          f" / 域随机化 {randomization['applied']}"
          + (f"（{'；'.join(randomization['summary'][:2])}）" if randomization.get("summary") else ""))
    print(f"  适配器 {head['adapter']['python']} python / mujoco {head['adapter']['mujoco']} / ort {head['adapter']['onnxruntime']}")
    return 0


#: 旧私有名保留（同包其它模块与文档曾引用；定义在末尾避免前向引用）
_policy_entry = resolve_policy_entry
_resolve_policy = resolve_policy


if __name__ == "__main__":
    raise SystemExit(main())
