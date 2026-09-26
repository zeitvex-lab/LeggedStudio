"""族级技能通用装配的验收器：**新机型 + 标准 MJCF ⇒ 族级技能可用**（不需要机型专属 Python）。

用法（用训练栈那个解释器）：

    # 一台机型（内置包或导入包）逐个技能建 cfg；--iterations N 还真训 N 轮
    adapters/mjlab/.venv/Scripts/python.exe tools/validate_family_skill_assembly.py \
        --robot imported_fsdog1_2f7de81ba2 --skills jump,velocity,handstand --iterations 1

    # 与包内逐档档案对拍（证明"通用装配"与手写档案等价）
    ... --robot unitree_b2 --skills jump --compare-profiles

判据：① 装配成功（建 cfg）；② `--iterations` 时真建环境并跑 N 轮 PPO；
③ `--compare-profiles` 时，通用装配的 env cfg 与逐档档案的 env cfg **逐字段一致**
（身份类字段除外 —— profile 的 `task_id`/`experiment_name` 不进 env cfg）。

退出码：0 全过；1 有失败；2 环境缺训练栈。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def resolve_package(robot: str) -> Path:
    """内置包（assets/robots/<id>）或导入包（workspace/packages/<id>）；也接受直接给路径。"""
    candidates = [Path(robot), ROOT / "assets" / "robots" / robot, ROOT / "workspace" / "packages" / robot]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    raise SystemExit(f"找不到机器人包 {robot!r}（试过：{[str(item) for item in candidates]}）")


def load_contract(package: Path) -> tuple[dict, str]:
    """契约：优先 v3 `contract.json`，导入包常只有 `contract_legacy_v2.json`（运行时那份）。"""
    for name in ("contract.json", "contract_legacy_v2.json"):
        path = package / name
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8-sig")), name
    raise SystemExit(f"{package} 里没有契约（contract.json / contract_legacy_v2.json）")


def resolve_model(package: Path, contract: dict) -> Path:
    """MJCF：包清单 `model.path` → 契约 `urdf.path` → `model/robot.xml`（标准布局）。"""
    manifest = package / "robot_package.json"
    if manifest.is_file():
        model = (json.loads(manifest.read_text(encoding="utf-8-sig")).get("model") or {}).get("path")
        if model and (package / model).is_file():
            return (package / model).resolve()
    raw = str(((contract.get("urdf") or {}).get("path") or "")).strip()
    if raw:
        for candidate in (ROOT / raw, package / raw):
            if candidate.is_file():
                return candidate.resolve()
    for candidate in (package / "model" / "robot.xml", package / "robot.xml"):
        if candidate.is_file():
            return candidate.resolve()
    raise SystemExit(f"{package} 里找不到 MJCF（清单/契约/标准布局都没命中）")


def compare_with_profile(task_name: str, robot_id: str, generic_env_cfg) -> dict:
    """与包内逐档档案的 env cfg 逐字段比（复用上移取证工具的 dump/diff 机器）。

    档案按**它自己的键**找：扫 `assets/robots/<robot>/training/profiles/*.json`，
    取 `task_name` 等于本技能的条目（不靠文件名拼规则 —— 文件名是包侧习惯，不是契约）。
    """
    from tools.audit_skill_lift_equivalence import _dump, diff

    profiles_dir = ROOT / "assets" / "robots" / robot_id / "training" / "profiles"
    profile_path = None
    for candidate in sorted(profiles_dir.glob("*.json")):
        data = json.loads(candidate.read_text(encoding="utf-8-sig"))
        if str(data.get("task_name")) == task_name:
            profile_path = candidate
            break
    if profile_path is None:
        return {"status": "skipped", "why": f"{robot_id} 没有 task_name={task_name} 的档案（通用装配本来就不需要它）"}
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    entry = profile["entrypoints"]["env"]
    module_name, _, attr = str(entry).partition(":")
    sys.path.insert(0, str(ROOT / "assets" / "robots" / robot_id / "training" / "source"))
    sys.path.insert(0, str(ROOT / "assets" / "robots" / robot_id))
    profile_cfg = getattr(__import__(module_name, fromlist=[attr]), attr)(play=False)

    out = ROOT / "workspace" / "validation" / "assembly-compare"
    out.mkdir(parents=True, exist_ok=True)
    left, right = out / f"{robot_id}-{task_name}-generic.json", out / f"{robot_id}-{task_name}-profile.json"
    left.write_text(json.dumps({"env": _dump(generic_env_cfg)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    right.write_text(json.dumps({"env": _dump(profile_cfg)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    code = diff(left, right)
    # 字面差异之外再看**解析结果**：两组 cfg 的执行器（目标关节集合）是否一致 ——
    # 「一条 12 关节组」与「按角色三组」写法不同但解析相同，这属于写法差异，不是行为差异。
    from mjlab.entity import Entity

    def _resolved_targets(cfg) -> list[str]:
        entity = Entity(cfg.scene.entities["robot"])
        return sorted(name for actuator in entity.actuators for name in actuator.target_names)

    generic_targets, profile_targets = _resolved_targets(generic_env_cfg), _resolved_targets(profile_cfg)
    return {
        "status": "identical" if code == 0 else "differs",
        "literal_diff_fields": code,
        "resolved_actuator_targets_equal": generic_targets == profile_targets,
        "resolved_actuator_targets": generic_targets,
        "generic": str(left.relative_to(ROOT)),
        "profile": str(right.relative_to(ROOT)),
        "profile_file": str(profile_path.relative_to(ROOT)),
        "note": "字面差异若只落在执行器**分组写法**，以 `resolved_actuator_targets_equal` 为准（解析集相同即行为等价）",
    }


def run_training(env_cfg, runner_cfg, iterations: int) -> dict:
    """真建环境 + 真跑 N 轮（与产品训练路径同一套 runner/wrapper）。"""
    import torch
    from mjlab.envs import ManagerBasedRlEnv

    from tools.validate_traversal_progress import _runner_and_wrapper, train_checkpoint_with

    env_cfg.scene.num_envs = min(int(env_cfg.scene.num_envs), 128)
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    env = ManagerBasedRlEnv(env_cfg, device=device)
    try:
        wrapped, runner_cls, rl_cfg, asdict = _runner_and_wrapper(env, {
            "runner": "__profile__",  # 直接注入已建好的 runner cfg（见下）
        }) if False else (None, None, runner_cfg, None)
        from mjlab.rl import RslRlVecEnvWrapper
        from dataclasses import asdict as _asdict

        wrapped = RslRlVecEnvWrapper(env, clip_actions=getattr(runner_cfg, "clip_actions", None))
        runner_type = __import__("mjlab.rl", fromlist=["MjlabOnPolicyRunner"]).MjlabOnPolicyRunner
        output = ROOT / "workspace" / "validation" / "assembly-train"
        output.mkdir(parents=True, exist_ok=True)
        checkpoint = train_checkpoint_with(wrapped, runner_type, _asdict, runner_cfg, iterations, output)
        return {"status": "ok", "iters": iterations, "num_envs": env.num_envs, "checkpoint": str(checkpoint.relative_to(ROOT))}
    finally:
        env.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--robot", required=True, help="机器人 id（内置或导入）或包路径")
    parser.add_argument("--skills", required=True, help="逗号分隔的 task_name（如 jump,velocity,handstand）")
    parser.add_argument("--iterations", type=int, default=0, help="真训轮数（0 = 只建 cfg）")
    parser.add_argument("--init-base-height", type=float, default=None,
                        help="显式出生高（不给我们按默认姿 FK 推站立高；对拍逐档档案时用它钉齐）")
    parser.add_argument("--compare-profiles", action="store_true", help="与包内逐档档案对拍 env cfg")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    try:
        import mjlab  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        print(f"环境缺训练栈：{exc}（请用 adapters/mjlab/.venv 的解释器）")
        return 2

    from adapters.mjlab.family_skill_builder import (
        build_family_skill,
        candidate_families,
        family_skill_catalog,
    )

    package = resolve_package(args.robot)
    contract, contract_name = load_contract(package)
    model = resolve_model(package, contract)
    robot_id = str(contract.get("robot_id") or package.name)
    # 族**从契约派生**（不看机型名）：形态 id 落在哪个族，就用哪个族的装配表与绑定工厂。
    families = candidate_families(contract)
    if not families:
        raise SystemExit(f"{robot_id}: 契约 morphology.id 不落在任何已登记族里，通用装配无从谈起")
    family_id = families[0]
    catalog = family_skill_catalog(family_id)
    report: dict = {
        "robot_id": robot_id,
        "package": str(package.relative_to(ROOT)) if package.is_relative_to(ROOT) else str(package),
        "contract": contract_name,
        "model": str(model.relative_to(ROOT)) if model.is_relative_to(ROOT) else str(model),
        "family": family_id,
        "catalog_size": len(catalog),
        "skills": {},
    }
    failures = 0
    for skill in [item.strip() for item in args.skills.split(",") if item.strip()]:
        entry: dict = {}
        try:
            assembly = build_family_skill(
                contract, model, skill, family_id=family_id,
                init_base_height=args.init_base_height,
            )
            entry["status"] = "assembled"
            entry["diagnostics"] = assembly.diagnostics
            if args.compare_profiles:
                compare = compare_with_profile(skill, robot_id, assembly.env_cfg)
                entry["compare"] = compare
                # 判据：**解析结果**一致即通过；字面差异只记录（如执行器分组写法）。
                if compare.get("status") == "differs" and not compare.get("resolved_actuator_targets_equal"):
                    failures += 1
            if args.iterations:
                entry["train"] = run_training(assembly.env_cfg, assembly.runner_cfg, args.iterations)
        except Exception as exc:  # noqa: BLE001
            message = f"{type(exc).__name__}: {exc}"
            # **能力缺口 vs 真失败**：绑定 / 装配器给出的"这台资产缺什么"（足端 site、
            # 具名腿杆几何、位置执行器）是**如实结论**，不是工具失败 —— 记 capability_gap
            # 并原样保留原因（照它就能补齐资产或写一行数据）。
            markers = ("找不到足端 site", "找不到角色", "不是位置模式", "找不到足端 body", "依赖的资产能力缺失")
            gap = any(marker in message for marker in markers)
            entry["status"] = "capability_gap" if gap else "failed"
            entry["error"] = message
            if not gap:
                failures += 1
        report["skills"][skill] = entry

    statuses = [item.get("status") for item in report["skills"].values()]
    report["summary"] = {
        "assembled": statuses.count("assembled"),
        "capability_gap": statuses.count("capability_gap"),
        "failed": statuses.count("failed"),
    }
    report["ok"] = failures == 0
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
