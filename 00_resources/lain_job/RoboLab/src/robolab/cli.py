"""Small command line entry point for framework checks and smoke tests."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from robolab.frameworks.isaacgym.runtime import (
    IsaacGymRuntimeError,
    list_isaacgym_tasks,
    run_isaacgym_play,
    run_isaacgym_evaluate,
    run_isaacgym_smoke,
    run_isaacgym_train,
)
from robolab.frameworks.mjlab.runtime import (
    MjlabSourceError,
    list_mjlab_tasks,
    run_mjlab_evaluate,
    run_mjlab_play,
    run_mjlab_smoke,
    run_mjlab_train,
)
from robolab.workflows import list_workflows, run_workflow


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="robolab")
    subparsers = parser.add_subparsers(dest="command")

    isaacgym = subparsers.add_parser(
        "isaacgym", help="inspect or smoke-test local Isaac Gym + legged_gym"
    )
    isaacgym_subparsers = isaacgym.add_subparsers(
        dest="isaacgym_command", required=True
    )
    isaacgym_subparsers.add_parser("list", help="list registered legged_gym tasks")
    isaacgym_smoke = isaacgym_subparsers.add_parser(
        "smoke", help="run one legged_gym reset/step smoke test"
    )
    isaacgym_smoke.add_argument("--task", default="a1")
    isaacgym_smoke.add_argument("--num-envs", type=int, default=1)
    isaacgym_smoke.add_argument("--device", default="cuda:0")
    isaacgym_smoke.add_argument("--seed", type=int, default=0)
    isaacgym_smoke.add_argument("--method", default="ppo")
    isaacgym_train = isaacgym_subparsers.add_parser(
        "train", help="run a real rsl_rl PPO training job"
    )
    isaacgym_train.add_argument("--task", default="a1")
    isaacgym_train.add_argument("--num-envs", type=int, default=1024)
    isaacgym_train.add_argument("--device", default="cuda:0")
    isaacgym_train.add_argument("--seed", type=int, default=0)
    isaacgym_train.add_argument("--max-iterations", type=int, default=1500)
    isaacgym_train.add_argument("--run-dir", default=None)
    isaacgym_train.add_argument("--resume-from", default=None)
    isaacgym_train.add_argument("--method", default="ppo")
    isaacgym_play = isaacgym_subparsers.add_parser(
        "play", help="run a trained checkpoint in the real A1 environment"
    )
    isaacgym_play.add_argument("--task", default="a1")
    isaacgym_play.add_argument("--checkpoint", required=True)
    isaacgym_play.add_argument("--num-envs", type=int, default=1)
    isaacgym_play.add_argument("--device", default="cuda:0")
    isaacgym_play.add_argument("--seed", type=int, default=0)
    isaacgym_play.add_argument("--steps", type=int, default=256)
    isaacgym_play.add_argument(
        "--visualize",
        action="store_true",
        help="stream normalized SceneFrame data to MJLab's web-based Viser viewer",
    )
    isaacgym_play.add_argument("--method", default="ppo")
    isaacgym_evaluate = isaacgym_subparsers.add_parser(
        "evaluate", help="evaluate an Isaac Gym checkpoint in an independent worker"
    )
    isaacgym_evaluate.add_argument("--task", default="a1")
    isaacgym_evaluate.add_argument("--checkpoint", required=True)
    isaacgym_evaluate.add_argument("--num-envs", type=int, default=1024)
    isaacgym_evaluate.add_argument("--device", default="cuda:0")
    isaacgym_evaluate.add_argument("--seed", type=int, default=0)
    isaacgym_evaluate.add_argument("--steps", type=int, default=1024)
    isaacgym_evaluate.add_argument("--method", default="ppo")

    mjlab = subparsers.add_parser("mjlab", help="inspect or smoke-test local MJLab")
    mjlab_subparsers = mjlab.add_subparsers(dest="mjlab_command", required=True)
    mjlab_subparsers.add_parser("list", help="list registered MJLab tasks")
    smoke = mjlab_subparsers.add_parser("smoke", help="run one reset/step smoke test")
    smoke.add_argument(
        "--task",
        default="Mjlab-Velocity-Flat-Unitree-Go1",
        help="registered MJLab task ID",
    )
    smoke.add_argument("--num-envs", type=int, default=1)
    smoke.add_argument("--device", default=None, help="e.g. cuda:0 or cpu")
    smoke.add_argument("--seed", type=int, default=0)
    mjlab_train = mjlab_subparsers.add_parser(
        "train", help="run native MJLab RSL-RL PPO training"
    )
    mjlab_train.add_argument("--task", default="Mjlab-Velocity-Flat-Unitree-Go1")
    mjlab_train.add_argument("--num-envs", type=int, default=64)
    mjlab_train.add_argument("--device", default="cuda:0")
    mjlab_train.add_argument("--seed", type=int, default=0)
    mjlab_train.add_argument("--max-iterations", type=int, default=1)
    mjlab_train.add_argument("--run-dir", default=None)
    mjlab_train.add_argument("--resume-from", default=None)
    mjlab_play = mjlab_subparsers.add_parser(
        "play", help="run a trained policy in MJLab"
    )
    mjlab_play.add_argument("--task", default="Mjlab-Velocity-Flat-Unitree-Go1")
    mjlab_play.add_argument("--checkpoint", required=True)
    mjlab_play.add_argument("--num-envs", type=int, default=1)
    mjlab_play.add_argument("--device", default="cuda:0")
    mjlab_play.add_argument("--seed", type=int, default=0)
    mjlab_play.add_argument("--steps", type=int, default=256)
    mjlab_play.add_argument(
        "--visualize",
        action="store_true",
        help="open MJLab's web-based Viser viewer instead of headless metrics mode",
    )
    mjlab_evaluate = mjlab_subparsers.add_parser(
        "evaluate", help="evaluate a trained MJLab velocity policy"
    )
    mjlab_evaluate.add_argument("--task", default="Mjlab-Velocity-Flat-Unitree-Go1")
    mjlab_evaluate.add_argument("--checkpoint", required=True)
    mjlab_evaluate.add_argument("--num-envs", type=int, default=64)
    mjlab_evaluate.add_argument("--device", default="cuda:0")
    mjlab_evaluate.add_argument("--seed", type=int, default=0)
    mjlab_evaluate.add_argument("--steps", type=int, default=512)
    workflow = subparsers.add_parser("workflow", help="run a Python RoboLab workflow")
    workflow_subparsers = workflow.add_subparsers(dest="workflow_command", required=True)
    workflow_subparsers.add_parser("list", help="list available workflows")
    workflow_run = workflow_subparsers.add_parser("run", help="run one workflow")
    workflow_run.add_argument("workflow", choices=("train", "reproduce", "evaluate", "export"))
    workflow_run.add_argument("--framework", choices=("isaacgym", "mjlab"), default="isaacgym")
    workflow_run.add_argument("--task", default="a1")
    workflow_run.add_argument("--method", default="ppo")
    workflow_run.add_argument("--robot", default="unitree_a1")
    workflow_run.add_argument("--checkpoint")
    workflow_run.add_argument("--num-envs", type=int, default=1024)
    workflow_run.add_argument("--device", default="cuda:0")
    workflow_run.add_argument("--seed", type=int, default=0)
    workflow_run.add_argument("--steps", type=int, default=1024)
    workflow_run.add_argument("--max-iterations", type=int, default=1500)
    workflow_run.add_argument("--checkpoint-interval", type=int, default=300)
    workflow_run.add_argument("--run-dir")
    workflow_run.add_argument("--resume-from")
    workflow_run.add_argument("--recipe", help="path to a complete resolved recipe JSON")
    workflow_run.add_argument("--output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command is None:
        _build_parser().print_help()
        return 0

    try:
        if args.command == "workflow":
            list_command = args.workflow_command
            if list_command == "list":
                print("\n".join(list_workflows()))
                return 0
            values = vars(args).copy()
            values.pop("command", None)
            values.pop("workflow_command", None)
            skill_name = values.pop("workflow")
            recipe_path = values.pop("recipe", None)
            if recipe_path and skill_name != "train":
                raise ValueError("--recipe is supported only by workflow train")
            if recipe_path:
                from pathlib import Path
                recipe_file = Path(recipe_path).expanduser().resolve()
                if not recipe_file.is_file():
                    raise FileNotFoundError(f"recipe does not exist: {recipe_file}")
                recipe = json.loads(recipe_file.read_text())
                values.update({key: value for key, value in recipe.items() if key not in {"schema_version", "recipe_path"}})
                values["recipe_path"] = str(recipe_file)
            if skill_name in ("evaluate", "export") and not values.get("checkpoint"):
                raise ValueError(f"workflow {skill_name!r} requires --checkpoint")
            if skill_name == "export":
                values = {
                    key: value for key, value in values.items()
                    if key in {"checkpoint", "framework", "method", "robot", "task", "output"}
                }
            elif skill_name == "evaluate":
                values.pop("max_iterations", None)
                values.pop("run_dir", None)
                values.pop("resume_from", None)
                values.pop("robot", None)
                values.pop("output", None)
            else:
                values.pop("checkpoint", None)
                values.pop("steps", None)
                values.pop("output", None)
            result = run_workflow(skill_name, **values)
            output = result.to_dict()
            if args.command == "workflow":
                output["workflow"] = skill_name
            print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "isaacgym":
            if args.isaacgym_command == "list":
                print("\n".join(list_isaacgym_tasks()))
                return 0
            if args.isaacgym_command == "train":
                result = run_isaacgym_train(
                    task_id=args.task,
                    num_envs=args.num_envs,
                    device=args.device,
                    seed=args.seed,
                    max_iterations=args.max_iterations,
                    run_dir=args.run_dir,
                    resume_from=args.resume_from,
                    method_id=args.method,
                )
                print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            if args.isaacgym_command == "play":
                result = run_isaacgym_play(
                    args.checkpoint,
                    task_id=args.task,
                    num_envs=args.num_envs,
                    device=args.device,
                    seed=args.seed,
                    steps=args.steps,
                    visualize=args.visualize,
                    method_id=args.method,
                )
                print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            if args.isaacgym_command == "evaluate":
                result = run_isaacgym_evaluate(
                    args.checkpoint,
                    task_id=args.task,
                    num_envs=args.num_envs,
                    device=args.device,
                    seed=args.seed,
                    steps=args.steps,
                    method_id=args.method,
                )
                print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            result = run_isaacgym_smoke(
                task_id=args.task,
                num_envs=args.num_envs,
                device=args.device,
                seed=args.seed,
                method_id=args.method,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.mjlab_command == "list":
            print("\n".join(list_mjlab_tasks()))
            return 0
        if args.mjlab_command == "train":
            result = run_mjlab_train(
                task_id=args.task,
                num_envs=args.num_envs,
                device=args.device,
                seed=args.seed,
                max_iterations=args.max_iterations,
                run_dir=args.run_dir,
                resume_from=args.resume_from,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.mjlab_command == "play":
            result = run_mjlab_play(
                args.checkpoint,
                task_id=args.task,
                num_envs=args.num_envs,
                device=args.device,
                seed=args.seed,
                steps=args.steps,
                visualize=args.visualize,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.mjlab_command == "evaluate":
            result = run_mjlab_evaluate(
                args.checkpoint,
                task_id=args.task,
                num_envs=args.num_envs,
                device=args.device,
                seed=args.seed,
                steps=args.steps,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        result = run_mjlab_smoke(
            task_id=args.task,
            num_envs=args.num_envs,
            device=args.device,
            seed=args.seed,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (IsaacGymRuntimeError, MjlabSourceError) as exc:
        print(f"RoboLab: {exc}")
        return 2
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"RoboLab command failed: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
