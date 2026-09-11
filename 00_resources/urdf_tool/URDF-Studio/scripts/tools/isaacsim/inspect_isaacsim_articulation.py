#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json

from isaaclab.app import AppLauncher


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open USD stages in Isaac Sim and inspect articulation initialization results.",
    )
    parser.add_argument("paths", nargs="+", help="USD stage paths to inspect.")
    parser.add_argument("--output", required=True, help="Where to write the JSON summary.")
    AppLauncher.add_app_launcher_args(parser)
    return parser.parse_args()


def inspect_stage(path: str) -> dict[str, object]:
    import isaacsim.core.utils.stage as stage_utils
    from isaacsim.core.api.simulation_context import SimulationContext
    from isaacsim.core.prims import Articulation
    from pxr import UsdPhysics

    result = {
        "path": path,
        "open_ok": False,
        "default_prim": None,
        "articulation_root_candidates": [],
        "attempts": [],
    }

    if not stage_utils.open_stage(path):
        return result

    stage = stage_utils.get_current_stage()
    if stage is None:
        return result

    result["open_ok"] = True
    default_prim = stage.GetDefaultPrim()
    default_prim_path = default_prim.GetPath().pathString if default_prim and default_prim.IsValid() else None
    result["default_prim"] = default_prim_path

    articulation_root_candidates = [
        prim.GetPath().pathString
        for prim in stage.Traverse()
        if prim.HasAPI(UsdPhysics.ArticulationRootAPI)
    ]
    result["articulation_root_candidates"] = articulation_root_candidates

    sim = SimulationContext(
        physics_dt=0.01,
        rendering_dt=0.01,
        stage_units_in_meters=1.0,
        backend="numpy",
    )

    try:
        candidate_paths = []
        if default_prim_path:
            candidate_paths.append(default_prim_path)
        candidate_paths.extend(
            path for path in articulation_root_candidates if path not in candidate_paths
        )

        for candidate in candidate_paths:
            attempt: dict[str, object] = {
                "candidate": candidate,
                "initialized": False,
            }
            try:
                articulation = Articulation(candidate, reset_xform_properties=False)
                sim.reset()
                articulation.initialize()
                attempt.update(
                    {
                        "initialized": True,
                        "num_dof": articulation.num_dof,
                        "dof_names": list(articulation.dof_names or []),
                        "body_count": articulation.num_bodies,
                    }
                )
            except Exception as error:  # noqa: BLE001
                attempt["error"] = str(error)
            result["attempts"].append(attempt)
    finally:
        sim.stop()
        sim.clear()
        sim.clear_all_callbacks()
        sim.clear_instance()

    return result


def main() -> None:
    args = parse_args()
    app_launcher = AppLauncher(args)
    simulation_app = app_launcher.app

    try:
        payload = {path: inspect_stage(path) for path in args.paths}
        with open(args.output, "w", encoding="utf-8") as output_file:
            json.dump(payload, output_file, indent=2)
    finally:
        simulation_app.close()


if __name__ == "__main__":
    main()
