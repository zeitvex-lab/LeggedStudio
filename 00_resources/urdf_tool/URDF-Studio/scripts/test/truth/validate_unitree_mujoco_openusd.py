#!/usr/bin/env python3
"""Probe MuJoCo OpenUSD import support against Unitree USD fixtures."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from xml.sax.saxutils import escape


DEFAULT_FIXTURE_ROOT = Path("test/unitree_model")
DEFAULT_OUTPUT_PATH = Path("tmp/regression/unitree-mujoco-openusd.json")
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_STEP_COUNT = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate whether MuJoCo Python can compile Unitree OpenUSD fixtures."
    )
    parser.add_argument("--fixture-root", default=str(DEFAULT_FIXTURE_ROOT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--match", action="append", default=[])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--step-count", type=int, default=DEFAULT_STEP_COUNT)
    parser.add_argument(
        "--require-openusd",
        action="store_true",
        help="Exit non-zero when the active MuJoCo runtime has no OpenUSD decoder.",
    )
    parser.add_argument("--_worker", default=None, help=argparse.SUPPRESS)
    return parser.parse_args()


def is_openusd_decoder_missing(message: str) -> bool:
    lowered = message.lower()
    return (
        "could not find decoder" in lowered
        or "could not decode content" in lowered
        or "unknown resource type" in lowered
        or "unsupported content type" in lowered
        or "only text/xml is supported" in lowered
    )


def result(status: str, path: str, error: str | None = None, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"path": path, "status": status, "error": error}
    payload.update(extra)
    return payload


def compile_direct(mujoco: Any, usd_path: Path) -> Any:
    spec = mujoco.MjSpec.from_file(str(usd_path))
    return spec.compile()


def compile_via_mjcf_wrapper(mujoco: Any, usd_path: Path) -> Any:
    xml = f"""
<mujoco model="unitree_openusd_wrapper">
  <asset>
    <model file="{escape(str(usd_path))}" name="unitree_openusd" content_type="text/usd"/>
  </asset>
  <worldbody>
    <attach model="unitree_openusd" prefix="unitree_"/>
  </worldbody>
</mujoco>
"""
    spec = mujoco.MjSpec.from_string(xml)
    return spec.compile()


def step_model(mujoco: Any, model: Any, data: Any, step_count: int) -> None:
    if step_count <= 0:
        return
    try:
        mujoco.mj_step(model, data, nstep=step_count)
    except TypeError:
        for _ in range(step_count):
            mujoco.mj_step(model, data)


def run_worker(path: str, step_count: int) -> int:
    usd_path = Path(path).resolve()
    try:
        import mujoco  # type: ignore
    except Exception as exc:
        print(json.dumps(result("unsupported", str(usd_path), f"{type(exc).__name__}: {exc}")))
        return 0

    if not hasattr(mujoco, "MjSpec"):
        print(
            json.dumps(
                result(
                    "unsupported",
                    str(usd_path),
                    "mujoco.MjSpec is not available",
                    mujocoVersion=getattr(mujoco, "__version__", None),
                    reason="mjspec-missing",
                )
            )
        )
        return 0

    attempts = []
    model = None
    import_mode = None
    for mode, compile_model in (("direct", compile_direct), ("mjcf-wrapper", compile_via_mjcf_wrapper)):
        try:
            model = compile_model(mujoco, usd_path)
            import_mode = mode
            break
        except Exception as exc:
            attempts.append({"mode": mode, "error": f"{type(exc).__name__}: {exc}"})

    if model is None:
        message = "; ".join(f"{item['mode']}: {item['error']}" for item in attempts)
        status = "unsupported" if attempts and all(
            is_openusd_decoder_missing(str(item["error"])) for item in attempts
        ) else "fail"
        print(
            json.dumps(
                result(
                    status,
                    str(usd_path),
                    message,
                    attempts=attempts,
                    mujocoVersion=getattr(mujoco, "__version__", None),
                    reason="openusd-decoder-missing" if status == "unsupported" else "compile-failed",
                )
            )
        )
        return 0

    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    step_model(mujoco, model, data, step_count)
    print(
        json.dumps(
            result(
                "pass",
                str(usd_path),
                None,
                attempts=attempts,
                importMode=import_mode,
                mujocoVersion=getattr(mujoco, "__version__", None),
                counts={
                    "nbody": int(model.nbody),
                    "ngeom": int(model.ngeom),
                    "njnt": int(model.njnt),
                    "nmesh": int(model.nmesh),
                    "nq": int(model.nq),
                    "nv": int(model.nv),
                    "nu": int(model.nu),
                },
                dataTime=float(data.time),
                stepCount=step_count,
            )
        )
    )
    return 0


def inspect_mujoco_environment() -> dict[str, Any]:
    try:
        import mujoco  # type: ignore
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}", "python": sys.executable}

    module_file = getattr(mujoco, "__file__", None)
    return {
        "available": True,
        "version": getattr(mujoco, "__version__", None),
        "module": str(Path(module_file).resolve()) if module_file else None,
        "python": sys.executable,
        "hasMjSpec": hasattr(mujoco, "MjSpec"),
        "hasMjVfs": hasattr(mujoco, "MjVfs"),
    }


def discover_fixtures(root: Path, matches: list[str], limit: int | None) -> list[Path]:
    normalized_matches = [match.lower() for match in matches if match.strip()]
    paths = []
    for path in root.rglob("*.usd"):
        relative = path.relative_to(root)
        parts = {part.lower() for part in relative.parts}
        if "configuration" in parts or path.name.endswith(".viewer_roundtrip.usd"):
            continue
        haystack = str(relative).lower()
        if normalized_matches and not all(match in haystack for match in normalized_matches):
            continue
        paths.append(path)
    paths.sort(key=lambda item: str(item.relative_to(root)))
    return paths[:limit] if limit is not None else paths


def run_fixture(path: Path, root: Path, timeout: float, step_count: int) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--_worker", str(path.resolve()), "--step-count", str(step_count)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        env=os.environ.copy(),
    )
    json_line = next((line for line in completed.stdout.splitlines() if line.strip().startswith("{")), "")
    try:
        payload = json.loads(json_line or "{}")
    except json.JSONDecodeError:
        payload = result("fail", str(path.resolve()), "worker did not emit JSON", stdout=completed.stdout)
    payload["relativePath"] = str(path.relative_to(root))
    payload["exitCode"] = completed.returncode
    if completed.stderr:
        payload["stderr"] = completed.stderr.strip()
    if completed.returncode != 0 and payload.get("status") == "pass":
        payload["status"] = "fail"
        payload["error"] = f"worker exited with code {completed.returncode}"
    return payload


def summarize(results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"total": len(results), "pass": 0, "fail": 0, "unsupported": 0}
    for item in results:
        status = item.get("status")
        summary[status if status in summary else "fail"] += 1
    return summary


def main() -> int:
    args = parse_args()
    if args._worker:
        return run_worker(args._worker, args.step_count)

    root = Path(args.fixture_root).resolve()
    output_path = Path(args.output).resolve()
    if not root.exists():
        raise SystemExit(f"Fixture root does not exist: {root}")
    fixtures = discover_fixtures(root, args.match, args.limit)
    if not fixtures:
        raise SystemExit(f"No Unitree USD fixtures found under {root}")

    env = inspect_mujoco_environment()
    if not env.get("available") or not env.get("hasMjSpec"):
        message = str(env.get("error") or "mujoco.MjSpec is not available")
        results = [
            result("unsupported", str(path.resolve()), message, relativePath=str(path.relative_to(root)))
            for path in fixtures
        ]
    else:
        results = [run_fixture(path, root, args.timeout, args.step_count) for path in fixtures]

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "fixtureRoot": str(root),
        "outputPath": str(output_path),
        "requireOpenUsd": bool(args.require_openusd),
        "stepCount": args.step_count,
        "timeoutSeconds": args.timeout,
        "mujocoEnvironment": env,
        "results": results,
        "summary": summarize(results),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"[mujoco-openusd] python: {env.get('python')}")
    print(f"[mujoco-openusd] mujoco: {env.get('version') if env.get('available') else 'unavailable'}")
    for item in results:
        if item["status"] == "pass":
            counts = item.get("counts", {})
            print(
                f"[pass] {item['relativePath']} mode={item.get('importMode')} "
                f"nbody={counts.get('nbody')} ngeom={counts.get('ngeom')} njnt={counts.get('njnt')}"
            )
        else:
            print(f"[{item['status']}] {item['relativePath']} {item.get('error')}")
    print(
        "[summary] "
        f"total={report['summary']['total']} pass={report['summary']['pass']} "
        f"unsupported={report['summary']['unsupported']} fail={report['summary']['fail']}"
    )
    print(f"[report] {output_path}")

    if report["summary"]["fail"]:
        return 1
    if args.require_openusd and report["summary"]["unsupported"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
