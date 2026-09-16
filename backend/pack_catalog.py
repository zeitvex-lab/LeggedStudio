"""Capability Pack 校验与目录（B1 剩余，2026-09-12）。

B1 的目标是「`capability-pack-1.0` schema + 14 个默认 Pack + 可列出」。2026-09-12
实测发现前两半已在位、后一半缺失：`contracts/schema/capability-pack-1.0.schema.json`
存在，`packs/*.pack.json` 14 份也能解析，但**没有任何入口**能校验它们或列出来——
:func:`backend.plugin_protocol.generate_catalog` 汇总的是**机器人包**（catalog 只有
``packages`` 键），`backend/` 下也没有 packs 路由。本模块补上这两件事：

* :func:`validate_pack` —— 逐份做**语义校验**：schema 必填 / 正则 / 枚举 + 引用可解析 +
  ``sha256`` 对账，对应 schema 里「引用路径一律为相对路径 + sha256，保证 Pack 可跨机复现」；
* :func:`pack_catalog` —— 列出全部 Pack（``pack_id`` / 三个引用 / ``bindings`` / 校验结论），
  并检出重复 ``pack_id``；
* ``GET /api/packs``、``GET /api/packs/validation``、``GET /api/packs/{pack_id}`` 控制面入口。

Pack 是**纯引用组合**（重构方案 §2.1 的 M1 锚点）：``morphology_ref × skill_ref
[× scenario_ref] [× policy_ref]`` + 四阶段质量门 ``bindings``，不拷贝任何资源内容——
因此这里的校验重点是「引用能不能落到真实文件上、哈希对不对、门禁声明是否合法」。

为什么不引 ``jsonschema``：本仓其余契约（``robot-contract-3.0`` / ``skill-recipe-2.0`` /
``scenario-contract-1.1``）都是手写校验，控制面也刻意保持轻依赖（``backend/requirements.txt``
只有 FastAPI / pydantic / numpy 一线）。schema 文件仍是唯一权威，本模块的检查逐条对应其
``required`` / ``pattern`` / ``enum`` / ``additionalProperties``，两侧漂移由
``backend/test_pack_catalog.py`` 的合成用例守住。
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
PACKS_DIR = WORKSPACE_ROOT / "packs"
SCHEMA_PATH = WORKSPACE_ROOT / "contracts" / "schema" / "capability-pack-1.0.schema.json"

SCHEMA_VERSION = "capability-pack-1.0"
CATALOG_SCHEMA_VERSION = "capability-pack-catalog-1.0"
PACK_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")

REF_KEYS = ("morphology_ref", "skill_ref", "scenario_ref", "policy_ref")
REQUIRED_REFS = ("morphology_ref", "skill_ref")
BINDING_KEYS = ("verify", "train", "simulate", "deploy")
PIPELINE_TOPOLOGIES = {
    "direct", "asymmetric_ac", "rma", "latent", "distill_2stage", "distill_3stage",
}
EXECUTORS = {"wasm", "server_mujoco"}
TARGET_PLATFORMS = {"unitree_sdk2", "ros2"}

# 路由：/validation 必须先于 /{pack_id} 声明，否则会被动态段吞掉。
router = APIRouter(prefix="/api/packs", tags=["packs"])


def _content_sha256(data: bytes) -> str:
    """规范化内容哈希：CRLF → LF 后再哈希。

    对原始字节做 sha256 会随 git ``core.autocrlf`` 漂移（Windows 检出 CRLF、
    CI 检出 LF，同一文件两个哈希），Pack 对账就失去跨机复现意义。生成器
    ``tools/generate_packs.py`` 用同一口径，两侧必须同步修改。
    """
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def _sha256_file(path: Path) -> str | None:
    try:
        return _content_sha256(path.read_bytes())
    except OSError:
        return None


def _is_relative_path(value: str) -> bool:
    """schema 约定：包内相对路径，禁止绝对路径与 ``..`` 越界。"""

    if not value or Path(value).is_absolute():
        return False
    return ".." not in Path(value).parts


def _check_skill_ref_resolution(ref: Any, *, required: bool) -> tuple[list[str], dict[str, Any] | None]:
    """``skill_ref.id`` 必须能在**技能注册表**（``registry/skills/index.json``，K4 权威）里解析。

    为什么单独有一条（2026-09-16 发现）：``_check_ref`` 对 **id 型引用**只查"id 非空"，
    于是 14 个内置 Pack 全指向 ``core/velocity@2.0`` —— 一个在仓库里**没有任何实体**的命名
    （没有 SkillSpec 类/文件；真技能是 ``registry/skills/velocity_base.json``）。
    这些 Pack 同时声明 ``bindings.verify.require_refs_resolved: true``，等于一句没人执行的话。

    schema 原话是「skill_ref：SkillSpec **或** SkillRecipe」，所以指到 recipe 完全合规；
    本检查按"**必须解析到登记在册的 recipe**"执行，把引用变成可执行判据 ——
    悬空引用（写了个好听的 id 却指向不存在的东西）从此报错。
    ``require_refs_resolved`` 显式为 false 时降级为告警（契约里那个开关是要起作用的）。
    """

    if not isinstance(ref, dict):
        return [], None
    ref_id = str(ref.get("id") or "")
    if not ref_id:
        return [], None
    try:
        from backend.skill_registry import skill_manifest
    except Exception as exc:  # 注册表模块不可用：如实降级为告警，不假装检查过
        return [], {"id": ref_id, "resolved": False, "reason": f"技能注册表不可用：{type(exc).__name__}: {exc}"}
    entries = {str(item.get("recipe_id")): item for item in (skill_manifest().get("skills") or [])}
    entry = entries.get(ref_id)
    if entry is None:
        message = (
            f"skill_ref.id 解析不到实体：技能注册表里没有 {ref_id!r}"
            f"（登记在册：{sorted(entries)}）—— 引用必须指向登记在册的 recipe（SkillSpec 实体尚未建立）"
        )
        return ([message] if required else []), {"id": ref_id, "resolved": False}
    return [], {"id": ref_id, "resolved": True, "path": str(entry.get("path")), "role": entry.get("role")}


def _check_ref(
    name: str,
    ref: Any,
    *,
    required: bool,
    workspace_root: Path,
) -> tuple[list[str], list[str], dict[str, Any] | None]:
    """校验一个 ``$defs/ref``；返回 (errors, warnings, resolved)。"""

    errors: list[str] = []
    warnings: list[str] = []
    if ref is None:
        if required:
            errors.append(f"{name} 缺失（schema required）")
        return errors, warnings, None
    if not isinstance(ref, dict):
        errors.append(f"{name} 必须是对象或 null，得到 {type(ref).__name__}")
        return errors, warnings, None

    ref_id = ref.get("id")
    if not isinstance(ref_id, str) or not ref_id:
        errors.append(f"{name}.id 必须是非空字符串")
    version = ref.get("version")
    if version is not None and not isinstance(version, str):
        errors.append(f"{name}.version 必须是字符串")

    resolved: dict[str, Any] = {"id": ref_id, "version": version, "path": ref.get("path")}
    rel_path = ref.get("path")
    if rel_path is None:
        warnings.append(f"{name} 未给 path——只能按 id 解析，无法做内容对账")
    elif not isinstance(rel_path, str):
        errors.append(f"{name}.path 必须是字符串")
    elif not _is_relative_path(rel_path):
        errors.append(f"{name}.path 必须是包内相对路径（禁止绝对路径与 .. 越界）：{rel_path!r}")
    else:
        target = workspace_root / rel_path
        resolved["resolved_path"] = str(target)
        if not target.is_file():
            errors.append(f"{name}.path 指向的文件不存在：{rel_path}")
            resolved["exists"] = False
        else:
            resolved["exists"] = True
            actual = _sha256_file(target)
            declared = ref.get("sha256")
            if declared is None:
                warnings.append(f"{name} 未声明 sha256——加载即校验（verify.require_refs_resolved）会降级")
            elif not isinstance(declared, str) or not SHA256_PATTERN.fullmatch(declared):
                errors.append(f"{name}.sha256 必须是 64 位小写十六进制")
            elif actual != declared:
                errors.append(
                    f"{name}.sha256 与实际文件不一致（声明 {declared[:12]}… 实际 "
                    f"{(actual or '')[:12]}…）：{rel_path} 已变更或 Pack 过期"
                )
                resolved["sha256_ok"] = False
            else:
                resolved["sha256_ok"] = True

    declared_hash = ref.get("sha256")
    if declared_hash is not None and not isinstance(declared_hash, str):
        errors.append(f"{name}.sha256 必须是字符串")
    return errors, warnings, resolved


def _check_bindings(
    bindings: Any,
    *,
    workspace_root: Path = WORKSPACE_ROOT,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if bindings is None:
        warnings.append("bindings 缺失——四阶段门禁按 schema 默认值补齐")
        return errors, warnings
    if not isinstance(bindings, dict):
        errors.append("bindings 必须是对象")
        return errors, warnings

    unknown = sorted(set(bindings) - set(BINDING_KEYS))
    if unknown:
        errors.append(f"bindings 含未声明字段 {unknown}（schema additionalProperties: false）")

    def sub(name: str, allowed: set[str]) -> dict | None:
        value = bindings.get(name)
        if value is None:
            return None
        if not isinstance(value, dict):
            errors.append(f"bindings.{name} 必须是对象")
            return None
        extra = sorted(set(value) - allowed)
        if extra:
            errors.append(f"bindings.{name} 含未声明字段 {extra}（schema additionalProperties: false）")
        return value

    verify = sub("verify", {"require_contract_valid", "require_refs_resolved", "require_physics_consistent"})
    if verify is not None:
        for key in ("require_contract_valid", "require_refs_resolved", "require_physics_consistent"):
            if key in verify and not isinstance(verify[key], bool):
                errors.append(f"bindings.verify.{key} 必须是布尔值")

    train = sub("train", {"recipe_ref", "pipeline_topology", "runner_ref", "smoke"})
    if train is not None:
        topology = train.get("pipeline_topology")
        if topology is not None and topology not in PIPELINE_TOPOLOGIES:
            errors.append(
                f"bindings.train.pipeline_topology {topology!r} 不在枚举 "
                f"{sorted(PIPELINE_TOPOLOGIES)}"
            )
        for key in ("recipe_ref", "runner_ref"):
            if key in train:
                ref_errors, ref_warnings, _ = _check_ref(
                    f"bindings.train.{key}", train[key], required=False, workspace_root=workspace_root
                )
                errors.extend(ref_errors)
                warnings.extend(ref_warnings)
        smoke = train.get("smoke")
        if smoke is not None:
            if not isinstance(smoke, dict):
                errors.append("bindings.train.smoke 必须是对象")
            else:
                extra = sorted(set(smoke) - {"num_envs", "max_iterations"})
                if extra:
                    errors.append(f"bindings.train.smoke 含未声明字段 {extra}")
                for key in ("num_envs", "max_iterations"):
                    if key in smoke and (not isinstance(smoke[key], int) or smoke[key] < 1):
                        errors.append(f"bindings.train.smoke.{key} 必须是 ≥1 的整数")

    simulate = sub("simulate", {"executors", "require_deterministic_replay", "require_onnx_metadata_check"})
    if simulate is not None:
        executors = simulate.get("executors")
        if executors is not None:
            if not isinstance(executors, list) or any(e not in EXECUTORS for e in executors):
                errors.append(f"bindings.simulate.executors 只能取 {sorted(EXECUTORS)}")
        for key in ("require_deterministic_replay", "require_onnx_metadata_check"):
            if key in simulate and not isinstance(simulate[key], bool):
                errors.append(f"bindings.simulate.{key} 必须是布尔值")

    deploy = sub("deploy", {"denylist", "require_human_confirm", "target_platform"})
    if deploy is not None:
        denylist = deploy.get("denylist")
        if denylist is not None and (
            not isinstance(denylist, list) or any(not isinstance(d, str) for d in denylist)
        ):
            errors.append("bindings.deploy.denylist 必须是字符串数组")
        platform = deploy.get("target_platform")
        if platform is not None and platform not in TARGET_PLATFORMS:
            errors.append(f"bindings.deploy.target_platform 只能取 {sorted(TARGET_PLATFORMS)}")
        if "require_human_confirm" in deploy and not isinstance(deploy["require_human_confirm"], bool):
            errors.append("bindings.deploy.require_human_confirm 必须是布尔值")

    return errors, warnings


def validate_pack(
    pack: Any,
    *,
    pack_root: Path | None = None,
    workspace_root: Path = WORKSPACE_ROOT,
) -> dict[str, Any]:
    """单份 Pack 的语义校验；``ok`` 为真才算通过（warnings 不阻断）。"""

    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(pack, dict):
        return {"ok": False, "errors": ["Pack 必须是 JSON 对象"], "warnings": [],
                "pack_id": None, "pack_root": str(pack_root) if pack_root else None, "refs": {}}

    if pack.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version 必须是 {SCHEMA_VERSION!r}，得到 {pack.get('schema_version')!r}")

    pack_id = pack.get("pack_id")
    if not isinstance(pack_id, str) or not PACK_ID_PATTERN.fullmatch(pack_id or ""):
        errors.append(f"pack_id 不合法（^[a-z0-9][a-z0-9_-]*$）：{pack_id!r}")

    for key in ("display_name", "description"):
        if key in pack and not isinstance(pack[key], str):
            errors.append(f"{key} 必须是字符串")
    tags = pack.get("tags")
    if tags is not None and (not isinstance(tags, list) or any(not isinstance(t, str) for t in tags)):
        errors.append("tags 必须是字符串数组")

    refs: dict[str, Any] = {}
    for name in REF_KEYS:
        ref_errors, ref_warnings, resolved = _check_ref(
            name, pack.get(name), required=name in REQUIRED_REFS, workspace_root=workspace_root
        )
        errors.extend(ref_errors)
        warnings.extend(ref_warnings)
        if resolved is not None:
            refs[name] = resolved

    # skill_ref 是**唯一的 id 型必需引用**（morphology_ref 自带 path+sha256）⇒ 单独做"可解析"检查。
    bindings_value = pack.get("bindings")
    require_resolved = True
    if isinstance(bindings_value, dict):
        verify_value = bindings_value.get("verify")
        if isinstance(verify_value, dict) and isinstance(verify_value.get("require_refs_resolved"), bool):
            require_resolved = verify_value["require_refs_resolved"]
    skill_errors, skill_resolved = _check_skill_ref_resolution(
        pack.get("skill_ref"), required=require_resolved
    )
    errors.extend(skill_errors)
    if skill_resolved is not None:
        refs.setdefault("skill_ref", {})["recipe"] = skill_resolved
        if not skill_resolved.get("resolved") and not require_resolved:
            warnings.append(
                f"skill_ref.id {skill_resolved.get('id')!r} 解析不到实体，"
                "但 bindings.verify.require_refs_resolved=false ⇒ 仅告警"
            )

    binding_errors, binding_warnings = _check_bindings(pack.get("bindings"))
    errors.extend(binding_errors)
    warnings.extend(binding_warnings)

    unknown = sorted(set(pack) - {"schema_version", "pack_id", "display_name", "description",
                                  "tags", *REF_KEYS, "bindings"})
    if unknown:
        warnings.append(f"顶层未声明字段 {unknown}（schema additionalProperties: true，放行）")

    return {
        "ok": not errors,
        "pack_id": pack_id if isinstance(pack_id, str) else None,
        "pack_root": str(pack_root) if pack_root else None,
        "errors": errors,
        "warnings": warnings,
        "refs": refs,
    }


def load_packs(
    packs_dir: Path = PACKS_DIR,
    *,
    workspace_root: Path = WORKSPACE_ROOT,
) -> list[dict[str, Any]]:
    """读取 ``packs/*.pack.json`` 并逐份校验（按文件名排序，解析失败也登记）。"""

    packs_dir = Path(packs_dir)
    entries: list[dict[str, Any]] = []
    for path in sorted(packs_dir.glob("*.pack.json")):
        try:
            pack = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            entries.append({
                "pack_id": path.name[: -len(".pack.json")],
                "display_name": None, "tags": [], "file": path.name,
                "pack_root": str(path), "valid": False,
                "errors": [f"不可解析：{type(exc).__name__}: {exc}"], "warnings": [],
                "morphology_ref": None, "skill_ref": None, "scenario_ref": None,
                "policy_ref": None, "bindings": None, "refs": {},
            })
            continue
        report = validate_pack(pack, pack_root=path, workspace_root=workspace_root)
        entries.append({
            "pack_id": report["pack_id"] or path.name[: -len(".pack.json")],
            "display_name": pack.get("display_name"),
            "tags": pack.get("tags") or [],
            "file": path.name,
            "pack_root": str(path),
            "valid": report["ok"],
            "errors": report["errors"],
            "warnings": report["warnings"],
            "morphology_ref": pack.get("morphology_ref"),
            "skill_ref": pack.get("skill_ref"),
            "scenario_ref": pack.get("scenario_ref"),
            "policy_ref": pack.get("policy_ref"),
            "bindings": pack.get("bindings"),
            "refs": report["refs"],
        })
    return entries


def pack_catalog(
    packs_dir: Path = PACKS_DIR,
    *,
    workspace_root: Path = WORKSPACE_ROOT,
) -> dict[str, Any]:
    """列出全部 Pack + 汇总；重复 ``pack_id`` 会同时记进每个重名条目的 errors。"""

    entries = load_packs(packs_dir, workspace_root=workspace_root)
    seen: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        seen.setdefault(entry["pack_id"], []).append(entry)
    duplicates = sorted(pid for pid, group in seen.items() if len(group) > 1)
    for pid in duplicates:
        for entry in seen[pid]:
            entry["valid"] = False
            entry["errors"] = [*entry["errors"], f"pack_id 重复：{pid} 出现在 {len(seen[pid])} 份文件中"]

    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "packs_dir": str(packs_dir),
        "count": len(entries),
        "valid_count": sum(1 for e in entries if e["valid"]),
        "invalid_count": sum(1 for e in entries if not e["valid"]),
        "duplicates": duplicates,
        "with_policy_ref": sum(1 for e in entries if e.get("policy_ref")),
        "packs": entries,
    }


def get_pack(
    pack_id: str,
    packs_dir: Path = PACKS_DIR,
    *,
    workspace_root: Path = WORKSPACE_ROOT,
) -> dict[str, Any] | None:
    for entry in load_packs(packs_dir, workspace_root=workspace_root):
        if entry["pack_id"] == pack_id:
            return entry
    return None


@router.get("")
async def list_packs() -> dict[str, Any]:
    """列出全部 Capability Pack（含校验结论、引用与门禁声明）。"""

    return pack_catalog()


@router.get("/validation")
async def validate_all_packs() -> dict[str, Any]:
    """只回校验结论：用于 CI / 前端的「Pack 是否齐备」徽章。"""

    catalog = pack_catalog()
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "count": catalog["count"],
        "valid_count": catalog["valid_count"],
        "invalid_count": catalog["invalid_count"],
        "duplicates": catalog["duplicates"],
        "ok": catalog["invalid_count"] == 0 and not catalog["duplicates"],
        "failures": [
            {"pack_id": e["pack_id"], "file": e["file"], "errors": e["errors"]}
            for e in catalog["packs"] if not e["valid"]
        ],
    }


@router.get("/{pack_id}")
async def get_pack_detail(pack_id: str) -> dict[str, Any]:
    entry = get_pack(pack_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Pack {pack_id} not found")
    return entry
