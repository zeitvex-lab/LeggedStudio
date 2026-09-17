#!/usr/bin/env python3
"""Command-line facade for the Legged Studio control-plane API.

The CLI intentionally calls the same HTTP contract used by the Web workbench.
It is therefore useful for smoke tests today and a stable automation surface
for native MJLab/Isaac adapters later.

离线子命令（I1）不连控制面，直接读仓库数据，并且**复用 backend/ 的同一实现**（单一真值来源）：

* ``onboard <目录>``    → :func:`backend.model_api.import_package_directory` / ``preview_package_import``
  —— 新机器人 = 1 目录 + 模型 → 校验 → 生成三件 JSON（contract.json / robot_package.json /
  contract_v3.json）→ 落 ``workspace/packages/`` → 登记索引；**默认预演**，``--write`` 落盘，
  校验不过一字节不写（与 Web 的 ``POST /api/models/import`` 共用同一份编排与内容摘要）；
* ``verify package <目录>`` → ``contracts.validator`` + ``contracts.contract_loader``
  —— 包对账门禁（v2 契约 / v3 角色语义 / 训练侧消费的合并契约 / 清单与模型对得上），
  不通过退出码 1；
* ``verify run <run_id|目录>`` / ``verify run --all`` → :func:`backend.training.runs.verify_run`
  —— Run 档案（四件套）对账，不通过退出码 1；
* ``verify artifacts`` → :func:`backend.policy_artifacts.verify_artifacts`
  —— 出库索引对账（索引覆盖 / hash 一致 / produced 自完整性），不通过退出码 1；
* ``pack list``     → :func:`backend.pack_catalog.pack_catalog`（与 ``tools/validate_packs.py`` 同源）；
* ``run list``      → 扫描 ``workspace/`` 下含 ``run.json`` 的目录 + :func:`backend.training.runs.load_run`；
* ``artifact list`` → :func:`backend.policy_artifacts.load_index`；
* ``deploy gate <robot_id>``   → ``backend.export_gate.compare_contracts``
  （与 ``GET /api/deploy/gate/{robot_id}`` 同一组成：包内 contract_v3 vs contract.json，
  DENYLIST fail-closed，存在 blocker 退出码 1）；
* ``deploy package <robot_id>`` → ``backend.deploy_pack.generate_deploy_package``
  （与 ``POST /api/deploy/package`` 同一实现：部署四件套 + 平台适配层；只生成物料，
  不直接发电机命令——一键生成 ≠ 一键上机）。

因此这些命令**无需后端**（离线命令），只是参数解析与输出格式化在本文件完成。

``--offline``：显式声明"本次不碰后端"。离线命令不受影响；需后端的命令会**直接拒绝并返回
非 0**（绝不静默跳过——"离线模式下悄悄不发请求"会让 CI 以为命令成功了）。

训练在线命令（I1 第二批）：``train create`` / ``train status`` / ``train stop`` /
``train list`` —— **需要后端在跑**，走与 Web 工作台完全相同的 HTTP 契约
（``/api/training/*``）。``--base`` 指定后端地址（默认 http://127.0.0.1:8765）；
后端不可达时给出中文可操作提示并以非 0 码退出，**绝不静默编造结果**。
原顶层 ``train <contract.json>``（10 命令时期的叶子命令）并入
``train create --contract <path>``，请求字段保持不变。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# 仓库根 bootstrap：脚本方式运行时 sys.path[0] 是 scripts/，离线命令要 import backend.*
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _http_detail_hint(detail: str) -> str | None:
    """从错误体里提取人类可读原因（FastAPI 的 detail 可能是字符串或 dict）。"""

    try:
        parsed = json.loads(detail)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    inner = parsed.get("detail")
    if isinstance(inner, str):
        return inner
    if isinstance(inner, dict):
        for key in ("message", "reason"):
            value = inner.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _request(
    base_url: str,
    method: str,
    route: str,
    payload: object | None = None,
    *,
    headers: dict[str, str] | None = None,
    unreachable_hint: str | None = None,
    friendly_http: bool = False,
) -> object:
    """对控制面发一次 HTTP 请求并解析 JSON 响应。

    关键字参数只被训练在线命令（I1 第二批）使用，默认关闭时行为与既有
    10 个 HTTP 门面命令完全一致：

    * ``headers``          —— 追加请求头（如 Idempotency-Key）；
    * ``unreachable_hint`` —— 连接失败时的中文可操作提示模板（{base}/{reason} 占位）；
    * ``friendly_http``    —— HTTP 错误体里提取 message/reason 给可读行（原始体仍保留）。
    """

    body = None if payload is None else json.dumps(payload).encode("utf-8")
    all_headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if headers:
        all_headers.update(headers)
    request = Request(f"{base_url.rstrip('/')}{route}", data=body, method=method, headers=all_headers)
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if friendly_http:
            hint = _http_detail_hint(detail)
            if hint:
                raise SystemExit(f"HTTP {exc.code} 请求被拒：{hint}\n{detail}") from exc
        raise SystemExit(f"HTTP {exc.code}: {detail}") from exc
    except (URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        if unreachable_hint:
            raise SystemExit(unreachable_hint.format(base=base_url, reason=reason)) from exc
        raise SystemExit(f"无法连接控制平面 {base_url}: {reason}") from exc


def _json_file(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------
# 离线命令（I1 第一批）：不连控制面，直接读仓库数据；逻辑一律复用 backend/，这里只做输出
# --------------------------------------------------------------------------------------
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


def _workspace_root(workspace: str | None) -> Path:
    """workspace 根：``--workspace`` 参数 > 环境变量 > 仓库 ``workspace/``（与 backend 各模块同约定）。"""

    if workspace:
        return Path(workspace).expanduser()
    configured = os.environ.get("LEGGED_STUDIO_WORKSPACE", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    from backend.training.runs import ROOT

    return ROOT / "workspace"


def _run_status(run_dir: Path, fallback: str) -> str:
    """读 ``status.json`` 的 ``status`` 字段；缺失/不可解析时回退 run.json 自带的 status（如实，不编造）。"""

    try:
        payload = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback
    value = payload.get("status") if isinstance(payload, dict) else None
    return str(value) if value else fallback


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


def _cmd_onboard(args: argparse.Namespace) -> int:
    """``onboard <目录>``：把一个机器人目录导入为机器人包（离线命令，无需后端）。

    与 Web 的 ``POST /api/models/import`` **共用同一份编排**（``backend.model_api``）：
    校验模型 → 生成三件 JSON（``contract.json`` / ``robot_package.json`` /
    ``contract_v3.json``）→ 落 ``workspace/packages/<package_id>/`` → 登记索引。
    两条入口的 ``package_id`` 由同一份内容摘要算出，所以"同一份资产"不会变成两个包。

    **默认预演**（与 ``tools/skill_pack.py import`` 同惯例：导入是写操作，先看清再落盘），
    ``--write`` 才真写；校验不过**一个字节都不写**（fail-closed）。
    """

    from backend.model_api import import_package_directory, preview_package_import

    workspace = _workspace_root(args.workspace)
    if args.workspace:
        # `--workspace` 是"**这个进程**的 workspace"：同步到环境变量，让下游（model_api 的
        # workspace 解析与模型路径守卫）看到同一处。只在 CLI 里传 packages_root 会造成
        # "包落在 A、路径守卫按 B 判"——两处不一致时该报的错会变成莫名其妙的越界拒绝。
        os.environ["LEGGED_STUDIO_WORKSPACE"] = str(workspace)
    packages_root = workspace / "packages"
    runner = import_package_directory if args.write else preview_package_import
    try:
        report = runner(
            args.directory,
            model_filename=args.model,
            model_format=args.format,
            packages_root=packages_root,
        )
    except (ValueError, OSError) as exc:
        raise SystemExit(f"onboard 失败：{exc}") from exc

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("valid") else 1

    errors = list(report.get("errors") or [])
    warnings = list(report.get("warnings") or [])
    print(f"机器人 onboard（离线命令，无需后端）：{report.get('source_dir')}")
    print(f"  模型文件：{report.get('model_file')}（{report.get('format')}）")
    skipped = report.get("skipped_dirs") or []
    print(f"  文件数：{report.get('file_count')}（{report.get('staged_bytes', 0) / 1024 / 1024:.2f} MB"
          + (f"；已跳过 {', '.join(skipped)}" if skipped else "") + "）")
    stats = report.get("stats") or {}
    if stats:
        print(f"  结构：{stats.get('links')} 体 / {stats.get('joints')} 关节 / "
              f"{stats.get('actuated_joints')} 驱动关节"
              + (f" / 总质量 {stats.get('total_mass_kg')} kg" if stats.get("total_mass_kg") else ""))
    print(f"  校验：{'通过' if report.get('valid') else '未通过'}（{len(errors)} 错误 / {len(warnings)} 警告）")
    for item in errors:
        print(f"    ✗ {item}")
    for item in warnings:
        print(f"    ~ {item}")
    if not report.get("valid"):
        print("（未写任何文件：校验不过不落盘）")
        return 1

    print(f"  包 id：{report.get('package_id')}")
    print(f"  落点：{report.get('package_root')}")
    print("  三件 JSON：contract.json / robot_package.json / contract_v3.json")
    note = (report.get("contract_v3") or {}).get("note")
    if note:
        print(f"  contract_v3：{note}")
    if args.write:
        print("已导入并登记索引。下一步：verify package <落点> → train create")
    else:
        print("（预演：未写任何文件；加 --write 落盘）")
    return 0


def _cmd_verify_package(args: argparse.Namespace) -> int:
    """``verify package <目录>``：对一个机器人包做全面对账（离线命令，无需后端）。

    判据一律取**既有实现**（不在这里另写一套校验）：
      * v2 契约 → ``contracts.validator.validate_contract_file``（模型哈希 / 驱动关节 /
        观测与动作维度）；
      * v3 契约 → ``contracts.contract_loader.load_contract_v3``（角色语义
        ``RoleResolver.validate``）；
      * 「训练实际消费的那份合并契约」→ ``load_training_contract``（v3 覆盖 v2）；
      * 清单与模型文件对得上（``robot_package.json`` 的 ``model.path`` / ``contract_path``）。

    任一不过 → 退出码 1（可直接当 CI / 脚本门禁）。
    """

    from contracts.contract_loader import ContractLoadError, load_contract_v3, load_training_contract
    from contracts.validator import validate_contract_file

    root = Path(args.directory).expanduser()
    problems: list[str] = []
    warnings: list[str] = []
    report: dict[str, object] = {"directory": str(root), "package_id": None}

    if not root.is_dir():
        raise SystemExit(f"verify 失败：目录不存在：{root}")

    manifest_path = root / "robot_package.json"
    contract_path = root / "contract.json"
    manifest: dict = {}
    if not manifest_path.is_file():
        problems.append("缺 robot_package.json（不是机器人包）")
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            report["package_id"] = manifest.get("package_id")
        except json.JSONDecodeError as exc:
            problems.append(f"robot_package.json 不可解析：{exc}")

    if not contract_path.is_file():
        problems.append("缺 contract.json（v2 契约）")
    else:
        try:
            result = validate_contract_file(str(contract_path))
            problems.extend(f"契约 v2：{item.message}" for item in result.errors)
            warnings.extend(f"契约 v2：{item.message}" for item in result.warnings)
        except Exception as exc:  # 解析失败也要如实报，而不是崩掉
            problems.append(f"契约 v2 校验异常：{type(exc).__name__}: {exc}")

    try:
        v3 = load_contract_v3(root)
        report["contract_v3"] = "present" if v3 is not None else "missing"
        if v3 is None:
            warnings.append("缺 contract_v3.json（语义层：构型/角色/执行器按 v3 取，缺它训练侧只能退回 v2）")
    except Exception as exc:
        problems.append(f"契约 v3 角色语义校验失败：{exc}")
        report["contract_v3"] = "invalid"

    try:
        merged = load_training_contract(root)
        report["merged_keys"] = len(merged)
        report["robot_id"] = merged.get("robot_id")
    except ContractLoadError as exc:
        problems.append(f"合并契约加载失败：{exc}")
    except Exception as exc:
        problems.append(f"合并契约加载异常：{type(exc).__name__}: {exc}")

    model = ((manifest.get("model") or {}) if isinstance(manifest, dict) else {}) or {}
    model_path = root / str(model.get("path") or "")
    declared_contract = root / str(manifest.get("contract_path") or "contract.json")
    if model and not model_path.is_file():
        problems.append(f"robot_package.json 指认的模型文件不存在：{model.get('path')}")
    if not declared_contract.is_file():
        problems.append(f"robot_package.json 指认的契约文件不存在：{manifest.get('contract_path')}")
    if manifest.get("package_id") and manifest.get("package_id") != root.name:
        warnings.append(f"包目录名 {root.name} 与 package_id {manifest.get('package_id')} 不一致（重命名过？）")

    report["problems"] = problems
    report["warnings"] = warnings
    report["ok"] = not problems

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if not problems else 1

    print(f"机器人包对账（离线命令，无需后端）：{root}")
    print(f"  包 id：{report.get('package_id') or '(未知)'}")
    print(f"  契约：v2 {'在' if contract_path.is_file() else '缺'} / v3 {report.get('contract_v3')}")
    print(f"  合并契约：{report.get('merged_keys', 0)} 个键（训练侧实际消费的那份）")
    for item in warnings:
        print(f"  ~ {item}")
    if problems:
        print(f"✗ 不通过（{len(problems)} 项）：")
        for item in problems:
            print(f"  - {item}")
        return 1
    print("✓ 通过")
    return 0


def _cmd_verify_run(args: argparse.Namespace) -> int:
    """``verify run <run_id|目录>`` / ``--all``：Run 档案（B9 四件套）对账（离线命令）。

    判据取 :func:`backend.training.runs.verify_run` —— 重新规范化 ``inputs`` 求摘要与登记值
    逐字比对，并检查依赖锁与四件套文件是否落盘。**不在这里重算一遍**（否则两处判据会分叉）。
    """

    from backend.training import runs

    workspace = _workspace_root(args.workspace)
    checks: list[dict] = []
    if args.all:
        if not workspace.is_dir():
            raise SystemExit(f"verify 失败：workspace 不存在：{workspace}")
        targets = [
            child for child in sorted(workspace.iterdir())
            if child.is_dir() and (child / "run.json").is_file()
        ]
        if not targets:
            raise SystemExit(f"verify 失败：{workspace} 下没有含 run.json 的 Run")
    else:
        candidate = Path(args.target).expanduser()
        target = candidate if candidate.is_dir() else workspace / args.target
        if not (target / "run.json").is_file():
            raise SystemExit(f"verify 失败：不是 Run 目录（缺 run.json）：{target}")
        targets = [target]

    for target in targets:
        try:
            checks.append(runs.verify_run(target))
        except (TypeError, ValueError, KeyError) as exc:  # 坏档案如实报，不崩
            checks.append({"ok": False, "run_id": target.name, "problems": [f"档案不可读：{type(exc).__name__}: {exc}"]})

    failed = [item for item in checks if not item.get("ok")]
    if args.json:
        print(json.dumps({"workspace": str(workspace), "count": len(checks),
                          "ok_count": len(checks) - len(failed), "runs": checks}, ensure_ascii=False, indent=2))
        return 0 if not failed else 1

    print(f"训练 Run 对账（离线命令，无需后端）：{workspace}")
    for item in checks:
        mark = "✓" if item.get("ok") else "✗"
        print(f"  {mark} {item.get('run_id')}  seed/输入指纹 {str(item.get('inputs_digest') or '-')[:12]}…")
        for problem in item.get("problems") or []:
            print(f"      - {problem}")
    print(f"汇总：{len(checks)} 个 Run，{len(checks) - len(failed)} 通过，{len(failed)} 不通过")
    return 0 if not failed else 1


def _cmd_verify_artifacts(args: argparse.Namespace) -> int:
    """``verify artifacts``：策略产物出库索引对账（离线命令）。

    判据取 :func:`backend.policy_artifacts.verify_artifacts`（索引是否覆盖全部声明、
    每个 hash 是否仍与包内源文件一致、produced 条目自完整性）。
    """

    from backend.policy_artifacts import OUT_DIR, ROBOTS_DIR, verify_artifacts

    out_dir = Path(args.out_dir).expanduser() if args.out_dir else OUT_DIR
    robots_dir = Path(args.robots_dir).expanduser() if args.robots_dir else ROBOTS_DIR
    report = verify_artifacts(robots_dir=robots_dir, out_dir=out_dir)
    if args.json:
        print(json.dumps({**report, "out_dir": str(out_dir)}, ensure_ascii=False, indent=2))
        return 0 if report.get("ok") else 1

    print(f"策略产物对账（离线命令，无需后端）：{out_dir}")
    print(f"  机器人包根：{robots_dir}")
    print(f"  索引 {report.get('indexed')} 条 / 声明 {report.get('declared')} 条 / 实际检查 {report.get('checked')} 条")
    for problem in report.get("problems") or []:
        print(f"  - {problem}")
    if report.get("problems"):
        print(f"✗ 不通过（{len(report['problems'])} 项）")
        return 1
    print("✓ 通过（索引覆盖全部声明，hash 与包内一致）")
    return 0


def _cmd_verify_motions(args: argparse.Namespace) -> int:
    """``verify motions``：Motion 参考动作注册表对账（离线命令）。

    判据取 :func:`backend.motion_registry.audit`（注册表 vs 磁盘逐文件对账 + 字段校验）——
    与 ``tools/audit_motions.py``（CI 门禁）**同一实现**，不在这里重算一遍。
    """

    from backend.motion_registry import INDEX_PATH, audit, derive

    report = audit()
    if args.json:
        print(json.dumps({**report, "index": INDEX_PATH.as_posix()}, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    print(f"Motion 参考动作对账（离线命令，无需后端）：{INDEX_PATH}")
    print(f"  条目 {report['clips']} 条 / 数据文件 {report['files']} 份")
    for entry in derive()["motions"]:
        print(
            f"  {entry['robot']:<14}{entry['source']:<12}{entry['format']:<5}"
            f"fps={str(entry['fps']):<6}dof={entry['dof_layout']:<17}"
            f"许可={entry['license'].get('spdx') or '未取证'}"
        )
    if report["license_gaps"]:
        print(f"  许可未取证（如实登记，不阻断）：{len(report['license_gaps'])} 条")
    if report["problems"]:
        print(f"✗ 不通过（{len(report['problems'])} 项）：")
        for item in report["problems"]:
            print(f"  - {item}")
        return 1
    print("✓ 通过（注册表覆盖磁盘全部 motion，逐文件 sha256 一致）")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    """``export <kind>``：导出五类粒度之一（离线命令，无需后端）。

    逻辑全在 :mod:`backend.bundle_export`（不在这里另写一套哈希/拷贝）：五类共用一份
    ``manifest.json``（逐条 ``{path, sha256, bytes, role}``），导出物**自带证据**，
    ``verify bundle <目录>`` 能在另一台机器上重算。
    """

    from backend import bundle_export as bx

    kind = args.kind
    try:
        if kind == "morphology":
            if not args.robot:
                raise ValueError("morphology 需要 --robot <robot_id>")
            out = Path(args.out) if args.out else bx.default_out_dir(kind, args.robot)
            manifest = bx.export_morphology(args.robot, out)
        elif kind == "skill":
            if not args.recipe:
                raise ValueError("skill 需要 --recipe <recipe_id>")
            out = Path(args.out) if args.out else bx.default_out_dir(kind, args.recipe)
            manifest = bx.export_skill(args.recipe, out)
        elif kind == "scenario":
            if not args.scenario:
                raise ValueError("scenario 需要 --scenario <scenario.json>")
            out = Path(args.out) if args.out else bx.default_out_dir(kind, Path(args.scenario).stem)
            manifest = bx.export_scenario(args.scenario, out)
        elif kind == "policy":
            if not args.artifact:
                raise ValueError("policy 需要 --artifact <artifact_id>")
            out = Path(args.out) if args.out else bx.default_out_dir(kind, args.artifact)
            manifest = bx.export_policy(args.artifact, out, out_dir_index=Path(args.out_dir) if args.out_dir else None)
        else:
            if not args.pack:
                raise ValueError("bundle 需要 --pack <pack.json>")
            name = Path(args.pack).name.replace(".pack.json", "")
            out = Path(args.out) if args.out else bx.default_out_dir(kind, name)
            manifest = bx.export_bundle(
                args.pack, out, artifact_id=args.artifact, scenario_path=args.scenario, run_dir=args.run,
                replay=args.replay, replay_steps=args.replay_steps,
                quality=args.quality, quality_tier=args.tier, quality_min=args.quality_min,
                quality_steps=args.quality_steps, with_player=args.with_player,
            )
    except (ValueError, FileNotFoundError) as exc:
        raise SystemExit(f"export 失败：{exc}") from exc

    report = bx.verify_export(out)
    if args.json:
        print(json.dumps({"out_dir": str(out), "manifest": manifest, "verify": report}, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    print(f"导出 {kind}（离线命令，无需后端）：{out}")
    print(f"  条目 {report['entries']} 条 / 角色 {report['roles']}")
    reproduction = report.get("reproduction")
    if reproduction:
        print(f"  复现三档：R1回放={reproduction['R1_playback']} / R2评测={reproduction['R2_evaluation']} / "
              f"R3训练={reproduction['R3_training']}（差异 {reproduction['R3_gaps']} 条，其中影响数值 {reproduction['R3_warn']} 条）")
    player = report.get("player")
    if player:
        mark = "就绪" if player["ready"] else "有问题"
        print(f"  离线播放器：{mark}（{player['entry']}）→ {player['how_to_open']}")
        for problem in player["problems"]:
            print(f"    ! {problem}")
    quality = report.get("quality")
    if quality:
        score = "无" if quality["score"] is None else f"{quality['score']:.4f}"
        print(f"  质量门（{quality['tier']}）：{'达标' if quality['ok'] else '未达标'}（{score} / 下限 {quality['min_score']}）")
        for blocker in quality["blockers"]:
            print(f"    ! {blocker}")
    for note in manifest.get("notes") or []:
        print(f"  ~ {note}")
    for item in manifest.get("unresolved") or []:
        print(f"  ! 未解析 [{item.get('role')}] {item.get('reason')}")
    if not report["ok"]:
        print(f"✗ 导出物自校验未通过（{len(report['problems'])} 项）：")
        for problem in report["problems"]:
            print(f"  - {problem}")
        return 1
    print("✓ 导出物自校验通过（逐条 sha256 与 manifest 一致）")
    return 0


def _cmd_verify_bundle(args: argparse.Namespace) -> int:
    """``verify bundle <目录>``：校验一个导出物的 manifest 与内容（离线命令）。

    判据取 :func:`backend.bundle_export.verify_export`（与导出时同一实现）——
    所以"从别人那儿拷来的 Bundle"同样能验：逐条重算 sha256、必需角色齐备、无幽灵文件。
    """

    from backend.bundle_export import verify_export

    report = verify_export(args.directory)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    print(f"导出物对账（离线命令，无需后端）：{args.directory}")
    print(f"  类型 {report.get('kind')} / 条目 {report.get('entries')} / 角色 {report.get('roles')}")
    reproduction = report.get("reproduction")
    if reproduction:
        print(f"  复现三档：R1回放={reproduction['R1_playback']} / R2评测={reproduction['R2_evaluation']} / "
              f"R3训练={reproduction['R3_training']}（差异 {reproduction['R3_gaps']} 条）")
    for item in report.get("unresolved") or []:
        print(f"  ! Bundle 未包含被引用物 [{item.get('role')}] {item.get('reason')}")
    if not report["ok"]:
        print(f"✗ 不通过（{len(report['problems'])} 项）：")
        for problem in report["problems"]:
            print(f"  - {problem}")
        return 1
    print("✓ 通过")
    return 0


def _deploy_workspace(args: argparse.Namespace) -> None:
    """``--workspace`` 是"**这个进程**的 workspace"：与 onboard 同约定，同步进环境变量，
    让下游（backend.robot_packages 的包解析）看到同一处——否则"包在 A、解析按 B 判"。"""

    if getattr(args, "workspace", None):
        os.environ["LEGGED_STUDIO_WORKSPACE"] = str(Path(args.workspace).expanduser())


def _cmd_deploy_gate(args: argparse.Namespace) -> int:
    """``deploy gate <robot_id>``：部署契约校验（离线命令，无需后端）。

    与 ``GET /api/deploy/gate/{robot_id}``（backend.deploy_api）**同一组成**：
    ``backend.robot_presets.get_robot_preset`` 解析包根 → ``backend.deploy_pack._load_json``
    读包内 contract_v3.json / contract.json → ``backend.export_gate.compare_contracts``
    裁决（DENYLIST fail-closed，硬约束字段不一致即 deny）。判据只在 backend 有一份，
    这里不另写字段比较。存在 blocker → 退出码 1（可直接当上机前门禁）。
    """

    from backend.deploy_pack import ROOT, _load_json
    from backend.export_gate import compare_contracts
    from backend.robot_presets import get_robot_preset

    _deploy_workspace(args)
    preset = get_robot_preset(args.robot_id)
    root_value = str(((preset or {}).get("robot_package") or {}).get("package_root", ""))
    root = Path(root_value) if root_value else ROOT / "assets" / "robots" / args.robot_id
    if not root.is_dir():
        raise SystemExit(f"deploy 失败：找不到机器人包 {args.robot_id!r}（按过 {root}）")

    v3 = _load_json(root / "contract_v3.json")
    v2 = _load_json(root / "contract.json")
    missing = [name for name, value in (("contract_v3.json", v3), ("contract.json", v2)) if not value]
    if missing:
        raise SystemExit(f"deploy 失败：包内契约不全（缺 {' / '.join(missing)}）：{root}")

    report = compare_contracts(v3, v2)
    payload = {**report, "robot_id": args.robot_id, "package_root": str(root)}

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    print(f"部署契约校验（离线命令，无需后端）：{root}")
    print(f"  机器人：{args.robot_id}（包内 contract_v3 vs contract.json，硬约束字段 fail-closed）")
    for item in report.get("warnings") or []:
        print(f"  ~ {item}")
    blockers = report.get("blockers") or []
    if blockers:
        print(f"✗ 不通过（{len(blockers)} 项 blocker，处置 {report.get('disposition')}）：")
        for item in blockers:
            print(f"  - {item}")
        print("（先回训练区让包内契约一致，再重新导出/打包——不一致即视为没准备好上机）")
        return 1
    print(f"✓ 通过（处置 {report.get('disposition')}，包内契约硬约束字段一致）")
    return 0


def _cmd_deploy_package(args: argparse.Namespace) -> int:
    """``deploy package <robot_id>``：生成部署包 zip（离线命令，无需后端）。

    打包逻辑全在 :func:`backend.deploy_pack.generate_deploy_package`（与 Web 的
    ``POST /api/deploy/package`` 同一实现，这里只换落点与输出格式）：四件套
    （部署契约 / FSM 安全状态机 / 动作解码层 / 人工确认清单）+ 平台适配层。
    安全线不变：只生成物料，不直接发电机命令——"一键生成 ≠ 一键上机"。
    """

    from backend.deploy_pack import generate_deploy_package

    _deploy_workspace(args)
    try:
        report = generate_deploy_package(
            args.robot_id,
            degraded=args.degraded,
            target_platform=args.platform,
            bench_mode=args.bench,
            out_dir=Path(args.out).expanduser() if args.out else None,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"deploy 失败：{exc}") from exc

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"部署包已生成（离线命令，无需后端）：{report['path']}")
    print(f"  机器人：{report['robot_id']} / 目标平台：{report['target_platform']}"
          + (" / D2 台架模式" if report.get("bench_mode") else "")
          + (" / 劣化参数档（力矩 ×0.8）" if args.degraded else ""))
    print(f"  内含 {len(report['files'])} 个文件：{'、'.join(report['files'])}")
    print("  提醒：一键生成 ≠ 一键上机——按包内《人工确认清单》逐项确认后再上机。")
    return 0


# --------------------------------------------------------------------------------------
# 训练在线命令（I1 第二批）：需后端在跑，走 HTTP —— 与 Web 工作台同一 API 契约
# --------------------------------------------------------------------------------------
_DEFAULT_TRAIN_BASE = "http://127.0.0.1:8765"

#: 连接失败时的中文可操作提示（占位符 base/reason 由 _request 填充）
_TRAIN_UNREACHABLE_HINT = (
    "无法连接后端 {base}：{reason}\n"
    "后端未启动？可先启动后端再重试：npm start 或 uvicorn backend.api_complete:app"
    f"（默认 {_DEFAULT_TRAIN_BASE}）"
)


def _train_base(args: argparse.Namespace) -> str:
    """后端地址：子命令 ``--base`` > 全局 ``--base-url`` > 默认 http://127.0.0.1:8765。"""

    return str(getattr(args, "base", None) or args.base_url or _DEFAULT_TRAIN_BASE)


def _train_request(
    args: argparse.Namespace, method: str, route: str, payload: object | None = None, *, headers: dict[str, str] | None = None
) -> object:
    """训练命令专用请求：断连给中文可操作提示、HTTP 错误提取可读原因，**绝不静默编造结果**。"""

    return _request(
        _train_base(args), method, route, payload,
        headers=headers, unreachable_hint=_TRAIN_UNREACHABLE_HINT, friendly_http=True,
    )


def _iteration_text(record: dict) -> str:
    """把 current_iteration/max_iterations 拼成「5 / 5」；缺失侧如实留 -。"""

    current = record.get("current_iteration")
    total = record.get("max_iterations")
    if current is None:
        return "-"
    if total is None:
        return str(current)
    return f"{current} / {total}"


def _cmd_train_create(args: argparse.Namespace) -> int:
    """``train create``：按机器人预设创建训练任务（在线命令，需后端在跑）。

    契约取自 :func:`backend.robot_presets.get_robot_preset` 的 ``contract`` 字段
    （与 Web 训练页同一真值来源）；``--contract <path>`` 保留旧顶层
    ``train <file>`` 的显式契约用法，请求字段不变。
    """

    if args.contract:
        contract = _json_file(args.contract)
        num_envs = args.envs if args.envs is not None else 4096    # 旧 train 的默认规模
        max_iterations = args.iters if args.iters is not None else 1000
    else:
        from backend.robot_presets import get_robot_preset, list_robot_presets

        preset = get_robot_preset(args.robot)
        if preset is None:
            available = ", ".join(sorted(str(item.get("robot_id")) for item in list_robot_presets()))
            raise SystemExit(f"未知机器人预设 {args.robot}（可用：{available or '无'}）")
        contract = preset["contract"]
        num_envs = args.envs if args.envs is not None else 16      # 快速起步规模，见 --help 用法
        max_iterations = args.iters if args.iters is not None else 5

    body = {
        "contract": contract,
        "algorithm": args.algorithm,
        "num_envs": num_envs,
        "max_iterations": max_iterations,
        "task_name": args.task_name,
        "profile_id": args.profile,
        "device": args.device,
        "seed": args.seed,
        "smoke": args.smoke,
    }
    if args.contract:
        body["backend"] = args.backend                             # 旧用法的字段原样保留
    headers = {"Idempotency-Key": args.key} if args.key else None

    result = _train_request(args, "POST", "/api/training/create", body, headers=headers)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"训练任务已创建（在线命令）：{result.get('task_id')}")
    if result.get("idempotent_replay"):
        print("幂等重放：同 Idempotency-Key 返回既有任务，未重复启动")
    gate = result.get("smoke_gate")
    if isinstance(gate, dict):
        required = bool(gate.get("required"))
        ok = bool(gate.get("ok"))
        print(f"冒烟前置门：{'通过' if ok else '未通过'}（required={required}）")
    return 0


def _cmd_train_status(args: argparse.Namespace) -> int:
    """``train status``：输出状态/迭代/奖励（解包**内层** status 词表，在线命令，需后端）。"""

    result = _train_request(args, "GET", f"/api/training/{args.task_id}/status")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    status = result.get("status") if isinstance(result, dict) else None
    if not isinstance(status, dict):
        # 内层词表缺失/结构漂移：如实回显原始响应，不猜测字段
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"训练任务 {status.get('task_id', args.task_id)}（在线命令）")
    state = str(status.get("status", "-"))
    if state == "train_completed":
        state += "（已完成）"
    print(f"状态：{state}")
    print(f"迭代：{_iteration_text(status)}")
    reward = status.get("reward")
    print(f"奖励：{'-' if reward is None else reward}")
    error = status.get("error")
    if error:
        print(f"错误：{error}")
    return 0


def _cmd_train_stop(args: argparse.Namespace) -> int:
    """``train stop``：请求停止训练任务（在线命令，需后端）。"""

    result = _train_request(args, "POST", f"/api/training/{args.task_id}/stop")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"已请求停止训练任务：{args.task_id}")
    message = result.get("message") if isinstance(result, dict) else None
    if message:
        print(message)
    return 0


def _cmd_train_list(args: argparse.Namespace) -> int:
    """``train list``：列出后端全部训练任务（在线命令，需后端）。"""

    result = _train_request(args, "GET", "/api/training/list")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    tasks = result.get("tasks") if isinstance(result, dict) else None
    if not isinstance(tasks, list):
        # 响应结构漂移：如实回显，不编造表格
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"训练任务清单（在线命令，需后端）：{_train_base(args)}")
    if not tasks:
        print("（后端当前没有任何训练任务）")
    print(f"{'task_id':<40}{'状态':<18}{'迭代':<12}{'奖励':>10}")
    for task in tasks:
        if not isinstance(task, dict):
            continue
        reward = task.get("reward")
        print(
            f"{str(task.get('task_id', '-')):<40}{str(task.get('status', '-')):<18}"
            f"{_iteration_text(task):<12}{'-' if reward is None else str(reward):>10}"
        )
    print(f"汇总：{len(tasks)} 个任务")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Legged Studio CLI (shared Web/API contract)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765", help="running control-plane URL")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（离线 pack/run/artifact 的 list 与在线 train 各子命令均生效）")
    parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "离线模式：本次不连后端。离线命令（pack / run / artifact / onboard / verify / export / deploy）"
            "照常运行；需后端的命令会直接拒绝并返回非 0（绝不静默跳过）"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("algorithms", help="list registered algorithms")
    sub.add_parser("hardware", help="show CUDA and native MJLab capabilities")
    model = sub.add_parser("validate-model", help="validate a URDF/MJCF model")
    model.add_argument("path")
    model.add_argument("--format", choices=["auto", "urdf", "mjcf"], default="auto")
    contract = sub.add_parser("validate-contract", help="validate a Robot Contract JSON")
    contract.add_argument("path")
    scenario = sub.add_parser("validate-scenario", help="validate a Scenario Contract JSON")
    scenario.add_argument("path")
    sub.add_parser("maps", help="list simulation and navigation maps")

    simulate = sub.add_parser("simulate", help="create and optionally step a simulation session")
    simulate.add_argument("--robot", default="unitree_go2")
    simulate.add_argument("--map", default="flat", dest="map_id")
    simulate.add_argument("--mode", choices=["basic", "navigation"], default="basic")
    simulate.add_argument("--steps", type=int, default=0)
    simulate.add_argument("--vx", type=float, default=0.0)
    simulate.add_argument("--vy", type=float, default=0.0)
    simulate.add_argument("--wz", type=float, default=0.0)

    # ---- 训练在线命令（I1 第二批）：需后端在跑，与 Web 工作台同一 HTTP 契约 ----
    # 原顶层 `train <contract.json>`（10 命令时期的叶子命令）并入 `train create
    # --contract <path>`，请求字段不变；新预设用法 --robot/--profile 的契约来自
    # backend.robot_presets（与 Web 训练页同一真值来源）。
    train = sub.add_parser(
        "train",
        help="训练任务 create/status/stop/list（在线命令，需后端在跑）",
        description=f"训练任务 create/status/stop/list（在线命令，需后端在跑，默认 {_DEFAULT_TRAIN_BASE}）。",
    )
    train_sub = train.add_subparsers(dest="train_command", required=True)

    train_create = train_sub.add_parser(
        "create",
        help="创建训练任务（在线命令，需后端）",
        description=(
            "创建训练任务（在线命令，需后端在跑）。契约取自 backend.robot_presets 预设；"
            "--contract 保留旧 train <file> 的显式契约用法。示例：train create --robot "
            "unitree_go2 --profile go2-velocity-flat --envs 16 --iters 5 --seed 7 --smoke"
        ),
    )
    train_create.add_argument("--robot", default="unitree_go2", help="机器人预设 id（默认 unitree_go2；与 --contract 二选一）")
    train_create.add_argument("--profile", default=None, help="训练档案 profile_id（如 go2-velocity-flat）")
    train_create.add_argument("--contract", default=None, help="显式 Robot Contract JSON 路径（旧 train <file> 用法；给出时忽略 --robot）")
    train_create.add_argument("--algorithm", default="PPO")
    train_create.add_argument("--envs", type=int, default=None, help="并行环境数（预设用法默认 16；--contract 用法默认 4096）")
    train_create.add_argument("--iters", type=int, default=None, help="最大迭代数（预设用法默认 5；--contract 用法默认 1000）")
    train_create.add_argument("--seed", type=int, default=7, help="随机种子（默认 7）")
    train_create.add_argument("--smoke", action="store_true", default=False, help="冒烟档：未过冒烟门的长训会被后端 409 拒")
    train_create.add_argument("--task-name", default="forward_walk", help="任务名（默认 forward_walk）")
    train_create.add_argument("--device", default="auto", help="auto / cpu / cuda（默认 auto）")
    train_create.add_argument("--backend", choices=["native_mjlab"], default="native_mjlab", help="训练后端（仅 --contract 用法发送）")
    train_create.add_argument("--key", default=None, help="Idempotency-Key 幂等键（可选，重复提交返回既有任务）")
    train_create.add_argument("--base", default=None, help=f"后端地址（默认 {_DEFAULT_TRAIN_BASE}）")
    train_create.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出完整响应（含 smoke_gate 字段）")

    train_status = train_sub.add_parser(
        "status",
        help="查询任务状态/迭代/奖励（在线命令，需后端）",
        description="查询训练任务状态/迭代/奖励（在线命令，需后端在跑）。--json 输出完整响应（内层 status 才是词表）。",
    )
    train_status.add_argument("task_id", help="训练任务 id")
    train_status.add_argument("--base", default=None, help=f"后端地址（默认 {_DEFAULT_TRAIN_BASE}）")
    train_status.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出完整响应")

    train_stop = train_sub.add_parser(
        "stop",
        help="请求停止训练任务（在线命令，需后端）",
        description="请求停止训练任务（在线命令，需后端在跑）。",
    )
    train_stop.add_argument("task_id", help="训练任务 id")
    train_stop.add_argument("--base", default=None, help=f"后端地址（默认 {_DEFAULT_TRAIN_BASE}）")
    train_stop.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出完整响应")

    train_list = train_sub.add_parser(
        "list",
        help="列出后端全部训练任务（在线命令，需后端）",
        description="列出后端全部训练任务（在线命令，需后端在跑）。",
    )
    train_list.add_argument("--base", default=None, help=f"后端地址（默认 {_DEFAULT_TRAIN_BASE}）")
    train_list.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出完整响应")

    evaluate = sub.add_parser("evaluate", help="evaluate a completed task")
    evaluate.add_argument("task_id")
    evaluate.add_argument("--episodes", type=int, default=5)

    navigation = sub.add_parser("navigation", help="run a waypoint replay")
    navigation.add_argument("task_id")
    navigation.add_argument("--map", default="warehouse", dest="map_id")
    navigation.add_argument("--mode", choices=["auto", "manual"], default="auto", dest="control_mode")
    navigation.add_argument("--waypoints", default="0,0;2,0;4,0", help="x,y; x,y; ...")
    navigation.add_argument("--obstacles", default="", help="cx,cy,hw,hh; cx,cy,hw,hh; ... (optional map obstacles)")
    navigation.add_argument("--planner", default="astar", choices=["astar", "dijkstra"], dest="algorithm")
    navigation.add_argument("--use-planner", action="store_true", default=False, dest="use_planner")
    navigation.add_argument("--no-avoidance", action="store_true", default=False, dest="no_avoidance")

    # ---- 离线命令（I1 第一批）：不连控制面，直接读仓库数据，复用 backend/ 同一实现 ----
    # --json 在叶子子命令上再声明一次（default=SUPPRESS，不覆盖全局 --json 的值），
    # 因此 `--json pack list` 与 `pack list --json` 两种写法都可用。
    pack = sub.add_parser("pack", help="Capability Pack 目录（离线命令，无需后端）")
    pack_sub = pack.add_subparsers(dest="pack_command", required=True)
    pack_list = pack_sub.add_parser(
        "list",
        help="列出 packs/ 下全部 Pack 及校验状态（离线命令，无需后端）",
        description="列出 packs/ 下全部 Pack 及校验状态（离线命令，无需后端）。",
    )
    pack_list.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出")

    run = sub.add_parser("run", help="训练 Run 档案（离线命令，无需后端）")
    run_sub = run.add_subparsers(dest="run_command", required=True)
    run_list = run_sub.add_parser(
        "list",
        help="列出 workspace/ 下含 run.json 的训练任务（离线命令，无需后端）",
        description="列出 workspace/ 下含 run.json 的训练任务（离线命令，无需后端）。",
    )
    run_list.add_argument("--workspace", default=None, help="workspace 根目录（默认：LEGGED_STUDIO_WORKSPACE 环境变量或仓库 workspace/）")
    run_list.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出")

    artifact = sub.add_parser("artifact", help="策略产物出库索引（离线命令，无需后端）")
    artifact_sub = artifact.add_subparsers(dest="artifact_command", required=True)
    artifact_list = artifact_sub.add_parser(
        "list",
        help="列出 policies/ 出库索引全部产物（离线命令，无需后端）",
        description="列出 policies/ 出库索引全部产物（离线命令，无需后端）。",
    )
    artifact_list.add_argument("--out-dir", default=None, help="出库目录（默认：仓库 policies/）")
    artifact_list.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出")

    # ---- I1 剩余：onboard（新机器人导入）/ verify（包对账）—— 同样是离线命令 ----
    onboard = sub.add_parser(
        "onboard",
        help="把机器人目录导入为机器人包（离线命令，无需后端；默认预演，--write 落盘）",
        description=(
            "把机器人目录导入为机器人包（离线命令，无需后端）。与 Web 的 POST /api/models/import "
            "共用同一份编排：校验 → 生成 contract.json / robot_package.json / contract_v3.json "
            "→ 落 workspace/packages/<package_id>/ → 登记索引。**默认预演**（不写任何文件），"
            "--write 才落盘；校验不过一个字节都不写。"
        ),
    )
    onboard.add_argument("directory", help="机器人目录（含 URDF/MJCF 模型与随附 mesh）")
    onboard.add_argument("--model", default=None, help="指定模型文件（目录内有多个候选时必填；相对目录的路径）")
    onboard.add_argument("--format", choices=["auto", "urdf", "mjcf"], default="auto", help="模型格式（默认按后缀推断）")
    onboard.add_argument("--workspace", default=None, help="workspace 根（默认：LEGGED_STUDIO_WORKSPACE 或仓库 workspace/）")
    onboard.add_argument("--write", action="store_true", default=False, help="真正落盘并登记（默认只预演，不写任何文件）")
    onboard.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出完整报告")

    verify = sub.add_parser("verify", help="对账门禁（离线命令，无需后端；不通过退出码 1）")
    verify_sub = verify.add_subparsers(dest="verify_command", required=True)
    verify_package = verify_sub.add_parser(
        "package",
        help="对一个机器人包做全面对账（离线命令，无需后端）",
        description=(
            "对一个机器人包做全面对账（离线命令，无需后端）：v2 契约（模型哈希/驱动关节/维度）、"
            "v3 契约（角色语义）、训练侧实际消费的合并契约、清单与模型文件是否对得上。"
            "任一不过 → 退出码 1。"
        ),
    )
    verify_package.add_argument("directory", help="机器人包目录（含 contract.json / robot_package.json）")
    verify_package.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出")

    verify_run = verify_sub.add_parser(
        "run",
        help="对一个（或全部）训练 Run 的档案做对账（离线命令，无需后端）",
        description=(
            "对一个（或全部）训练 Run 的档案做对账（离线命令，无需后端）：重新规范化 inputs "
            "求摘要与登记值逐字比对 + 依赖锁与四件套文件是否落盘。任一不过 → 退出码 1。"
            "示例：verify run <run_id>｜verify run <目录>｜verify run --all"
        ),
    )
    verify_run.add_argument("target", nargs="?", default=None, help="run_id 或 Run 目录（--all 时省略）")
    verify_run.add_argument("--all", action="store_true", default=False, help="对账 workspace 下全部 Run")
    verify_run.add_argument("--workspace", default=None, help="workspace 根（默认：LEGGED_STUDIO_WORKSPACE 或仓库 workspace/）")
    verify_run.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出")

    verify_artifacts = verify_sub.add_parser(
        "artifacts",
        help="对策略产物出库索引做对账（离线命令，无需后端）",
        description=(
            "对策略产物出库索引做对账（离线命令，无需后端）：索引是否覆盖全部声明、每个 hash "
            "是否仍与包内源文件一致、produced 条目自完整性。不通过 → 退出码 1。"
        ),
    )
    verify_artifacts.add_argument("--out-dir", default=None, help="出库目录（默认：仓库 policies/）")
    verify_artifacts.add_argument("--robots-dir", default=None, help="机器人包根（默认：仓库 assets/robots；对账要两侧成对才说得通）")
    verify_artifacts.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出")

    verify_motions = verify_sub.add_parser(
        "motions",
        help="对 Motion 参考动作注册表做对账（离线命令，无需后端）",
        description=(
            "对 Motion 注册表做对账（离线命令，无需后端）：注册表是否覆盖磁盘上全部 motion 数据、"
            "逐文件 sha256 是否一致、每条是否具备 fps/dof 布局/血缘/许可（许可未取证须显式登记）。"
            "不通过 → 退出码 1。"
        ),
    )
    verify_motions.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出")

    verify_bundle = verify_sub.add_parser(
        "bundle",
        help="校验一个导出物（Bundle / 形态包 / 技能包 / 场景包 / 策略包）的 manifest 与内容",
        description=(
            "校验一个导出物（离线命令，无需后端）：manifest schema、逐条文件 sha256 与字节数、"
            "该类导出必需的角色是否齐备、有没有 manifest 未登记的幽灵文件。"
            "**对拷来的导出物同样有效**（判据只看磁盘与 manifest）。不通过 → 退出码 1。"
        ),
    )
    verify_bundle.add_argument("directory", help="导出目录（含 manifest.json）")
    verify_bundle.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出")

    # B12：五类粒度导出（Morphology / Skill / Scenario / Policy / Bundle）
    from backend.bundle_export import EXPORT_KINDS  # 单一真值：类目表只在 backend 里定义一次

    export = sub.add_parser(
        "export",
        help="导出五类粒度之一（离线命令，无需后端；导出物自带 manifest + 逐条 sha256）",
        description=(
            "导出五类粒度之一（离线命令，无需后端）：morphology（形态+契约）/ skill（自包含技能包）/ "
            "scenario（场景契约）/ policy（出库产物）/ bundle（Pack 引用 + **被引用物离线副本** + 哈希）。"
            "导出物落 manifest.json（逐条 path/sha256/bytes/role），并当场自校验；"
            "Bundle 里缺被引用物时如实记进 unresolved（不假装完整）。"
        ),
    )
    export.add_argument("kind", choices=list(EXPORT_KINDS), help="导出的粒度")
    export.add_argument("--robot", default=None, help="morphology：机器人 ID")
    export.add_argument("--recipe", default=None, help="skill：技能 recipe ID（见 registry/skills/index.json）")
    export.add_argument("--scenario", default=None, help="scenario：场景契约 JSON 路径")
    export.add_argument("--artifact", default=None, help="policy：出库产物 ID；bundle：覆盖 Pack 的 policy_ref")
    export.add_argument("--pack", default=None, help="bundle：Pack JSON 路径（如 packs/zex-w.pack.json）")
    export.add_argument("--out", default=None, help="导出目录（默认 <workspace>/exports/<kind>-<name>）")
    export.add_argument("--run", default=None, help="bundle：附上复现报告（Run 目录或 run_id；含 R1 回放就绪 / R3 环境对账）")
    export.add_argument("--replay", action="store_true",
                        help="bundle：在**导出物自身内**无头跑两遍做 R2（需适配器 venv；跑不了如实记 blocked）")
    export.add_argument("--replay-steps", type=int, default=60, help="--replay 的控制步数（默认 60）")
    export.add_argument("--quality", action="store_true",
                        help="bundle：在**导出物自身内**跑八指标评测并把报告放进包里（quality.json）")
    export.add_argument("--tier", default="single", choices=["single", "multi", "level", "stress"],
                        help="--quality 的评测档位（默认 single）")
    export.add_argument("--quality-min", type=float, default=0.5, help="质量分下限（默认 0.5）")
    export.add_argument("--quality-steps", type=int, default=200, help="--quality 的控制步数")
    export.add_argument("--with-player", action="store_true",
                        help="bundle：打入**离线播放器**（静态 sim2sim 包：无本仓库机器也能打开试玩）")
    export.add_argument("--out-dir", default=None, help="出库索引目录（policy 用，默认仓库 policies/）")
    export.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出")

    # I1 收尾：deploy（部署物料 = 契约校验 gate + 部署包打包 package）—— 同样是离线命令，
    # 判据/打包一律委托 backend 既有实现（deploy_api 同一组成），CLI 只做参数与输出。
    from backend.deploy_pack import PLATFORM_LABELS  # 单一真值：平台表只在 backend 里定义一次

    deploy = sub.add_parser(
        "deploy",
        help="部署物料 gate/package（离线命令，无需后端；校验不过退出码 1）",
        description=(
            "部署物料两条离线命令：gate（部署契约校验：包内 contract_v3 vs contract.json，"
            "DENYLIST fail-closed）与 package（部署包 zip：契约/FSM/解码层/人工确认清单 + 平台适配层）。"
            "判据与打包全部委托 backend 既有实现（与 Web 的 /api/deploy/* 同一实现），"
            "只生成物料不发电机命令——一键生成 ≠ 一键上机。"
        ),
    )
    deploy_sub = deploy.add_subparsers(dest="deploy_command", required=True)

    deploy_gate = deploy_sub.add_parser(
        "gate",
        help="部署契约校验：包内契约 v3 vs v2 一致性（离线命令，无需后端）",
        description=(
            "部署契约校验（离线命令，无需后端）：与 GET /api/deploy/gate/{robot_id} 同一组成——"
            "解析机器人包根，读包内 contract_v3.json 与 contract.json，交给 "
            "backend.export_gate.compare_contracts 裁决（硬约束字段不一致即 deny）。"
            "存在 blocker → 退出码 1，可当上机前门禁。"
        ),
    )
    deploy_gate.add_argument("robot_id", help="机器人 ID（包根解析顺序：workspace 包副本 > 内置 assets/robots/<id>）")
    deploy_gate.add_argument("--workspace", default=None, help="workspace 根（默认：LEGGED_STUDIO_WORKSPACE 环境变量或仓库 workspace/）")
    deploy_gate.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出")

    deploy_package = deploy_sub.add_parser(
        "package",
        help="生成部署包 zip：四件套 + 平台适配层（离线命令，无需后端）",
        description=(
            "生成部署包 zip（离线命令，无需后端）：与 POST /api/deploy/package 同一实现——"
            "deployment-contract.yaml / fsm_safety_template.py / action_decoder_template.py / "
            "人工确认清单.md + platform_adapter.py。只生成物料，不直接发电机命令"
            "（一键生成 ≠ 一键上机）。"
        ),
    )
    deploy_package.add_argument("robot_id", help="机器人 ID（包根解析顺序：workspace 包副本 > 内置 assets/robots/<id>）")
    deploy_package.add_argument("--platform", default="unitree_sdk2", choices=list(PLATFORM_LABELS),
                                help="目标平台适配层模板（默认 unitree_sdk2）")
    deploy_package.add_argument("--degraded", action="store_true", default=False,
                                help="劣化参数档：力矩 ×0.8（先跑稳再上真机）")
    deploy_package.add_argument("--bench", action="store_true", default=False,
                                help="D2 台架模式：额外生成 d2_bench_test.py（空载正弦扫频）")
    deploy_package.add_argument("--out", default=None, help="输出目录（默认 <仓库>/workspace/deploy）")
    deploy_package.add_argument("--workspace", default=None, help="workspace 根（默认：LEGGED_STUDIO_WORKSPACE 环境变量或仓库 workspace/）")
    deploy_package.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # 离线命令：不走 HTTP，直接复用 backend/ 实现读仓库数据，处理完即返回
    if args.command == "pack":
        return _cmd_pack_list(args.json)
    if args.command == "run":
        return _cmd_run_list(args.json, args.workspace)
    if args.command == "artifact":
        return _cmd_artifact_list(args.json, args.out_dir)
    if args.command == "onboard":
        return _cmd_onboard(args)
    if args.command == "verify":
        if args.verify_command == "package":
            return _cmd_verify_package(args)
        if args.verify_command == "run":
            return _cmd_verify_run(args)
        if args.verify_command == "motions":
            return _cmd_verify_motions(args)
        if args.verify_command == "bundle":
            return _cmd_verify_bundle(args)
        return _cmd_verify_artifacts(args)
    if args.command == "export":
        return _cmd_export(args)
    if args.command == "deploy":
        if args.deploy_command == "gate":
            return _cmd_deploy_gate(args)
        return _cmd_deploy_package(args)

    # `--offline` 的语义：**这次不碰后端**。离线命令在上面已经跑完并返回；走到这里说明
    # 命中的是需后端的命令，于是如实拒绝 —— 而不是"离线模式下悄悄不发请求"：
    # 后者会让调用方以为命令成功了，实际上什么都没做（CI 里最坏的一种"绿"）。
    if args.offline:
        raise SystemExit(
            f"`--offline` 模式下不执行需后端的命令 {args.command!r}（它要走 HTTP 访问控制面）。\n"
            "离线命令（pack / run / artifact / onboard / verify / export / deploy）不受影响；"
            "如需在线命令，请去掉 --offline。"
        )

    # 训练在线命令（I1 第二批）：需后端在跑，走 HTTP（与 Web 工作台同一契约）
    if args.command == "train":
        if args.train_command == "create":
            return _cmd_train_create(args)
        if args.train_command == "status":
            return _cmd_train_status(args)
        if args.train_command == "stop":
            return _cmd_train_stop(args)
        return _cmd_train_list(args)

    base = args.base_url
    if args.command == "algorithms":
        result = _request(base, "GET", "/api/training/options")
    elif args.command == "hardware":
        result = _request(base, "GET", "/api/training/hardware")
    elif args.command == "validate-model":
        result = _request(base, "POST", "/api/models/validate", {"path": args.path, "format": args.format})
    elif args.command == "validate-contract":
        result = _request(base, "POST", "/api/contracts/validate", _json_file(args.path))
    elif args.command == "validate-scenario":
        result = _request(base, "POST", "/api/scenarios/validate", _json_file(args.path))
    elif args.command == "maps":
        result = _request(base, "GET", "/api/simulation/maps")
    elif args.command == "simulate":
        result = _request(base, "POST", "/api/simulation/sessions", {"robot_id": args.robot, "map_id": args.map_id, "mode": args.mode})
        for _ in range(max(0, args.steps)):
            session_id = result["session_id"]
            result = _request(base, "POST", f"/api/simulation/sessions/{session_id}/step", {"command": {"vx": args.vx, "vy": args.vy, "wz": args.wz}})
    elif args.command == "evaluate":
        result = _request(base, "POST", "/api/evaluation/run", {"task_id": args.task_id, "episodes": args.episodes})
    else:
        waypoints = [[float(value) for value in point.split(",")] for point in args.waypoints.split(";")]
        obstacles = []
        for item in args.obstacles.split(";") if args.obstacles else []:
            if item.strip():
                obstacles.append([float(value) for value in item.split(",")])
        result = _request(base, "POST", "/api/navigation/run", {
            "task_id": args.task_id, "map_id": args.map_id, "control_mode": args.control_mode,
            "waypoints": waypoints, "obstacles": obstacles, "algorithm": args.algorithm,
            "use_planner": args.use_planner, "use_avoidance": not args.no_avoidance,
        })
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
