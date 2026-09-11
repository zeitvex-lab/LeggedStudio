"""Strip an MJCF down to what's needed for forward kinematics.

Removes geoms, mesh/material assets, actuators, sensors, contacts. Keeps
body/joint/site/inertial so MuJoCo can still load the model (for FK tests)
without needing any STL files on disk.

Usage:
    python strip_mjcf.py <input.xml> <output.xml>
"""

import sys
import xml.etree.ElementTree as ET


def strip(tree: ET.ElementTree) -> None:
    root = tree.getroot()

    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag in {"geom", "camera"}:
                parent.remove(child)

    for tag in ("asset", "actuator", "sensor", "contact", "default", "equality"):
        for el in root.findall(tag):
            root.remove(el)

    # `childclass` / `class` attributes reference <default> blocks we just
    # removed, so MuJoCo would refuse to load the model.
    for el in root.iter():
        for attr in ("class", "childclass"):
            el.attrib.pop(attr, None)

    compiler = root.find("compiler")
    if compiler is not None and "meshdir" in compiler.attrib:
        del compiler.attrib["meshdir"]


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    in_path, out_path = sys.argv[1], sys.argv[2]
    tree = ET.parse(in_path)
    strip(tree)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
