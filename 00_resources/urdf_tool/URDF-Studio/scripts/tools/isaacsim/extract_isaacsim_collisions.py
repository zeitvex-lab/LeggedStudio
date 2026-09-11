#!/usr/bin/env python3
"""
Extract collision geometry from Isaac Lab/Isaac Sim USD files.

This script uses pxr.Usd to parse USD files and extract collision geometry
information, which can then be used to fix collision imports in URDF Studio.

Usage:
    # Activate isaaclab22 environment
    conda activate isaaclab22

    # Run the script
    python scripts/extract_isaacsim_collisions.py /path/to/file.usd --output collision_data.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from pxr import Usd, UsdGeom, UsdPhysics, Gf
except ImportError:
    print("Error: pxr module not found. Please activate isaaclab22 environment:")
    print("  conda activate isaaclab22")
    exit(1)


def quat_to_euler(qw, qx, qy, qz) -> tuple[float, float, float]:
    """Convert quaternion (w, x, y, z) to XYZ Euler angles in radians."""
    # Normalize quaternion
    norm = (qw * qw + qx * qx + qy * qy + qz * qz) ** 0.5
    if norm < 1e-6:
        return 0.0, 0.0, 0.0
    qw, qx, qy, qz = qw / norm, qx / norm, qy / norm, qz / norm

    # Roll (x-axis rotation)
    sinr_cosp = 2 * (qw * qx + qy * qz)
    cosr_cosp = 1 - 2 * (qx * qx + qy * qy)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    # Pitch (y-axis rotation)
    sinp = 2 * (qw * qy - qz * qx)
    if abs(sinp) >= 1:
        pitch = math.copysign(math.pi / 2, sinp)
    else:
        pitch = math.asin(sinp)

    # Yaw (z-axis rotation)
    siny_cosp = 2 * (qw * qz + qx * qy)
    cosy_cosp = 1 - 2 * (qy * qy + qz * qz)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return roll, pitch, yaw


import math


def get_transform_with_parent_scale(prim: Usd.Prim) -> dict[str, Any]:
    """
    Extract transform from a prim, including parent scale for Isaac Lab collisions.

    In Isaac Lab USD files, collision geometry often has unit dimensions and
    the actual size is specified in the parent Xform's scale attribute.
    """
    translate = Gf.Vec3d(0, 0, 0)
    rotate = Gf.Vec3d(0, 0, 0)
    scale = Gf.Vec3d(1, 1, 1)

    # First, check if prim has xform ops (for collision containers)
    xformable = UsdGeom.Xformable(prim)
    if xformable:
        # Parse transform operations in order
        for op in xformable.GetOrderedXformOps():
            op_time = Usd.TimeCode.Default()
            op_type = op.GetOpType()

            if op_type == UsdGeom.XformOp.TypeTranslate:
                vec = op.Get(op_time)
                if vec:
                    translate = Gf.Vec3d(vec[0], vec[1], vec[2])
            elif op_type == UsdGeom.XformOp.TypeRotateXYZ:
                vec = op.Get(op_time)
                if vec:
                    rotate = Gf.Vec3d(vec[0], vec[1], vec[2])
            elif op_type == UsdGeom.XformOp.TypeRotateX:
                vec = op.Get(op_time)
                if vec:
                    rotate.x = float(vec)
            elif op_type == UsdGeom.XformOp.TypeRotateY:
                vec = op.Get(op_time)
                if vec:
                    rotate.y = float(vec)
            elif op_type == UsdGeom.XformOp.TypeRotateZ:
                vec = op.Get(op_time)
                if vec:
                    rotate.z = float(vec)
            elif op_type == UsdGeom.XformOp.TypeOrient:
                # Quaternion rotation (Isaac Lab uses this)
                quat = op.Get(op_time)
                if quat:
                    # quat is a Gf.Quatf with (w, x, y, z) components
                    qw, qx, qy, qz = quat.GetReal(), quat.GetImaginary()[0], quat.GetImaginary()[1], quat.GetImaginary()[2]
                    roll, pitch, yaw = quat_to_euler(qw, qx, qy, qz)
                    rotate = Gf.Vec3d(roll, pitch, yaw)
            elif op_type == UsdGeom.XformOp.TypeScale:
                vec = op.Get(op_time)
                if vec:
                    scale = Gf.Vec3d(vec[0], vec[1], vec[2])

    return {
        "translate": [float(translate[0]), float(translate[1]), float(translate[2])],
        "rotate": [float(rotate[0]), float(rotate[1]), float(rotate[2])],  # XYZ Euler in radians
        "scale": [float(scale[0]), float(scale[1]), float(scale[2])],
    }


def get_combined_transform(prim: Usd.Prim, parent: Usd.Prim | None) -> dict[str, Any]:
    """
    Get combined transform from parent (if collision container) and prim itself.

    For Isaac Lab collisions, the parent Xform (e.g., collision_0) contains
    the actual transform including scale that defines the collision size.
    """
    parent_transform = get_transform_with_parent_scale(parent) if parent and parent.IsValid() else None
    geom_transform = get_transform_with_parent_scale(prim)

    # If parent has scale (this is an Isaac Lab collision), apply it to geometry
    if parent_transform and parent_transform["scale"] != [1, 1, 1]:
        # For Isaac Lab collisions, the geometry has unit dimensions
        # and the actual size comes from parent scale
        return {
            "translate": parent_transform["translate"],
            "rotate": parent_transform["rotate"],
            "scale": parent_transform["scale"],  # This is the actual size
        }

    return geom_transform


def get_geometry_info(prim: Usd.Prim, parent_scale: list[float] | None = None) -> dict[str, Any] | None:
    """
    Extract geometry information from a prim, applying parent scale for Isaac Lab collisions.

    For Isaac Lab USD files, collision geometry has unit dimensions and the actual
    size is specified in the parent Xform's scale attribute.
    """
    # Check for various geometry types
    geom_type = prim.GetTypeName()

    # Default parent scale is [1, 1, 1]
    if parent_scale is None:
        parent_scale = [1, 1, 1]

    if geom_type == "Mesh":
        mesh = UsdGeom.Mesh(prim)
        if mesh:
            # Get extent for bounding box
            extent_attr = mesh.GetExtentAttr()
            if extent_attr:
                extent = extent_attr.Get()
                if extent:
                    min_pt = extent[0]
                    max_pt = extent[1]
                    size = [
                        float(max_pt[0] - min_pt[0]),
                        float(max_pt[1] - min_pt[1]),
                        float(max_pt[2] - min_pt[2]),
                    ]
                    # Apply parent scale to mesh dimensions
                    size = [size[i] * parent_scale[i] for i in range(3)]
                    center = [
                        float((min_pt[0] + max_pt[0]) / 2),
                        float((min_pt[1] + max_pt[1]) / 2),
                        float((min_pt[2] + max_pt[2]) / 2),
                    ]
                    return {
                        "type": "mesh",
                        "dimensions": size,
                        "center": center,
                        "base_dimensions": [float(max_pt[0] - min_pt[0]), float(max_pt[1] - min_pt[1]), float(max_pt[2] - min_pt[2])],
                    }
    elif geom_type == "Capsule":
        capsule = UsdGeom.Capsule(prim)
        if capsule:
            radius = float(capsule.GetRadiusAttr().Get() or 0.0)
            height = float(capsule.GetHeightAttr().Get() or 0.0)
            # Apply parent scale - for capsule: scale[0] and scale[2] affect radius, scale[1] affects height
            actual_radius = radius * parent_scale[0] if parent_scale[0] == parent_scale[2] else (radius * parent_scale[0] + radius * parent_scale[2]) / 2
            actual_height = height * parent_scale[1]
            return {
                "type": "capsule",
                "base_radius": radius,
                "base_height": height,
                "radius": actual_radius,
                "height": actual_height,
                "dimensions": [actual_radius * 2, actual_height, actual_radius * 2],
                "parent_scale": parent_scale,
            }
    elif geom_type == "Sphere":
        sphere = UsdGeom.Sphere(prim)
        if sphere:
            radius = float(sphere.GetRadiusAttr().Get() or 0.0)
            # Apply parent scale (use average of x and z if they differ)
            actual_radius = radius * (parent_scale[0] + parent_scale[2]) / 2
            return {
                "type": "sphere",
                "base_radius": radius,
                "radius": actual_radius,
                "dimensions": [actual_radius * 2, actual_radius * 2, actual_radius * 2],
                "parent_scale": parent_scale,
            }
    elif geom_type == "Cylinder":
        cylinder = UsdGeom.Cylinder(prim)
        if cylinder:
            radius = float(cylinder.GetRadiusAttr().Get() or 0.0)
            height = float(cylinder.GetHeightAttr().Get() or 0.0)
            # Apply parent scale - for cylinder: scale[0] and scale[2] affect radius, scale[1] affects height
            actual_radius = radius * parent_scale[0] if parent_scale[0] == parent_scale[2] else (radius * parent_scale[0] + radius * parent_scale[2]) / 2
            actual_height = height * parent_scale[1]
            return {
                "type": "cylinder",
                "base_radius": radius,
                "base_height": height,
                "radius": actual_radius,
                "height": actual_height,
                "dimensions": [actual_radius * 2, actual_height, actual_radius * 2],
                "parent_scale": parent_scale,
            }
    elif geom_type == "Cube":
        cube = UsdGeom.Cube(prim)
        if cube:
            size = float(cube.GetSizeAttr().Get() or 0.0)
            # Apply parent scale
            actual_size = [size * parent_scale[i] for i in range(3)]
            return {
                "type": "box",
                "base_size": size,
                "size": actual_size,
                "dimensions": actual_size,
                "parent_scale": parent_scale,
            }

    return None


def is_collision_prim(prim: Usd.Prim) -> bool:
    """
    Determine if a prim represents collision geometry.

    Isaac Lab/Isaac Sim uses several conventions:
    1. purpose="guide" attribute
    2. Prim name contains "collision" or "collider"
    3. Has PhysicsCollisionAPI applied
    """
    # Check for purpose attribute
    if prim.HasAttribute("purpose"):
        purpose = prim.GetAttribute("purpose").Get()
        if purpose == "guide":
            return True

    # Check for collision in name/path
    path_str = prim.GetPath().pathString.lower()
    if "collision" in path_str or "collider" in path_str:
        return True

    # Check for PhysicsCollisionAPI
    if UsdPhysics.CollisionAPI(prim):
        return True

    # Check parent scope
    current = prim.GetParent()
    while current and current.IsValid():
        ancestor_path = current.GetPath().pathString.lower()
        if "collision" in ancestor_path or "collider" in ancestor_path:
            # Check if ancestor has purpose="guide"
            if current.HasAttribute("purpose"):
                purpose = current.GetAttribute("purpose").Get()
                if purpose == "guide":
                    return True
        current = current.GetParent()

    return False


def get_link_name(prim: Usd.Prim, default_prim: Usd.Prim | None) -> str:
    """
    Determine the link name for a collision prim.

    For Isaac Lab USD files, the structure is typically:
    /robot_name/link_name/collisions/collision_N/geometry

    We need to extract the link name (the segment before "collisions").
    """
    path_str = prim.GetPath().pathString

    # Remove robot name prefix (first segment after leading /)
    parts = path_str.split("/")
    parts = [p for p in parts if p]  # Remove empty strings

    if len(parts) < 3:
        return "unknown_link"

    # Find the "collisions" or "colliders" segment index
    collision_index = -1
    for i, segment in enumerate(parts):
        if segment.lower() in ["collisions", "colliders"]:
            collision_index = i
            break

    if collision_index > 0:
        # Link name is the segment before "collisions"
        link_name = parts[collision_index - 1]
        return link_name

    # Fallback: try to find a segment that looks like a link name
    # (not "visuals", "collision", "geometry", etc.)
    for segment in reversed(parts):
        if segment.lower() not in ["visuals", "collisions", "colliders", "geometry", "collision", "collider", "visual", "box", "cylinder", "sphere", "mesh", "capsule"]:
            return segment

    return "unknown_link"


def extract_collisions(stage: Usd.Stage) -> dict[str, Any]:
    """
    Extract all collision geometry from a USD stage.

    For Isaac Lab USD files, collision geometry is structured as:
    - /link/collisions/collision_N (Xform with purpose='guide', contains transform including scale)
        - geometry (Cube, Cylinder, Sphere, Mesh with purpose='guide')

    The actual collision size is derived from the parent Xform's scale.
    """
    default_prim = stage.GetDefaultPrim()

    collisions_by_link: dict[str, list[dict[str, Any]]] = {}
    collision_count = 0
    skipped_count = 0

    # Track collision containers (Xforms that contain geometry)
    collision_containers: dict[Usd.Prim, list[Usd.Prim]] = {}

    # First pass: find collision containers
    for prim in stage.Traverse():
        if not is_collision_prim(prim):
            continue

        # Check if this is a collision container (Xform with child geometry)
        if prim.GetTypeName() == "Xform" and prim.HasAttribute("purpose"):
            purpose = prim.GetAttribute("purpose").Get()
            if purpose == "guide":
                # This is likely a collision container
                children = []
                for child in prim.GetChildren():
                    child_type = child.GetTypeName()
                    if child_type in ["Cube", "Cylinder", "Sphere", "Mesh", "Capsule"]:
                        children.append(child)
                if children:
                    collision_containers[prim] = children

    # Second pass: extract geometry from containers or standalone prims
    for prim in stage.Traverse():
        if not is_collision_prim(prim):
            continue

        geom_type = prim.GetTypeName()

        # Check if this prim is inside a collision container
        parent = prim.GetParent()
        parent_scale = None
        use_parent_transform = False

        if parent and parent.IsValid() and parent in collision_containers:
            # This geometry is inside an Isaac Lab collision container
            parent_xform = get_transform_with_parent_scale(parent)
            parent_scale = parent_xform["scale"]
            use_parent_transform = True

        # Only process geometry prims, not container Xforms
        if geom_type in ["Cube", "Cylinder", "Sphere", "Mesh", "Capsule"]:
            geom_info = get_geometry_info(prim, parent_scale)
            if not geom_info:
                skipped_count += 1
                continue

            # Get transform - use parent transform for Isaac Lab collisions
            if use_parent_transform and parent:
                transform = get_transform_with_parent_scale(parent)
            else:
                transform = get_transform_with_parent_scale(prim)

            link_name = get_link_name(prim, default_prim)

            collision_entry = {
                "prim_path": prim.GetPath().pathString,
                "parent_path": parent.GetPath().pathString if parent and parent.IsValid() else None,
                "geometry": geom_info,
                "transform": transform,
                "prim_type": geom_type,
                "is_isaac_lab_collision": use_parent_transform,
            }

            if link_name not in collisions_by_link:
                collisions_by_link[link_name] = []
            collisions_by_link[link_name].append(collision_entry)
            collision_count += 1

    return {
        "collision_count": collision_count,
        "skipped_count": skipped_count,
        "link_count": len(collisions_by_link),
        "collisions_by_link": collisions_by_link,
    }


def summarize_stage(stage: Usd.Stage) -> dict[str, Any]:
    """Create a summary of the USD stage structure."""
    default_prim = stage.GetDefaultPrim()

    prim_types: dict[str, int] = {}
    collision_prims: list[str] = []
    visual_prims: list[str] = []

    for prim in stage.Traverse():
        prim_type = prim.GetTypeName() or "Unknown"
        prim_types[prim_type] = prim_types.get(prim_type, 0) + 1

        path = prim.GetPath().pathString

        # Check purpose
        if prim.HasAttribute("purpose"):
            purpose = prim.GetAttribute("purpose").Get()
            if purpose == "guide":
                collision_prims.append(path)
            elif purpose == "default" or purpose == "render":
                visual_prims.append(path)

    return {
        "default_prim": default_prim.GetPath().pathString if default_prim and default_prim.IsValid() else None,
        "prim_types": prim_types,
        "collision_prims_by_purpose": collision_prims,
        "visual_prims_by_purpose": visual_prims,
        "total_prims": sum(prim_types.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract collision geometry from Isaac Lab/Isaac Sim USD files."
    )
    parser.add_argument("paths", nargs="+", help="USD file paths to process.")
    parser.add_argument("--output", "-o", required=True, help="Output JSON file path.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print detailed information.")
    args = parser.parse_args()

    results: dict[str, Any] = {}

    for path in args.paths:
        print(f"Processing: {path}")

        stage = Usd.Stage.Open(path)
        if stage is None:
            print(f"  ERROR: Failed to open stage")
            results[path] = {"error": "Failed to open stage"}
            continue

        # Create stage summary
        summary = summarize_stage(stage)

        # Extract collisions
        collisions = extract_collisions(stage)

        if args.verbose:
            print(f"  Total prims: {summary['total_prims']}")
            print(f"  Prim types: {summary['prim_types']}")
            print(f"  Collision prims (by purpose='guide'): {len(summary['collision_prims_by_purpose'])}")
            print(f"  Visual prims (by purpose='render'): {len(summary['visual_prims_by_purpose'])}")
            print(f"  Extracted collisions: {collisions['collision_count']}")
            print(f"  Skipped (no geometry): {collisions['skipped_count']}")
            print(f"  Links with collisions: {collisions['link_count']}")

        results[path] = {
            "summary": summary,
            "collisions": collisions,
        }

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults written to: {output_path}")


if __name__ == "__main__":
    main()
