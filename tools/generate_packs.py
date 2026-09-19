#!/usr/bin/env python3
"""为每个内置机器人包生成默认 Capability Pack（重构方案 M1）。

Pack 是**纯引用组合**：`morphology_ref × skill_ref [× scenario_ref] [× policy_ref]`
+ 四阶段质量门 `bindings`。本脚本只读不写资源本身，产出为 `packs/<robot_id>.pack.json`：

  morphology_ref → 该包 contract.json（包内相对路径 + sha256）
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
from contracts.jsonio import load_json  # JSON 读取唯一实现
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
    """规范化内容哈希：委托 ``contracts.validator.normalized_sha256``（**唯一实现**）。

    生成器与 ``backend/pack_catalog`` 此前各写一份、靠注释"两侧必须同步修改"维系；
    现在两侧都引用同一函数——口径是代码事实，改一处即全链生效。
    """

    from contracts.validator import normalized_sha256

    return normalized_sha256(path.read_bytes())


def _load_json(path: Path) -> dict:
    """严格读（异常原样抛）—— 实现见 ``contracts/jsonio``。"""

    return load_json(path)


def _morphology_id(contract_truth: dict) -> str | None:
    morphology = contract_truth.get("morphology")
    return str(morphology.get("id")) if isinstance(morphology, dict) and morphology.get("id") else None


#: 本次生成中**被丢弃**的 ``policy_ref``（路径指向 gitignored 目录）。``main()`` 统一打印——
#: "回挂被丢弃"必须在输出里可见，否则就成了静默丢数据。
DROPPED_POLICY_REFS: list[str] = []


def sanitize_policy_ref(ref: dict | None) -> dict | None:
    """回挂继承的卫生检查：**路径指向 gitignored 目录就丢弃**。

    为什么丢弃而不是原样继承（2026-09-19 收口）：``packs/*.pack.json`` 是随仓库分发的东西，
    而 ``workspace/**`` 在 ``.gitignore`` 里——继承它等于把"只有本机才有的路径"永久写进
    一份会被别人 clone 的文件（实测 go2 / lite3 两份 Pack 就是这么红的：本机 14/14、
    干净 clone 与 CI 12/14）。

    丢弃是**如实**的：策略 blob 不在仓库里，Pack 就不该声称自己带策略；产物与出处仍完整
    记在 ``policies/index.json``（产物登记的家在索引，不在 Pack）。等价判据在
    ``backend/pack_catalog._check_ref``（校验侧）与 ``policy_artifacts._policy_ref_path``
    （写入侧），三处同一口径。
    """

    if not isinstance(ref, dict) or not ref.get("id"):
        return None
    rel = str(ref.get("path") or "")
    from backend.pack_catalog import gitignored_ref_prefix

    blocker = gitignored_ref_prefix(rel) if rel else None
    if blocker:
        DROPPED_POLICY_REFS.append(f"{ref['id']} → {rel}（{blocker}** 在 .gitignore 里）")
        return None
    return dict(ref)


def existing_policy_ref(package_dir: Path, out_dir: Path) -> dict | None:
    """读出已生成 Pack 里的 `policy_ref`（若有）——**回挂不能被子生成器冲掉**。

    训练产物经 `attach_policy_to_pack()` 回挂后，Pack 的 `policy_ref` 指向产物的 onnx。
    生成器若一律写 `null`，下一次重生成就把这条回挂静默抹掉（"生成物"覆盖"产品数据"）——
    所以这里显式继承，并在 `--dry-run` 下同样生效（否则演练与实跑不一致）。
    继承前过一道 :func:`sanitize_policy_ref`（去掉指向 gitignored 目录的路径）。
    """

    path = out_dir / f"{package_dir.name}.pack.json"
    if not path.is_file():
        return None
    payload = _load_json(path)
    ref = payload.get("policy_ref") if isinstance(payload, dict) else None
    return sanitize_policy_ref(ref)



_LICENSE_INDEX: dict | None = None


def _project_license_for(robot: str) -> dict:
    """取该机型的许可投影（registry/licenses.json 是证据层，这里只做投影）。"""

    global _LICENSE_INDEX
    if _LICENSE_INDEX is None:
        from tools.audit_licenses import derive

        _LICENSE_INDEX = derive()
    from tools.audit_licenses import project_license

    return project_license(robot, _LICENSE_INDEX.get(robot))


def build_pack(package_dir: Path, *, policy_ref: dict | None = None) -> dict | None:
    """从单个机器人包构建默认 Pack；缺 contract.json 则跳过（返回 None）。"""

    contract_path = package_dir / "contract.json"
    if not contract_path.exists():
        return None

    contract_truth = _load_json(contract_path)
    robot_id = str(contract_truth.get("robot_id") or package_dir.name)
    skill_ref = default_skill_ref()

    return {
        "schema_version": "capability-pack-1.0",
        # I5：license 块**从取证层投影**（不在这里手写常量 —— 手写必然与 registry 漂移）
        "license": _project_license_for(package_dir.name),
        "pack_id": f"{robot_id}-velocity",
        "display_name": f"{contract_truth.get('family') or robot_id} · velocity",
        "description": f"默认 Pack（tools/generate_packs.py 生成）：引用该机型契约真值 与技能 {skill_ref['id']}。",
        "tags": ["generated", "default", _morphology_id(contract_truth) or "unknown_morphology"],
        "morphology_ref": {
            "id": robot_id,
            "path": f"assets/robots/{package_dir.name}/contract.json",
            "sha256": _sha256(contract_path),
        },
        "skill_ref": skill_ref,
        "scenario_ref": None,
        # 回挂过的 policy_ref 原样继承（见 existing_policy_ref 的说明）
        "policy_ref": dict(policy_ref) if policy_ref else None,
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
    DROPPED_POLICY_REFS.clear()
    for package_dir in sorted(p for p in robots_dir.iterdir() if p.is_dir()):
        pack = build_pack(package_dir, policy_ref=existing_policy_ref(package_dir, out_dir))
        if pack is None:
            skipped.append(package_dir.name)
            continue
        if not args.dry_run:
            (out_dir / f"{package_dir.name}.pack.json").write_text(
                json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        written.append(pack["pack_id"])

    print(f"packs 生成：{len(written)}" + (f"（{len(skipped)} 个包缺 contract.json，已跳过：{', '.join(skipped)}）" if skipped else ""))
    if not args.dry_run:
        print(f"输出目录：{out_dir}")
    for pack_id in written:
        print(f"  - {pack_id}")
    if DROPPED_POLICY_REFS:
        print(f"丢弃 {len(DROPPED_POLICY_REFS)} 条指向 gitignored 目录的 policy_ref（随仓分发的 Pack 不能引用机器本地状态）：")
        for item in DROPPED_POLICY_REFS:
            print(f"  ! {item}")
        print("  → 策略产物与出处仍在 policies/index.json；要进 Pack，先把产物安装进仓库内的机器人包。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
