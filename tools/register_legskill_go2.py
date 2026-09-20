#!/usr/bin/env python3
"""P 组 §P-1 #8/#9：LeggedSkillDeploy go2_loco / go2_silde_filp 产物入库。

上游只给 ``config.yaml + policy.pt``（无训练代码、无 LICENSE）⇒ **规则 S 产物-only**：
不移植训练侧，只把推理产物按"部署真值逐字段取自上游 config.yaml"登记进包。

四步，每步都可核：

1. **.pt → onnx**：opset 11、``input``/``output`` 命名与已入库的 backflip_69/jump_69
   一致（同一转换管线的既有约定）；导出后用 onnxruntime 与 torch 前向**逐值对拍**
   （浮点容差 1e-4）——"导出没报错"不算证据。
2. **blob 进包**：onnx（侧空翻另有参考动作 CSV）同时落 ``assets/`` 源树与
   ``workspace/packages/`` 浏览器副本——浏览器端点读 workspace 副本（包定位
   "workspace 副本优先"），只落一边会出现"源树有、页面选不到"。
3. **config 声明**：观测布局逐字段取自上游 ``observations`` 顺序与各 ``*_scale``，
   PD 取 ``rl_kp``/``rl_kd``，关节序与默认姿态由 ``joint_mapping`` ×
   ``joint_controller_names`` × ``default_dof_pos`` **按同一套约定推导**（推导规则
   与已入库 jump-69 条目逐字段对齐后固化，见 :func:`derive_joint_layout`）。
4. **出库索引**：``build_all(write=True)`` 整表重建（哈希/摘要实测，不手填）。

用法::

    .venv/Scripts/python.exe tools/register_legskill_go2.py            # 转换+登记+出库
    .venv/Scripts/python.exe tools/register_legskill_go2.py --dry-run  # 只算不落盘
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "00_resources" / "LeggedSkillDeploy" / "policy" / "unitree_rl_lab" / "go2"
PKG_TREES = (
    ROOT / "assets" / "robots" / "unitree_go2",
    ROOT / "workspace" / "packages" / "unitree_go2",
)

#: 上游 config.yaml 的 joint_controller_names（部署/控制器序，FR 打头）
CONTROLLER_NAMES = [
    "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
    "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
    "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
    "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint",
]
#: default_dof_pos 的 type-major 分块腿序（FL, FR, RL, RR）——与已入库 jump-69 条目
#: 及包内 special.py 的默认姿态块同一条约定（legs 按机型规范腿序，不按控制器序）。
TYPE_MAJOR_LEGS = ["FL", "FR", "RL", "RR"]


def derive_joint_layout(mapping: list[int], default_dof_pos: list[float]) -> tuple[list[str], dict[str, float]]:
    """``joint_mapping`` × ``joint_controller_names`` × ``default_dof_pos`` → (策略槽位序, 默认姿态)。

    - ``mapping[i]`` = 策略槽位 i 对应的**控制器**关节下标 ⇒ 策略槽位序 =
      ``[CONTROLLER_NAMES[m] for m in mapping]``（jump-69 已入库条目同口径）。
    - ``default_dof_pos`` 是 **type-major**（hips×4, thighs×4, calves×4，腿序
      FL/FR/RL/RR）而不是策略槽位序——jump-69 的非对称髋角（[0.1,-0.1,0.1,-0.1]）
      只有这一种读法能对上已入库值，侧空翻的 per-leg 槽位序更不能直接按位取。
    """
    order = [CONTROLLER_NAMES[m] for m in mapping]
    hips = {leg: default_dof_pos[i] for i, leg in enumerate(TYPE_MAJOR_LEGS)}
    thighs = {leg: default_dof_pos[4 + i] for i, leg in enumerate(TYPE_MAJOR_LEGS)}
    calves = {leg: default_dof_pos[8 + i] for i, leg in enumerate(TYPE_MAJOR_LEGS)}
    defaults: dict[str, float] = {}
    for name in order:
        leg, joint = name.split("_", 1)[0], name.split("_", 1)[1]
        block = {"hip_joint": hips, "thigh_joint": thighs, "calf_joint": calves}[joint]
        defaults[name] = block[leg]
    return order, defaults


def convert_to_onnx(pt_path: Path, onnx_path: Path, dim: int) -> float:
    """TorchScript → ONNX（与 backflip_69/jump_69 同一导出约定），返回与 torch 的最大逐值差。"""
    model = torch.jit.load(str(pt_path), map_location="cpu")
    model.eval()
    sample = torch.randn(1, dim)
    torch.onnx.export(
        model, sample, str(onnx_path),
        export_params=True, opset_version=11, do_constant_folding=True,
        input_names=["input"], output_names=["output"], dynamo=False,
    )
    with torch.no_grad():
        reference = model(sample).numpy()
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    exported = session.run(None, {"input": sample.numpy()})[0]
    return float(np.abs(reference - exported).max())


def _policies_array_span(raw: str) -> tuple[int, int]:
    """顶层 ``"policies": [`` 数组的起止字符偏移（用于保持原文件其余字节不变地插入）。"""
    key = raw.index('  "policies": [')
    start = raw.index("[", key)
    depth = 0
    cursor = start
    while True:
        if raw[cursor] == "[":
            depth += 1
        elif raw[cursor] == "]":
            depth -= 1
            if depth == 0:
                return start, cursor
        cursor += 1


def insert_policy_entry(config_path: Path, entry: dict) -> bool:
    """把声明插进 ``policies`` 数组末尾（幂等；只动这一处字节，保留原排版）。"""
    raw = config_path.read_text(encoding="utf-8")
    config = json.loads(raw)
    if any(p.get("id") == entry["id"] for p in config.get("policies") or []):
        return False
    _start, end = _policies_array_span(raw)
    block = ",\n    " + json.dumps(entry, ensure_ascii=False, indent=2).replace("\n", "\n    ")
    config_path.write_text(raw[:end] + block + raw[end:], encoding="utf-8")
    return True


def strip_entry_raw_path(config_path: Path, policy_id: str, relative: str) -> bool:
    """删掉声明里的裸 ``path``（B10 终态：路径真值只在 ``policies/index.json``）。

    索引已能独立解析 blob，``path`` 只是迁移债；``build_all`` 扫的是 assets 源树，
    留着它会让 ``declaration_has_raw_path`` 判红。只删这一行字节，不动其余排版。
    """
    raw = config_path.read_text(encoding="utf-8")
    anchor = raw.index(f'"id": "{policy_id}"')
    line = f'"path": "{relative}"'
    at = raw.index(line, anchor)
    end = raw.index("\n", at) + 1
    start = raw.rindex("\n", 0, at) + 1
    config_path.write_text(raw[:start] + raw[end:], encoding="utf-8")
    return True


def build_loco_entry() -> dict:
    """#8 go2_loco：45 维单帧速度策略（observations 序与 go2_rl_sdk_45 同序）。"""
    mapping = [3, 0, 9, 6, 4, 1, 10, 7, 5, 2, 11, 8]
    default_dof_pos = [0.1, -0.1, 0.1, -0.1, 0.8, 0.8, 1.0, 1.0, -1.5, -1.5, -1.5, -1.5]
    order, defaults = derive_joint_layout(mapping, default_dof_pos)
    return {
        "id": "go2-loco-45",
        "label": "Go2 Loco 45D (velocity, LeggedSkillDeploy)",
        "obs_dim": 45,
        "action_dim": 12,
        "history_len": 1,
        "source": "LeggedSkillDeploy go2_loco（第三方，无 LICENSE；仅内部研究）",
        "training_ref": {
            "profile": None,
            "match": "product_only",
            "upstream": "LeggedSkillDeploy go2_loco config.yaml（无训练代码；规则 S 产物-only）",
        },
        "contract": {
            "observation_kind": "go2_rl_sdk_45",
            "obs_dim": 45,
            "action_dim": 12,
            "history_len": 1,
            "command_dims": 3,
            "default_command": [0.0, 0.0, 0.0],
            "task_type": "velocity",
            "action_joint_order": order,
            "default_joint_angles": defaults,
            "action_scale": 0.25,
            "scales": {"ang_vel": 0.2, "dof_pos": 1.0, "dof_vel": 0.05, "command": [1.0, 1.0, 1.0]},
            "control": {
                "stiffness": {name: 25.0 for name in order},
                "damping": {name: 0.5 for name in order},
            },
        },
    }


def build_sideflip_entry(motion_csv: str, time_end: float) -> dict:
    """#9 go2_silde_filp：69 维模仿策略（motion_command 24 + anchor_ori 6 + 本体 39）。"""
    mapping = [3, 4, 5, 0, 1, 2, 9, 10, 11, 6, 7, 8]
    default_dof_pos = [-0.1, 0.1, -0.1, 0.1, 0.9, 0.9, 0.9, 0.9, -1.8, -1.8, -1.8, -1.8]
    order, defaults = derive_joint_layout(mapping, default_dof_pos)
    # rl_kp/rl_kd/action_scale 在配置里是 per-leg 三元组重复（hip, thigh, calf），四腿同值
    return {
        "id": "go2-side-flip-69",
        "label": "Go2 Side-Flip 69D (imitation, motion-csv)",
        "obs_dim": 69,
        "action_dim": 12,
        "history_len": 1,
        "source": "LeggedSkillDeploy go2_silde_filp（第三方，无 LICENSE；仅内部研究）",
        "training_ref": {
            "profile": None,
            "match": "product_only",
            "upstream": "LeggedSkillDeploy go2_silde_filp config.yaml + motion CSV（无训练代码；规则 S 产物-only）",
        },
        "contract": {
            "observation_kind": "go2_motion_69",
            "obs_dim": 69,
            "action_dim": 12,
            "history_len": 1,
            "command_dims": 3,
            "default_command": [0.0, 0.0, 0.0],
            "task_type": "imitation",
            "autoplay": False,
            "action_joint_order": order,
            "motion_joint_mapping": mapping,
            "default_joint_angles": defaults,
            "action_scale_by_joint": {
                **{f"{leg}_hip_joint": 0.3349008680922322 for leg in TYPE_MAJOR_LEGS},
                **{f"{leg}_thigh_joint": 0.3349008680922322 for leg in TYPE_MAJOR_LEGS},
                **{f"{leg}_calf_joint": 0.17414387605840184 for leg in TYPE_MAJOR_LEGS},
            },
            "scales": {"ang_vel": 1.0, "dof_pos": 1.0, "dof_vel": 1.0, "command": [1.0, 1.0, 1.0]},
            "control": {
                "stiffness": {
                    **{f"{leg}_hip_joint": 17.6918024541168 for leg in TYPE_MAJOR_LEGS},
                    **{f"{leg}_thigh_joint": 17.6918024541168 for leg in TYPE_MAJOR_LEGS},
                    **{f"{leg}_calf_joint": 65.21906056685614 for leg in TYPE_MAJOR_LEGS},
                },
                "damping": {
                    **{f"{leg}_hip_joint": 1.1262951251433972 for leg in TYPE_MAJOR_LEGS},
                    **{f"{leg}_thigh_joint": 1.1262951251433972 for leg in TYPE_MAJOR_LEGS},
                    **{f"{leg}_calf_joint": 4.1519743493286185 for leg in TYPE_MAJOR_LEGS},
                },
            },
            "motion_params": {
                "motion_csv": f"simulation/policies/{motion_csv}",
                "fps": 50.0,
                "time_start": 0.0,
                "time_end": time_end,
                "csv_layout": "root_pos3,quat_xyzw4,dof_pos12",
                "ref_axis": "y_up",
                "loop": False,
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="只转换与推导，不落盘")
    args = parser.parse_args()

    staging = ROOT / "workspace" / "tmp_porting"
    staging.mkdir(parents=True, exist_ok=True)

    specs = [
        {
            "pt": SRC / "go2_loco" / "policy.pt",
            "onnx_name": "loco_45.onnx",
            "dim": 45,
            "entry": build_loco_entry(),
        },
        {
            "pt": SRC / "go2_silde_filp" / "policy.pt",
            "onnx_name": "sideflip_69.onnx",
            "dim": 69,
            # time_end 取 CSV 全长的理由：t=2.0s（上游 config 的 time_end）时动作仍在进行
            # （thigh 0.938→0.707 rad，rows 100→116），截到 2.0s 会把参考动作冻在半空。
            "entry": build_sideflip_entry("sideflip_motion.csv", 2.36),
            "csv": SRC / "go2_silde_filp" / "go2_sildfilp_0428_for_csv_to_npz.csv",
            "csv_name": "sideflip_motion.csv",
        },
    ]

    for spec in specs:
        onnx_path = staging / spec["onnx_name"]
        drift = convert_to_onnx(spec["pt"], onnx_path, spec["dim"])
        print(f"[convert] {spec['pt'].parent.name:16s} -> {spec['onnx_name']:16s} max|onnx-pt| = {drift:.2e}")
        if drift > 1e-4:
            print(f"  !! 超出 1e-4 容差，终止", file=sys.stderr)
            return 1
        if args.dry_run:
            continue
        for tree in PKG_TREES:
            policies_dir = tree / "simulation" / "policies"
            policies_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(onnx_path, policies_dir / spec["onnx_name"])
            if spec.get("csv"):
                shutil.copyfile(spec["csv"], policies_dir / spec["csv_name"])
            config_path = tree / "simulation" / "config.json"
            inserted = insert_policy_entry(config_path, spec["entry"])
            # assets 源树是 build_all 的扫描对象，声明必须留 B10 终态（只留 id）；
            # workspace 副本留 path 无妨（不经 scan_declarations），但为口径一致也删。
            stripped = strip_entry_raw_path(config_path, spec["entry"]["id"], f"simulation/policies/{spec['onnx_name']}")
            action = "inserted" if inserted else ("already present" + ("+path stripped" if stripped else ""))
            print(f"[register] {tree.relative_to(ROOT)}: {action} {spec['entry']['id']}")

    if args.dry_run:
        print("[dry-run] 未落盘")
        return 0

    # 出库索引整表重建（哈希/摘要实测）。build_all 会经 pack_catalog  import fastapi，
    # 而训练 venv（adapters/mjlab/.venv，本脚本转换 .pt 需要的那个）没有它 ⇒ 用后端
    # venv（仓库根 .venv）起子进程跑，两边都不迁就。
    backend_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not backend_python.exists():
        print(f"!! 缺后端 venv：{backend_python}（build_all 需要 fastapi）", file=sys.stderr)
        return 1
    import subprocess

    completed = subprocess.run(
        [str(backend_python), "-c",
         "import sys; sys.path.insert(0, '.');"
         "from backend.policy_artifacts import build_all;"
         "r = build_all(write=True);"
         "print(r.get('count'), r.get('problems'))"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    tail = (completed.stdout.strip().splitlines() or ["<no output>"])[-1]
    print(f"[out-index] {tail}")
    if completed.returncode != 0:
        print(completed.stderr[-2000:], file=sys.stderr)
        return 1
    return 0 if tail.endswith("[]") else 1


if __name__ == "__main__":
    raise SystemExit(main())
