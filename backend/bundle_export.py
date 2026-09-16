"""B12：导出五类粒度（Morphology / Skill / Scenario / Policy / Bundle）+ 一套 hash 纪律。

## 为什么要有它

愿景的「导入导出分五类粒度」此前只有两种形态、且各自为政：

* **Skill** —— `backend/skill_pack.py`（自包含 JSON，每条 recipe 带 sha256）；
* **Policy** —— `backend/policy_artifacts.py`（出库目录 + `policies/index.json` 的 hash）；
* **整包项目** —— `backend/project_api.py` 的 zip（**manifest 里没有哈希**，无法验证内容）。

缺的三类正是最需要"能搬走"的三类：**Morphology 包**（形态 + 契约）、**Scenario 包**、
以及把它们串起来的 **Bundle**（Pack 引用 + **被引用物的离线副本** + 哈希）。本模块补上它们，
并且把五类收进**同一份 manifest 与同一套校验**：

    <out_dir>/manifest.json      ← schema=capability-export-1.0，逐条 {path, sha256, bytes, role}
    <out_dir>/<payload...>       ← 副本（离线可用的部分）

## 三条判据（写死在这里，调用方只读结论）

1. **导出即自证**：manifest 里每条都带 sha256 与字节数，`verify_export()` 逐条重算 ——
   "搬过去之后内容变了" 必须能被发现；
2. **不许有幽灵文件**：目录里出现 manifest 未登记的 payload 文件即判红（导出物 = manifest 说的那些，
   多一个少一个都算不一致）；
3. **五类各自可独立导出、独立 verify**：`REQUIRED_ROLES` 规定每类**至少要有哪些角色**，
   缺角色即拒（"导出了个空包但退出码 0" 是最坏的一种绿）。

## 与 Pack schema 的关系（不另立第二套形状）

Pack 的 `morphology_ref / skill_ref / scenario_ref / policy_ref` 用的是
`capability-pack-1.0.schema.json` 的 `$defs.ref`（`{id, version?, path?, sha256?}`，
`additionalProperties: false`）。Bundle 的 `refs` **原样沿用这个形状** —— 引用与副本并存时，
`sha256` 同时锁定"引用指向的那份"与"我们副本里的那份"。

风格：纯 stdlib（Scenario 校验复用 `contracts.scenario_contract`，Skill 复用 `backend.skill_pack`）。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
PACKS_DIR = ROOT / "packs"
ROBOTS_DIR = ROOT / "assets" / "robots"

MANIFEST_SCHEMA = "capability-export-1.0"
MANIFEST_NAME = "manifest.json"
EXPORT_KINDS = ("morphology", "skill", "scenario", "policy", "bundle")

#: 每类导出的**必需角色**（verify 据此判"到底导出了这一类没有"）。
REQUIRED_ROLES: dict[str, frozenset[str]] = {
    "morphology": frozenset({"package_manifest", "contract"}),
    "skill": frozenset({"skill"}),
    "scenario": frozenset({"scenario"}),
    "policy": frozenset({"policy"}),
    # Bundle 要能"在干净机器上跑起来"（R1/R2）⇒ 必须带**运行配置** simulation/config.json：
    # 没有它，PackageContract 建不起来，策略条目/执行器接口/初始高度全都无从谈起。
    "bundle": frozenset({"pack", "package_manifest", "contract", "simulation_config"}),
}

#: 拷贝时跳过的目录（与导入侧同口径：VCS 元数据与字节码缓存不属于资产）。
_SKIP_DIRS = frozenset({".git", "__pycache__", ".venv", "node_modules"})


def _workspace_root() -> Path:
    """工作区根（与 `backend.robot_packages._workspace_root` 同一优先级：环境变量 > 仓库 workspace/）。"""

    import os

    configured = os.environ.get("LEGGED_STUDIO_WORKSPACE")
    return Path(configured).expanduser().resolve() if configured else ROOT / "workspace"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe_relative(value: str) -> Path:
    candidate = Path(str(value).replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ValueError(f"非法路径（禁止绝对路径与 .. 越界）：{value}")
    return candidate


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def ref(*, id: str, path: Path | None = None, version: str | None = None) -> dict[str, Any]:
    """构造 Pack schema 的 `$defs.ref` 形状（引用与副本共用同一个形状）。"""

    payload: dict[str, Any] = {"id": id}
    if version:
        payload["version"] = version
    if path is not None and path.is_file():
        payload["path"] = _repo_relative(path)
        payload["sha256"] = _sha256(path)
    return payload


class ExportWriter:
    """把文件拷进导出目录并登记 manifest 条目（**所有类目共用**，避免五套哈希写法）。"""

    def __init__(self, out_dir: Path, kind: str) -> None:
        self.out_dir = Path(out_dir)
        self.kind = kind
        self.entries: list[dict[str, Any]] = []
        self.notes: list[str] = []

    def copy(self, src: Path, relative: str, *, role: str) -> Path:
        if not src.is_file():
            raise FileNotFoundError(f"{role} 源文件不存在：{src}")
        target = self.out_dir / _safe_relative(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        self.entries.append({
            "path": target.relative_to(self.out_dir).as_posix(),
            "sha256": _sha256(target),
            "bytes": target.stat().st_size,
            "role": role,
            "source": _repo_relative(src),
        })
        return target

    def write_json(self, payload: Any, relative: str, *, role: str) -> Path:
        target = self.out_dir / _safe_relative(relative)
        _write_json(target, payload)
        self.entries.append({
            "path": target.relative_to(self.out_dir).as_posix(),
            "sha256": _sha256(target),
            "bytes": target.stat().st_size,
            "role": role,
            "source": None,
        })
        return target

    def finish(
        self,
        *,
        refs: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
        emit: bool = True,
    ) -> dict[str, Any]:
        """收尾：写 ``manifest.json``（``emit=False`` 时只返回 manifest，供**嵌套导出**用）。

        嵌套导出（Bundle 里的 morphology/skill/...）**不写自己的 manifest** ——
        一个导出物只该有一份清单，多出来的嵌套清单既是冗余，也会让"幽灵文件"检查失去意义
        （任何名为 manifest.json 的文件都会被豁免）。嵌套的 notes 由调用方并进外层清单。
        """

        from backend.version import get_version

        manifest: dict[str, Any] = {
            "schema_version": MANIFEST_SCHEMA,
            "kind": self.kind,
            "product_version": get_version(),
            "entries": sorted(self.entries, key=lambda item: item["path"]),
            "refs": refs or {},
            "notes": self.notes,
        }
        if extra:
            manifest.update(extra)
        if emit:
            _write_json(self.out_dir / MANIFEST_NAME, manifest)
        return manifest


# 包根解析的**单一实现**在 `backend/robot_packages.py`（训练安装与导出必须指向同一个包）。
from backend.robot_packages import robot_package_root  # noqa: E402  (模块末尾导入，避免循环依赖)


def _model_files(package_root: Path, manifest: dict[str, Any]) -> list[tuple[Path, str]]:
    """包清单里登记的模型与网格文件（`model.path` 与 `model.assets_path` 两条线索）。"""

    model = manifest.get("model") or {}
    found: list[tuple[Path, str]] = []
    declared = model.get("path")
    if declared:
        candidate = package_root / _safe_relative(declared)
        if candidate.is_file():
            found.append((candidate, candidate.relative_to(package_root).as_posix()))
    assets_path = model.get("assets_path")
    if assets_path:
        directory = package_root / _safe_relative(assets_path)
        if directory.is_dir():
            for file in sorted(directory.rglob("*")):
                if file.is_file() and not (_SKIP_DIRS & set(file.parts)):
                    found.append((file, file.relative_to(package_root).as_posix()))
    return found


def export_morphology(
    robot_id: str, out_dir: Path | str, *, emit_manifest: bool = True, prefix: str = "morphology/",
) -> dict[str, Any]:
    """**Morphology 包**：形态与契约（`robot_package.json` + `contract.json` + `contract_v3.json` + 模型/网格）。

    有意**不含** `training/`（训练源码）与策略权重 —— 那些属别的粒度（Skill / Policy / Bundle），
    把它们塞进形态包会让"形态包"变成一个含糊的大包（也就没法单独校验形态是否可渲染/可加载）。
    """

    package_root = robot_package_root(robot_id)
    if not package_root.is_dir():
        raise FileNotFoundError(f"机器人包不存在：{package_root}")
    writer = ExportWriter(Path(out_dir), "morphology")
    package_manifest = package_root / "robot_package.json"
    writer.copy(package_manifest, f"{prefix}robot_package.json", role="package_manifest")
    manifest_data = _read_json(package_manifest)
    for name, role in (("contract.json", "contract"), ("contract_v3.json", "contract_v3")):
        source = package_root / name
        if source.is_file():
            writer.copy(source, f"{prefix}{name}", role=role)
        else:
            writer.notes.append(f"{name} 不存在（形态可渲染但语义层不完整）")
    for source, relative in _model_files(package_root, manifest_data):
        writer.copy(source, f"{prefix}{relative}", role="model")
    return writer.finish(refs={"morphology": ref(id=robot_id, path=package_root / "contract_v3.json")}, emit=emit_manifest)


def export_skill(recipe_id: str, out_dir: Path | str, *, emit_manifest: bool = True) -> dict[str, Any]:
    """**Skill 包**：复用 `backend/skill_pack.export_pack`（自包含 JSON），导出前先自校验。"""

    from backend import skill_pack

    payload = skill_pack.export_pack(recipe_id)
    check = skill_pack.verify_pack(payload)
    if not check.get("ok", False):
        raise ValueError(f"技能包自校验未通过：{check.get('problems')}")
    writer = ExportWriter(Path(out_dir), "skill")
    writer.write_json(payload, "skill.json", role="skill")
    return writer.finish(
        refs={"skill": {"id": recipe_id, "version": str(payload.get("recipe_version") or "") or None}},
        emit=emit_manifest,
    )


def export_scenario(scenario_path: Path | str, out_dir: Path | str, *, emit_manifest: bool = True) -> dict[str, Any]:
    """**Scenario 包**：场景契约 JSON（导出前用 `ScenarioContract` 校验，fail-closed）。"""

    from contracts.scenario_contract import ScenarioContract

    source = Path(scenario_path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"场景文件不存在：{source}")
    raw = _read_json(source)
    if not isinstance(raw, dict):
        raise ValueError(f"场景文件不是 JSON 对象：{source}")
    contract = ScenarioContract(**raw)  # 校验失败就抛（不导出半成品）
    writer = ExportWriter(Path(out_dir), "scenario")
    writer.write_json(contract.to_payload(), "scenario.json", role="scenario")
    return writer.finish(refs={"scenario": {"id": contract.scenario_id}}, emit=emit_manifest)


def export_policy(
    artifact_id: str, out_dir: Path | str, *, out_dir_index: Path | None = None, emit_manifest: bool = True,
    prefix: str = "", onnx_path: str | None = None,
) -> dict[str, Any]:
    """**Policy 包**：复用 B10 出库产物（`artifact.json` + `deploy.yaml` + `policy.onnx`）。"""

    from backend import policy_artifacts as pa

    index = pa.load_index(out_dir_index) if out_dir_index else pa.load_index()
    entry = index.get(artifact_id)
    if entry is None:
        raise ValueError(f"出库索引里没有这个产物：{artifact_id}")
    artifact_dir = (out_dir_index or pa.OUT_DIR) / artifact_id
    if not artifact_dir.is_dir():
        raise FileNotFoundError(f"产物目录不存在：{artifact_dir}")
    writer = ExportWriter(Path(out_dir), "policy")
    for name, role in (("artifact.json", "policy_meta"), ("deploy.yaml", "policy_meta")):
        source = artifact_dir / name
        if source.is_file():
            writer.copy(source, f"{prefix}{name}", role=role)
        else:
            writer.notes.append(f"{name} 不存在")
    # 产物 onnx 的落点由**统一解析器**给（`policy_blob_path`）：安装进包之后真副本已搬进
    # `assets/robots/<robot>/simulation/policies/`（出库目录里只剩元数据），此时若仍 glob
    # 出库目录就会报"产物目录里没有 onnx"——而它其实好端端在包里。
    from backend.policy_artifacts import policy_blob_path

    blob = policy_blob_path(entry, index=index)
    onnx_files: list[Path] = []
    if blob is not None and Path(blob).is_file() and Path(blob).resolve() != (artifact_dir / Path(blob).name).resolve():
        onnx_files = [Path(blob)]
    if not onnx_files:
        onnx_files = sorted(artifact_dir.glob("*.onnx"))
    if not onnx_files:
        raise FileNotFoundError(f"产物解析不到 onnx（出库目录与包内都没有）：{artifact_dir}")
    for source in onnx_files:
        # onnx 的**落点可以是绝对口径**（Bundle 要让包内配置能解析到它，见 _policy_placement）；
        # 元数据（artifact.json/deploy.yaml）只跟着 prefix 走。两者混用会把文件名当目录前缀拼，
        # 产出 `policy.onnxartifact.json` 这类垃圾名（2026-09-16 实测踩到）。
        writer.copy(source, onnx_path or f"{prefix}{source.name}", role="policy")
    return writer.finish(refs={"policy": ref(id=artifact_id, path=onnx_files[0])}, emit=emit_manifest)


def export_bundle(
    pack_json: Path | str,
    out_dir: Path | str,
    *,
    artifact_id: str | None = None,
    scenario_path: Path | str | None = None,
    run_dir: Path | str | None = None,
    replay: bool = False,
    replay_steps: int = 60,
    out_dir_index: Path | None = None,
) -> dict[str, Any]:
    """**Bundle**：Pack 引用 + **被引用物的离线副本** + 哈希（愿景原文口径）。

    组成：`pack.json`（原样副本）+ Morphology 三件 + Skill JSON +（可选）Scenario / Policy。
    Pack 里声明了 `policy_ref` 却**没有**可用副本时，如实记进 `unresolved`（**不假装完整**）：
    "包里少了被引用物"必须在 manifest 里看得见，而不是等用户在干净机器上打开才发现。
    """

    pack_path = Path(pack_json).expanduser()
    if not pack_path.is_file():
        raise FileNotFoundError(f"Pack 文件不存在：{pack_path}")
    pack = _read_json(pack_path)
    if not isinstance(pack, dict):
        raise ValueError(f"Pack 不是 JSON 对象：{pack_path}")

    writer = ExportWriter(Path(out_dir), "bundle")
    writer.copy(pack_path, "pack.json", role="pack")
    refs: dict[str, Any] = {
        "morphology": pack.get("morphology_ref"),
        "skill": pack.get("skill_ref"),
        "scenario": pack.get("scenario_ref"),
        "policy": pack.get("policy_ref"),
    }
    unresolved: list[dict[str, str]] = []

    morphology_id = str((pack.get("morphology_ref") or {}).get("id") or "")
    package_root: Path | None = None
    if morphology_id:
        # **Bundle = 可直接跑的包布局**：形态/契约/模型落在导出根（不再套 `morphology/` 子目录），
        # 于是 Bundle 根目录本身就是一个可被验收器/产出端消费的机器人包（R1 看、R2 用的前提）。
        package_root = robot_package_root(morphology_id)
        nested = export_morphology(morphology_id, Path(out_dir), emit_manifest=False, prefix="")
        writer.entries.extend(nested["entries"])
        writer.notes.extend(f"morphology: {note}" for note in nested.get("notes") or [])
        simulation_config = package_root / "simulation" / "config.json"
        if simulation_config.is_file():
            writer.copy(simulation_config, "simulation/config.json", role="simulation_config")
        else:
            unresolved.append({"role": "simulation_config", "reason": f"包内缺 simulation/config.json：{package_root}"})
    else:
        unresolved.append({"role": "package_manifest", "reason": "Pack 未声明 morphology_ref"})

    skill_ref = pack.get("skill_ref") or {}
    skill_id = str(skill_ref.get("id") or "")
    if skill_id:
        # 技能解析**只走 K4 注册表**（不猜 id 形态）：`registry/skills/index.json` 是权威清单。
        # 历史上 Pack 指向 `core/velocity@2.0`（无实体的 M1 命名），那时这里除了"如实记成
        # unresolved"没有别的诚实选择 —— 现在 Pack 由生成器解析出真 recipe id（带 path+sha256），
        # 于是 Bundle 能真的把被引用的技能装进去。
        try:
            from backend.skill_registry import skill_manifest

            known = {str(item.get("recipe_id")) for item in (skill_manifest().get("skills") or [])}
            if skill_id not in known:
                raise ValueError(f"技能注册表里没有 {skill_id!r}（登记在册：{sorted(known)}）")
            nested = export_skill(skill_id, Path(out_dir) / "skill", emit_manifest=False)
            writer.entries.append({**nested["entries"][0], "path": f"skill/{nested['entries'][0]['path']}"})
            writer.notes.extend(f"skill: {note}" for note in nested.get("notes") or [])
        except Exception as exc:
            unresolved.append({"role": "skill", "reason": f"{skill_id}: {type(exc).__name__}: {exc}"})
    else:
        unresolved.append({"role": "skill", "reason": "Pack 未声明 skill_ref"})

    scenario_target = scenario_path or (pack.get("scenario_ref") or {}).get("path")
    if scenario_target:
        try:
            nested = export_scenario(
                ROOT / str(scenario_target) if not Path(str(scenario_target)).is_absolute() else scenario_target,
                Path(out_dir) / "scenario", emit_manifest=False,
            )
            writer.entries.append({**nested["entries"][0], "path": f"scenario/{nested['entries'][0]['path']}"})
        except Exception as exc:
            unresolved.append({"role": "scenario", "reason": f"{scenario_target}: {type(exc).__name__}: {exc}"})
    else:
        writer.notes.append("Pack 未声明 scenario_ref，Bundle 不含场景")

    policy_ref = pack.get("policy_ref") or {}
    policy_id = artifact_id or str(policy_ref.get("id") or "")
    if policy_id:
        try:
            metadata_prefix, onnx_path, bound_entry = _policy_placement(
                package_root, policy_id, out_dir_index=out_dir_index,
            )
            nested = export_policy(
                policy_id, Path(out_dir), emit_manifest=False, prefix=metadata_prefix, onnx_path=onnx_path,
                out_dir_index=out_dir_index,
            )
            writer.entries.extend(nested["entries"])
            writer.notes.extend(f"policy: {note}" for note in nested.get("notes") or [])
            refs["policy"] = {
                **(refs.get("policy") or {}),
                "artifact_id": policy_id,
                "onnx_in_bundle": onnx_path,
                "bound_entry": bound_entry,
            }
            if bound_entry is None:
                writer.notes.append(
                    f"产物 {policy_id} 未绑定任何包内策略条目（artifact.json 无 policy_id）⇒ "
                    f"onnx 放在 {onnx_path}，需在包内配置里显式引用后才可被 --policy-id 解析"
                )
        except Exception as exc:
            unresolved.append({"role": "policy", "reason": f"{policy_id}: {type(exc).__name__}: {exc}"})
    else:
        writer.notes.append("Pack 未声明 policy_ref 且未指定 --artifact：Bundle 不含策略权重（形态/技能仍可复现）")

    if run_dir is not None or replay:
        # R1/R2/R3 一起出：R3 用**当时那套 venv**重算环境并逐项对账；
        # R2 只有 `--replay` 时才真跑（要适配器 venv + 几秒），否则如实记 not_run（未跑 ≠ 通过）。
        from backend import reproduce as rp

        replay_inputs = None
        if replay:
            onnx_in_bundle = (refs.get("policy") or {}).get("onnx_in_bundle")
            if onnx_in_bundle:
                # **在被导出的这份 Bundle 自身内跑**（package = 导出目录）：这才是
                # "Bundle 在干净机器可 R2" 的证据，而不是拿仓库里的包凑出来的一次运行。
                replay_inputs = {
                    "package_dir": Path(out_dir),
                    "policy": onnx_in_bundle,
                    "steps": replay_steps,
                }
            else:
                unresolved.append({"role": "replay", "reason": "Bundle 里没有策略（未给 --artifact 且 Pack 无 policy_ref），R2 无法跑"})
        report = rp.build_reproduction(run_dir=run_dir, bundle_dir=out_dir, replay=replay_inputs)
        writer.write_json(report, rp.REPRODUCE_NAME, role="reproduce")
        summary = rp.summarise(report)
        writer.notes.append(
            f"复现报告已附（{rp.REPRODUCE_NAME}）：R1回放={summary['R1_playback']} / "
            f"R2评测={summary['R2_evaluation']} / R3训练={summary['R3_training']}"
        )

    return writer.finish(refs=refs, extra={"unresolved": unresolved})


def _policy_placement(
    package_root: Path | None, artifact_id: str, *, out_dir_index: Path | None = None,
) -> tuple[str, str, str | None]:
    """产物在 Bundle 里该放哪：**优先放到包内配置声明的位置**（这样 `--policy-id` 能解析到它）。

    两种情形（2026-09-16 实测）：

    * 产物 `source_onnx` 已在某个包内（提升/B10 回挂之后）⇒ 放回同一相对路径，
      于是 Bundle 的 `simulation/config.json` + `--policy-id <id>` **在 Bundle 自身内**就能解析；
    * produced 产物（`<robot>__produced-<run_id>`，`artifact.json` 里**没有** `policy_id`）⇒
      它并未绑定到任何包内策略条目（实测：产物 onnx 的哈希与包内 4 条 onnx 全不匹配）——
      此时放到 `simulation/policies/<文件名>`，并如实记 `bound_entry=null`：
      **"训练产物回挂 Pack/策略条目"这一环至今没闭环**，不能假装它已经绑上了。

    ``package_root`` 为 None（Pack 没声明形态）时只按文件名放。
    """

    from backend import policy_artifacts as pa

    # 出库目录**必须可指定**：单元测试与"导出别人机器上的索引"都要能指到别处；
    # 写死默认目录会让"装进包但在另一个 out_dir"的产物解析不到（回挂的落点就退回兜底文件名）。
    entry = (pa.load_index(out_dir_index) if out_dir_index else pa.load_index()).get(artifact_id) or {}
    source = str(entry.get("source_onnx") or "")
    name = Path(source).name if source else "policy.onnx"
    if source and package_root is not None:
        resolved = Path(source)
        resolved = resolved if resolved.is_absolute() else ROOT / resolved
        try:
            # 产物已在包内（提升/B10 回挂之后）：落回同一相对路径 ⇒ Bundle 的 config 能解析到它，
            # `--policy-id` 在 Bundle 自身内即可用。
            return "policy/", resolved.resolve().relative_to(package_root.resolve()).as_posix(), str(entry.get("policy_id") or "") or None
        except ValueError:
            pass
    # produced 产物（未绑定任何包内策略条目）⇒ 放 simulation/policies/<文件名>，bound_entry=null
    return "policy/", f"simulation/policies/{name}", None


def verify_export(out_dir: Path | str) -> dict[str, Any]:
    """校验一个导出目录：manifest schema + 必需角色 + 逐条 sha256 + 幽灵文件。

    判据全部来自**磁盘与 manifest 的对比**（不读导出时的内存状态），所以它对"从别处拷来的
    导出物"同样有效 —— 这正是 Bundle 要在干净机器上被信任的前提。
    """

    root = Path(out_dir).expanduser()
    problems: list[str] = []
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        return {"ok": False, "kind": None, "entries": 0, "problems": [f"缺 {MANIFEST_NAME}（不是导出物）：{root}"]}
    try:
        manifest = _read_json(manifest_path)
    except Exception as exc:
        return {"ok": False, "kind": None, "entries": 0, "problems": [f"{MANIFEST_NAME} 不可解析：{exc}"]}
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        problems.append(f"schema_version 应为 {MANIFEST_SCHEMA!r}，得到 {manifest.get('schema_version')!r}")
    kind = str(manifest.get("kind") or "")
    if kind not in EXPORT_KINDS:
        problems.append(f"未知 kind：{kind!r}")
        return {"ok": False, "kind": kind, "entries": 0, "problems": problems}

    entries = manifest.get("entries") or []
    registered: set[str] = set()
    for entry in entries:
        relative = str(entry.get("path") or "")
        try:
            target = root / _safe_relative(relative)
        except ValueError as exc:
            problems.append(f"{relative}: {exc}")
            continue
        registered.add(relative)
        if not target.is_file():
            problems.append(f"缺文件 {relative}（manifest 登记了但磁盘上没有）")
            continue
        actual = _sha256(target)
        if actual != entry.get("sha256"):
            problems.append(f"{relative}: sha256 与 manifest 不符（内容被改过）")
        if entry.get("bytes") is not None and target.stat().st_size != entry["bytes"]:
            problems.append(f"{relative}: 字节数与 manifest 不符")
        if not entry.get("role"):
            problems.append(f"{relative}: 缺 role")

    roles = {str(entry.get("role")) for entry in entries}
    for role in sorted(REQUIRED_ROLES[kind] - roles):
        problems.append(f"缺必需角色 {role}（这类导出至少要有 {sorted(REQUIRED_ROLES[kind])}）")

    ghost = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and path != manifest_path
        and not (_SKIP_DIRS & set(path.parts))
        and path.relative_to(root).as_posix() not in registered
    )
    if ghost:
        problems.append(f"存在 manifest 未登记的文件（幽灵文件）：{', '.join(ghost[:5])}")

    reproduction = None
    reproduce_payload = _read_json(root / "reproduce.json") if (root / "reproduce.json").exists() else None
    if isinstance(reproduce_payload, dict):
        # 完整性 ≠ 可复现性：导出物自洽（ok）与"三档复现到什么程度"是两件事，分开报。
        from backend import reproduce as rp

        reproduction = rp.summarise(reproduce_payload)

    return {
        "ok": not problems,
        "kind": kind,
        "entries": len(entries),
        "roles": sorted(roles),
        "refs": manifest.get("refs") or {},
        "unresolved": manifest.get("unresolved") or [],
        "reproduction": reproduction,
        "problems": problems,
    }


def default_out_dir(kind: str, name: str) -> Path:
    """默认导出落点：``<workspace>/exports/<kind>-<name>``。"""

    return _workspace_root() / "exports" / f"{kind}-{name}"


def list_exports() -> list[dict[str, Any]]:
    """列出工作区里已有的导出物（供 CLI/页面展示）。"""

    root = _workspace_root() / "exports"
    if not root.is_dir():
        return []
    found: list[dict[str, Any]] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        report = verify_export(child)
        found.append({
            "name": child.name,
            "path": str(child),
            "kind": report.get("kind"),
            "entries": report.get("entries"),
            "ok": report.get("ok"),
            "unresolved": len(report.get("unresolved") or []),
        })
    return found


def iter_pack_files() -> Iterable[Path]:
    return sorted(PACKS_DIR.glob("*.pack.json")) if PACKS_DIR.is_dir() else []
