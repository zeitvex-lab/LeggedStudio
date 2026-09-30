#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""golden_env_parity.py — 金标准环境对拍（2026-09-30 固化）。

**为什么存在**：本仓训练环境（kit/契约派生）与上游 vendored 环境是两套构建路径。
今天之前从未验证过二者行为一致——所有"训练质量问题"的归因都缺这个前提。
方法：**同一个上游原生成品模型**（已验证的好策略）分别在
  A = 上游环境（00_resources vendored 源码优先 import）
  B = 我们的训练环境（40k run 同一构建路径）
里同命令 rollout，对比位移。A≈B ⇒ 环境忠实；A≠B ⇒ 环境分叉，训练结论作废。

已知版本差（对拍脚本内置适配，均为本仓既有裁决）：
  * 上游 mujoco_warp 旧 API（ls_parallel 已移除）→ no-op 垫片；
  * 上游模型带非零 geom margin × MULTICCD → 运行时置零（= 契约 margin_policy=zero）；
  * 观测组名：上游 "policy" vs 本仓 "actor"（B26 裁决）；
  * 上游网格被 _SPEC 同步规则剥离 → 从兄弟源树按需恢复，跑完删除（不入 git）。

用法：
  python tools/golden_env_parity.py            # 自派生两子进程对拍并汇总
  python tools/golden_env_parity.py --side upstream|ours   # 单侧（调试用）
  需 adapters/mjlab/.venv 解释器。

判据：每命令 |A-B| ≤ max(0.3 m, 20%·max(|A|,|B|))；不平价即非零退出。
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_ROOT = ROOT / "00_resources" / "unitree_rl_mjlab_go2w"
MESH_SRC = ROOT.parent / "unitree_rl_mjlab_go2w" / "mjlab" / "asset_zoo" / "robots" / "unitree_go2w" / "xmls" / "assets"
MESH_DST = UPSTREAM_ROOT / "mjlab" / "asset_zoo" / "robots" / "unitree_go2w" / "xmls" / "assets"
POLICY = ROOT / "assets" / "robots" / "unitree_go2w" / "simulation" / "policies" / "go2w-upstream-legsonly-v0.onnx"
CMDS = [(0.5, 0.0, 0.0), (0.0, 0.0, 0.5), (0.0, 0.4, 0.0)]

SIDE_SCRIPT = r'''
import sys, argparse
SIDE = sys.argv[1]
if SIDE == "upstream":
    sys.path.insert(0, r"{upstream}")
    import numpy as np, torch, onnxruntime as ort, mujoco
    import mujoco_warp._src.types as _mwt
    for _c in vars(_mwt).values():
        if isinstance(_c, type) and "ls_parallel" in getattr(_c, "__dict__", {{}}):
            _c.ls_parallel = property(lambda s: False, lambda s, v: None)
    from mjlab.asset_zoo.robots.unitree_go2w import go2w_constants
    _orig = go2w_constants.get_spec
    def _zero(spec):
        for g in spec.geoms:
            if float(g.margin) != 0.0:
                g.margin = 0.0
        return spec
    go2w_constants.get_spec = lambda: _zero(_orig())
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.tasks.robots.unitree_go2w.velocity.env_cfgs import unitree_go2w_flat_legs_only_env_cfg
    cfg = unitree_go2w_flat_legs_only_env_cfg(play=True)
    GROUP = "policy"
else:
    sys.path.insert(0, r"{oursrc}")
    sys.path.insert(0, r"{root}")
    import numpy as np, torch, onnxruntime as ort
    from mjlab.envs import ManagerBasedRlEnv
    from go2w_velocity import unitree_go2w_flat_legs_only_env_cfg
    cfg = unitree_go2w_flat_legs_only_env_cfg(play=True)
    GROUP = "actor"
cfg.scene.num_envs = 1
env = ManagerBasedRlEnv(cfg, device="cpu")
env.reset(seed=7)
term = env.command_manager._terms["twist"]
sess = ort.InferenceSession(r"{policy}", providers=["CPUExecutionProvider"])
iname = sess.get_inputs()[0].name
for cmd in {cmds}:
    obs, _ = env.reset()
    xy0 = None
    for i in range(250):
        with torch.no_grad():
            term.command[:] = torch.tensor([cmd])
        o = env.observation_manager.compute_group(GROUP).detach().cpu().numpy().astype(np.float32)
        a = sess.run(None, {{iname: o}})[0]
        env.step(torch.from_numpy(a).float())
        p = env.scene["robot"].data.root_link_pos_w[0]
        if xy0 is None:
            xy0 = [float(p[0]), float(p[1])]
    print("RESULT %s %s dx=%+.3f dy=%+.3f z=%.2f obs=%d act=%d" % (
        SIDE, cmd, float(p[0]) - xy0[0], float(p[1]) - xy0[1], float(p[2]), o.shape[-1], a.shape[-1]))
env.close()
'''.format(upstream=str(UPSTREAM_ROOT), oursrc=str(ROOT / "assets/robots/unitree_go2w/training/source"),
           root=str(ROOT), policy=str(POLICY), cmds=repr(CMDS))


def run_side(side: str) -> dict[tuple, tuple[float, float]]:
    restored: list[Path] = []
    if side == "upstream" and MESH_SRC.is_dir():
        for f in list(MESH_SRC.glob("*.obj")) + list(MESH_SRC.glob("*.stl")):
            dst = MESH_DST / f.name
            if not dst.exists():
                shutil.copyfile(f, dst)
                restored.append(dst)
    try:
        proc = subprocess.run(
            [sys.executable, "-c", SIDE_SCRIPT, side],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
        )
        out: dict[tuple, tuple[float, float]] = {}
        for m in re.finditer(r"RESULT (\w+) \(([^)]*)\) dx=([+-][\d.]+) dy=([+-][\d.]+)", proc.stdout):
            cmd = tuple(float(x) for x in m.group(2).split(","))
            out[cmd] = (float(m.group(3)), float(m.group(4)))
        if not out:
            raise RuntimeError(f"{side} 侧无结果：stderr 尾={proc.stderr[-400:]}")
        return out
    finally:
        for dst in restored:
            dst.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="金标准环境对拍（上游模型×双环境）")
    ap.add_argument("--side", choices=("upstream", "ours"), default=None, help="单侧调试")
    args = ap.parse_args()
    if args.side:
        res = run_side(args.side)
        for cmd, (dx, dy) in res.items():
            print(f"[{args.side}] cmd{cmd}: dx={dx:+.3f} dy={dy:+.3f}")
        return 0

    a = run_side("upstream")
    b = run_side("ours")
    ok = True
    print("金标准对拍（同一上游原生模型，同命令 5s rollout）:")
    for cmd in CMDS:
        da, db = a.get(cmd), b.get(cmd)
        if da is None or db is None:
            print(f"  cmd{cmd}: 缺结果 A={da} B={db}")
            ok = False
            continue
        disp_a = (da[0] ** 2 + da[1] ** 2) ** 0.5
        disp_b = (db[0] ** 2 + db[1] ** 2) ** 0.5
        diff = abs(disp_a - disp_b)
        tol = max(0.3, 0.2 * max(disp_a, disp_b))
        verdict = "OK " if diff <= tol else "DIFF"
        if diff > tol:
            ok = False
        print(f"  cmd{cmd}: A 位移 {disp_a:.2f}m / B 位移 {disp_b:.2f}m | Δ={diff:.2f} ≤ tol {tol:.2f} [{verdict}]")
    print("结论:", "环境忠实（训练结论可信）" if ok else "环境分叉（训练结论需重估）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
