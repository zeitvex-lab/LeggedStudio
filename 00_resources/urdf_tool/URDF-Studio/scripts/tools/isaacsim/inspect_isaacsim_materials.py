#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re

from isaaclab.app import AppLauncher


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open USD stages in Isaac Sim and summarize material palettes and bindings.",
    )
    parser.add_argument("paths", nargs="+", help="USD stage paths to inspect.")
    parser.add_argument("--output", required=True, help="Where to write the JSON summary.")
    AppLauncher.add_app_launcher_args(parser)
    return parser.parse_args()


def _to_json_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if hasattr(value, "__iter__") and not isinstance(value, (bytes, bytearray, str)):
        try:
            return [_to_json_value(entry) for entry in value]
        except TypeError:
            pass

    return str(value)


def _extract_color_tuple(value: object) -> list[float] | None:
    converted = _to_json_value(value)
    components: list[object] | None = None
    if isinstance(converted, list):
        if (
            len(converted) >= 1
            and isinstance(converted[0], list)
            and len(converted[0]) >= 3
        ):
            components = converted[0][:3]
        elif len(converted) >= 3:
            components = converted[:3]
    elif isinstance(converted, str):
        matches = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", converted)
        if len(matches) >= 3:
            components = [float(entry) for entry in matches[:3]]

    if components is None:
        return None

    result: list[float] = []
    for entry in components:
        if not isinstance(entry, (int, float)):
            return None
        result.append(round(float(entry), 6))

    return result


def _extract_texture_reference(value: object) -> str | None:
    converted = _to_json_value(value)
    if not isinstance(converted, str):
        return None

    normalized = converted.strip()
    return normalized or None


def _iter_prims_with_instance_proxies(stage) -> object:
    from pxr import Usd

    predicate = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
    stack = [stage.GetPseudoRoot()]

    while stack:
        prim = stack.pop()
        yield prim

        children = list(prim.GetFilteredChildren(predicate))
        children.reverse()
        stack.extend(children)


def _resolve_imageable_context(prim) -> tuple[object, object]:
    from pxr import UsdGeom

    current = prim
    while current and current.IsValid():
        imageable = UsdGeom.Imageable(current)
        if imageable:
            return imageable.ComputePurpose(), imageable.ComputeVisibility()
        current = current.GetParent()

    return None, None


def _sorted_signature_key(entry: dict[str, object]) -> tuple[object, ...]:
    color = entry.get("color")
    color_key = tuple(color) if isinstance(color, list) else ()
    return (
        1 if entry.get("textured") else 0,
        *color_key,
        str(entry.get("source") or ""),
        str(entry.get("colorSource") or ""),
    )


def summarize_stage(path: str) -> dict[str, object]:
    from pxr import Usd, UsdGeom, UsdShade

    stage = Usd.Stage.Open(path)
    if stage is None:
        return {
            "path": path,
            "open_ok": False,
        }

    materials: dict[str, dict[str, dict[str, object]]] = {}
    material_info_by_path: dict[str, dict[str, object]] = {}
    material_names: list[str] = []
    material_colors: list[list[float]] = []
    material_color_by_path: dict[str, list[float]] = {}
    color_keys: set[tuple[float, float, float]] = set()
    bindings: list[dict[str, object]] = []
    visible_material_names: set[str] = set()
    visible_material_paths: set[str] = set()
    visible_material_color_keys: set[tuple[float, float, float]] = set()
    visible_material_colors: list[list[float]] = []
    visible_appearance_signatures: list[dict[str, object]] = []
    visible_signature_keys: set[tuple[object, ...]] = set()

    def push_visible_signature(entry: dict[str, object]) -> None:
        key = _sorted_signature_key(entry)
        if key in visible_signature_keys:
            return

        visible_signature_keys.add(key)
        visible_appearance_signatures.append(entry)

    for prim in stage.Traverse():
        prim_path = prim.GetPath().pathString

        if prim.GetTypeName() == "Material":
            material_names.append(prim.GetName())
            material_entry: dict[str, dict[str, object]] = {}
            material_textures: set[str] = set()
            preferred_color: list[float] | None = None
            fallback_color: list[float] | None = None
            for child in prim.GetChildren():
                shader = UsdShade.Shader(child)
                if not shader:
                    continue

                shader_entry: dict[str, object] = {}
                for shader_input in shader.GetInputs():
                    value = _to_json_value(shader_input.GetAttr().Get())
                    shader_entry[shader_input.GetFullName()] = value
                    input_base_name = shader_input.GetBaseName()
                    if input_base_name in {"diffuseColor", "diffuse_color_constant"}:
                        color_tuple = _extract_color_tuple(value)
                        if color_tuple:
                            preferred_color = color_tuple
                    elif input_base_name == "fallback":
                        color_tuple = _extract_color_tuple(value)
                        if color_tuple:
                            fallback_color = color_tuple

                    if input_base_name in {"diffuse_texture", "opacity_texture", "file"}:
                        texture_reference = _extract_texture_reference(value)
                        if texture_reference:
                            material_textures.add(texture_reference)

                for shader_output in shader.GetOutputs():
                    shader_entry[shader_output.GetFullName()] = _to_json_value(
                        shader_output.GetAttr().Get()
                    )

                material_entry[child.GetName()] = shader_entry

            material_color = preferred_color or fallback_color
            material_color_source = (
                "authored"
                if preferred_color
                else "fallback"
                if fallback_color
                else None
            )
            if material_color:
                color_key = tuple(material_color)
                material_color_by_path[prim_path] = material_color
                if color_key not in color_keys:
                    color_keys.add(color_key)
                    material_colors.append(material_color)

            material_info_by_path[prim_path] = {
                "path": prim_path,
                "name": prim.GetName(),
                "color": material_color,
                "colorSource": material_color_source,
                "textures": sorted(material_textures),
                "textured": len(material_textures) > 0,
            }
            materials[prim.GetName()] = material_entry
            continue

    for prim in _iter_prims_with_instance_proxies(stage):
        is_gprim = prim.IsA(UsdGeom.Gprim)
        is_geom_subset = prim.GetTypeName() == "GeomSubset"
        if not is_gprim and not is_geom_subset:
            continue

        purpose, visibility = _resolve_imageable_context(prim)
        if purpose == UsdGeom.Tokens.guide or visibility == UsdGeom.Tokens.invisible:
            continue

        prim_path = prim.GetPath().pathString
        display_color = (
            _extract_color_tuple(UsdGeom.Gprim(prim).GetDisplayColorAttr().Get())
            if is_gprim
            else None
        )

        bound_material = None
        try:
            computed = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
            if computed:
                bound_material = computed[0]
        except Exception:
            bound_material = None

        binding_entry: dict[str, object] = {
            "path": prim_path,
            "type": prim.GetTypeName(),
            "purpose": purpose if purpose else None,
            "visibility": visibility if visibility else None,
        }

        if bound_material and bound_material.GetPrim().IsValid():
            material_path = bound_material.GetPath().pathString
            material_info = material_info_by_path.get(material_path) or {}
            material_has_color = material_path in material_color_by_path
            material_color = material_color_by_path.get(material_path) or display_color
            material_color_source = (
                material_info.get("colorSource")
                if material_has_color
                else "displayColor"
                if display_color
                else None
            )
            binding_entry["material"] = [material_path]
            binding_entry["materialName"] = bound_material.GetPrim().GetName()
            binding_entry["textured"] = bool(material_info.get("textured"))
            binding_entry["color"] = material_color
            binding_entry["colorSource"] = material_color_source
            bindings.append(binding_entry)

            visible_material_paths.add(material_path)
            visible_material_names.add(bound_material.GetPrim().GetName())
            if material_color:
                color_key = tuple(material_color)
                if color_key not in visible_material_color_keys:
                    visible_material_color_keys.add(color_key)
                    visible_material_colors.append(material_color)

            push_visible_signature(
                {
                    "source": "material",
                    "color": material_color,
                    "colorSource": material_color_source,
                    "textured": bool(material_info.get("textured")),
                }
            )
            continue

        if display_color:
            binding_entry["material"] = []
            binding_entry["color"] = display_color
            binding_entry["colorSource"] = "displayColor"
            binding_entry["textured"] = False
            bindings.append(binding_entry)

            color_key = tuple(display_color)
            if color_key not in visible_material_color_keys:
                visible_material_color_keys.add(color_key)
                visible_material_colors.append(display_color)

            push_visible_signature(
                {
                    "source": "displayColor",
                    "color": display_color,
                    "colorSource": "displayColor",
                    "textured": False,
                }
            )

    visible_bindings = [binding for binding in bindings if binding.get("purpose") != "guide"]
    visible_textured_material_count = sum(
        1
        for material_path in visible_material_paths
        if bool(material_info_by_path.get(material_path, {}).get("textured"))
    )

    return {
        "path": path,
        "open_ok": True,
        "materialCount": len(material_names),
        "materialNames": sorted(material_names),
        "materialColors": sorted(material_colors),
        "materials": materials,
        "materialInfo": {
            material_path: material_info_by_path[material_path]
            for material_path in sorted(material_info_by_path)
        },
        "bindingCount": len(bindings),
        "firstBindings": bindings[:64],
        "visibleBindingCount": len(visible_bindings),
        "visibleMaterialCount": len(visible_material_paths),
        "visibleMaterialNames": sorted(visible_material_names),
        "visibleMaterialColors": sorted(visible_material_colors),
        "visibleMaterialPaths": sorted(visible_material_paths),
        "visibleTexturedMaterialCount": visible_textured_material_count,
        "visibleAppearanceCount": len(visible_appearance_signatures),
        "visibleAppearanceSignatures": sorted(
            visible_appearance_signatures,
            key=_sorted_signature_key,
        ),
    }


def main() -> None:
    args = parse_args()
    app_launcher = AppLauncher(args)
    simulation_app = app_launcher.app

    try:
        payload = {path: summarize_stage(path) for path in args.paths}
        with open(args.output, "w", encoding="utf-8") as output_file:
            json.dump(payload, output_file, indent=2)
    finally:
        simulation_app.close()


if __name__ == "__main__":
    main()
