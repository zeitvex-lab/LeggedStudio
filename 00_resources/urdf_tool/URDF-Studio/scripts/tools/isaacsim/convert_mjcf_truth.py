#!/usr/bin/env python3
"""Convert MJCF to USD for regression truth generation in Isaac Sim.

This patches two IsaacLab issues relevant to our regression flow:
1. The default headless experience does not preload the MJCF importer extension.
2. IsaacLab's MjcfConverter currently hardcodes import_sites=True.
"""

from __future__ import annotations

import argparse
import os

from isaaclab.app import AppLauncher


parser = argparse.ArgumentParser(description="Convert a MJCF file into USD for Isaac Sim truth generation.")
parser.add_argument("input", type=str, help="The path to the input MJCF file.")
parser.add_argument("output", type=str, help="The path to store the USD file.")
parser.add_argument("--fix-base", action="store_true", default=False, help="Fix the base to where it is imported.")
parser.add_argument(
    "--import-sites",
    action="store_true",
    default=False,
    help="Import sites by parsing the <site> tag.",
)
parser.add_argument(
    "--make-instanceable",
    action="store_true",
    default=False,
    help="Make the asset instanceable for efficient cloning.",
)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import carb
import mujoco
import omni.kit.app
import omni.kit.commands
from isaacsim.core.utils.extensions import enable_extension

from isaaclab.sim.converters import MjcfConverter, MjcfConverterCfg
from isaaclab.utils.assets import check_file_path
from isaaclab.utils.dict import print_dict


def ensure_mjcf_importer_enabled() -> None:
    app = omni.kit.app.get_app()
    manager = app.get_extension_manager()
    extension_name = "isaacsim.asset.importer.mjcf"

    if manager.is_extension_enabled(extension_name):
        return

    enable_extension(extension_name)
    for _ in range(120):
        app.update()
        if manager.is_extension_enabled(extension_name):
            return

    raise RuntimeError(f"Failed to enable required Isaac Sim extension: {extension_name}")


def validate_mujoco_can_parse(mjcf_path: str) -> None:
    try:
        mujoco.MjModel.from_xml_path(mjcf_path)
    except Exception as exc:
        raise RuntimeError(
            f"MuJoCo failed to parse MJCF before Isaac Sim conversion: {mjcf_path}: {exc}"
        ) from exc


class RegressionMjcfConverter(MjcfConverter):
    """MjcfConverter variant that respects cfg.import_sites in regression runs."""

    def __init__(self, cfg: MjcfConverterCfg):
        ensure_mjcf_importer_enabled()
        super().__init__(cfg)

    def _get_mjcf_import_config(self):
        ok, import_config = omni.kit.commands.execute("MJCFCreateImportConfig")
        if not ok or import_config is None:
            raise RuntimeError("Isaac Sim did not provide a valid MJCF import config.")

        import_config.set_import_sites(bool(self.cfg.import_sites))
        import_config.set_make_instanceable(self.cfg.make_instanceable)
        import_config.set_instanceable_usd_path(self.usd_instanceable_meshes_path)
        import_config.set_density(self.cfg.link_density)
        import_config.set_import_inertia_tensor(self.cfg.import_inertia_tensor)
        import_config.set_fix_base(self.cfg.fix_base)
        import_config.set_self_collision(self.cfg.self_collision)
        return import_config


def main() -> None:
    mjcf_path = args_cli.input
    if not os.path.isabs(mjcf_path):
        mjcf_path = os.path.abspath(mjcf_path)
    if not check_file_path(mjcf_path):
        raise ValueError(f"Invalid file path: {mjcf_path}")
    validate_mujoco_can_parse(mjcf_path)

    dest_path = args_cli.output
    if not os.path.isabs(dest_path):
        dest_path = os.path.abspath(dest_path)

    mjcf_converter_cfg = MjcfConverterCfg(
        asset_path=mjcf_path,
        usd_dir=os.path.dirname(dest_path),
        usd_file_name=os.path.basename(dest_path),
        fix_base=args_cli.fix_base,
        import_sites=args_cli.import_sites,
        force_usd_conversion=True,
        make_instanceable=args_cli.make_instanceable,
    )

    print("-" * 80)
    print("-" * 80)
    print(f"Input MJCF file: {mjcf_path}")
    print("MJCF importer config:")
    print_dict(mjcf_converter_cfg.to_dict(), nesting=0)
    print("-" * 80)
    print("-" * 80)

    mjcf_converter = RegressionMjcfConverter(mjcf_converter_cfg)

    print("MJCF importer output:")
    print(f"Generated USD file: {mjcf_converter.usd_path}")
    print("-" * 80)
    print("-" * 80)

    carb_settings_iface = carb.settings.get_settings()
    local_gui = carb_settings_iface.get("/app/window/enabled")
    livestream_gui = carb_settings_iface.get("/app/livestream/enabled")

    if local_gui or livestream_gui:
        app = omni.kit.app.get_app_interface()
        while app.is_running():
            app.update()


if __name__ == "__main__":
    try:
        main()
    finally:
        simulation_app.close()
