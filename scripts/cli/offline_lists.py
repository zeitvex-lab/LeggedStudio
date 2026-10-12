"""CLI 离线清单命令（pack / run / artifact）（自 scripts/legged_studio_cli.py 拆分，2026-10-12；函数体零改动）。

不连控制面，直接读仓库数据（backend/ 同一实现，单一真值来源）。
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.cli.workspace import _run_status, _workspace_root



def _cmd_pack_list(as_json: bool) -> int:
    """``pack list``：列出 packs/ 下全部 Pack 及校验状态（离线命令，无需后端）。

    校验清单与 ``tools/validate_packs.py``、``GET /api/packs`` 同源——都走
    :func:`backend.pack_catalog.pack_catalog`，不抄第二份逻辑。
    """

    from backend.pack_catalog import pack_catalog

    catalog = pack_catalog()
    if as_json:
        payload = {
            "packs_dir": catalog["packs_dir"],
            "count": catalog["count"],
            "valid_count": catalog["valid_count"],
            "invalid_count": catalog["invalid_count"],
            "duplicates": catalog["duplicates"],
            "packs": [
                {
                    "pack_id": entry["pack_id"],
                    "valid": entry["valid"],
                    "file": entry["file"],
                    "errors": entry["errors"],
                    "warnings": entry["warnings"],
                }
                for entry in catalog["packs"]
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"Pack 校验清单（离线命令，无需后端）：{catalog['packs_dir']}")
    print(f"{'pack_id':<26}{'校验':<6}{'错误':>4}{'警告':>4}  文件")
    for entry in catalog["packs"]:
        mark = "通过" if entry["valid"] else "失败"
        print(
            f"{entry['pack_id']:<26}{mark:<6}"
            f"{len(entry['errors']):>4}{len(entry['warnings']):>4}  {entry['file']}"
        )
        for error in entry["errors"]:
            print(f"    - {error}")
    print(f"汇总：{catalog['count']} 个 Pack，{catalog['valid_count']} 通过，{catalog['invalid_count']} 失败")
    return 0


def _cmd_run_list(as_json: bool, workspace: str | None) -> int:
    """``run list``：列出 workspace/ 下含 run.json 的训练任务（离线命令，无需后端）。

    记录一律经 :func:`backend.training.runs.load_run` 读回（与后端同一实现）；
    不含 run.json 的旧目录**如实跳过**并在末尾汇总，不算作 Run。
    """

    from backend.training import runs

    root = _workspace_root(workspace)
    entries: list[dict] = []
    skipped: list[str] = []
    if root.is_dir():
        for child in sorted(path for path in root.iterdir() if path.is_dir()):
            if not (child / "run.json").is_file():
                skipped.append(child.name)
                continue
            try:
                record = runs.load_run(child)
            except (TypeError, ValueError, KeyError):
                record = None  # run.json 结构漂移：按“读不出来”如实处理，不崩
            if record is None:
                skipped.append(child.name)
                continue
            entries.append({
                "run_id": record.run_id,
                "robot_id": record.robot_id,
                "seed": record.seed,
                "status": _run_status(child, record.status),
                "created_at": record.created_at,
            })

    if as_json:
        payload = {"workspace": str(root), "count": len(entries), "runs": entries, "skipped": skipped}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"训练 Run 清单（离线命令，无需后端）：{root}")
    if not entries:
        print("（没有含 run.json 的任务目录）")
    print(f"{'run_id':<44}{'robot_id':<16}{'seed':>5}  {'状态':<16}创建时间")
    for entry in entries:
        print(
            f"{entry['run_id']:<44}{entry['robot_id']:<16}{entry['seed']:>5}"
            f"  {entry['status']:<16}{entry['created_at']}"
        )
    print(f"汇总：{len(entries)} 个 Run")
    if skipped:
        print(f"跳过 {len(skipped)} 个无 run.json 的目录：{', '.join(skipped)}")
    return 0


def _cmd_artifact_list(as_json: bool, out_dir: str | None) -> int:
    """``artifact list``：列出 policies/ 出库索引全部产物（离线命令，无需后端）。

    索引读回一律走 :func:`backend.policy_artifacts.load_index`（与后端同一实现）；
    ``produced`` 条目（产品自产策略）特别标注。
    """

    from backend.policy_artifacts import OUT_DIR, load_index

    root = Path(out_dir).expanduser() if out_dir else OUT_DIR
    index = load_index(root)
    artifacts = [
        {
            "artifact_id": artifact_id,
            "kind": entry.get("kind"),
            "produced": entry.get("kind") == "produced",
            "onnx_sha256_prefix": (entry.get("onnx_sha256") or "")[:12] or None,
            "onnx_bytes": entry.get("onnx_bytes"),
        }
        for artifact_id, entry in sorted(index.items())
    ]
    produced_count = sum(1 for item in artifacts if item["produced"])

    if as_json:
        payload = {
            "out_dir": str(root),
            "count": len(artifacts),
            "produced_count": produced_count,
            "artifacts": artifacts,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"策略产物清单（离线命令，无需后端）：{root}")
    if not artifacts:
        print("（出库索引为空：先跑 backend.policy_artifacts.build_all(write=True)）")
    print(f"{'artifact_id':<44}{'kind':<12}{'onnx_sha256':<14}{'bytes':>10}")
    for item in artifacts:
        kind = "produced *" if item["produced"] else str(item["kind"] or "-")
        prefix = item["onnx_sha256_prefix"] or "-"
        size = "-" if item["onnx_bytes"] is None else str(item["onnx_bytes"])
        print(f"{item['artifact_id']:<44}{kind:<12}{prefix:<14}{size:>10}")
    print(f"汇总：{len(artifacts)} 个产物（其中产品自产 produced {produced_count} 个，标 * 号）")
    return 0
