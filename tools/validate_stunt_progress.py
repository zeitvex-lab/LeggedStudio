"""特技/姿态类的**验收器级度量**：把「跳起来了 / 真翻了 / 立住了」量成可跨机型比的数。

为什么需要它：效果口径（`registry/effect_criterion.json`）要的是**跨机型可比**的度量，
而冒烟给的累计奖励量纲随机型与奖励表变、不可比。本工具的度量为特技/姿态四档提供那个分母：

| 动作 | 度量 | 判据（都从**档案自己的目标**推，不另立刻度） |
|---|---|---|
| jump / spring_jump | `peak_height_ratio` = 峰值机身高度 / 出生站立高 | ≥ `0.9 × 档案 flight_height / 出生高`（jump 没声明飞行目标 ⇒ 用族默认 1.2，写明待标定） |
| backflip | 同上 + `pitch_turns` = 累积俯仰转过的整圈数（`∫|ω_pitch|dt / 2π`） | 高度线同上 + **≥ 1 圈**（物理量，不是调出来的数） |
| stance（handstand / leggedstand） | `hold_ratio` = 达标保持的步数占比（高度 ≥ 目标高的 0.9 **且** 足端接触模式符合该档要求） | ≥ `criteria.stance.hold_ratio_min`（族默认 0.5，可被档案覆盖） |

度量都从**仿真真值**读（root 位姿/线速度 + FEET_SENSOR 的 found），不读奖励，所以换机型、换奖励表都可比。
`--train-iters` 与越障验收器同口径：不给 checkpoint 就只报"未测"。

退出码：0 = 判据全过；1 = 有不过的判据；3 = 只建了环境（未给策略 ⇒ 未测，不谎报通过）。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: 足端接触模式：哪两个腿在空中（`_ENDS` 同源口径 —— handstand 后腿离地 / leggedstand 前腿离地）
AIR_LEGS = {"handstand": ("rear",), "leggedstand": ("front",), "rear_stand": ("front",)}


def find_profile(profile_id: str) -> tuple[str, Path, dict]:
    for path in sorted(ROOT.glob("assets/robots/*/training/profiles/*.json")):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if str(data.get("profile_id")) == profile_id:
            return path.parts[-4], path, data
    raise SystemExit(f"找不到档案 {profile_id!r}")


def build_env(robot_id: str, profile: dict, num_envs: int):
    import torch
    from mjlab.envs import ManagerBasedRlEnv

    package_root = ROOT / "assets" / "robots" / robot_id
    source_root = package_root / str(profile.get("source_root", "training/source"))
    for entry in (str(source_root), str(package_root)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    if str(ROOT) not in sys.path:
        sys.path.append(str(ROOT))

    module_name, _, attr = str(profile["entrypoints"]["env"]).partition(":")
    cfg = getattr(__import__(module_name, fromlist=[attr]), attr)(play=False)
    cfg.scene.num_envs = int(num_envs)
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    return cfg, ManagerBasedRlEnv(cfg, device=device), device


def _initial_height(cfg, profile: dict) -> float:
    """出生（站立）高度：实体初始位姿的 z；找不到就用档案声明的回退值。"""
    entity = cfg.scene.entities["robot"]
    pos = getattr(entity.init_state, "pos", None)
    if pos:
        return float(pos[2])
    return float(((profile.get("criteria") or {}).get("stunt") or {}).get("init_height", 0.4))


def stunt_criteria(profile: dict, task_name: str, initial_height: float) -> dict:
    """判据：优先档案 `criteria.stunt`，其次从档案/族默认推（每一条都带出处）。"""
    declared = ((profile.get("criteria") or {}).get("stunt") or {})
    criteria: dict = {
        "peak_height_ratio_min": declared.get("peak_height_ratio_min"),
        "pitch_turns_min": declared.get("pitch_turns_min"),
        "hold_ratio_min": declared.get("hold_ratio_min"),
        "sources": {},
    }
    if task_name in ("jump", "spring_jump", "backflip"):
        flight = None
        for key in ("flight_height", "min_flight_height"):
            if key in declared:
                flight = float(declared[key])
        if flight is None:
            # 档案 JSON 不重复技能 profile 的字段，这里用**族里该技能的源配方目标**（写清出处）
            flight = {"backflip": 0.6, "spring_jump": 0.47}.get(task_name)
            criteria["sources"]["flight_height"] = (
                f"族技能 profile 的默认 flight_height（{flight}）" if flight else
                "jump 没有飞行高度目标 ⇒ 用族默认 1.2（**待标定**）"
            )
        else:
            criteria["sources"]["flight_height"] = "档案 criteria.stunt.flight_height"
        criteria["peak_height_ratio_min"] = float(
            declared.get("peak_height_ratio_min", 0.9 * flight / initial_height if flight else 1.2)
        )
        if task_name == "backflip":
            criteria["pitch_turns_min"] = float(declared.get("pitch_turns_min", 1.0))
            criteria["sources"]["pitch_turns"] = "物理量：完成一整圈（2π）"
    else:  # 站姿类
        criteria["hold_ratio_min"] = float(declared.get("hold_ratio_min", 0.5))
        criteria["sources"]["hold_ratio"] = "族默认 0.5（可被档案 criteria.stunt.hold_ratio_min 覆盖）"
    return criteria


def rollout(env, cfg, profile: dict, task_name: str, entry: dict, checkpoint: Path | None, seconds: float, iters: int, output_dir: Path) -> dict:
    import torch

    from tools.validate_traversal_progress import _runner_and_wrapper, train_checkpoint_with

    # wrapper **只包一次**（复用同一份训练/验收）：训练收尾的导出路径会把张量置于
    # InferenceMode，二次包装会触发 env.reset() 的原地写而崩。两工具共用同一套 helper。
    wrapped, runner_cls, rl_cfg, asdict = _runner_and_wrapper(env, entry)
    if checkpoint is None:
        if not iters:
            return {"status": "not_tested", "why": "未给 --checkpoint / --train-iters（策略级未测）"}
        checkpoint = train_checkpoint_with(wrapped, runner_cls, asdict, rl_cfg, iters, output_dir)

    runner = runner_cls(wrapped, asdict(rl_cfg), str(ROOT / "workspace" / "validation"), env.device)
    runner.load(str(checkpoint), load_cfg={"actor": True}, strict=True, map_location=env.device)
    policy = runner.get_inference_policy(device=env.device)

    initial_height = _initial_height(cfg, profile)
    criteria = stunt_criteria(profile, task_name, initial_height)
    from adapters.mjlab.kits.quadruped_kit.skills.mdp.contacts import source_vertical_contact

    foot_sensor = env.scene["feet_ground_contact"]
    base_sensor = env.scene["base_ground_contact"]
    steps = max(1, int(seconds / (cfg.decimation * cfg.sim.mujoco.timestep)))

    robot = env.scene["robot"]
    peak_height = torch.zeros(env.num_envs, device=env.device)
    pitch_turns = torch.zeros(env.num_envs, device=env.device)
    air_steps = torch.zeros(env.num_envs, device=env.device)
    hold_steps = torch.zeros(env.num_envs, device=env.device)
    fell_seen = torch.zeros(env.num_envs, device=env.device, dtype=torch.bool)
    target_height = float(
        ((profile.get("criteria") or {}).get("stunt") or {}).get("height_target")
        or (cfg.rewards.get("base_height") and cfg.rewards["base_height"].params.get("target_height"))
        or 0.0
    )
    air_set = AIR_LEGS.get(task_name, ())
    with torch.inference_mode():  # 同 traversal 工具：推理张量只允许在推理模式内原地写
        obs, _ = wrapped.reset()
        for step in range(steps):
            action = policy(obs)
            obs, _, dones, _ = wrapped.step(action)
            height = robot.data.root_link_pos_w[:, 2]
            peak_height = torch.maximum(peak_height, height)
            omega = robot.data.root_link_ang_vel_b[:, 1]
            pitch_turns += torch.abs(omega) * env.step_dt / (2.0 * math.pi)
            contact = source_vertical_contact(foot_sensor, 1.0)  # (num_envs, 足端数)
            in_air = (~contact).sum(dim=1).clamp(max=1).float()
            air_steps += in_air
            if air_set:
                # 达标保持：高度 ≥ 目标高的 0.9 且**该档要求的腿**在空
                slots = {"front": slice(0, 2), "rear": slice(-2, None)}[air_set[0]]
                legs_air = (~contact[:, slots]).all(dim=1).float()
                ok = (height >= 0.9 * target_height).float() * legs_air if target_height else legs_air
            else:
                ok = (height >= 0.9 * target_height).float() if target_height else torch.zeros_like(height)
            hold_steps += ok
            base_force = base_sensor.data.force
            assert base_force is not None
            fell = torch.linalg.vector_norm(base_force, dim=-1) > 1.0
            fell_seen |= fell.any(dim=-1) if fell.dim() > 1 else fell
            del dones

    metrics = {
        "status": "ok",
        "checkpoint": str(checkpoint),
        "seconds": seconds,
        "control_steps": steps,
        "initial_height": round(initial_height, 3),
        "peak_height_m": round(float(peak_height.max().item()), 3),
        "peak_height_mean_m": round(float(peak_height.mean().item()), 3),
        "peak_height_ratio": round(float((peak_height / initial_height).max().item()), 3),
        "pitch_turns_max": round(float(pitch_turns.max().item()), 3),
        "air_ratio": round(float((air_steps / steps).mean().item()), 3),
        "hold_ratio": round(float((hold_steps / steps).mean().item()), 3),
        "survived_ratio": round(float((~fell_seen).float().mean().item()), 3),
        "criteria": criteria,
    }
    checks = {"survived": metrics["survived_ratio"] >= float(
        ((profile.get("criteria") or {}).get("stunt") or {}).get("survived_ratio_min", 0.9)
    )}
    if criteria.get("peak_height_ratio_min") is not None:
        checks["peak_height"] = metrics["peak_height_ratio"] >= criteria["peak_height_ratio_min"]
    if criteria.get("pitch_turns_min") is not None:
        checks["pitch_turns"] = metrics["pitch_turns_max"] >= criteria["pitch_turns_min"]
    if criteria.get("hold_ratio_min") is not None:
        checks["hold_ratio"] = metrics["hold_ratio"] >= criteria["hold_ratio_min"]
    metrics["checks"] = checks
    metrics["ok"] = all(checks.values()) if checks else False
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--train-iters", type=int, default=0)
    parser.add_argument("--num-envs", type=int, default=64)
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    robot_id, profile_path, profile = find_profile(args.profile)
    task_name = str(profile.get("task_name") or "")
    cfg, env, _device = build_env(robot_id, profile, args.num_envs)
    report = {
        "profile_id": args.profile,
        "robot": robot_id,
        "task_name": task_name,
        "profile_path": str(profile_path.relative_to(ROOT)),
        "num_envs": args.num_envs,
    }
    try:
        report["metrics"] = rollout(
            env, cfg, profile, task_name, profile["entrypoints"],
            args.checkpoint.resolve() if args.checkpoint else None,
            args.seconds, args.train_iters,
            ROOT / "workspace" / "validation" / f"stunt-{args.profile}-train",
        )
    finally:
        env.close()

    if report["metrics"].get("status") == "not_tested":
        report["verdict"] = "not_tested"
    else:
        report["verdict"] = "pass" if report["metrics"]["ok"] else "fail"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if report["verdict"] == "pass":
        return 0
    return 3 if report["verdict"] == "not_tested" else 1


if __name__ == "__main__":
    sys.exit(main())
