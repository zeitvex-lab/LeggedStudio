"""把一个 URDF 转成能独立编译的 MJCF（**手动路径**；导入流程已自动做这一步）。

转换实现只有一份：`backend/package_import._convert_urdf_to_mjcf`——本工具只是它的 CLI 壳，
免得"手动转"与"导入自动转"两份实现悄悄漂移。导入时（`onboard` / `POST /api/models/import`）
URDF 会被自动转成 MJCF 并作为训练模型，除非转换失败（那种情况会按 URDF 原样收下并写明原因）。

用法：
    python tools/urdf_to_mjcf.py <robot.urdf> [<out_model.xml>]

不给输出路径时写到源文件同目录的 `<stem>.xml`。生成的 MJCF 含
joints/bodies/inertials/collision geoms，但**不含执行器**——执行器由 mjlab 的
actuator cfg（`Builtin*` / `XmlActuatorCfg`）在训练/仿真时提供。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def convert(urdf_path: Path, out_path: Path | None = None) -> Path:
    from backend.package_import import _convert_urdf_to_mjcf

    converted, note = _convert_urdf_to_mjcf(Path(urdf_path))
    if converted is None:
        print(f"error: {note}", file=sys.stderr)
        raise SystemExit(1)
    if out_path is not None and Path(out_path) != converted:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(converted.read_text(encoding="utf-8"), encoding="utf-8")
        converted.unlink()
        converted = Path(out_path)
    import mujoco

    model = mujoco.MjModel.from_xml_path(str(converted))
    print(f"converted: nq={model.nq} nu={model.nu} nbody={model.nbody}")
    print(f"wrote {converted}")
    return converted


def main() -> None:
    parser = argparse.ArgumentParser(description="URDF → MJCF（薄封装，实现见 backend.package_import）")
    parser.add_argument("urdf", type=Path, help="输入 URDF")
    parser.add_argument("out_xml", type=Path, nargs="?", help="输出 MJCF（默认写到源文件同目录 <stem>.xml）")
    args = parser.parse_args()
    if not args.urdf.exists():
        print(f"error: {args.urdf} not found", file=sys.stderr)
        raise SystemExit(1)
    convert(args.urdf, args.out_xml)


if __name__ == "__main__":
    main()
