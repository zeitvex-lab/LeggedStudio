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
import os
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
    """仓库相对路径（posix）。不在仓库内时退回绝对路径 —— 不抛异常（外部/临时目录也会走到这里）。

    回退分支也必须 ``as_posix()``：这些字符串会写进 pack/artifact 的 JSON（``policy_ref.path``、
    ``source_onnx``），反斜杠会让同一份产物在 Windows 写出、Linux 复核时对不上（2026-09-17）。
    """
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


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


PACKS_DIR = ROOT / "packs"


def _repo_path(text: str | None) -> Path | None:
    """把 :func:`_repo_relative` 的产物还原成绝对路径（仓库外路径原样返回）。"""
    if not text:
        return None
    candidate = Path(str(text))
    return candidate if candidate.is_absolute() else ROOT / candidate


def policy_aux_blobs(
    declaration: Mapping[str, Any],
    *,
    robot_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """**辅助 blob**：一个策略除主 onnx 之外还要加载的文件（目前只有 ``encoder``）。

    为什么要多一个文件：TRON1 这类部署把策略拆成两个 onnx 图 ——
    ``encoder``（历史 → 隐状态）+ ``policy``（隐状态 + 观测 → 动作）。这是**上游的导出约定**，
    不是我们的发明：`00_resources/tron1-rl-deploy-python`（54 onnx）与 `-ros2`（40 onnx）
    里就是成对发的。

    也就是说**运行时早就统一了**（`contract.encoder_rel` + `engine.run_encoder_mode`），
    此前只有**出库/统计层**把 `encoder` 当外人 —— 于是 TRON1 那 3 个 encoder 文件被
    `unexported_onnx()` 报成"影子产物"（其实是被声明的）。这里按
    「一个策略 = 主 blob + 辅助 blob」统一建模，**hash 同样实测**；
    解析不出来时如实记 ``missing``，不静默。
    """
    if robot_dir is None and declaration.get("robot_dir"):
        robot_dir = Path(str(declaration["robot_dir"]))
    blobs: list[dict[str, Any]] = []
    for item in declaration.get("aux_blobs") or []:
        role = str(item.get("role"))
        declared = str(item.get("declared") or "")
        # **外部提供**（`external:<what>`）：它不是包内文件，**不得报成缺件** ✗。
        # 用它表达"这份输入由部署侧自己产生"——如 image encoder 的 latent(128)、
        # 历史缓冲(5 帧)、手部任务里从 ZMQ 读的 cube pose。这与"包内 encoder onnx"
        # （TRON1 ✓）是**两种形态**，硬按路径解析只会得到一条假的缺件报警。
        if declared.startswith("external:"):
            blobs.append({
                "role": role,
                "declared": declared,
                "source": None,
                "sha256": None,
                "external": declared.split(":", 1)[1] or "external",
                "missing": False,
            })
            continue
        path: Path | None = None
        if robot_dir is not None and declared:
            candidate = Path(str(robot_dir)) / _URL_PREFIX.sub("", declared).lstrip("/")
            path = candidate if candidate.is_file() else None
        blobs.append({
            "role": role,
            "declared": declared,
            "source": _repo_relative(path) if path else None,
            "sha256": file_digest(path) if path else None,
            "missing": path is None,
        })
    return blobs


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
                    # 辅助 blob：`encoder` 是"第二个 onnx 图"（上游导出约定，见
                    # :func:`policy_aux_blobs`）。此前只认 `path`，于是它被误报成影子产物。
                    "encoder": entry.get("encoder"),
                    "aux_blobs": [
                        {"role": role, "declared": entry.get(key)}
                        for role, key in (("encoder", "encoder"),)
                        if entry.get(key)
                    ],
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
        # 主 blob 之外的产物（encoder 等）：同一个框架内建模，hash 同样实测
        "aux_blobs": policy_aux_blobs(declaration),
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

    # 产品自产条目（promote_from_run 写入）**跨重建保留**：索引从声明整表重建，
    # 不主动并回的话一次 build_all 就会把它们冲掉（目录还在、索引没了＝孤儿产物）。
    for produced in _produced_index_entries(out):
        pid = str(produced.get("artifact_id"))
        if pid in seen:
            problems.append(f"产物 ID 冲突：声明条目与 produced 条目同名 {pid}（改 produced 的 artifact_id）")
            continue
        seen.add(pid)
        artifacts.append(produced)

    index = {
        "schema": ARTIFACT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(artifacts),
        "blobs": "引用式：onnx 仍单副本留在包内（source_onnx + onnx_sha256 锁定），不复制二进制；"
                 "produced 条目例外（训练产物入库时 policy.onnx 是唯一副本，真复制）",
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
        if recorded[artifact_id].get("kind") == "produced":
            continue  # produced 出自 Run（promote_from_run），本就不在声明里，不是"悬空"
        problems.append(f"{artifact_id}：索引里有、声明里没有（悬空产物）")

    # produced 条目的对账口径：不比对声明（没有声明），实测**自完整性**——
    # onnx 真副本还在、hash 没被换、档案两件套齐全。
    for artifact_id, entry in recorded.items():
        if entry.get("kind") != "produced":
            continue
        checked += 1
        source = str(entry.get("source_onnx") or "")
        blob = Path(source) if Path(source).is_absolute() else ROOT / source
        actual = file_digest(blob) if blob.is_file() else None
        if actual is None:
            problems.append(f"{artifact_id}：produced 的 onnx 缺失（{source or '未登记'}）")
        elif actual != entry.get("onnx_sha256"):
            problems.append(f"{artifact_id}：produced onnx 已变（重跑 promote_from_run 或查明改动）")
        if not (out / artifact_id / ARTIFACT_NAME).is_file():
            problems.append(f"{artifact_id}：缺 {ARTIFACT_NAME}")
        if not (out / artifact_id / DEPLOY_NAME).is_file():
            problems.append(f"{artifact_id}：缺 {DEPLOY_NAME}")

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
    robot: str | None = None,
    policy_id: str | None = None,
) -> dict[str, Any]:
    """**产品自产**策略出库：真写 ``policy.onnx``（它此时是唯一副本，不违反单副本）。

    上游导入的 46 条走 :func:`build_all` 的引用式路径；本函数供 B9 的训练产物出库使用。

    ``robot`` / ``policy_id``（2026-09-16 加）是**回挂**需要的绑定：没有它们就说不清
    "这份产物是哪台机的哪条策略"，浏览器与无头侧也就都按 id 找不到它（只给非空值写入，
    缺省不编造）。
    """
    target = Path(out_dir) / artifact_id
    target.mkdir(parents=True, exist_ok=True)
    blob = target / POLICY_BLOB_NAME
    shutil.copyfile(onnx, blob)
    artifact = {
        "schema": ARTIFACT_SCHEMA,
        "artifact_id": artifact_id,
        "kind": "produced",
        "source_onnx": str(blob.relative_to(ROOT).as_posix()) if blob.is_relative_to(ROOT) else blob.as_posix(),
        "onnx_sha256": file_digest(blob),
        "onnx_bytes": blob.stat().st_size,
        "run_id": run_id,
    }
    if robot:
        artifact["robot"] = str(robot)
    if policy_id:
        artifact["policy_id"] = str(policy_id)
    (target / ARTIFACT_NAME).write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    (target / DEPLOY_NAME).write_text(dump_yaml(dict(deploy)), encoding="utf-8")
    return artifact


def _produced_index_entries(out_dir: Path) -> list[dict[str, Any]]:
    """既有索引里的 **produced 条目**（目录与 ``artifact.json`` 还在的才算）。

    ``build_all`` 的索引是从包声明**整表重建**的 —— 不主动保留的话，一次重建就会把
    产品自产的条目冲掉（目录还在、索引没了＝"孤儿产物"）。被人工删掉目录的条目
    **不复活**（复活一个指向不存在文件的索引条目比缺它更糟）。
    """
    index = _load_json(Path(out_dir) / INDEX_NAME)
    entries: list[dict[str, Any]] = []
    if not isinstance(index, Mapping):
        return entries
    for item in index.get("artifacts") or []:
        if not isinstance(item, Mapping) or item.get("kind") != "produced":
            continue
        if (Path(out_dir) / str(item.get("artifact_id")) / ARTIFACT_NAME).is_file():
            entries.append(dict(item))
    return entries


def produced_for_run(run_id: str, *, out_dir: Path | str = OUT_DIR) -> list[dict[str, Any]]:
    """某个 Run 已入库的 produced 产物（按索引里的 ``run_id`` 反查）。

    页面侧据此显示"这条 Run 的策略已进产物库"；没有就是空表（Run 未入库是
    正常状态，promote 是显式动作）。
    """
    if not run_id:
        return []
    return [
        {
            "artifact_id": str(item.get("artifact_id")),
            "onnx_sha256": item.get("onnx_sha256"),
            "onnx_bytes": item.get("onnx_bytes"),
        }
        for item in _produced_index_entries(Path(out_dir))
        if item.get("run_id") == run_id
    ]


def _policy_id_from_run(robot_id: str, run_id: str) -> str:
    """由 run_id 的时间戳派生一个稳定、可读、唯一的包内策略 id（如 ``zex-w-trained-20260916-100632``）。"""

    match = re.search(r"(\d{8})_(\d{6})", str(run_id))
    stamp = f"{match.group(1)}-{match.group(2)}" if match else ""
    return f"{robot_id}-trained{'-' + stamp if stamp else ''}"


def promote_from_run(
    run_dir: Path | str,
    *,
    artifact_id: str | None = None,
    out_dir: Path | str = OUT_DIR,
    policy_id: str | None = None,
    install: bool = False,
    attach_pack: bool = False,
) -> dict[str, Any]:
    """L7「训练→导出→入库」的**入库入口**：把一份已完成 Run 的导出产物收进出库。

    证据链全部取自 Run 档案（B9 四件套 + worker 产物），不信任调用方口述：

    * ``run.json`` 必在 —— 没有 run_id/robot_id/seed 就没有"可追溯"（V1）；
    * ``status.json`` 必须 ``completed`` —— 没训完的 Run 不入库；
    * ``exported/policy.onnx`` 必在 —— worker ⑤「训练完成即导出」的产物；缺件说明
      导出失败（见 status.json 的 ``onnx_export_error``），如实报缺、不伪造。

    produced 条目是索引里唯一的**真副本**（onnx 从 task_dir 复制进出库目录 —— 此时
    它是唯一副本，不违反 B5 单副本；上游导入的 46 条仍走引用式）。

    ## 回挂（2026-09-16 加）

    ``install=True`` 会把产物**装进机器人包**（`simulation/policies/<policy_id>.onnx` +
    `simulation/config.json` 里声明一条策略条目），``attach_pack=True`` 再把 Pack 的
    `policy_ref` 指向它。**默认都关**：它们会**改写包内资产文件**（`simulation/config.json`）
    与生成物（`packs/*.pack.json`），属于"产品动作"，应由产品入口显式开启，
    而不是每个调用方（含测试）默认触发。
    """
    from backend.training.runs import load_run

    run_dir = Path(run_dir)
    record = load_run(run_dir)
    if record is None:
        raise FileNotFoundError(f"{run_dir} 不是一份 Run 档案（缺 run.json；B9 接线前的旧任务无法入库）")

    status = _load_json(run_dir / "status.json")
    status_value = str((status or {}).get("status") or "") if isinstance(status, Mapping) else ""
    # worker 的完成态词表：train 模式写 "train_completed"（report 覆盖了模板的
    # "completed"）；smoke/evaluate 各有自己的终态且不产 exported/policy.onnx，
    # 由下面的导出存在性硬证据挡住，不在这里放行。
    if status_value not in ("completed", "train_completed"):
        raise RuntimeError(f"Run {record.run_id} 状态为 {status_value or '未知'}，只有训练完成的 Run 才能入库")

    onnx = run_dir / "exported" / POLICY_BLOB_NAME
    if not onnx.is_file():
        detail = (status or {}).get("onnx_export_error") if isinstance(status, Mapping) else None
        raise FileNotFoundError(
            f"Run {record.run_id} 缺 exported/policy.onnx（worker 导出失败或未导出"
            + (f"：{detail}" if detail else "")
            + "）"
        )

    robot_id = str(record.robot_id or "robot")
    final_id = artifact_id or artifact_id_for(robot_id, f"produced-{record.run_id}")

    snapshot = _load_json(run_dir / "contract_snapshot.json")
    observation = (snapshot or {}).get("observation") if isinstance(snapshot, Mapping) else None
    action = (snapshot or {}).get("action") if isinstance(snapshot, Mapping) else None
    deploy: dict[str, Any] = {
        "robot": robot_id,
        "policy_id": final_id,
        "kind": "produced",
        "run_id": record.run_id,
        "seed": record.seed,
        "source_onnx": "product-training（训练→导出→入库链路自产）",
    }
    # 部署维度只写快照里真实有的（缺项不编造，与 deploy_payload 同原则）
    if isinstance(observation, Mapping) and observation.get("dimension") is not None:
        deploy["obs_dim"] = observation["dimension"]
    if isinstance(action, Mapping):
        if action.get("dimension") is not None:
            deploy["action_dim"] = action["dimension"]
        if action.get("joint_order"):
            deploy["action_joint_order"] = list(action["joint_order"])
    if isinstance(status, Mapping) and status.get("max_iterations") is not None:
        deploy["trained_iterations"] = status["max_iterations"]

    artifact = promote_produced_policy(
        artifact_id=final_id, onnx=onnx, deploy=deploy, run_id=record.run_id, out_dir=out_dir,
        robot=robot_id, policy_id=policy_id,
    )

    write_out_index(out_dir, upsert=[artifact])

    if install or attach_pack:
        from backend.robot_packages import robot_package_root

        robot_dir = robot_package_root(robot_id)
        if install:
            installed = install_produced_policy(
                artifact_id=final_id,
                robot_dir=robot_dir,
                policy_id=policy_id or _policy_id_from_run(robot_id, record.run_id),
                declaration={
                    "label": f"训练产物（run {record.run_id}）",
                    "obs_dim": deploy.get("obs_dim"),
                    "action_dim": deploy.get("action_dim"),
                    "contract": {
                        **({"obs_dim": deploy["obs_dim"]} if deploy.get("obs_dim") else {}),
                        **({"action_dim": deploy["action_dim"]} if deploy.get("action_dim") else {}),
                    } or None,
                },
                out_dir=out_dir,
            )
            artifact = installed["artifact"]
            artifact["installation"] = {
                "policy_id": installed["policy_id"],
                "package_path": installed["package_path"],
                "removed_local_blob": installed["removed_local_blob"],
            }
            if policy_id is None:
                artifact["policy_id"] = installed["policy_id"]
        if attach_pack:
            attached = attach_policy_to_pack(robot_id, artifact_id=final_id, out_dir=out_dir)
            artifact["pack_ref"] = attached["policy_ref"]

    return artifact


def write_out_index(out_dir: Path | str, *, upsert: list[Mapping[str, Any]]) -> Path:
    """更新出库索引（声明条目不动 —— 它们由 :func:`build_all` 重建；只增/改给定条目）。"""

    out = Path(out_dir)
    index = _load_json(out / INDEX_NAME)
    artifacts = [
        dict(item) for item in (index or {}).get("artifacts") or []
        if isinstance(item, Mapping)
    ] if isinstance(index, Mapping) else []
    incoming = {str(item.get("artifact_id")): dict(item) for item in upsert if isinstance(item, Mapping)}
    artifacts = [item for item in artifacts if item.get("artifact_id") not in incoming]
    artifacts.extend(incoming.values())
    doc = {
        "schema": ARTIFACT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(artifacts),
        "blobs": "引用式：onnx 单副本留在包内（source_onnx + onnx_sha256 锁定），不复制二进制；"
                 "produced 条目在**安装进包之前**持真副本，安装后转为引用式（见 install_produced_policy）",
        "artifacts": artifacts,
        "problems": list((index or {}).get("problems") or []) if isinstance(index, Mapping) else [],
    }
    out.mkdir(parents=True, exist_ok=True)
    path = out / INDEX_NAME
    path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------------------
# 回挂（2026-09-16）：训练产物 → 包内策略条目 → Pack.policy_ref
# --------------------------------------------------------------------------------------
def _repo_relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()  # 与 _repo_relative 同纪律：序列化进 JSON 的路径一律 posix 分隔符


def _write_json_atomic(path: Path, payload: Any) -> None:
    """原子写（先写临时文件再替换）——包里的 ``simulation/config.json`` 是手工维护过的资产文件，
    写坏一半比写错更糟。"""

    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def install_produced_policy(
    *,
    artifact_id: str,
    robot_dir: Path | str,
    policy_id: str,
    declaration: Mapping[str, Any] | None = None,
    out_dir: Path | str = OUT_DIR,
    keep_blob: bool = False,
) -> dict[str, Any]:
    """把训练产物**装进机器人包**并声明成一条策略条目（回挂的真正落点）。

    ## 为什么必须"装进包"（2026-09-16 实测三处约束）

    1. **浏览器只服务包内 blob**：`policy_relative_path()` 对包外文件返回 ``None``，而
       `simulation_api` 对解析不到的条目**连 URL 都不编**（直接 continue）—— 产物留在
       `policies/<id>/` 里，页面上根本看不到这条策略；
    2. **无头侧按包内配置解析**：`policy_acceptance.py` 与 B12 的无头产出端都从
       `simulation/config.json` 的 `policies[]` 取 `--policy-id`；
    3. **Bundle 的 R2 诚实闸门**要求策略解析落在包内（`inside_package=true`），否则判 blocked。

    ## 单副本

    装进包后**删掉出库目录里的真副本**，把 `source_onnx` 改指包内文件（`onnx_sha256` 继续锁定）——
    "一个策略字节只存一处"在 produced 上也成立，与 B10 的"声明式条目 = 引用式"同一套模型。

    `declaration` 里**只写真实有的字段**（缺项不编造）；`provenance` 记 artifact_id/run_id/时间，
    让"这条策略是自产还是上游导入"一眼可查（V1）。
    """

    out = Path(out_dir)
    index = load_index(out)
    entry = index.get(artifact_id)
    if entry is None:
        raise ValueError(f"出库索引里没有这个产物：{artifact_id}")
    blob = policy_blob_path(entry, index=index)
    if blob is None or not Path(blob).is_file():
        raise FileNotFoundError(f"解析不到产物 onnx（artifact_id={artifact_id}）")

    robot_dir = Path(robot_dir).expanduser().resolve()
    config_path = robot_dir / "simulation" / "config.json"
    if not config_path.is_file():
        raise FileNotFoundError(f"不是机器人包（缺 simulation/config.json）：{robot_dir}")

    policies_dir = robot_dir / "simulation" / "policies"
    policies_dir.mkdir(parents=True, exist_ok=True)
    target = policies_dir / f"{policy_id}.onnx"
    if Path(blob).resolve() != target.resolve():
        shutil.copyfile(blob, target)

    config = _load_json(config_path)
    if not isinstance(config, Mapping):
        raise ValueError(f"simulation/config.json 顶层不是对象：{config_path}")
    policies = [dict(item) for item in (config.get("policies") or []) if isinstance(item, Mapping)]
    package_relative = target.relative_to(robot_dir).as_posix()

    declared: dict[str, Any] = {
        "id": policy_id,
        "path": package_relative,
        "provenance": {
            "artifact_id": artifact_id,
            "run_id": entry.get("run_id"),
            "origin": "product-training",
            "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    }
    extra = dict(declaration or {})
    label = extra.pop("label", None)
    declared["label"] = str(label or f"训练产物 {artifact_id}")
    for key in ("obs_dim", "action_dim", "history_len", "contract", "task_type"):
        if extra.get(key) is not None:
            declared[key] = extra[key]
    declared.update(extra)
    policies = [item for item in policies if str(item.get("id")) != policy_id]
    policies.append(declared)
    _write_json_atomic(config_path, {**dict(config), "policies": policies})

    updated = dict(entry)
    updated["source_onnx"] = _repo_relative_path(target)
    updated["onnx_sha256"] = file_digest(target)
    updated["onnx_bytes"] = target.stat().st_size
    updated["installed"] = {
        "robot": robot_dir.name,
        "policy_id": policy_id,
        "package_path": package_relative,
        "repo_path": _repo_relative_path(target),
    }
    artifact_path = Path(out) / artifact_id / ARTIFACT_NAME
    if artifact_path.is_file():
        artifact_path.write_text(
            json.dumps(updated, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
    write_out_index(out, upsert=[updated])

    removed_local = None
    local_blob = Path(out) / artifact_id / POLICY_BLOB_NAME
    if not keep_blob and local_blob.is_file() and local_blob.resolve() != target.resolve():
        removed_local = str(local_blob)
        local_blob.unlink()

    return {
        "artifact": updated,
        "policy_id": policy_id,
        "declaration": declared,
        "package_path": package_relative,
        "config_path": str(config_path),
        "removed_local_blob": removed_local,
    }


def attach_policy_to_pack(
    robot_id: str,
    *,
    artifact_id: str,
    out_dir: Path | str = OUT_DIR,
    packs_dir: Path | str = PACKS_DIR,
) -> dict[str, Any]:
    """把产物回挂到该机型的 Pack（`policy_ref`）—— 愿景原文的"训练/导出后回挂"。

    写的是 Pack schema 的 `$defs.ref`（`{id, path, sha256}`，`additionalProperties: false`），
    **与 `morphology_ref` 同纪律**：引用也带内容哈希，飘了能被发现（`pack_catalog._check_ref`）。
    找不到形态 id 匹配的 Pack 就报错，不猜一个写进去（写错 Pack 比不写更坏）。
    """

    out = Path(out_dir)
    index = load_index(out)
    entry = index.get(artifact_id)
    if entry is None:
        raise ValueError(f"出库索引里没有这个产物：{artifact_id}")
    blob = policy_blob_path(entry, index=index)
    if blob is None or not Path(blob).is_file():
        raise FileNotFoundError(f"解析不到产物 onnx（artifact_id={artifact_id}）")

    pack_path: Path | None = None
    for candidate in sorted(Path(packs_dir).glob("*.pack.json")):
        payload = _load_json(candidate)
        if isinstance(payload, Mapping) and str((payload.get("morphology_ref") or {}).get("id")) == robot_id:
            pack_path = candidate
            break
    if pack_path is None:
        raise FileNotFoundError(f"packs/ 里找不到 morphology_ref.id == {robot_id!r} 的 Pack")

    pack = dict(_load_json(pack_path))
    policy_ref: dict[str, Any] = {
        "id": artifact_id,
        "path": _repo_relative_path(Path(blob)),
        "sha256": file_digest(blob),
    }
    if entry.get("policy_id"):
        policy_ref["version"] = str(entry["policy_id"])
    pack["policy_ref"] = policy_ref
    _write_json_atomic(pack_path, pack)
    return {"pack_path": str(pack_path), "pack_id": pack.get("pack_id"), "policy_ref": policy_ref}


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

    **副本回退（2026-09-17，G1 全机型浏览器实测缺陷 A）**：索引里的 `source_onnx` 按仓库
    相对路径记录（出库时以 `assets/robots/<id>` 为包根），但运行期包根可能是 workspace
    副本（`workspace/packages/<id>`，D7/C6 的持久化权威）——此时 blob 解析命中索引路径
    （在"包外"）⇒ 旧逻辑直接返回 None ⇒ browser-config 对该包**静默跳过全部策略**，
    浏览器里整机以"无策略"姿态运行（实测 lite3/go2/zex-w/wuji_hand 四台同病，go2 还是
    浏览器默认落点）。workspace 副本与源树的策略 blob 由同步机制（C6）保证逐字节一致，
    故回退按**同一包内相对路径**找副本是安全的：命中副本 ⇒ 返回该相对路径。
    """
    robot = Path(robot_dir)
    blob = policy_blob_path(declaration, robot_dir=robot, index=index)
    if blob is not None:
        try:
            return blob.resolve().relative_to(robot.resolve()).as_posix()
        except ValueError:
            pass  # 落在包外（如索引按源树记录而包根是 workspace 副本）——试副本回退
    # 副本回退：索引按源树记录（assets/robots）而运行期包根是 workspace 副本时，
    # 按声明/推导的相对路径在**真实包根**下找文件。只认包内真实存在的文件——
    # 包外路径（如 demo 的 web/sim2sim/models/）在包内不存在，is_file() 为假 ⇒ 仍返回
    # None（"包内相对路径"对它们不成立，编一个只会产出取不到文件的 URL，既有测试钉住）。
    stem = declaration.get("path") or declaration.get("declared") or ""
    if not stem:
        policy_id = declaration.get("policy_id") or declaration.get("id")
        if not policy_id:
            return None
        stem = f"simulation/policies/{policy_id}"
    stem = str(stem).replace("\\", "/").lstrip("/")
    candidate = (robot / stem).resolve()
    robot_root = robot.resolve()
    if candidate.is_file() and robot_root in candidate.parents:
        return candidate.relative_to(robot_root).as_posix()
    return None


def declaration_has_raw_path(declaration: Mapping[str, Any]) -> bool:
    """声明里是否**仍留着裸路径字段**（`path`/`url` 且指向 .onnx）。

    这是"迁移进度"的判据：索引已能独立解析（见 :func:`policy_blob_path` 的第 ①② 条），
    所以裸路径字段的存在与否只影响**契约整洁度**，不影响功能 —— 因此删它们可以安全地
    排在消费者切换之后。
    """
    for key in ("path", "url"):
        value = str(declaration.get(key) or "")
        if not value.lower().endswith(".onnx"):
            continue
        # `demo_policies` 的 `url` 是递送地址而非 blob 引用（同 :func:`strip_raw_paths`
        # 的豁免），因此不算"未迁移"。
        if key == "url" and declaration.get("kind") == "demo_policies":
            continue
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
                # `demo_policies` 的 `url` 是**递送地址**（`simulation_api` 直接把它当
                # `onnx_url` 交给前端），不是包内 blob 的冗余引用 —— 删掉会让整条 demo
                # 被跳过、默认策略静默掉回数组第一条（2026-09-14 真实回归，CI 抓到）。
                if key == "url" and declaration.get("kind") == "demo_policies":
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
    declared: set[Path] = set()
    for declaration in scan_declarations(robots_dir):
        blob = policy_blob_path(declaration, index=index)
        if blob is not None:
            declared.add(blob.resolve())
        # **辅助 blob 也算被声明** —— 否则 TRON1 的 encoder 文件会被误报成"影子产物"。
        for aux in policy_aux_blobs(declaration):
            aux_path = _repo_path(aux.get("source"))
            if aux_path is not None:
                declared.add(aux_path.resolve())
    return [
        _repo_relative(path)
        for path in iter_onnx_files(robots_dir)
        if path.resolve() not in declared
    ]
