"""族级越障验收器：判「真的过了障碍」，不是「奖励有限」。

**为什么另立一条判据**：既有冒烟只证明"建得起环境、奖励有限"，对越障而言那等于没验——
原地站着也能拿有限奖励。本工具用**课程自己的那条线**当判据，不另立一套口径：

1. **课程侧**（不需要策略）：把 `common_step_counter` 推到档案声明的每个释放节点，
   环境里的**地形类型集合必须按日程增长**（族默认 5→6→7→8：`random_grid` /
   `pyramid_stairs_inv` / `rc_wall` 依次并入）—— 证明障碍真按日程放出来了；
2. **策略侧**（给了 `--checkpoint` 才跑）：滚 `--seconds`，统计每条环境**从出生点
   （所在地块中心）的水平位移**；判据 = **越过半个地块（默认 4.0 m）** ——
   与课程晋级线**同一条**（`terrain_levels_*` 的 Upgrade 就是"越过半地块"），
   所以"过了障碍"与"课程认可升级"是同一个口径。阈值可由档案声明覆盖：
   `criteria.traversal.progress_min_m` / `progress_env_ratio_min`。

退出码：0 = 判据全过；1 = 有判据不过；3 = **只测了课程侧**（未给 checkpoint，策略级未测）。

用法（解释器必须是训练栈那个 venv）：

    adapters/mjlab/.venv/Scripts/python.exe tools/validate_traversal_progress.py \
        --profile b2w-traversal [--checkpoint <model_x.pt>] [--seconds 20] [--num-envs 64]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROFILES_GLOB = "assets/robots/*/training/profiles/*.json"


def find_profile(profile_id: str) -> tuple[str, Path, dict]:
    for path in sorted(ROOT.glob(PROFILES_GLOB)):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if str(data.get("profile_id")) == profile_id:
            return path.parts[-4], path, data
    raise SystemExit(f"找不到档案 {profile_id!r}（扫的是 {PROFILES_GLOB}）")


def build_env(robot_id: str, profile: dict, num_envs: int):
    """按档案声明建环境（与产品链路同一入口）。"""
    import torch
    from mjlab.envs import ManagerBasedRlEnv

    package_root = ROOT / "assets" / "robots" / robot_id
    source_root = package_root / str(profile.get("source_root", "training/source"))
    for entry in (str(source_root), str(package_root)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    if str(ROOT) not in sys.path:
        sys.path.append(str(ROOT))

    entry = profile["entrypoints"]
    module_name, _, attr = str(entry["env"]).partition(":")
    module = __import__(module_name, fromlist=[attr])
    cfg = getattr(module, attr)(play=False)
    cfg.scene.num_envs = int(num_envs)
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    return cfg, ManagerBasedRlEnv(cfg, device=device), device, entry


def course_side(env, profile: dict) -> dict:
    """把课程推到每个释放节点，核对地形类型集合**只含应放出的那些**、且新放出的真出现。

    判据用"子集 + 主要地块必须现身"，而不是"每个应放出的都出现"：
    地块是**按配比随机采样**的，`random_rough` / `perlin_noise` 这类 0.01 配比的地块在
    64 条环境里本来就可能一条都不中 —— 那是采样，不是课程没放。反过来，
    **出现未放出的地形**才是真违反（说明释放日程没生效）。
    """
    import torch

    curriculum = profile.get("curriculum") or {}
    schedule = curriculum.get("terrain_release_env_steps") or []
    initial = list(curriculum.get("initial_terrains") or [])
    terrain = env.scene.terrain
    generator = terrain.cfg.terrain_generator
    names = list(generator.sub_terrains.keys())
    proportions = {name: float(generator.sub_terrains[name].proportion) for name in names}
    # 配比 ≥ 0.10 的地块：64 条环境里"一条都不中"的概率可忽略，出现与否才算证据。
    major = 0.10

    allowed = set(initial)
    checks: list[dict] = []
    for step, released in schedule:
        env.common_step_counter = int(step)
        env.curriculum_manager.compute(env_ids=torch.arange(env.num_envs, device=env.device))
        allowed.update(str(name) for name in released)
        present = {names[int(index)] for index in torch.unique(terrain.terrain_types).tolist()}
        violations = sorted(present - allowed)
        missing_major = sorted(
            name for name in (str(item) for item in released)
            if proportions.get(name, 0.0) >= major and name not in present
        )
        checks.append({
            "step": int(step),
            "released": list(released),
            "allowed_terrains": sorted(allowed),
            "present_terrains": sorted(present),
            "unexpected_terrains": violations,
            "missing_major_terrains": missing_major,
            "ok": not violations and not missing_major,
        })
    return {
        "scheduled_nodes": len(schedule),
        "nodes": checks,
        "ok": all(item["ok"] for item in checks) if checks else False,
        "verdict_hint": (
            "地形按日程释放（且没有未放出的地形混进来）"
            if checks and all(item["ok"] for item in checks)
            else "地形没有按日程释放（课程侧判不过）" if checks else "档案没声明释放日程"
        ),
    }


def policy_side(env, cfg, entry: dict, checkpoint: Path, seconds: float, profile: dict) -> dict:
    """加载 checkpoint 滚一段，量每条环境从出生点的位移（判据 = 半地块）。"""
    import torch
    from dataclasses import asdict
    from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper

    generator = cfg.scene.terrain.terrain_generator
    half_tile = float(generator.size[0]) / 2.0 if generator is not None else 4.0
    criteria = ((profile.get("criteria") or {}).get("traversal") or {})
    progress_min_m = float(criteria.get("progress_min_m", half_tile))
    ratio_min = float(criteria.get("progress_env_ratio_min", 0.5))

    module_name, _, attr = str(entry["runner"]).partition(":")
    rl_cfg = getattr(__import__(module_name, fromlist=[attr]), attr)()
    steps = max(1, int(seconds / (cfg.decimation * cfg.sim.mujoco.timestep)))
    wrapped = RslRlVecEnvWrapper(env, clip_actions=rl_cfg.clip_actions)
    runner = MjlabOnPolicyRunner(wrapped, asdict(rl_cfg), str(ROOT / "workspace" / "validation"), env.device)
    runner.load(str(checkpoint), load_cfg={"actor": True}, strict=True, map_location=env.device)
    policy = runner.get_inference_policy(device=env.device)

    obs, _ = wrapped.reset()
    best = torch.zeros(env.num_envs, device=env.device)
    with torch.no_grad():
        for _ in range(steps):
            action = policy(obs)
            obs, _, dones, _ = wrapped.step(action)
            robot = env.scene["robot"]
            distance = torch.norm(
                robot.data.root_link_pos_w[:, :2] - env.scene.env_origins[:, :2], dim=1
            )
            best = torch.maximum(best, distance)
    ratio = float((best >= progress_min_m).float().mean().item())
    return {
        "checkpoint": str(checkpoint),
        "seconds": seconds,
        "control_steps": steps,
        "half_tile_m": half_tile,
        "progress_min_m": progress_min_m,
        "progress_env_ratio_min": ratio_min,
        "progress_max_m": round(float(best.max().item()), 3),
        "progress_mean_m": round(float(best.mean().item()), 3),
        "progress_env_ratio": round(ratio, 3),
        "terrain_level_mean": round(float(env.scene.terrain.terrain_levels.float().mean().item()), 3),
        "ok": ratio >= ratio_min,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, help="越障档案 profile_id（如 b2w-traversal）")
    parser.add_argument("--checkpoint", type=Path, default=None, help="策略 checkpoint（.pt）；不给则只测课程侧")
    parser.add_argument("--num-envs", type=int, default=64)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    robot_id, profile_path, profile = find_profile(args.profile)
    cfg, env, _device, entry = build_env(robot_id, profile, args.num_envs)
    report = {
        "profile_id": args.profile,
        "robot": robot_id,
        "profile_path": str(profile_path.relative_to(ROOT)),
        "num_envs": args.num_envs,
    }
    try:
        report["course"] = course_side(env, profile)
        if args.checkpoint is None:
            report["policy"] = {"status": "not_tested", "why": "未给 --checkpoint（策略级未测）"}
            report["verdict"] = "course_only"
        else:
            report["policy"] = policy_side(env, cfg, entry, args.checkpoint.resolve(), args.seconds, profile)
            report["verdict"] = "pass" if (report["course"]["ok"] and report["policy"]["ok"]) else "fail"
    finally:
        env.close()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if report["verdict"] == "pass":
        return 0
    return 3 if report["verdict"] == "course_only" else 1


if __name__ == "__main__":
    sys.exit(main())
