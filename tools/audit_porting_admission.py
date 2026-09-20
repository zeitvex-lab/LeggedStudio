#!/usr/bin/env python3
"""B8 移植准入审计：按 00_resources 的上游证据筛选可移植的训练与仿真。

两条准入规则（用户裁决）：
  T. 训练准入 —— 机器人包可携带「训练」资产，当且仅当 00_resources 中存在该机型的
     训练任务源码（任务/env cfg/奖励/runner，且属训练框架
     mjlab|isaaclab|isaacgym|legged_gym|rsl_rl）。否则不移植。
  S. 仿真准入 —— 机器人包可携带「仿真策略」资产，当且仅当该策略能对应到具体的
     训练任务源码（上游或包内已准入的训练代码）。否则不移植。

用法：
  python tools/audit_porting_admission.py --refresh   # 重扫 00_resources，刷新证据清单
  python tools/audit_porting_admission.py             # 按清单审计资产包（CI 用）
  python tools/audit_porting_admission.py --json out.json

退出码：0 全部准入；1 存在不达标项（CI 门禁）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# 自举：本审计复用 backend.policy_artifacts 的**同一解析入口**（见 package_inventory 的
# 一致性段），脚本方式运行时 sys.path[0] 是 tools/，故先把仓库根放进去（与 validate_packs 同款）。
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

RESOURCES_ROOT = PROJECT_ROOT / "00_resources"
ASSETS_ROOT = PROJECT_ROOT / "assets" / "robots"
EVIDENCE_PATH = PROJECT_ROOT / "registry" / "porting_evidence.json"

ROBOTS = [
    "unitree_go2", "unitree_go2w", "unitree_go1", "unitree_b2", "unitree_b2w",
    "unitree_g1", "deeprobotics_lite3", "deeprobotics_m20",
    "limx_tron1_pf", "limx_tron1_sf", "limx_tron1_wf", "microduck",
    "wuji_hand", "zex-w",
]

# 机型 token：用于在上游路径中定位「机型专属」训练任务
ROBOT_TOKENS: dict[str, list[str]] = {
    "unitree_go2": [r"unitree_go2", r"/go2", r"go2_"],
    "unitree_go2w": [r"unitree_go2w", r"go2w"],
    "unitree_go1": [r"unitree_go1", r"/go1", r"go1_"],
    "unitree_b2": [r"unitree_b2", r"/b2\b", r"b2_"],
    "unitree_b2w": [r"unitree_b2w", r"b2w"],
    "unitree_g1": [r"unitree_g1", r"/g1\b", r"g1_2[39]dof", r"g1_"],
    "deeprobotics_lite3": [r"lite3"],
    "deeprobotics_m20": [r"deeprobotics_m20", r"/m20\b", r"m20_"],
    "limx_tron1_pf": [r"pointfoot", r"tron1_pf", r"/PF\b", r"/pf\b"],
    "limx_tron1_sf": [r"solefoot", r"tron1_sf", r"/SF\b", r"/sf\b"],
    "limx_tron1_wf": [r"wheelfoot", r"tron1_wf", r"/WF\b", r"/wf\b"],
    "microduck": [r"microduck", r"micro_duck"],
    "wuji_hand": [r"wuji"],
    "zex-w": [r"wheelleg", r"rc_mjlab/src/robot", r"zex"],
}

TASK_DIR = re.compile(r"(tasks?/|envs?/|config/|mdp/|agents/|learning/)", re.IGNORECASE)
TASK_FILE = re.compile(
    r"(env_cfg|env_cfgs|rl_cfg|rsl_rl_ppo|ppo_cfg|robot_cfg|task|reward|runner|"
    r"velocity|locomotion|tracking|constants|assets/config)",
    re.IGNORECASE,
)
FRAMEWORK = re.compile(
    r"(mjlab|isaaclab|isaacgym|legged_gym|rsl_rl|rsl-rl|mjx|dm_control)", re.IGNORECASE
)

SCAN_SKIP_PROJECTS = {"knowledge_base", "wandb", "urdf_tool", "sdk_deploy"}
SCAN_SKIP_PARTS = {
    "build", "dist", "outputs", "logs", "node_modules", "__pycache__", ".git",
    "site-packages", "docs",
}

# ---------------------------------------------------------------------------
# 仿真准入裁定表（规则 S）：逐条策略给出「对应的训练源码」证据。
# 值为空串 = 不达标 = 不移植。人工裁定，但每条都必须给出可核对的上游路径。
# ---------------------------------------------------------------------------
POLICY_ADMISSION: dict[str, dict[str, str]] = {
    "deeprobotics_lite3": {
        "lite3-velocity-benchmark": "robot_lab/.../velocity/config/quadruped/deeprobotics_lite3",
        "lite3-velocity-sdk45": "deep_rl + rl_training（云深处官方 RL 训练工程）",
        "lite3-official-sdk": "sdk_deploy/src/Lite3_sdk_deploy/policy/policy.onnx（官方部署包）+ deep_rl（官方训练工程）",
    },
    "deeprobotics_m20": {
        "m20-velocity-57": "m20_rl_isaacsim + Dreamwaq/legged_gym/envs/M20",
        "m20-official-sdk": "sdk_deploy/src/M20_sdk_deploy/policy/policy.onnx（官方部署包）+ deep_rl wheeled/deeprobotics_m20（官方训练工程）",
    },
    "microduck": {
        "microduck-walking": "microduck_rl/.../microduck_velocity_env_cfg.py",
        "microduck-stand": "microduck_rl/.../microduck_standup_env_cfg.py",
        "microduck-sitstand": "microduck_rl/.../microduck_sitstand_env_cfg.py",
        "microduck-roulade": "microduck_rl/.../microduck_roulade_env_cfg.py",
        "microduck-roller": "microduck_rl/.../microduck_velocity_rollers_env_cfg.py",
        "microduck-roller-crouch": "microduck_rl/.../microduck_roller_crouch_env_cfg.py",
        "microduck-ground-pick": "microduck_rl/.../microduck_ground_pick_env_cfg.py",
        "microduck-ball-kick-left": "microduck_rl/.../microduck_ball_kick_env_cfg.py",
        "microduck-ball-kick-right": "microduck_rl/.../microduck_ball_kick_env_cfg.py",
    },
    "unitree_b2": {
        "b2-velocity-benchmark": "robot_lab/.../velocity/config/quadruped/unitree_b2",
    },
    "unitree_b2w": {
        "b2w-velocity-robotlab": "robot_lab/.../velocity/config/wheeled/unitree_b2w",
    },
    "unitree_g1": {
        "g1-velocity": "unitree_rl_mjlab（官方 velocity 任务）",
        "g1-dance-102": "uni_rl/unitree_rl_lab/.../tasks/mimic/robots/g1_29dof/dance_102",
        "g1-dance-gangnam-style": "uni_rl/unitree_rl_lab/.../tasks/mimic（motion-tracking）",
        "g1-dance-subject2": "uni_rl/unitree_rl_lab/.../tasks/mimic（motion-tracking）",
        "g1-velocity-mjswan": "unitree_rl_mjlab（G1 velocity 任务，mjswan 为导出方）",
    },
    "unitree_go1": {
        "go1-playground-joystick": "mujoco_playground/.../locomotion/go1/joystick.py",
        # LeggedSkillDeploy 仅提供 moe_best.pt + config.yaml（推理产物），无训练源码
        "go1-moe-loco": "",
    },
    "limx_tron1_pf": {
        "pf-velocity": "tron1-rl-isaaclab/.../tasks/locomotion/robots/limx_pointfoot_env_cfg.py",
    },
    "limx_tron1_sf": {
        "sf-velocity": "tron1-rl-isaaclab/.../tasks/locomotion/robots/limx_solefoot_env_cfg.py",
    },
    "limx_tron1_wf": {
        "wf-velocity": "tron1-rl-isaaclab/.../tasks/locomotion/robots/limx_wheelfoot_env_cfg.py",
    },
    "unitree_go2": {
        "go2-backflip-69": "包内 local_tasks/robots/unitree/go2/tasks/aerial（backflip）",
        "go2-jump-69": "包内 local_tasks/robots/unitree/go2/tasks/aerial（jump）",
        "go2-moe-cts": "go2_rl_robotlab/source/robot_lab/.../tasks/go2/env_cfg.py（MoE-CTS, hist10）",
        "go2-arenax-velocity": "lain_job/LLoco/src/lloco/tasks/go2_skills/amp_dreamwaq（ArenaX README：go2_amp_dreamwaq 检查点）",
        "go2-rlsar-robotlab": "rl_sar/policy/go2/robot_lab（robot_lab Go2 velocity 训练工程）",
        "go2-rlsar-himloco": "rl_sar/policy/go2/himloco + 00_resources/HIMLoco（HIMLoco 训练工程）",
        "go2-pie-parkour": "parkour_mjlab logs/rsl_rl/go2_pie（Unitree-Go2-PIE 深度跑酷训练任务）",
        "go2-kaiwu-cts-max2": "kaiwu_rl/go2_rl_gym/legged_gym/envs/go2（legged_gym go2 训练工程）",
        "go2-kaiwu-moe-cts-124k": "kaiwu_rl/go2_rl_gym/legged_gym/envs/go2（legged_gym go2 训练工程）",
        "go2-kaiwu-moe-cts-137k": "kaiwu_rl/go2_rl_gym/legged_gym/envs/go2（legged_gym go2 训练工程）",
        "go2-kaiwu-moe-cts-8exp": "kaiwu_rl/go2_rl_gym/legged_gym/envs/go2（legged_gym go2 训练工程）",
        # P1③（2026-09-20）：LainLab playground 7 条（Apache-2.0，mjlab 1.6；训练源 169 py
        # 已同步进 00_resources/LainLab，逐技能 config+mdp+rl 完整——见 §P-1 附表 #1）。
        "go2-lainlab-amp-cts": "LainLab/src/tasks/robots/go2/skills/cts（AMP-CTS，mjlab 1.6）",
        "go2-lainlab-dreamwaq": "LainLab/src/tasks/robots/go2/skills/dreamwaq（DreamWaQ + VAE）",
        "go2-lainlab-trot": "LainLab/src/tasks/robots/go2/skills/trot（cycle_time 0.5）",
        "go2-lainlab-jump": "LainLab/src/tasks/robots/go2/skills/jump（cycle_time 1.5）",
        "go2-lainlab-spring-jump": "LainLab/src/tasks/robots/go2/skills/spring_jump（无相位项）",
        "go2-lainlab-rear-stand": "LainLab/src/tasks/robots/go2/skills/rear_stand",
        "go2-lainlab-handstand": "LainLab/src/tasks/robots/go2/skills/hand_stand",
        # P 组 #8/#9（2026-09-20）：LeggedSkillDeploy 另两条产物——上游只给 config.yaml
        # + policy.pt（无训练代码、无 LICENSE）⇒ 规则 S 产物-only：准入证据 = 上游部署
        # 配置自身（observations 顺序/缩放/PD/joint_mapping 逐字段可取），登记口径见
        # tools/register_legskill_go2.py。
        "go2-loco-45": "LeggedSkillDeploy go2_loco/config.yaml（无训练代码；规则 S 产物-only）",
        "go2-side-flip-69": "LeggedSkillDeploy go2_silde_filp/config.yaml + motion CSV（无训练代码；规则 S 产物-only）",
    },
    "unitree_go2w": {
        "go2w-velocity-legs": "unitree_rl_mjlab_go2w（velocity_legs_only）",
        "go2w-velocity-robotlab": "robot_lab/.../velocity/config/wheeled/unitree_go2w",
        "go2w-himloco-loco": "LeggedSkillDeploy go2w_himloco + 00_resources/HIMLoco（HIMLoco 训练工程）",
        "go2w-himloco-stand-front": "LeggedSkillDeploy go2w_himloco + 00_resources/HIMLoco（HIMLoco 训练工程）",
        "go2w-himloco-handstand": "LeggedSkillDeploy go2w_himloco + 00_resources/HIMLoco（HIMLoco 训练工程）",
        "go2w-himloco-leggedstand": "LeggedSkillDeploy go2w_himloco + 00_resources/HIMLoco（HIMLoco 训练工程）",
    },
    "wuji_hand": {
        "wuji-reorient": "wuji-mjlab src/wuji_mjlab/tasks/reorient（WujiHand_Reorient 训练任务）",
    },
    "zex-w": {
        "zex-w-rough-6800": "rc_old/RC_WheelLeg/05_software/train/rc_mjlab/src/robot",
        "zex-w-wall-84": "rc_old/RC_WheelLeg/05_software/train/rc_mjlab/src/robot",
        "zex-w-rough-9600": "rc_old/RC_WheelLeg/05_software/train/rc_mjlab/src/robot",
        "zex-w-rough-baseline": "rc_old/RC_WheelLeg/05_software/train/rc_mjlab/src/robot",
    },
}

# 包自包含约束：包内不得出现「其他机型」的训练任务目录
FOREIGN_TASK_PATTERNS = {
    "unitree_g1": re.compile(r"(^|/)local_tasks/robots/unitree/g1/"),
    "unitree_go2": re.compile(r"(^|/)local_tasks/robots/unitree/go2/"),
}


def scan_training_evidence() -> dict[str, Any]:
    """扫描 00_resources，产出机型 → 训练任务源码证据。"""
    evidence: dict[str, list[str]] = {robot: [] for robot in ROBOTS}
    if not RESOURCES_ROOT.is_dir():
        return {"available": False, "robots": evidence}
    projects = [
        p for p in sorted(RESOURCES_ROOT.iterdir())
        if p.is_dir() and p.name not in SCAN_SKIP_PROJECTS
    ]
    for project in projects:
        for path in project.rglob("*.py"):
            if any(part in SCAN_SKIP_PARTS for part in path.parts):
                continue
            rel = path.relative_to(project).as_posix()
            if not (TASK_DIR.search(rel) and TASK_FILE.search(rel)):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if not FRAMEWORK.search(text):
                continue
            for robot, tokens in ROBOT_TOKENS.items():
                if any(re.search(token, rel) for token in tokens):
                    evidence[robot].append(f"{project.name}/{rel}")
    return {
        "generated_from": str(RESOURCES_ROOT),
        "available": True,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "robots": {robot: sorted(set(files)) for robot, files in evidence.items()},
    }


def load_evidence(refresh: bool) -> dict[str, Any]:
    if refresh or not EVIDENCE_PATH.exists():
        manifest = scan_training_evidence()
        EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_PATH.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        return manifest
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8-sig"))


def package_inventory(package_root: Path) -> dict[str, Any]:
    source_root = package_root / "training" / "source"
    profiles_dir = package_root / "training" / "profiles"
    profiles = sorted(p.name for p in profiles_dir.glob("*.json")) if profiles_dir.is_dir() else []
    py_files = (
        sorted(p.relative_to(package_root).as_posix() for p in source_root.rglob("*.py"))
        if source_root.is_dir() else []
    )
    sim_path = package_root / "simulation" / "config.json"
    policies: list[dict[str, Any]] = []
    if sim_path.is_file():
        try:
            sim = json.loads(sim_path.read_text(encoding="utf-8-sig"))
            policies = list(sim.get("policies") or [])
        except (OSError, json.JSONDecodeError):
            policies = []
    # X 规则只覆盖**浏览器仿真策略**（simulation/ 下的 onnx）。包内 deploy/ 目录
    # 携带的是部署产物（如 wuji 手持重定向的 policy.onnx/model.pt），不参与仿真准入。
    sim_root = package_root / "simulation"
    onnx = (
        sorted(p.relative_to(package_root).as_posix() for p in sim_root.rglob("*.onnx"))
        if sim_root.is_dir()
        else []
    )
    # 一致性：策略声明 ↔ 实际 onnx 文件必须一一对应。
    #
    # 2026-09-16 修正（B39 同族第五处，**真回归**）：旧实现按 `p.get("path")` 收集"已声明"
    # 集合，而 B10 已按「引用 + hash」把 14 包 46 处裸 `path`/`url` **全部删掉**（声明只留
    # `id`，hash 在 `policies/index.json`）⇒ 声明集恒空 ⇒ 包内**每一个** onnx 都被判成
    # "孤儿"（13 条假违规，CI 恒红），同时 `dangling` 检查静默失效（永远查不出东西）。
    # B10 当时已修 3 处读取点（simulation_api / sim2sim_headless / policy_acceptance），
    # 本工具被那次 grep 的关键词过滤漏掉 —— 又一次印证"读取点必须靠运行验证"。
    # 现统一走 backend.policy_artifacts 的**同一解析入口**（引用 → 索引 → 包内相对路径），
    # 与其余四处消费者同源，不在这里另写第二套解析规则。
    from backend.policy_artifacts import load_index, policy_relative_path

    index = load_index()
    declared: set[str] = set()
    for policy in policies:
        relative = policy_relative_path(policy, robot_dir=package_root, index=index)
        if relative:
            declared.add(relative)
    # 双模型部署（encoder + policy，如 TRON1）：encoder.onnx 也算已声明。
    declared |= {str(p.get("encoder") or "") for p in policies if p.get("encoder")}
    dangling = sorted(p for p in declared if not (package_root / p).is_file())
    orphan = sorted(f for f in onnx if f not in declared)
    return {
        "package_root": str(package_root),
        "training_profiles": profiles,
        "training_py_files": py_files,
        "policies": policies,
        "onnx": onnx,
        "dangling_policy_paths": dangling,
        "orphan_onnx": orphan,
    }


def product_training_evidence(policy: dict[str, Any], index: dict[str, dict[str, Any]]) -> str | None:
    """产品内训练产物（promote 安装进包）的规则 S 证据，fail-closed。

    背景（B8 试点轮 2026-09-17 实测发现）：promote 的「产物默认安装进包」链路
    会往 ``simulation/config.json`` 追加 ``origin=product-training`` 的策略条目
    （带 run_id / artifact_id 溯源）。人工裁定表里没有这种 id —— 首个无 workspace
    镜像的包（unitree_b2）跑冒烟全链时被误判「准入表未登记」。按本审计自己的
    规则 S 措辞（「上游**或包内已准入的训练代码**」），产物由包内已准入 profile
    训练而来，属自证；但**必须能在出库索引解析到对应 artifact** 才算数
    （索引查无此 artifact → 不给证据，照旧走裁定表 → 不达标），防手编 provenance。
    """
    provenance = policy.get("provenance") if isinstance(policy, dict) else None
    if not isinstance(provenance, dict):
        return None
    if str(provenance.get("origin") or "") != "product-training":
        return None
    artifact_id = str(provenance.get("artifact_id") or "")
    entry = index.get(artifact_id) if artifact_id else None
    if not entry:
        return None
    run_id = str(provenance.get("run_id") or entry.get("run_id") or "unknown-run")
    return f"包内已准入训练代码自证（product-training run={run_id}）"


def audit(evidence: dict[str, Any]) -> dict[str, Any]:
    available = bool(evidence.get("available"))
    evidence_robots: dict[str, list[str]] = evidence.get("robots", {})
    report: dict[str, Any] = {
        "rules": {
            "training": "机型须在 00_resources 有训练任务源码，否则不移植",
            "simulation": "仿真策略须对应具体训练任务源码，否则不移植",
        },
        "evidence_available": available,
        "robots": {},
        "violations": [],
    }
    for robot in ROBOTS:
        package_root = ASSETS_ROOT / robot
        if not package_root.is_dir():
            continue
        evidence_files = evidence_robots.get(robot, [])
        training_admitted = bool(evidence_files) or not available
        inv = package_inventory(package_root)

        admitted, rejected = [], []
        table = POLICY_ADMISSION.get(robot, {})
        from backend.policy_artifacts import load_index

        index = load_index()
        for policy in inv["policies"]:
            policy_id = str(policy.get("id") or "")
            reason = table.get(policy_id, "")
            if not reason:
                # 人工裁定表未登记时，产品训练产物可凭可解析的溯源自证（见
                # product_training_evidence docstring；解析不到则照旧不达标）。
                reason = product_training_evidence(policy, index)
            if reason:
                admitted.append({"id": policy_id, "evidence": reason})
            else:
                rejected.append({
                    "id": policy_id,
                    "reason": "准入表未登记" if policy_id not in table else "无对应训练任务源码",
                })

        foreign: list[str] = []
        for other_robot, pattern in FOREIGN_TASK_PATTERNS.items():
            if other_robot == robot:
                continue
            foreign += [f for f in inv["training_py_files"] if pattern.search(f)]

        report["robots"][robot] = {
            "training_evidence_projects": sorted({f.split("/")[0] for f in evidence_files}),
            "training_evidence_files": len(evidence_files),
            "training_admitted": training_admitted,
            "training_migrated": bool(inv["training_py_files"]),
            "training_profiles": len(inv["training_profiles"]),
            "training_py_files": len(inv["training_py_files"]),
            "policies_admitted": admitted,
            "policies_rejected": rejected,
            "onnx_files": inv["onnx"],
            "foreign_task_files": sorted(foreign),
            "dangling_policy_paths": inv["dangling_policy_paths"],
            "orphan_onnx": inv["orphan_onnx"],
        }
        if not training_admitted:
            report["violations"].append({"robot": robot, "type": "training_no_upstream_source"})
        for item in rejected:
            report["violations"].append({
                "robot": robot, "type": "simulation_no_training_code", "policy": item["id"],
            })
        if foreign:
            report["violations"].append({
                "robot": robot, "type": "foreign_task_residue", "files": len(foreign),
            })
        if inv["dangling_policy_paths"]:
            report["violations"].append({
                "robot": robot, "type": "dangling_policy_path",
                "files": inv["dangling_policy_paths"],
            })
        if inv["orphan_onnx"]:
            report["violations"].append({
                "robot": robot, "type": "orphan_onnx", "files": inv["orphan_onnx"],
            })
    return report


def print_summary(report: dict[str, Any]) -> None:
    print("=" * 78)
    print("B8 移植准入审计")
    print("=" * 78)
    if not report["evidence_available"]:
        print("!! 00_resources 不可用：仅做结构审计，训练准入跳过\n")
    print(f"{'机型':<22}{'训练证据':>8}{'已移植':>7}{'profiles':>9}{'策略准入':>9}{'策略不达标':>11}")
    print("-" * 78)
    for robot, entry in report["robots"].items():
        print(
            f"{robot:<22}{entry['training_evidence_files']:>8}"
            f"{'是' if entry['training_migrated'] else '否':>7}"
            f"{entry['training_profiles']:>9}"
            f"{len(entry['policies_admitted']):>9}"
            f"{len(entry['policies_rejected']):>11}"
        )
    print("-" * 78)
    if report["violations"]:
        print(f"\n不达标项 {len(report['violations'])} 条：")
        for item in report["violations"]:
            detail = item.get("policy") or item.get("files", "")
            if isinstance(detail, list):
                detail = ", ".join(str(x) for x in detail[:3]) + ("..." if len(detail) > 3 else "")
            print(f"  [{item['type']}] {item['robot']} {detail}")
    else:
        print("\n全部准入。")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="B8 移植准入审计")
    parser.add_argument("--refresh", action="store_true", help="重扫 00_resources 刷新证据清单")
    parser.add_argument("--json", help="把完整报告写入该文件")
    args = parser.parse_args(argv)

    evidence = load_evidence(args.refresh)
    report = audit(evidence)
    print_summary(report)
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(f"\n报告已写入 {args.json}")
    return 1 if report["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
