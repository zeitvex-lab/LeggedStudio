#!/usr/bin/env python3
"""
Assemble Microduck robot from individual STL meshes using MuJoCo MJCF transforms.

Usage:
    python3 assemble.py                    # Assembles both variants
    python3 assemble.py --variant legs     # Only legs (walking) variant
    python3 assemble.py --variant rollers  # Only rollers (wheeled) variant

Requires: trimesh, numpy
    pip install trimesh numpy
"""
import argparse
import os
import xml.etree.ElementTree as ET

import numpy as np
import trimesh


def parse_quat(q):
    """Convert quaternion [w, x, y, z] to 3x3 rotation matrix."""
    w, x, y, z = q
    return np.array([
        [1 - 2*(y*y + z*z), 2*(x*y - w*z),     2*(x*z + w*y)],
        [2*(x*y + w*z),     1 - 2*(x*x + z*z), 2*(y*z - w*x)],
        [2*(x*z - w*y),     2*(y*z + w*x),     1 - 2*(x*x + y*y)]
    ])


def build_body_tree(worldbody):
    """Extract body hierarchy from MJCF worldbody element."""
    body_info = {}

    def walk(el, parent_name):
        for child in el:
            if child.tag == 'body':
                name = child.get('name')
                pos = list(map(float, child.get('pos', '0 0 0').split()))
                quat = list(map(float, child.get('quat', '1 0 0 0').split()))
                body_info[name] = {'pos': pos, 'quat': quat, 'parent': parent_name}
                walk(child, name)

    walk(worldbody, None)
    return body_info


def assemble(mjcf_path, stl_dir, output_path):
    """Read MJCF, apply transforms to STLs, export combined mesh."""
    tree = ET.parse(mjcf_path)
    root = tree.getroot()
    wb = root.find('worldbody')

    body_info = build_body_tree(wb)
    print(f"  Bodies: {len(body_info)} ({', '.join(body_info.keys())})")

    cache = {}

    def cum_transform(name):
        if name is None:
            return np.eye(4)
        if name in cache:
            return cache[name]
        b = body_info[name]
        R = parse_quat(b['quat'])
        T = np.eye(4)
        T[:3, :3] = R
        T[:3, 3] = b['pos']
        result = cum_transform(b['parent']) @ T
        cache[name] = result
        return result

    meshes = []
    loaded = 0

    def walk_geoms(el, body_name):
        nonlocal loaded
        for child in el:
            if child.tag == 'body':
                walk_geoms(child, child.get('name'))
            elif child.tag == 'geom':
                if child.get('type') != 'mesh':
                    continue
                if child.get('class', '') in ('collision', 'self_collision_only'):
                    continue
                mesh_name = child.get('mesh')
                if not mesh_name:
                    continue
                stl_file = os.path.join(stl_dir, f"{mesh_name}.stl")
                if not os.path.exists(stl_file):
                    continue
                body_T = cum_transform(body_name)
                gpos = list(map(float, child.get('pos', '0 0 0').split()))
                gquat = list(map(float, child.get('quat', '1 0 0 0').split()))
                R = parse_quat(gquat)
                T = np.eye(4)
                T[:3, :3] = R
                T[:3, 3] = gpos
                m = trimesh.load(stl_file)
                m.apply_transform(body_T @ T)
                meshes.append(m)
                loaded += 1

    walk_geoms(wb, None)
    print(f"  Loaded: {loaded} meshes")

    if not meshes:
        print("  ERROR: No meshes loaded!")
        return

    combined = trimesh.util.concatenate(meshes)
    size = combined.bounds[1] - combined.bounds[0]
    print(f"  Combined: {len(combined.vertices)} vertices, {len(combined.faces)} faces")
    print(f"  Size: {np.round(size, 3)} m")

    combined.export(output_path)
    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"  Exported: {output_path} ({size_mb:.1f} MB)")


def main():
    parser = argparse.ArgumentParser(description="Assemble Microduck robot from STL meshes")
    parser.add_argument('--variant', choices=['legs', 'rollers', 'both'], default='both')
    parser.add_argument('--dir', default=os.path.dirname(os.path.abspath(__file__)),
                        help="Directory containing STL files and MJCF XML")
    args = parser.parse_args()

    stl_dir = args.dir

    variants = []
    if args.variant in ('legs', 'both'):
        variants.append(('robot_allcollisions.xml', 'microduck_combined.stl', 'LEGS (walking)'))
    if args.variant in ('rollers', 'both'):
        variants.append(('robot_allcollisions_rollers.xml', 'microduck_combined_rollers.stl', 'ROLLERS (wheeled)'))

    for mjcf_name, out_name, label in variants:
        mjcf_path = os.path.join(stl_dir, mjcf_name)
        out_path = os.path.join(stl_dir, out_name)
        if not os.path.exists(mjcf_path):
            print(f"  SKIP {label}: {mjcf_name} not found")
            continue
        print(f"\n=== {label} ===")
        assemble(mjcf_path, stl_dir, out_path)

    print("\nDone!")


if __name__ == '__main__':
    main()
