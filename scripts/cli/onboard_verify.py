"""CLI 离线命令：onboard 与 verify 族（自 scripts/legged_studio_cli.py 拆分，2026-10-12；函数体零改动）。

包导入编排 / 包对账 / Run 档案对账 / 产物索引对账 / motions 台账 / bundle 校验。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from scripts.cli.workspace import _workspace_root



def _cmd_onboard(args: argparse.Namespace) -> int:
    """``onboard <目录>``：把一个机器人目录导入为机器人包（离线命令，无需后端）。

    与 Web 的 ``POST /api/models/import`` **共用同一份编排**（``backend.package_import``）：
    校验模型 → 生成三件 JSON（``contract.json`` / ``robot_package.json`` /
    ``contract_legacy_v2.json``）→ 落 ``workspace/packages/<package_id>/`` → 登记索引。
    两条入口的 ``package_id`` 由同一份内容摘要算出，所以"同一份资产"不会变成两个包。

    **默认预演**（与 ``tools/skill_pack.py import`` 同惯例：导入是写操作，先看清再落盘），
    ``--write`` 才真写；校验不过**一个字节都不写**（fail-closed）。
    """

    from backend.package_import import onboard_package

    workspace = _workspace_root(args.workspace)
    if args.workspace:
        # `--workspace` 是"**这个进程**的 workspace"：同步到环境变量，让下游（模型服务的
        # workspace 解析与模型路径守卫）看到同一处。只在 CLI 里传 packages_root 会造成
        # "包落在 A、路径守卫按 B 判"——两处不一致时该报的错会变成莫名其妙的越界拒绝。
        os.environ["LEGGED_STUDIO_WORKSPACE"] = str(workspace)
    packages_root = workspace / "packages"
    try:
        report = onboard_package(
            args.directory,
            write=args.write,
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
    print("  三件 JSON：contract.json / robot_package.json / contract_legacy_v2.json")
    note = (report.get("contract") or {}).get("note")
    if note:
        print(f"  contract_truth：{note}")
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
      * 契约真值 → ``contracts.contract_loader.load_contract``（角色语义
        ``RoleResolver.validate``）；
      * 「训练实际消费的那份合并契约」→ ``load_training_contract``（v3 覆盖 v2）；
      * 清单与模型文件对得上（``robot_package.json`` 的 ``model.path`` / ``contract_path``）。

    任一不过 → 退出码 1（可直接当 CI / 脚本门禁）。
    """

    from contracts.contract_loader import ContractLoadError, load_contract, load_training_contract
    from contracts.validator import validate_contract_file

    root = Path(args.directory).expanduser()
    problems: list[str] = []
    warnings: list[str] = []
    report: dict[str, object] = {"directory": str(root), "package_id": None}

    if not root.is_dir():
        raise SystemExit(f"verify 失败：目录不存在：{root}")

    manifest_path = root / "robot_package.json"
    contract_path = root / "contract_legacy_v2.json"
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
        problems.append("缺 contract_legacy_v2.json（v2 契约）")
    else:
        try:
            result = validate_contract_file(str(contract_path))
            problems.extend(f"契约 v2：{item.message}" for item in result.errors)
            warnings.extend(f"契约 v2：{item.message}" for item in result.warnings)
        except Exception as exc:  # 解析失败也要如实报，而不是崩掉
            problems.append(f"契约 v2 校验异常：{type(exc).__name__}: {exc}")

    try:
        v3 = load_contract(root)
        report["contract"] = "present" if v3 is not None else "missing"
        if v3 is None:
            warnings.append("缺 contract.json（语义层：构型/角色/执行器按 v3 取，缺它训练侧只能退回 v2）")
    except Exception as exc:
        problems.append(f"契约真值角色语义校验失败：{exc}")
        report["contract"] = "invalid"

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
    declared_contract = root / str(manifest.get("contract_path") or "contract_legacy_v2.json")
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
    print(f"  契约：v2 {'在' if contract_path.is_file() else '缺'} / 真值 {report.get('contract')}")
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
