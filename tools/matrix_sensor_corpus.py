"""Container probe for the MATRiX v1.0.13 sensor corpus.

MATRiX v1.0.13 ships two recorded sensor dumps next to the sensor simulation
plugin::

    UeSim/Plugins/RobotSensorSimulation/Data/
        Airy_2026-07-03_frame0225.airybin       63,652,192 B
        Mid360_2025-11-28_2s_valid.mid360bin    12,717,276 B

Both are little-endian containers that start with a 4-byte magic
(``ARY1`` for the Airy lidar, ``M3D1`` for the Mid360) followed by a version and
a frame table. The framing is deterministic and is verified here: the payload
starts at a fixed small offset and the remainder divides exactly into frames::

    body_offset + frames * frame_size == file_size

Measured on the shipped files: Airy -> body 352 B, 37 frames; Mid360 -> body
348 B, 48 frames. At the documented 10 Hz lidar rate that is 3.7 s and 4.8 s of
recording.

The *point payload* is intentionally not decoded. It is not a plain little
endian ``float32`` array — probing the body as float columns yields mostly
non-finite/denormal values for both files, i.e. the records mix integer and
float fields with a layout that the release does not document. Rather than ship
a guessed parser, this tool pins down what is verifiable (magic, version, frame
table, framing) and keeps the payload opaque.

Usage::

    python tools/matrix_sensor_corpus.py                 # probe the extracted release
    python tools/matrix_sensor_corpus.py --json          # machine readable
    python tools/matrix_sensor_corpus.py --selftest      # synthetic round-trip, no release needed

Exit codes: 0 = all present and consistent, 1 = inconsistent, 2 = corpus absent
(the release directory is a downloaded artifact and is not tracked by git).
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

MAGICS: dict[bytes, str] = {b"ARY1": "airy", b"M3D1": "mid360"}
DOCUMENTED_FREQUENCY_HZ = 10.0
HEADER_PROBE_BYTES = 32
BODY_OFFSET_LIMIT = 4096

CORPUS: tuple[tuple[str, str], ...] = (
    ("Airy_2026-07-03_frame0225.airybin", "Plugins/RobotSensorSimulation/Data"),
    ("Mid360_2025-11-28_2s_valid.mid360bin", "Plugins/RobotSensorSimulation/Data"),
)

DEFAULT_PACKAGE_DIR = Path("matrix-v1.0.13/extracted/MATRiX_v1.0.13")


def probe_container(path: Path) -> dict[str, object]:
    """Read one ``.airybin`` / ``.mid360bin`` container header and its framing.

    Returns a plain dict so the result can be serialized or asserted in tests.
    ``consistent`` is True only when the magic is known and
    ``body_offset + frames * frame_size == size`` exactly.
    """
    result: dict[str, object] = {
        "path": str(path),
        "exists": path.is_file(),
        "size": 0,
        "magic": None,
        "lidar_type": None,
        "version": None,
        "frame_size": None,
        "body_offset": None,
        "frames": None,
        "duration_s": None,
        "consistent": False,
        "notes": [],
    }
    if not path.is_file():
        result["notes"].append("文件不存在（发行包未下载或路径不同）")
        return result

    size = path.stat().st_size
    result["size"] = size
    with path.open("rb") as handle:
        header = handle.read(HEADER_PROBE_BYTES)
    if len(header) < HEADER_PROBE_BYTES:
        result["notes"].append(f"文件过短（{len(header)} B），不足以读取容器头")
        return result

    magic = header[:4]
    result["magic"] = magic.decode("ascii", errors="replace")
    lidar_type = MAGICS.get(magic)
    result["lidar_type"] = lidar_type
    if lidar_type is None:
        result["notes"].append(f"未知魔数 {magic!r}（期望 {sorted(m.decode() for m in MAGICS)}）")
        return result

    result["version"] = struct.unpack_from("<I", header, 4)[0]
    frame_size = struct.unpack_from("<I", header, 12)[0]
    result["frame_size"] = frame_size
    if frame_size <= 0:
        result["notes"].append("frame_size 字段非正数")
        return result

    body_offset = size % frame_size
    frames = (size - body_offset) // frame_size if body_offset <= BODY_OFFSET_LIMIT else 0
    result["body_offset"] = body_offset
    result["frames"] = frames
    result["duration_s"] = round(frames / DOCUMENTED_FREQUENCY_HZ, 3) if frames else None
    result["consistent"] = body_offset <= BODY_OFFSET_LIMIT and frames > 0
    if result["consistent"]:
        result["notes"].append(
            f"分帧自洽：{body_offset} + {frames} × {frame_size} = {body_offset + frames * frame_size}"
        )
    else:
        result["notes"].append(
            f"分帧不自洽：body_offset={body_offset} 超出 [{0}, {BODY_OFFSET_LIMIT}]"
        )
    result["notes"].append("点云载荷未解码（记录混排整型/浮点字段，发行包未公开布局）")
    return result


def probe_corpus(package_dir: Path) -> list[dict[str, object]]:
    records = []
    for name, relative in CORPUS:
        records.append(probe_container(package_dir / "UeSim" / relative / name))
    return records


def _format_table(records: list[dict[str, object]]) -> str:
    lines = [f"{'文件':<40} {'魔数':<6} {'版本':<5} {'帧大小':>12} {'正体偏移':>9} {'帧数':>6} {'时长/s':>7} {'自洽':<4}"]
    for record in records:
        lines.append(
            f"{Path(str(record['path'])).name:<40} "
            f"{str(record['magic']):<6} {str(record['version']):<5} "
            f"{str(record['frame_size']):>12} {str(record['body_offset']):>9} "
            f"{str(record['frames']):>6} {str(record['duration_s']):>7} "
            f"{'是' if record['consistent'] else '否':<4}"
        )
    return "\n".join(lines)


def _selftest() -> int:
    """Build synthetic containers and check the probe round-trips."""
    import tempfile

    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "UeSim" / "Plugins" / "RobotSensorSimulation" / "Data"
        root.mkdir(parents=True)
        for name, _relative in CORPUS:
            source = Path(name)
            target = root / source.name
            magic = b"ARY1" if source.suffix == ".airybin" else b"M3D1"
            frame_size, frames = 1024, 5
            header_size = 352 if source.suffix == ".airybin" else 348
            header = bytearray(header_size)
            header[:4] = magic
            struct.pack_into("<I", header, 4, 1)
            struct.pack_into("<I", header, 8, 20)
            struct.pack_into("<I", header, 12, frame_size)
            target.write_bytes(bytes(header) + bytes(frames * frame_size))
            record = probe_container(target)
            if not record["consistent"]:
                failures.append(f"{source.name}: 合成容器未判定自洽 {record['notes']}")
            if record["frames"] != frames:
                failures.append(f"{source.name}: 帧数应为 {frames}，实得 {record['frames']}")
            if record["body_offset"] != header_size:
                failures.append(f"{source.name}: 正体偏移应为 {header_size}，实得 {record['body_offset']}")
            if record["magic"] != magic.decode():
                failures.append(f"{source.name}: 魔数应为 {magic.decode()}，实得 {record['magic']}")
        missing = probe_container(Path(tmp) / "nope.airybin")
        if missing["exists"] or missing["consistent"]:
            failures.append("不存在的文件应判定 exists=False / consistent=False")

    if failures:
        print("自检失败：")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("自检通过：合成容器可被正确识别与分帧，缺失文件按约定降级。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MATRiX v1.0.13 传感器语料容器探测")
    parser.add_argument("--package-dir", default=str(DEFAULT_PACKAGE_DIR), help="解压后的 MATRiX 发行包根目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--selftest", action="store_true", help="用合成容器自检，不依赖发行包")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    records = probe_corpus(Path(args.package_dir))
    if args.json:
        print(json.dumps({"package_dir": str(args.package_dir), "records": records}, ensure_ascii=False, indent=2))
    else:
        print(_format_table(records))
        for record in records:
            for note in record["notes"]:
                print(f"  · {Path(str(record['path'])).name}: {note}")

    if not any(record["exists"] for record in records):
        print(f"提示：未在 {args.package_dir} 找到语料（发行包为外部下载物，不入 git）。")
        return 2
    return 0 if all(record["consistent"] for record in records) else 1


if __name__ == "__main__":
    sys.exit(main())
