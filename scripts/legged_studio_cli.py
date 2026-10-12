#!/usr/bin/env python3
"""Command-line facade for the Legged Studio control-plane API.

The CLI intentionally calls the same HTTP contract used by the Web workbench.
It is therefore useful for smoke tests today and a stable automation surface
for native MJLab/Isaac adapters later.

离线子命令（I1）不连控制面，直接读仓库数据，并且**复用 backend/ 的同一实现**（单一真值来源）：

* ``onboard <目录>``    → :func:`backend.package_import.onboard_package`
  —— 新机器人 = 1 目录 + 模型 → 校验 → 生成三件 JSON（contract.json / robot_package.json /
  contract.json）→ 落 ``workspace/packages/`` → 登记索引；**默认预演**，``--write`` 落盘，
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
  （与 ``GET /api/deploy/gate/{robot_id}`` 同一组成：包内 contract_truth vs contract_legacy_v2.json，
  DENYLIST fail-closed，存在 blocker 退出码 1）；
* ``deploy package <robot_id>`` → ``backend.deploy_pack.generate_deploy_package``
  （与 ``POST /api/deploy/package`` 同一实现：部署四件套 + 平台适配层；只生成物料，
  不直接发电机命令——一键生成 ≠ 一键上机）。

因此这些命令**无需后端**（离线命令），只是参数解析与输出格式化在本文件完成。

**2026-10-12 薄内核化**：实现按领域拆到 ``scripts/cli/``（http / workspace /
offline_lists / onboard_verify / export_deploy / train），本文件只留 argparse 树
与分发（函数体零改动、子命令与输出契约零变化，subprocess 测试面不动）。

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
import sys
from pathlib import Path

# 仓库根 bootstrap：脚本方式运行时 sys.path[0] 是 scripts/，离线命令要 import backend.*
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.cli.export_deploy import (  # noqa: E402
    _cmd_deploy_gate,
    _cmd_deploy_package,
    _cmd_export,
    _cmd_import_scenario,
)
from scripts.cli.http import _json_file, _request  # noqa: E402
from scripts.cli.offline_lists import (  # noqa: E402
    _cmd_artifact_list,
    _cmd_pack_list,
    _cmd_run_list,
)
from scripts.cli.onboard_verify import (  # noqa: E402
    _cmd_onboard,
    _cmd_verify_artifacts,
    _cmd_verify_bundle,
    _cmd_verify_motions,
    _cmd_verify_package,
    _cmd_verify_run,
)
from scripts.cli.train import (  # noqa: E402
    _DEFAULT_TRAIN_BASE,
    _cmd_train_create,
    _cmd_train_list,
    _cmd_train_status,
    _cmd_train_stop,
)
from scripts.cli.workspace import _run_status, _workspace_root  # noqa: E402,F401

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
    sub.add_parser("panels", help="list product-surface plugin panels (registry projection)")
    panel = sub.add_parser("panel", help="invoke a panel's CLI provider (declaration-driven)")
    panel.add_argument("panel_id", help="panel id from registry/plugins/panel/ (see: panels)")
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
            "共用同一份编排：校验 → 生成 contract.json / robot_package.json / contract_legacy_v2.json "
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
            "真值契约（角色语义）、训练侧实际消费的合并契约、清单与模型文件是否对得上。"
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

    # H5：`import-scenario` —— 导入（**导出的对偶**）。只实现 scenario 一种粒度：其余四类的
    # "导入"没有明确语义（形态/技能从注册表来、策略由出库索引管、Bundle 是整包搬），
    # **不为了对称而假装支持**。
    import_scenario = sub.add_parser(
        "import-scenario",
        help="导入 Scenario 包（离线命令，无需后端；三种形态都认）",
        description=(
            "导入 Scenario 包（离线命令，无需后端）：认三种实际会被递过来的形态——场景导出目录"
            "（manifest.json + scenario.json）、Bundle 里内嵌的场景（scenario/scenario.json）、裸场景 JSON。"
            "有 manifest 就先验完整性（损坏/被改过 ⇒ 拒绝导入），再过 ScenarioContract（与导出口同一道闸）。"
            "给 --out 才落盘；默认**不覆盖**已存在文件（要覆盖需 --force）。"
        ),
    )
    import_scenario.add_argument("path", help="导出目录 / Bundle 目录 / 裸场景 JSON 路径")
    import_scenario.add_argument("--out", default=None, help="落盘目标（目录或文件；省略则只校验并打印）")
    import_scenario.add_argument("--force", action="store_true", default=False, help="允许覆盖已存在的目标文件")
    import_scenario.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出")

    # I1 收尾：deploy（部署物料 = 契约校验 gate + 部署包打包 package）—— 同样是离线命令，
    # 判据/打包一律委托 backend 既有实现（deploy_api 同一组成），CLI 只做参数与输出。
    from backend.deploy_pack import PLATFORM_LABELS  # 单一真值：平台表只在 backend 里定义一次

    deploy = sub.add_parser(
        "deploy",
        help="部署物料 gate/package（离线命令，无需后端；校验不过退出码 1）",
        description=(
            "部署物料两条离线命令：gate（部署契约校验：包内 contract_truth vs contract_legacy_v2.json，"
            "DENYLIST fail-closed）与 package（部署包 zip：契约/FSM/解码层/人工确认清单 + 平台适配层）。"
            "判据与打包全部委托 backend 既有实现（与 Web 的 /api/deploy/* 同一实现），"
            "只生成物料不发电机命令——一键生成 ≠ 一键上机。"
        ),
    )
    deploy_sub = deploy.add_subparsers(dest="deploy_command", required=True)

    deploy_gate = deploy_sub.add_parser(
        "gate",
        help="部署契约校验：包内契约真值 vs v2 一致性（离线命令，无需后端）",
        description=(
            "部署契约校验（离线命令，无需后端）：与 GET /api/deploy/gate/{robot_id} 同一组成——"
            "解析机器人包根，读包内 contract_legacy_v2.json 与 contract_legacy_v2.json，交给 "
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
    deploy_package.add_argument("--policy", default=None,
                                help="随包携带的策略 ONNX（打进包内 policy.onnx；路径不存在即失败，不静默忽略）")
    deploy_package.add_argument("--workspace", default=None, help="workspace 根（默认：LEGGED_STUDIO_WORKSPACE 环境变量或仓库 workspace/）")
    deploy_package.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # 离线命令：不走 HTTP，直接复用 backend/ 实现读仓库数据，处理完即返回
    if args.command == "panels":
        from backend.panel_registry import load_panels

        panels = load_panels()
        for item in panels:
            cli = (item.get("cli") or {}).get("command") or "-"
            print(f"  {item['id']:12s} [{item.get('group', '-')}] {item.get('title', '')}  (cli: {cli})")
        print(f"  → {len(panels)} panels（registry/plugins/panel/ 清单目录是唯一来源；CLI 命令随声明投影）")
        return 0

    if args.command == "panel":
        # 一切皆插件：面板 CLI 表面 = 注册表声明（cli.provider）→ backend.cli_panels
        # 惰性解析。面板没写 cli 声明 = 该面板没有 CLI 投影，如实报错而非编造输出。
        from backend.cli_panels import resolve_provider
        from backend.panel_registry import load_panels

        entry = next((p for p in load_panels() if p.get("id") == args.panel_id), None)
        if entry is None:
            known = ", ".join(sorted(p.get("id", "?") for p in load_panels()))
            raise SystemExit(f"panel 失败：未知面板 {args.panel_id!r}（已知：{known}）")
        cli_decl = entry.get("cli") or {}
        if not cli_decl.get("provider"):
            raise SystemExit(
                f"panel 失败：面板 {args.panel_id!r} 未声明 CLI 投影"
                f"（registry/plugins/panel/{panel_id}.json 缺 cli.provider；Web/桌面入口：{entry.get('entry', '-')}) "
            )
        payload = resolve_provider(cli_decl["provider"])()
        print(json.dumps({"panel": args.panel_id, "command": cli_decl.get("command"), **payload},
                         ensure_ascii=False, indent=2))
        return 0

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
    if args.command == "import-scenario":
        return _cmd_import_scenario(args)
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
            "离线命令（pack / run / artifact / onboard / verify / export / import-scenario / deploy）不受影响；"
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
