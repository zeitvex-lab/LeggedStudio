"""Checkpoint -> ONNX 导出工具：让长训的中间 checkpoint（model_*.pt）可评测。

背景：mjlab worker 只在训练完成时导出 policy.onnx（native_worker.export_runner_policy_onnx），
中间 checkpoint 停留在 .pt，"预算-质量曲线"因此只能看终点。本工具把训练链的
"建 env + 建 runner -> runner.load(checkpoint) -> 复用既有导出函数" 拼成一条独立链路：
导出逻辑零重写（直接调 adapters.mjlab.native_worker.export_runner_policy_onnx，
走 mjlab 自带 `runner.export_policy_to_onnx`，obs 归一化含在图内，与训练完的原生
导出同一条已验证路径），env/runner 装配取自机型包
assets/robots/unitree_go2w/training/source/go2w_velocity（flat_legs_only 档），
小 num_envs（默认 4）只为元数据提取服务，不做仿真训练。

用法（在仓库根，用适配器 venv；MUJOCO_GL=disabled）：
  MUJOCO_GL=disabled adapters/mjlab/.venv/Scripts/python.exe tools/export_checkpoint_onnx.py \
      --run workspace/unitree_go2w_contract_v1_20260930_062231_995409 \
      --checkpoint model_final.pt \
      --out workspace/.../exported/model_final.onnx

  --checkpoint  默认 model_final.pt；文件名相对 --run，也接受绝对路径
  --out         默认 <run>/exported/<checkpoint stem>.onnx；绝不覆盖训练真值
                exported/policy.onnx（除非 --force）
  --num-envs    默认 4（仅构建轻量 env）
  --device      默认 cpu（不与在跑训练抢 GPU）
  --verify/--no-verify
                默认开启：run 目录存在真值 exported/policy.onnx 时，用 onnxruntime
                对 64 个固定随机观测（numpy default_rng(0)，shape (64,53)，参照图是
                定长 batch=1 故逐样本喂）对比两张图的输出，max|Δ| < 1e-5 打印
                "[verify] OK"。
"""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

# 必须在 mujoco 被任何子模块导入前生效（无头环境，见仓库既有约定）。
os.environ.setdefault("MUJOCO_GL", "disabled")

# 裸脚本自举（contracts/path_bootstrap.py 契约：script dir 不含仓库根，需手动补）。
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from contracts.path_bootstrap import ensure_on_path  # noqa: E402

REPO_ROOT = _PROJECT_ROOT
DEFAULT_PACKAGE_ROOT = REPO_ROOT / "assets" / "robots" / "unitree_go2w"

VERIFY_SAMPLES = 64
VERIFY_OBS_DIM = 53
VERIFY_SEED = 0
VERIFY_TOLERANCE = 1e-5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a mjlab training checkpoint (.pt) to a deployable policy.onnx."
    )
    parser.add_argument("--run", required=True, help="training run directory (holds model_*.pt)")
    parser.add_argument("--checkpoint", default="model_final.pt",
                        help="checkpoint filename inside the run dir (or absolute path); default model_final.pt")
    parser.add_argument("--out", default=None,
                        help="output .onnx path; default <run>/exported/<checkpoint stem>.onnx")
    parser.add_argument("--package-root", default=str(DEFAULT_PACKAGE_ROOT),
                        help="robot package root holding training/source (default: unitree_go2w)")
    parser.add_argument("--num-envs", type=int, default=4,
                        help="lightweight env size for metadata extraction (default 4)")
    parser.add_argument("--device", default="cpu", help="torch device (default cpu)")
    parser.add_argument("--force", action="store_true",
                        help="allow overwriting the run's reference exported/policy.onnx")
    verify_group = parser.add_mutually_exclusive_group()
    verify_group.add_argument("--verify", dest="verify", action="store_true", default=True,
                              help="numerically compare against the run's exported/policy.onnx (default: on)")
    verify_group.add_argument("--no-verify", dest="verify", action="store_false",
                              help="skip the onnxruntime self-check")
    return parser.parse_args()


def resolve_contract(run_dir: Path, package_root: Path):
    """best-effort 解析机型契约对象（export 的 joint 名兜底用，失败不致命）。"""
    candidates = [
        run_dir / "contract.json",
        run_dir / "contract_snapshot.json",
        package_root / "contract_legacy_v2.json",
    ]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            from contracts.contract_legacy_v2 import ContractLegacyV2

            return ContractLegacyV2.from_json_file(str(candidate))
        except Exception as exc:  # noqa: BLE001
            print(f"[contract] skip {candidate.name}: {type(exc).__name__}: {exc}")
    return None


def build_env_and_runner(run_dir: Path, package_root: Path, num_envs: int, device: str):
    """复刻 native_worker 的装配：包 env_cfg + 包 runner_cfg + VelocityOnPolicyRunner。"""
    # sys.path 装配（与 native_worker.run 同序）：
    ensure_on_path(REPO_ROOT)                          # adapters.* / contracts.*
    ensure_on_path(REPO_ROOT / "adapters" / "mjlab")   # onnx_exporter 顶层导入（导出函数第一选择）
    ensure_on_path(package_root / "training" / "source")  # go2w_velocity 包（__init__ 已自举）

    import mjlab  # noqa: F401
    import mjlab.tasks  # noqa: F401
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.rl import RslRlVecEnvWrapper
    from mjlab.tasks.velocity.rl import VelocityOnPolicyRunner

    # 档案入口**按 run 动态解析**（2026-10-02 实测：硬编码 legs-only 入口载混合
    # 16 动作 checkpoint 必然 size mismatch）。解析链 = 包档案 JSON 的
    # entrypoints（env/runner，与 native_worker 同源）→ 缺失回落 legs-only
    # （历史行为，旧 run 无档案 JSON 时保底）。
    import json  # 函数内局部：模块顶层未导入（历史代码只在分支内 import json）

    env_factory = runner_factory = None
    training_config = run_dir / "training_config.json"
    profile_id = ""
    if training_config.is_file():
        try:
            profile_id = str(json.loads(training_config.read_text(encoding="utf-8-sig")).get("profile_id") or "")
        except Exception:
            profile_id = ""
    if profile_id:
        profile_json = package_root / "training" / "profiles" / f"{profile_id}.json"
        if profile_json.is_file():
            entrypoints = (json.loads(profile_json.read_text(encoding="utf-8-sig")).get("entrypoints") or {})
            env_ep = str(entrypoints.get("env") or "")
            runner_ep = str(entrypoints.get("runner") or "")
            if ":" in env_ep and ":" in runner_ep:
                ensure_on_path(package_root / "training" / "source")
                env_mod, env_fn = env_ep.split(":", 1)
                run_mod, run_fn = runner_ep.split(":", 1)
                env_factory = getattr(importlib.import_module(env_mod), env_fn)
                runner_factory = getattr(importlib.import_module(run_mod), run_fn)
    if env_factory is None or runner_factory is None:
        from go2w_velocity import (
            unitree_go2w_flat_legs_only_env_cfg as env_factory,
            unitree_go2w_flat_legs_only_ppo_runner_cfg as runner_factory,
        )

    env_cfg = env_factory(play=False)
    rl_cfg = runner_factory()
    # 装配口径对齐 assemble_training_config：只动 num_envs/seed（不影响网络与观测宽度）。
    env_cfg.scene.num_envs = max(1, int(num_envs))
    seed = 7
    training_config = run_dir / "training_config.json"
    if training_config.is_file():
        try:
            import json

            seed = int(json.loads(training_config.read_text(encoding="utf-8-sig")).get("seed") or seed)
        except Exception:  # noqa: BLE001
            pass
    env_cfg.seed = seed

    env = ManagerBasedRlEnv(cfg=env_cfg, device=device)
    env.reset()
    wrapped = RslRlVecEnvWrapper(env, clip_actions=rl_cfg.clip_actions)
    runner = VelocityOnPolicyRunner(wrapped, asdict(rl_cfg), None, device)
    return env, runner, wrapped, rl_cfg


def export_checkpoint(args: argparse.Namespace) -> Path:
    run_dir = Path(args.run).resolve()
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run directory not found: {run_dir}")
    checkpoint = Path(args.checkpoint)
    if not checkpoint.is_absolute():
        checkpoint = run_dir / checkpoint
    checkpoint = checkpoint.resolve()
    if not checkpoint.is_file():
        raise FileNotFoundError(f"checkpoint not found: {checkpoint}")

    package_root = Path(args.package_root).resolve()
    out = Path(args.out).resolve() if args.out else run_dir / "exported" / f"{checkpoint.stem}.onnx"
    reference = run_dir / "exported" / "policy.onnx"
    if out == reference and not args.force:
        raise ValueError(
            f"--out points at the training-time reference {reference}; "
            "choose another path or pass --force"
        )

    print(f"[run]        {run_dir}")
    print(f"[checkpoint] {checkpoint}")
    print(f"[out]        {out}")

    env, runner, wrapped, rl_cfg = build_env_and_runner(
        run_dir, package_root, args.num_envs, args.device
    )
    try:
        runner.load(str(checkpoint), load_cfg={"actor": True}, strict=True,
                    map_location=args.device)
        print(f"[load] actor weights restored from {checkpoint.name}")

        # 复用训练完成的导出函数（actor -> ONNX + 部署元数据盖章），导出到临时
        # staging 再搬到 --out，避免写出 exported/exported/policy.onnx 或覆盖真值。
        from adapters.mjlab import native_worker

        staging = Path(tempfile.mkdtemp(prefix="ckpt_onnx_export_"))
        report: dict = {}
        try:
            native_worker.export_runner_policy_onnx(
                report=report,
                env=env,
                runner=runner,
                wrapped=wrapped,
                rl_cfg=rl_cfg,
                output=staging,
                device=args.device,
                contract=resolve_contract(run_dir, package_root),
            )
        finally:
            produced = staging / "exported" / "policy.onnx"
            if produced.is_file():
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(produced), str(out))
            shutil.rmtree(staging, ignore_errors=True)
        _restamp_run_path(out, run_dir)
        print(f"[export] {out}")
        if report.get("onnx_metadata_keys"):
            print(f"[export] metadata keys: {', '.join(report['onnx_metadata_keys'])}")
    finally:
        env.close()
    return out


def _restamp_run_path(onnx_path: Path, run_dir: Path) -> None:
    """staging 导出的 run_path 指向临时目录；改成 checkpoint 所属 run，保持元数据诚实。"""
    try:
        import onnx

        model = onnx.load(str(onnx_path))
        for entry in model.metadata_props:
            if entry.key == "run_path":
                entry.value = str(run_dir)
        onnx.save(model, str(onnx_path))
    except Exception as exc:  # noqa: BLE001
        print(f"[export] run_path restamp skipped: {type(exc).__name__}: {exc}")


def verify_against_reference(out_path: Path, reference: Path) -> bool:
    """64 个固定随机观测（seed 0）逐样本喂两张图（参照图定长 batch=1），比 max|Δ|。"""
    import numpy as np
    import onnxruntime as ort

    rng = np.random.default_rng(VERIFY_SEED)
    obs = rng.standard_normal((VERIFY_SAMPLES, VERIFY_OBS_DIM), dtype=np.float32)

    def run_graph(path: Path) -> np.ndarray:
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
        input_name = session.get_inputs()[0].name
        outputs = [session.run(None, {input_name: obs[i:i + 1]})[0] for i in range(VERIFY_SAMPLES)]
        return np.concatenate(outputs, axis=0)

    mine = run_graph(out_path)
    theirs = run_graph(reference)
    max_abs_diff = float(np.max(np.abs(mine - theirs)))
    print(f"[verify] samples={VERIFY_SAMPLES} obs=({VERIFY_SAMPLES},{VERIFY_OBS_DIM}) rng seed={VERIFY_SEED}")
    print(f"[verify] reference: {reference}")
    print(f"[verify] max|Δ| = {max_abs_diff:.3e} (tolerance {VERIFY_TOLERANCE:.0e})")
    if max_abs_diff < VERIFY_TOLERANCE:
        print("[verify] OK")
        return True
    print("[verify] FAIL")
    return False


def main() -> int:
    args = parse_args()
    out = export_checkpoint(args)
    reference = Path(args.run).resolve() / "exported" / "policy.onnx"
    if args.verify and reference.is_file():
        if not verify_against_reference(out, reference):
            return 1
    elif args.verify:
        print(f"[verify] skipped: no reference at {reference}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
