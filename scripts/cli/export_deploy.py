"""CLI 离线命令：export / import-scenario / deploy 族（自 scripts/legged_studio_cli.py 拆分，2026-10-12；函数体零改动）。

导出（bundle/scenario/project）/ 场景导入 / 部署 gate 与部署包（backend 同一实现）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path



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


def _cmd_import_scenario(args: argparse.Namespace) -> int:
    """``import-scenario <路径>``：导入场景包（离线命令）。

    H5「Scenario 包可导出/导入」的**导入入口** —— 此前只有导出。判据一律委托
    :func:`backend.bundle_export.import_scenario`（三种形态、完整性校验、契约校验都在那里），
    CLI 只做参数与输出（与 ``export`` 同一分工）。退出码：校验通过 0，被拒 1。
    """
    from backend import bundle_export as bx

    try:
        result = bx.import_scenario(args.path, dest=args.out, force=args.force)
    except FileExistsError as exc:
        raise SystemExit(f"import-scenario 失败：{exc}") from exc
    except (ValueError, FileNotFoundError) as exc:
        # 「不是场景」「完整性不过」「契约不合法」都不是崩溃，是**判据说不通过**：清晰报错 + 非零退出。
        print(f"✗ import-scenario 失败：{exc}")
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    integrity = result.get("integrity") or {}
    print(f"✓ 已校验场景：{result['scenario_id']}（{result['schema_version']}）")
    print(f"  形态：{result['form']}    来源：{result['scenario_file']}")
    if integrity:
        print(f"  完整性：通过（kind={integrity.get('kind')}，登记 {integrity.get('entries')} 条，逐条 sha256 一致）")
    else:
        print("  完整性：裸 JSON，无 manifest 可验（如实标注，不假装验过）")
    print(f"  落盘：{result['written'] or '（未落盘，仅校验；要落盘请给 --out）'}")
    return 0


def _deploy_workspace(args: argparse.Namespace) -> None:
    """``--workspace`` 是"**这个进程**的 workspace"：与 onboard 同约定，同步进环境变量，
    让下游（backend.robot_packages 的包解析）看到同一处——否则"包在 A、解析按 B 判"。"""

    if getattr(args, "workspace", None):
        os.environ["LEGGED_STUDIO_WORKSPACE"] = str(Path(args.workspace).expanduser())


def _cmd_deploy_gate(args: argparse.Namespace) -> int:
    """``deploy gate <robot_id>``：部署契约校验（离线命令，无需后端）。

    判据全在 :func:`backend.deploy_pack.deploy_gate_report`（与 ``GET /api/deploy/gate/{robot_id}``
    **同一实现**）：包根解析 → 读包内 contract_legacy_v2.json / contract_legacy_v2.json →
    ``backend.export_gate.compare_contracts`` 裁决（DENYLIST fail-closed，硬约束字段不一致即 deny）。
    本命令只做异常到退出码/措辞的映射，不自己拼路径、不自己比字段。
    存在 blocker → 退出码 1（可直接当上机前门禁）。
    """

    from backend.deploy_pack import RobotPackageNotFound, deploy_gate_report

    _deploy_workspace(args)
    try:
        report = deploy_gate_report(args.robot_id)
    except RobotPackageNotFound as exc:
        raise SystemExit(f"deploy 失败：找不到机器人包 {exc.robot_id!r}（按过 {exc.attempted}）") from exc
    except ValueError as exc:
        raise SystemExit(f"deploy 失败：{exc}") from exc

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    print(f"部署契约校验（离线命令，无需后端）：{report['package_root']}")
    print(f"  机器人：{args.robot_id}（包内 contract_truth vs contract_legacy_v2.json，硬约束字段 fail-closed）")
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

    from backend.deploy_pack import RobotPackageNotFound, generate_deploy_package

    _deploy_workspace(args)
    try:
        report = generate_deploy_package(
            args.robot_id,
            degraded=args.degraded,
            target_platform=args.platform,
            bench_mode=args.bench,
            out_dir=Path(args.out).expanduser() if args.out else None,
            policy_onnx=Path(args.policy).expanduser() if args.policy else None,
        )
    except RobotPackageNotFound as exc:
        raise SystemExit(f"deploy 失败：找不到机器人包 {exc.robot_id!r}（按过 {exc.attempted}）") from exc
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"deploy 失败：{exc}") from exc

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"部署包已生成（离线命令，无需后端）：{report['path']}")
    print(f"  机器人：{report['robot_id']} / 目标平台：{report['target_platform']}"
          + (" / D2 台架模式" if report.get("bench_mode") else "")
          + (" / 劣化参数档（力矩 ×0.8）" if args.degraded else "")
          + (" / 随包携带策略" if args.policy else ""))
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
