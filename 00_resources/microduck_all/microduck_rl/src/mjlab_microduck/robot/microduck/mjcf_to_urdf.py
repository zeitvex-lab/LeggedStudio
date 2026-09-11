#!/usr/bin/env python3
"""Convert Microduck's articulated walking MJCF to a portable URDF."""

from __future__ import annotations

import argparse
import math
import xml.etree.ElementTree as ET
from pathlib import Path


ZERO3 = "0 0 0"
IDENTITY_QUAT = "1 0 0 0"
DEFAULT_VELOCITY_LIMIT = "10"


def floats(value: str | None, default: str) -> list[float]:
    return [float(item) for item in (value or default).split()]


def scalar(value: float) -> str:
    if abs(value) < 1e-12:
        value = 0.0
    return f"{value:.12g}"


def vector(values: list[float]) -> str:
    return " ".join(scalar(value) for value in values)


def quat_to_rpy(value: str | None) -> str:
    w, x, y, z = floats(value, IDENTITY_QUAT)
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    if norm == 0:
        raise ValueError("zero-length quaternion")
    w, x, y, z = (component / norm for component in (w, x, y, z))

    r00 = 1 - 2 * (y * y + z * z)
    r01 = 2 * (x * y - z * w)
    r02 = 2 * (x * z + y * w)
    r10 = 2 * (x * y + z * w)
    r20 = 2 * (x * z - y * w)
    r21 = 2 * (y * z + x * w)
    r22 = 1 - 2 * (x * x + y * y)

    horizontal = math.hypot(r00, r10)
    pitch = math.atan2(-r20, horizontal)
    if horizontal > 1e-10:
        roll = math.atan2(r21, r22)
        yaw = math.atan2(r10, r00)
    elif r20 < 0:
        # At +pi/2, roll and yaw are coupled; choose yaw=0 deterministically.
        roll = math.atan2(r01, r02)
        yaw = 0.0
    else:
        # At -pi/2, choose the equivalent solution with yaw=0.
        roll = math.atan2(-r01, -r02)
        yaw = 0.0
    return vector([roll, pitch, yaw])


def add_origin(parent: ET.Element, source: ET.Element) -> None:
    ET.SubElement(
        parent,
        "origin",
        xyz=vector(floats(source.get("pos"), ZERO3)),
        rpy=quat_to_rpy(source.get("quat")),
    )


def default_attributes(root: ET.Element, tag: str) -> dict[str, dict[str, str]]:
    attributes: dict[str, dict[str, str]] = {}
    for default in root.findall(".//default"):
        class_name = default.get("class")
        item = default.find(tag)
        if class_name and item is not None:
            attributes[class_name] = dict(item.attrib)
    return attributes


def mesh_files(root: ET.Element) -> dict[str, str]:
    result: dict[str, str] = {}
    asset = root.find("asset")
    if asset is None:
        return result
    for mesh in asset.findall("mesh"):
        filename = mesh.get("file")
        if not filename:
            continue
        name = mesh.get("name") or Path(filename).stem
        result[name] = filename
    return result


def add_geometry(
    link: ET.Element,
    geom: ET.Element,
    kind: str,
    index: int,
    meshes: dict[str, str],
) -> None:
    item = ET.SubElement(link, kind, name=f"{link.get('name')}_{kind}_{index}")
    add_origin(item, geom)
    geometry = ET.SubElement(item, "geometry")
    mesh_name = geom.get("mesh")
    if not mesh_name or mesh_name not in meshes:
        raise ValueError(f"unknown mesh on {link.get('name')}: {mesh_name!r}")
    ET.SubElement(geometry, "mesh", filename=f"assets/{meshes[mesh_name]}")
    if kind == "visual" and geom.get("material"):
        ET.SubElement(item, "material", name=geom.get("material"))


def build_urdf(source: Path) -> ET.ElementTree:
    mjcf = ET.parse(source).getroot()
    robot = ET.Element("robot", name=mjcf.get("model", "microduck"))
    robot.append(
        ET.Comment(
            " Generated from robot_walk.xml; mesh paths are relative to this file. "
        )
    )

    asset = mjcf.find("asset")
    if asset is not None:
        for material in asset.findall("material"):
            name = material.get("name")
            rgba = material.get("rgba")
            if name and rgba:
                urdf_material = ET.SubElement(robot, "material", name=name)
                ET.SubElement(urdf_material, "color", rgba=rgba)

    meshes = mesh_files(mjcf)
    joint_defaults = default_attributes(mjcf, "joint")
    actuator_defaults = default_attributes(mjcf, "position")
    joints: list[ET.Element] = []
    frame_joints: list[ET.Element] = []

    def add_body(body: ET.Element, parent_name: str | None) -> None:
        body_name = body.get("name")
        if not body_name:
            raise ValueError("every MJCF body must have a name")

        link = ET.SubElement(robot, "link", name=body_name)
        inertial = body.find("inertial")
        if inertial is None:
            raise ValueError(f"body {body_name} has no inertial")
        urdf_inertial = ET.SubElement(link, "inertial")
        add_origin(urdf_inertial, inertial)
        ET.SubElement(urdf_inertial, "mass", value=inertial.get("mass", "0"))
        values = floats(inertial.get("fullinertia"), "0 0 0 0 0 0")
        if len(values) != 6:
            raise ValueError(f"body {body_name} has invalid fullinertia")
        ixx, iyy, izz, ixy, ixz, iyz = values
        ET.SubElement(
            urdf_inertial,
            "inertia",
            ixx=scalar(ixx),
            ixy=scalar(ixy),
            ixz=scalar(ixz),
            iyy=scalar(iyy),
            iyz=scalar(iyz),
            izz=scalar(izz),
        )

        visual_index = 0
        collision_index = 0
        for geom in body.findall("geom"):
            class_name = geom.get("class")
            if class_name == "visual":
                add_geometry(link, geom, "visual", visual_index, meshes)
                visual_index += 1
            elif class_name in {"collision", "self_collision_only"}:
                add_geometry(link, geom, "collision", collision_index, meshes)
                collision_index += 1

        if parent_name is not None:
            joint = body.find("joint")
            if joint is None or joint.get("type", "hinge") != "hinge":
                raise ValueError(f"body {body_name} must have one hinge joint")
            if any(abs(v) > 1e-12 for v in floats(joint.get("pos"), ZERO3)):
                raise ValueError(f"non-zero joint pos is unsupported on {body_name}")

            urdf_joint = ET.Element(
                "joint", name=joint.get("name", f"{body_name}_joint"), type="revolute"
            )
            ET.SubElement(urdf_joint, "parent", link=parent_name)
            ET.SubElement(urdf_joint, "child", link=body_name)
            add_origin(urdf_joint, body)
            ET.SubElement(
                urdf_joint,
                "axis",
                xyz=vector(floats(joint.get("axis"), "0 0 1")),
            )

            limits = floats(joint.get("range"), "0 0")
            class_name = joint.get("class", "")
            actuator = actuator_defaults.get(class_name, {})
            force_range = floats(actuator.get("forcerange"), "-10 10")
            effort = max(abs(force_range[0]), abs(force_range[1]))
            ET.SubElement(
                urdf_joint,
                "limit",
                lower=scalar(limits[0]),
                upper=scalar(limits[1]),
                effort=scalar(effort),
                velocity=DEFAULT_VELOCITY_LIMIT,
            )

            dynamics = joint_defaults.get(class_name, {})
            ET.SubElement(
                urdf_joint,
                "dynamics",
                damping=dynamics.get("damping", "0"),
                friction=dynamics.get("frictionloss", "0"),
            )
            joints.append(urdf_joint)

        for site in body.findall("site"):
            site_name = site.get("name")
            if not site_name:
                continue
            frame_name = site_name if site_name not in {body_name} else f"{site_name}_frame"
            ET.SubElement(robot, "link", name=frame_name)
            frame_joint = ET.Element(
                "joint", name=f"{frame_name}_fixed_joint", type="fixed"
            )
            ET.SubElement(frame_joint, "parent", link=body_name)
            ET.SubElement(frame_joint, "child", link=frame_name)
            add_origin(frame_joint, site)
            frame_joints.append(frame_joint)

        for child in body.findall("body"):
            add_body(child, body_name)

    worldbody = mjcf.find("worldbody")
    if worldbody is None:
        raise ValueError("MJCF has no worldbody")
    roots = worldbody.findall("body")
    if len(roots) != 1:
        raise ValueError(f"expected one root body, found {len(roots)}")
    add_body(roots[0], None)

    robot.extend(joints)
    robot.extend(frame_joints)
    ET.indent(robot, space="  ")
    return ET.ElementTree(robot)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", type=Path, default=Path("robot_walk.xml"))
    parser.add_argument("output", nargs="?", type=Path, default=Path("microduck.urdf"))
    args = parser.parse_args()
    tree = build_urdf(args.source)
    tree.write(args.output, encoding="utf-8", xml_declaration=True)
    print(args.output)


if __name__ == "__main__":
    main()
