"""B10 产物出库（**引用式**）：``policies/<artifact-id>/{deploy.yaml, artifact.json}`` + ``policies/index.json``。

**真值来源**：各机器人包 ``simulation/config.json`` 的 ``policies`` + ``demo_policies`` 声明段
（消费者：`backend/simulation_api.py` / `health_api.py` / `perception_binding.py` / `pretrained_api.py`；
全局索引另见 ``pretrained_models/index.json``）。

**为什么是"引用 + hash"而不是把 onnx 复制一份**（对 B10 原文的一处有意收窄）：

B10 原文写 ``policies/<artifact-id>/{policy.onnx, deploy.yaml}``。但 47 份 onnx 约 50 MB，
再复制一份就与 **B5（mesh 单副本）** 和瘦身目标正面冲突 —— 同一份二进制两处存在，必然漂移。
因此出库的语义按 B10 自己的后半句"**契约只留引用 + hash**"落实：

* ``artifact.json`` —— 源 onnx 的**仓库相对路径 + sha256 + 字节数**，外加契约块哈希与血缘；
* ``deploy.yaml`` —— 从 ``contract`` 段展开的**部署参数**（关节序、action_scale、默认角、scales…）；
* onnx 本体**仍单副本留在包内**，由 sha256 锁定 —— 谁改了就立刻对不上。

**产品自产**的策略（B9 的 Run 产出）出库时才真写 ``policy.onnx``（那时它是唯一副本，不违反单副本）。
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from backend.training.runs import canonical_digest, file_digest

ROOT = Path(__file__).resolve().parents[1]

#: 机器人包根（每个包内含 ``simulation/config.json``）。
ROBOTS_DIR = ROOT / "assets" / "robots"

#: 出库根（与 B10 约定一致）。
OUT_DIR = ROOT / "policies"

INDEX_NAME = "index.json"
ARTIFACT_NAME = "artifact.json"
DEPLOY_NAME = "deploy.yaml"
POLICY_BLOB_NAME = "policy.onnx"

ARTIFACT_SCHEMA = "policy-artifact-1.0"

#: 浏览器包 URL 前缀（``/api/simulation/browser-package/<robot>/``）——声明里可能是 URL 形式。
_URL_PREFIX = re.compile(r"^/api/simulation/browser-package/[^/]+/")

#: ``deploy.yaml`` 从 ``contract`` 段展开的字段（顺序即书写顺序）。
_DEPLOY_FIELDS = (
    "observation_kind", "obs_dim", "action_dim", "history_len",
    "command_dims", "default_command", "action_joint_order",
    "default_joint_angles", "action_scale", "scales",
)


# --------------------------------------------------------------------------------------
# 声明扫描
# --------------------------------------------------------------------------------------
def _repo_relative(path: Path) -> str:
    """仓库相对路径（posix）。不在仓库内时退回绝对路径 —— 不抛异常（外部/临时目录也会走到这里）。"""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def resolve_declared_onnx(robot_dir: Path, *declared: str) -> Path | None:
    """把声明的 ``path`` / ``url`` 解析成真实文件；**三种既有形式都支持**：

    1. 包内相对路径 —— ``simulation/policies/x.onnx``（主流形式）；
    2. 浏览器包 URL —— ``/api/simulation/browser-package/<robot>/simulation/policies/x.onnx``；
    3. web 静态目录 —— ``/web/sim2sim/models/x.onnx``（实存于 ``web/sim2sim/models/``）。

    逐个候选实测存在性；都解析不出来返回 ``None`` —— 调用方据此报"缺件"，
    而不是瞎猜一个路径（V1 可追溯）。
    """
    for raw in declared:
        text = str(raw or "").strip()
        if not text.lower().endswith(".onnx"):
            continue
        relative = _URL_PREFIX.sub("", text).lstrip("/")
        for candidate in (robot_dir / relative, ROOT / relative):
            if candidate.is_file():
                return candidate
    return None


def scan_declarations(robots_dir: Path | str = ROBOTS_DIR) -> list[dict[str, Any]]:
    """扫描全部机器人包的策略声明，返回**声明清单**（不做任何落盘）。

    每个包的两段都收：``policies``（常规）与 ``demo_policies``（首页 demo 卡素材）。
    """
    root = Path(robots_dir)
    declarations: list[dict[str, Any]] = []
    for config_path in sorted(root.glob("*/simulation/config.json")):
        config = _load_json(config_path)
        if not isinstance(config, Mapping):
            continue
        robot_dir = config_path.parents[1]
        robot = robot_dir.name
        for section in ("policies", "demo_policies"):
            entries = config.get(section)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, Mapping):
                    continue
                policy_id = str(entry.get("id") or "").strip()
                if not policy_id:
                    continue
                declared = str(entry.get("path") or entry.get("url") or "")
                declarations.append({
                    "robot": robot,
                    "robot_dir": str(robot_dir),
                    "policy_id": policy_id,
                    "kind": section,
                    "label": entry.get("label") or entry.get("name") or policy_id,
                    "declared": declared,
                    # 两种原始形式都保留：有的声明 `path` 在包内、`url` 指向 web 静态目录，
                    # 只留一个就会解析失败（go2-baseline-164k 正是这种）。
                    "path": entry.get("path"),
                    "url": entry.get("url"),
                    "onnx": resolve_declared_onnx(
                        robot_dir, entry.get("path") or "", entry.get("url") or "",
                    ),
                    "obs_dim": entry.get("obs_dim"),
                    "action_dim": entry.get("action_dim"),
                    "history_len": entry.get("history_len"),
                    "task_type": entry.get("task_type"),
                    "algorithm": entry.get("algorithm"),
                    "declared_source": entry.get("source"),
                    "contract": entry.get("contract") if isinstance(entry.get("contract"), Mapping) else None,
                })
    return declarations


def artifact_id_for(robot: str, policy_id: str) -> str:
    """``<robot>__<policy-id>``（只保留安全字符）——目录名即产物 ID，可读且唯一。"""
    raw = f"{robot}__{policy_id}"
    return re.sub(r"[^0-9A-Za-z._-]+", "-", raw).strip("-")


# --------------------------------------------------------------------------------------
# 产物内容
# --------------------------------------------------------------------------------------
def contract_digest(declaration: Mapping[str, Any]) -> str | None:
    """契约块哈希：观测/动作约定一变，同一个 onnx 也不再是同一个"产物"。

    复用 ``backend.training.runs.canonical_digest`` —— 与 Run 档案同一套规范化摘要，
    因此两条链上的 hash 可直接互相引用。
    """
    contract = declaration.get("contract")
    return canonical_digest(contract) if contract else None


def deploy_payload(declaration: Mapping[str, Any]) -> dict[str, Any]:
    """``deploy.yaml`` 的内容：从 ``contract`` 段展开的部署参数（缺项不编造，直接省略）。"""
    contract = declaration.get("contract") or {}
    payload = {key: contract[key] for key in _DEPLOY_FIELDS if key in contract}
    payload["robot"] = declaration.get("robot")
    payload["policy_id"] = declaration.get("policy_id")
    return payload


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value)
    return f'"{text}"' if text == "" or re.search(r"[:#\[\]{},&*!|>'\"%@`]|^\s|\s$", text) else text


def dump_yaml(payload: Mapping[str, Any], *, indent: int = 0) -> str:
    """极简 YAML 写出（dict / list / 标量）。

    不引第三方依赖是有意的：控制面要能在"双击即用"的最小环境里跑（V5 分层）。
    只用于我们**自己生成**的结构，形态可控、可测。
    """
    pad = "  " * indent
    lines: list[str] = []
    for key, value in payload.items():
        if isinstance(value, Mapping):
            lines.append(f"{pad}{key}:")
            lines.append(dump_yaml(value, indent=indent + 1).rstrip("\n"))
        elif isinstance(value, (list, tuple)):
            if not value:
                lines.append(f"{pad}{key}: []")
                continue
            lines.append(f"{pad}{key}:")
            for item in value:
                if isinstance(item, Mapping):
                    lines.append(f"{pad}  -")
                    lines.append(dump_yaml(item, indent=indent + 2).rstrip("\n"))
                else:
                    lines.append(f"{pad}  - {_yaml_scalar(item)}")
        else:
            lines.append(f"{pad}{key}: {_yaml_scalar(value)}")
    return "\n".join(lines) + "\n"


def build_artifact(declaration: Mapping[str, Any], onnx: Path | None = None) -> dict[str, Any]:
    """单条产物的 ``artifact.json`` 内容（含源路径与 sha256；onnx 不存在时如实记空）。

    ``onnx`` 可显式传入 —— 迁移后声明只留 ``id``，blob 需经出库索引解析（见 :func:`build_all`）；
    但 **hash 始终实测**，不照抄索引。
    """
    onnx = onnx if onnx is not None else declaration.get("onnx")
    return {
        "schema": ARTIFACT_SCHEMA,
        "artifact_id": artifact_id_for(str(declaration.get("robot")), str(declaration.get("policy_id"))),
        "robot": declaration.get("robot"),
        "policy_id": declaration.get("policy_id"),
        "kind": declaration.get("kind"),
        "label": declaration.get("label"),
        "source_onnx": _repo_relative(onnx) if onnx else None,
        "onnx_sha256": file_digest(onnx) if onnx else None,
        "onnx_bytes": onnx.stat().st_size if onnx else None,
        "obs_dim": declaration.get("obs_dim"),
        "action_dim": declaration.get("action_dim"),
        "history_len": declaration.get("history_len"),
        "task_type": declaration.get("task_type"),
        "algorithm": declaration.get("algorithm"),
        "declared_source": declaration.get("declared_source"),
        "contract_digest": contract_digest(declaration),
        #: 血缘：产品自产策略出库时由 B9 的 Run 填入（上游导入的 46 条为 None，如实留空）。
        "run_id": None,
    }


def build_all(
    *,
    robots_dir: Path | str = ROBOTS_DIR,
    out_dir: Path | str = OUT_DIR,
    write: bool = False,
) -> dict[str, Any]:
    """出库全量：``policies/<artifact-id>/{deploy.yaml, artifact.json}`` + ``policies/index.json``。

    ``write=False`` 时只**算出**内容（干跑），不落盘 —— 门禁与页面都能安全调用。
    """
    out = Path(out_dir)
    declarations = scan_declarations(robots_dir)
    index = load_index(out)     # 迁移后声明只留 `id`，blob 由索引解析（hash 仍实测）
    artifacts: list[dict[str, Any]] = []
    problems: list[str] = []
    seen: set[str] = set()

    for declaration in declarations:
        artifact = build_artifact(
            declaration,
            declaration.get("onnx") or policy_blob_path(declaration, index=index),
        )
        artifact_id = str(artifact["artifact_id"])
        if artifact_id in seen:
            problems.append(f"产物 ID 重复：{artifact_id}（声明 id 在包内必须唯一）")
            continue
        seen.add(artifact_id)
        if artifact["onnx_sha256"] is None:
            problems.append(f"{artifact_id}：声明的 onnx 解析不到（{declaration.get('declared')!r}）")
        artifacts.append(artifact)

        if write:
            target = out / artifact_id
            target.mkdir(parents=True, exist_ok=True)
            (target / ARTIFACT_NAME).write_text(
                json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (target / DEPLOY_NAME).write_text(
                dump_yaml(deploy_payload(declaration)), encoding="utf-8",
            )

    index = {
        "schema": ARTIFACT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(artifacts),
        "blobs": "引用式：onnx 仍单副本留在包内（source_onnx + onnx_sha256 锁定），不复制二进制",
        "artifacts": artifacts,
        "problems": problems,
    }
    if write:
        out.mkdir(parents=True, exist_ok=True)
        (out / INDEX_NAME).write_text(
            json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return index


# --------------------------------------------------------------------------------------
# 对账
# --------------------------------------------------------------------------------------
def verify_artifacts(
    *,
    robots_dir: Path | str = ROBOTS_DIR,
    out_dir: Path | str = OUT_DIR,
) -> dict[str, Any]:
    """**对账**：出库索引是否覆盖全部声明、每个 hash 是否仍与包内源文件一致。

    "出库"最怕的是**悄悄漂移** —— 有人换了包里的 onnx，产物目录却还指着旧 hash。
    本函数把这件事实测出来（返回问题清单，不抛异常：对账工具不该在坏档案上崩）。
    """
    out = Path(out_dir)
    problems: list[str] = []
    index = _load_json(out / INDEX_NAME)
    if not isinstance(index, Mapping):
        return {"ok": False, "checked": 0, "problems": [f"缺 {INDEX_NAME}（先跑 build_all(write=True)）"]}

    recorded = {str(item.get("artifact_id")): item for item in index.get("artifacts") or []}
    declarations = scan_declarations(robots_dir)
    checked = 0

    for declaration in declarations:
        artifact_id = artifact_id_for(str(declaration.get("robot")), str(declaration.get("policy_id")))
        entry = recorded.get(artifact_id)
        if entry is None:
            problems.append(f"{artifact_id}：声明存在但索引未覆盖")
            continue
        checked += 1
        onnx = declaration.get("onnx") or policy_blob_path(declaration, index=recorded)
        actual = file_digest(onnx) if onnx else None
        if actual is None:
            problems.append(f"{artifact_id}：解析不到 onnx（声明只留 id 且索引也没给出可用路径）")
        elif actual != entry.get("onnx_sha256"):
            problems.append(
                f"{artifact_id}：onnx 已变（索引 {str(entry.get('onnx_sha256'))[:12]}… vs 实测 {actual[:12]}…）"
                "—— 需要重新出库"
            )
        if entry.get("contract_digest") != contract_digest(declaration):
            problems.append(f"{artifact_id}：契约块已变（观测/动作约定变了，需重新出库）")
        if not (out / artifact_id / ARTIFACT_NAME).is_file():
            problems.append(f"{artifact_id}：缺 {ARTIFACT_NAME}")
        if not (out / artifact_id / DEPLOY_NAME).is_file():
            problems.append(f"{artifact_id}：缺 {DEPLOY_NAME}")

    for artifact_id in recorded.keys() - {
        artifact_id_for(str(d.get("robot")), str(d.get("policy_id"))) for d in declarations
    }:
        problems.append(f"{artifact_id}：索引里有、声明里没有（悬空产物）")

    return {
        "ok": not problems,
        "checked": checked,
        "declared": len(declarations),
        "indexed": len(recorded),
        "problems": problems,
    }


def promote_produced_policy(
    *,
    artifact_id: str,
    onnx: Path | str,
    deploy: Mapping[str, Any],
    run_id: str | None = None,
    out_dir: Path | str = OUT_DIR,
) -> dict[str, Any]:
    """**产品自产**策略出库：真写 ``policy.onnx``（它此时是唯一副本，不违反单副本）。

    上游导入的 46 条走 :func:`build_all` 的引用式路径；本函数供 B9 的训练产物出库使用。
    """
    target = Path(out_dir) / artifact_id
    target.mkdir(parents=True, exist_ok=True)
    blob = target / POLICY_BLOB_NAME
    shutil.copyfile(onnx, blob)
    artifact = {
        "schema": ARTIFACT_SCHEMA,
        "artifact_id": artifact_id,
        "kind": "produced",
        "source_onnx": str(blob.relative_to(ROOT).as_posix()) if blob.is_relative_to(ROOT) else str(blob),
        "onnx_sha256": file_digest(blob),
        "onnx_bytes": blob.stat().st_size,
        "run_id": run_id,
    }
    (target / ARTIFACT_NAME).write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    (target / DEPLOY_NAME).write_text(dump_yaml(dict(deploy)), encoding="utf-8")
    return artifact


# --------------------------------------------------------------------------------------
# 引用解析（B10 收尾：契约只留引用 + hash 的读侧）
# --------------------------------------------------------------------------------------
def load_index(out_dir: Path | str = OUT_DIR) -> dict[str, dict[str, Any]]:
    """读回出库索引：``artifact_id`` → 条目。未出库时返回空字典（调用方据此判定，不抛异常）。"""
    index = _load_json(Path(out_dir) / INDEX_NAME)
    if not isinstance(index, Mapping):
        return {}
    return {str(item.get("artifact_id")): dict(item) for item in index.get("artifacts") or []}


def policy_blob_path(
    declaration: Mapping[str, Any],
    *,
    robot_dir: Path | None = None,
    index: Mapping[str, Mapping[str, Any]] | None = None,
) -> Path | None:
    """**统一解析入口**：新形式（``artifact_id`` → 索引 → ``source_onnx``）与旧形式（``path``/``url``）都认。

    两种形式并存是刻意的：迁移期间消费者不必知道自己读到的是哪一种，因此**声明可以逐包切换、
    不必一次性全改**（这正是能安全落地的关键）。
    """
    if robot_dir is None and declaration.get("robot_dir"):
        robot_dir = Path(str(declaration["robot_dir"]))
    index = index if index is not None else load_index()

    # 引用优先级：① 显式 artifact_id → ② 由 (robot, policy_id) **推导**（＝终态：契约只留 id，
    # hash 全在出库索引里）→ ③ 裸 path/url（迁移前的旧形式）。三者都走同一个入口，
    # 所以声明可以逐包删除裸路径字段，消费者无需知道切换发生在哪一刻。
    candidates: list[str] = []
    if declaration.get("artifact_id"):
        candidates.append(str(declaration["artifact_id"]))
    # 消费者手上是**原始 config 条目**（键是 `id`、没有 `robot`），所以两种键名都认，
    # 并允许从 `robot_dir` 反推机型 —— 否则 serv 层一条策略都解析不出来。
    robot_name = declaration.get("robot") or (
        Path(robot_dir).name if robot_dir is not None else declaration.get("robot_dir")
    )
    policy_id = declaration.get("policy_id") or declaration.get("id")
    if robot_name and policy_id:
        candidates.append(artifact_id_for(Path(str(robot_name)).name, str(policy_id)))

    for candidate in candidates:
        entry = index.get(candidate)
        source = (entry or {}).get("source_onnx")
        if not source:
            continue
        resolved = Path(str(source))
        resolved = resolved if resolved.is_absolute() else ROOT / resolved
        if resolved.is_file():
            return resolved

    if robot_dir is not None:
        return resolve_declared_onnx(
            Path(robot_dir),
            declaration.get("path") or declaration.get("declared") or "",
            declaration.get("url") or "",
        )
    return None


def policy_relative_path(
    declaration: Mapping[str, Any],
    *,
    robot_dir: Path | str,
    index: Mapping[str, Mapping[str, Any]] | None = None,
) -> str | None:
    """解析出**包内相对路径**（serv 层拼前端 URL 用）。

    三种声明形式都吃：裸 `path` / 裸 `url` / 只留 `id`（经索引 → `source_onnx`）。
    解析结果落在包外时（如 `web/sim2sim/models/` 的那条）返回 ``None`` —— 因为此时
    "包内相对路径"这个概念本身不成立，编一个出来只会产出一个取不到文件的 URL。
    """
    blob = policy_blob_path(declaration, robot_dir=Path(robot_dir), index=index)
    if blob is None:
        return None
    try:
        return blob.resolve().relative_to(Path(robot_dir).resolve()).as_posix()
    except ValueError:
        return None


def declaration_has_raw_path(declaration: Mapping[str, Any]) -> bool:
    """声明里是否**仍留着裸路径字段**（`path`/`url` 且指向 .onnx）。

    这是"迁移进度"的判据：索引已能独立解析（见 :func:`policy_blob_path` 的第 ①② 条），
    所以裸路径字段的存在与否只影响**契约整洁度**，不影响功能 —— 因此删它们可以安全地
    排在消费者切换之后。
    """
    for key in ("path", "url"):
        value = str(declaration.get(key) or "")
        if value.lower().endswith(".onnx"):
            return True
    return False


def policy_reference(
    declaration: Mapping[str, Any],
    *,
    robot_dir: Path | None = None,
    index: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """把一条声明翻译成"**引用 + hash**"（B10 判据的字面语义）。

    ``onnx_sha256`` 一律以**实测**为准（而不是照抄索引）：这样"索引说自己是什么"
    与"文件实际是什么"一旦分叉，立刻暴露。
    """
    index = index if index is not None else load_index()
    artifact_id = declaration.get("artifact_id") or artifact_id_for(
        str(declaration.get("robot")), str(declaration.get("policy_id")),
    )
    blob = policy_blob_path(declaration, robot_dir=robot_dir, index=index)
    return {
        "artifact_id": artifact_id,
        "onnx_sha256": file_digest(blob) if blob else None,
        "source_onnx": _repo_relative(blob) if blob else None,
        "routed_via": (
            "declaration.artifact_id"
            if declaration.get("artifact_id")
            else "policy.path/url"      # 尚未迁移：仍是裸路径声明
        ),
    }


def reference_gaps(
    *,
    robots_dir: Path | str = ROBOTS_DIR,
    out_dir: Path | str = OUT_DIR,
) -> dict[str, Any]:
    """迁移对账：哪些声明还在用裸路径、哪些声明的 hash 与出库索引不一致。

    返回问题清单（不抛异常），既是门禁输入，也是"迁移进度"的唯一真值。
    """
    index = load_index(out_dir)
    declarations = scan_declarations(robots_dir)
    legacy: list[str] = []
    problems: list[str] = []

    for declaration in declarations:
        artifact_id = artifact_id_for(str(declaration.get("robot")), str(declaration.get("policy_id")))
        if declaration_has_raw_path(declaration):
            legacy.append(artifact_id)
        reference = policy_reference(declaration, index=index)
        if reference["onnx_sha256"] is None:
            problems.append(f"{artifact_id}：引用解析不到 blob")
            continue
        entry = index.get(str(reference["artifact_id"]))
        if entry is None:
            problems.append(f"{artifact_id}：不在出库索引里（先跑 build_all(write=True)）")
        elif entry.get("onnx_sha256") != reference["onnx_sha256"]:
            problems.append(
                f"{artifact_id}：实测 hash 与索引不一致"
                f"（索引 {str(entry.get('onnx_sha256'))[:12]}… vs 实测 {str(reference['onnx_sha256'])[:12]}…）"
            )

    return {
        "ok": not problems,
        "declared": len(declarations),
        "legacy_path_declarations": legacy,     # 仍写裸 path/url 的声明（待迁移）
        "problems": problems,
    }


def strip_raw_paths(
    *,
    robots_dir: Path | str = ROBOTS_DIR,
    out_dir: Path | str = OUT_DIR,
    write: bool = False,
) -> dict[str, Any]:
    """把声明里指向 onnx 的裸 ``path``/``url`` **删掉**（纯删除，不重排文件）。

    安全性来自 :func:`policy_blob_path` 的第 ①② 条 —— 索引已能独立解析，所以删除只是
    "清理冗余字段"。两条 fail-closed 保证：

    * 任一声明解析不到 blob → **保留其裸路径不动**（宁可留着，也不能删成取不到）；
    * 改写后 JSON 解析不过 → **整份文件跳过**（绝不留下读不出来的 config）。
    """
    robots = Path(robots_dir)
    index = load_index(out_dir)
    files: list[dict[str, Any]] = []
    problems: list[str] = []

    for robot_dir in sorted(path for path in robots.iterdir() if path.is_dir()):
        config_path = robot_dir / "simulation" / "config.json"
        if not config_path.is_file():
            continue
        text = config_path.read_text(encoding="utf-8")
        removed: list[str] = []
        for declaration in scan_declarations(robots):
            if declaration["robot"] != robot_dir.name:
                continue
            artifact_id = artifact_id_for(robot_dir.name, str(declaration["policy_id"]))
            if policy_reference(declaration, index=index)["onnx_sha256"] is None:
                problems.append(f"{artifact_id}：解析不到 blob，保留裸路径不动")
                continue
            for key in ("path", "url"):
                value = str(declaration.get(key) or "")
                if not value.lower().endswith(".onnx"):
                    continue
                pattern = re.compile(
                    rf'^[ \t]*"{key}":\s*{re.escape(json.dumps(value))},?[ \t]*\n', re.MULTILINE,
                )
                text, count = pattern.subn("", text)
                if count:
                    removed.append(f"{key}={value}")
        if not removed:
            continue
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            problems.append(f"{robot_dir.name}/simulation/config.json：删除后 JSON 不合法，整份跳过（{exc}）")
            continue
        if write:
            config_path.write_text(text, encoding="utf-8")
        files.append({"robot": robot_dir.name, "removed": removed, "written": bool(write)})

    return {
        "ok": not problems,
        "files": files,
        "removed_count": sum(len(item["removed"]) for item in files),
        "problems": problems,
    }


def iter_onnx_files(robots_dir: Path | str = ROBOTS_DIR) -> Iterable[Path]:
    """包内全部 onnx 实体（供出库覆盖率核对：包里有几个、声明了几个）。"""
    return sorted(Path(robots_dir).glob("*/simulation/policies/*.onnx"))


def unexported_onnx(*, robots_dir: Path | str = ROBOTS_DIR) -> list[str]:
    """**包内有 onnx、但没有任何声明指向它** —— 这类文件是"影子产物"，必须报出来。"""
    index = load_index()
    # 声明可能只留 `id`（B10 终态），所以"被声明"＝**经索引解析得到该文件**，
    # 而不是"声明里写了 path"。
    declared = {
        blob.resolve()
        for declaration in scan_declarations(robots_dir)
        if (blob := policy_blob_path(declaration, index=index)) is not None
    }
    return [
        _repo_relative(path)
        for path in iter_onnx_files(robots_dir)
        if path.resolve() not in declared
    ]
