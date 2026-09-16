#!/usr/bin/env python3
"""为每个内置机器人包生成默认 Capability Pack（重构方案 M1）。

Pack 是**纯引用组合**：`morphology_ref × skill_ref [× scenario_ref] [× policy_ref]`
+ 四阶段质量门 `bindings`。本脚本只读不写资源本身，产出为 `packs/<robot_id>.pack.json`：

  morphology_ref → 该包 contract_v3.json（包内相对路径 + sha256）
  skill_ref      → 默认 core/velocity@2.0（M1 阶段的唯一 Spec）
  bindings       → verify/train/simulate/deploy 的默认门禁（冒烟 64×5、确定性回放、DENYLIST）

用法：
    python tools/generate_packs.py                 # 写入 packs/
    python tools/generate_packs.py --out packs --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from contracts.path_bootstrap import ensure_project_root_on_path

ROOT = ensure_project_root_on_path() and Path(__file__).resolve().parents[1]

def default_skill_ref() -> dict:
    """Pack 的默认技能引用：**从 K4 技能注册表解析**（基座 recipe），带路径 + 内容哈希。

    此前这里写死 ``{"id": "core/velocity@2.0", "version": "2.0"}`` —— 那个命名在仓库里
    **没有任何实体**（没有 SkillSpec 类、没有 SkillSpec 文件；真技能是
    ``registry/skills/velocity_base.json``，其 recipe_id 为 ``velocity_base``）。后果是 14 个
    内置 Pack 的 ``skill_ref`` **谁也解析不到**，而它们又都声明
    ``bindings.verify.require_refs_resolved: true`` —— 一句没人执行的话（id 型引用此前
    只查"非空"，见 ``backend/pack_catalog._check_ref``）。

    2026-09-16 改为解析式：schema 原话是「skill_ref：SkillSpec **或** SkillRecipe」，
    所以指到真 recipe 完全合规；同时带上 ``path`` + ``sha256``，让"引用"也能**逐字节对账**
    （与 ``morphology_ref`` 同纪律）。
    """

    from backend.skill_registry import SKILLS_DIR, skill_manifest

    entries = skill_manifest().get("skills") or []
    base = next((item for item in entries if item.get("role") == "base"), None)
    if base is None:
        raise SystemExit("技能注册表里没有 role=base 的 recipe，无法生成 Pack 的 skill_ref")
    recipe_path = SKILLS_DIR / str(base["path"])
    if not recipe_path.is_file():
        raise SystemExit(f"技能清单登记的 recipe 文件不存在：{recipe_path}")
    return {
        "id": str(base["recipe_id"]),
        "path": recipe_path.relative_to(ROOT).as_posix(),
        "sha256": _sha256(recipe_path),
    }


DEFAULT_BINDINGS = {
    "verify": {
        "require_contract_valid": True,
        "require_refs_resolved": True,
        "require_physics_consistent": False,
    },
    "train": {
        "pipeline_topology": "asymmetric_ac",
        "smoke": {"num_envs": 64, "max_iterations": 5},
    },
    "simulate": {
        "executors": ["wasm", "server_mujoco"],
        "require_deterministic_replay": True,
        "require_onnx_metadata_check": True,
    },
    "deploy": {
        "denylist": [
            "observation_groups",
            "action_scale",
            "joint_order",
            "control_hz",
            "armature",
        ],
        "require_human_confirm": True,
    },
}


def _sha256(path: Path) -> str:
    # 规范化内容哈希（CRLF → LF），与 backend/pack_catalog._content_sha256 同口径；
    # 对原始字节哈希会随 git core.autocrlf 漂移，跨机对账失效。两侧须同步修改。
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _morphology_id(contract_v3: dict) -> str | None:
    morphology = contract_v3.get("morphology")
    return str(morphology.get("id")) if isinstance(morphology, dict) and morphology.get("id") else None


def build_pack(package_dir: Path) -> dict | None:
    """从单个机器人包构建默认 Pack；缺 contract_v3.json 则跳过（返回 None）。"""

    contract_path = package_dir / "contract_v3.json"
    if not contract_path.exists():
        return None

    contract_v3 = _load_json(contract_path)
    robot_id = str(contract_v3.get("robot_id") or package_dir.name)
    skill_ref = default_skill_ref()

    return {
        "schema_version": "capability-pack-1.0",
        "pack_id": f"{robot_id}-velocity",
        "display_name": f"{contract_v3.get('family') or robot_id} · velocity",
        "description": f"默认 Pack（tools/generate_packs.py 生成）：引用该机型契约 v3 与技能 {skill_ref['id']}。",
        "tags": ["generated", "default", _morphology_id(contract_v3) or "unknown_morphology"],
        "morphology_ref": {
            "id": robot_id,
            "path": f"assets/robots/{package_dir.name}/contract_v3.json",
            "sha256": _sha256(contract_path),
        },
        "skill_ref": skill_ref,
        "scenario_ref": None,
        "policy_ref": None,
        "bindings": json.loads(json.dumps(DEFAULT_BINDINGS)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成默认 Capability Pack")
    parser.add_argument("--robots", default=str(ROOT / "assets" / "robots"), help="机器人包目录")
    parser.add_argument("--out", default=str(ROOT / "packs"), help="Pack 输出目录")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写盘")
    args = parser.parse_args(argv)

    robots_dir = Path(args.robots)
    if not robots_dir.exists():
        raise SystemExit(f"机器人包目录不存在：{robots_dir}")

    out_dir = Path(args.out)
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    skipped: list[str] = []
    for package_dir in sorted(p for p in robots_dir.iterdir() if p.is_dir()):
        pack = build_pack(package_dir)
        if pack is None:
            skipped.append(package_dir.name)
            continue
        if not args.dry_run:
            (out_dir / f"{package_dir.name}.pack.json").write_text(
                json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        written.append(pack["pack_id"])

    print(f"packs 生成：{len(written)}" + (f"（{len(skipped)} 个包缺 contract_v3.json，已跳过：{', '.join(skipped)}）" if skipped else ""))
    if not args.dry_run:
        print(f"输出目录：{out_dir}")
    for pack_id in written:
        print(f"  - {pack_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
