#!/usr/bin/env python3
"""校验"包内 MJCF 就是执行真值"：独立编译 + 断言 + 漂移清单（B-系列：单一真值）。

为什么需要它
------------
运行时的"猴子补丁"拆掉之后，"资产是坏的但被补丁救活"这条退路没有了。于是必须有一道
**独立**检查（不经任何运行时改写路径，直接编译包内 XML），把三类问题显式暴露出来：

1. **硬失败**（结构问题，必须修资产）
   * ``model/robot.xml`` 声明了 ``timestep``——步长真值是契约 ``control.physics_hz``，
     文件里再写一个数字就是"会撒谎的占位"；
   * 契约里没有 ``physics_hz``；
   * 契约声明的驱动关节在 MJCF 里**没有执行器**（"模型加载了但动不了"）；
   * ``model/robot.xml``（验收/训练口径）与 ``simulation/scene.xml``（浏览器口径）
     编译出的 ``opt`` 不一致——这是 TRON1 事故那一类问题，必须为 0。
2. **漂移清单**（契约与 MJCF 的两处真值，`--strict` 时升级为失败）
   * 执行器 ``kp/kv/forcerange`` 与契约 ``actuator_profile`` 不同；
   * 关节 ``armature`` / ``frictionloss`` 与契约常量表不同。

注意：漂移**不是错误**——对没有补丁的包，MJCF 才是执行真值（例如 go1 的 ``kp=35``、
go2w 轮的 ``kv=4``），此时的漂移意味着"契约里那份数没跟上资产"，需要人裁决到底以哪份为准，
而不是由工具静默覆盖。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.physics_binding import joint_constant_tables, physics_scalars  # noqa: E402
from contracts.role_resolver import RoleResolver  # noqa: E402

OPTION_RE = re.compile(r"<option\b([^>]*?)/?>")
ATTR_RE = re.compile(r'([A-Za-z_][\w.-]*)\s*=\s*"([^"]*)"')
OPT_KEYS = ("integrator", "cone", "impratio", "iterations", "ls_iterations", "solver", "gravity")


def load_model(path: Path):
    import mujoco

    return mujoco.MjModel.from_xml_path(str(path))


def joint_name(model, index: int) -> str:
    import mujoco

    return mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, index) or f"#{index}"


def actuator_bindings(model) -> dict[str, int]:
    """``{关节名: 执行器下标}``（按执行器顺序，后者覆盖前者）。"""
    import mujoco

    out: dict[str, int] = {}
    for i in range(model.nu):
        jid = int(model.actuator_trnid[i][0])
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, jid)
        if name:
            out[name] = i
    return out


def check_package(package: Path) -> tuple[list[str], list[str]]:
    """返回 ``(hard_failures, drift)``。"""
    hard: list[str] = []
    drift: list[str] = []
    contract_path = package / "contract_v3.json"
    model_path = package / "model" / "robot.xml"
    if not contract_path.is_file() or not model_path.is_file():
        return [f"缺 contract_v3.json 或 model/robot.xml"], drift

    contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
    expanded = RoleResolver(contract).expand_actuator_profile()
    scalars = physics_scalars(package)
    tables = joint_constant_tables(package)

    # 1) timestep 不得声明（真值 = 契约 physics_hz）
    text = model_path.read_text(encoding="utf-8-sig")
    match = OPTION_RE.search(text)
    attrs = dict(ATTR_RE.findall(match.group(1))) if match else {}
    if "timestep" in attrs:
        hard.append(f"model/robot.xml 仍声明 timestep={attrs['timestep']}（应删除，真值在契约）")
    if scalars.get("physics_hz") in (None, 0):
        hard.append("契约 control.physics_hz 缺失")

    sim_cfg_path = package / "simulation" / "config.json"
    sim_cfg = json.loads(sim_cfg_path.read_text(encoding="utf-8-sig")) if sim_cfg_path.is_file() else {}

    try:
        robot = load_model(model_path)
    except Exception as exc:  # 编译失败本身就是硬失败
        return [f"model/robot.xml 编译失败：{type(exc).__name__}: {exc}"] + hard, drift

    scene_path = package / str(sim_cfg.get("scene_path") or "")
    scene = None
    if sim_cfg.get("scene_path") and scene_path.is_file():
        try:
            scene = load_model(scene_path)
        except Exception as exc:
            hard.append(f"scene 编译失败：{type(exc).__name__}: {exc}")

    # 2) 验收口径 == 浏览器口径（除 timestep）
    if scene is not None:
        for key in OPT_KEYS:
            left, right = getattr(robot.opt, key), getattr(scene.opt, key)
            try:
                same = list(left) == list(right)
            except TypeError:
                same = abs(float(left) - float(right)) < 1e-9
            if not same:
                hard.append(f"robot 与 scene 的 opt.{key} 不一致（{left} vs {right}）")

    # 3) 契约驱动关节必须有执行器
    bindings = actuator_bindings(robot)
    missing = [joint for joint in expanded if joint not in bindings]
    if missing:
        hard.append(f"契约驱动关节在 MJCF 里没有执行器：{missing[:6]}{' …' if len(missing) > 6 else ''}")

    # 4) 执行器参数与契约（漂移清单）
    import mujoco

    for joint, index in bindings.items():
        params = expanded.get(joint)
        if not params or joint in missing:
            continue
        effort = params.get("effort")
        if effort is not None:
            want = round(float(effort), 3)
            limited_by: str | None = None
            if robot.actuator_forcelimited[index]:
                lo, hi = (round(float(x), 3) for x in robot.actuator_forcerange[index])
                limited_by = f"forcerange=[{lo},{hi}]"
                ok = abs(lo) == want and hi == want
            elif robot.actuator_ctrllimited[index]:
                # general/motor 的常见写法：ctrllimited + ctrlrange 等效限力
                lo, hi = (round(float(x), 3) for x in robot.actuator_ctrlrange[index])
                limited_by = f"ctrlrange=[{lo},{hi}]"
                ok = abs(lo) == want and hi == want
            else:
                jid = int(robot.actuator_trnid[index][0])
                if robot.jnt_actfrclimited[jid]:
                    lo, hi = (round(float(x), 3) for x in robot.jnt_actfrcrange[jid])
                    limited_by = f"关节 actuatorfrcrange=[{lo},{hi}]"
                    ok = abs(lo) == want and hi == want
                else:
                    limited_by = "未限力"
                    ok = False
            if not ok:
                drift.append(f"{joint}: {limited_by} vs 契约 effort={want}")
        mode = str(params.get("mode") or "position")
        gain = float(robot.actuator_gainprm[index][0])
        if mode == "position" and params.get("stiffness") is not None:
            want = float(params["stiffness"])
            if abs(gain - want) > 1e-6:
                drift.append(f"{joint}: MJCF kp={gain:g} vs 契约 stiffness={want:g}")
        if mode in ("position", "velocity") and params.get("damping") is not None:
            want = float(params["damping"])
            actual = -float(robot.actuator_biasprm[index][2])
            if abs(actual - want) > 1e-6:
                drift.append(f"{joint}: MJCF kv={actual:g} vs 契约 damping={want:g}")
        if mode == "torque" and abs(gain - 1.0) > 1e-6:
            drift.append(f"{joint}: 契约 mode=torque 但 MJCF 增益={gain:g}（不是直通力矩）")

    # 5) 关节常量与契约（漂移清单）
    armature, friction = tables["armature"], tables["frictionloss"]
    for i in range(robot.njnt):
        # 浮基关节不参与常量对账：freejoint 不接受 armature/frictionloss（schema 禁止），
        # 契约 `default.friction_loss` 的语义是"驱动关节兜底"，不该套到 6 自由 dof 上。
        if robot.jnt_type[i] == mujoco.mjtJoint.mjJNT_FREE:
            continue
        name = joint_name(robot, i)
        dof = int(robot.jnt_dofadr[i])
        lowered = name.lower()
        want_a = armature.get(lowered, armature.get("__default__"))
        want_f = friction.get(lowered, friction.get("__default__"))
        have_a = float(robot.dof_armature[dof])
        have_f = float(robot.dof_frictionloss[dof])
        if want_a is not None and abs(have_a - float(want_a)) > 1e-9:
            drift.append(f"{name}: MJCF armature={have_a:g} vs 契约={float(want_a):g}")
        if want_f is not None and abs(have_f - float(want_f)) > 1e-9:
            drift.append(f"{name}: MJCF frictionloss={have_f:g} vs 契约={float(want_f):g}")
    _ = mujoco
    return hard, drift


def main() -> int:
    parser = argparse.ArgumentParser(description="校验包内 MJCF 与契约的一致性")
    parser.add_argument("--strict", action="store_true", help="把漂移清单也视为失败")
    parser.add_argument("--only", default=None)
    parser.add_argument("--quiet-drift", action="store_true", help="不逐行打印漂移，只给计数")
    args = parser.parse_args()

    packages = sorted(p for p in (ROOT / "assets" / "robots").iterdir() if (p / "contract_v3.json").is_file())
    if args.only:
        packages = [p for p in packages if p.name == args.only]

    failed = 0
    drift_total = 0
    for package in packages:
        hard, drift = check_package(package)
        drift_total += len(drift)
        if hard:
            failed += 1
            print(f"[FAIL] {package.name}")
            for item in hard:
                print(f"       硬失败: {item}")
        elif drift:
            print(f"[DRIFT] {package.name}: {len(drift)} 项契约↔MJCF 漂移")
        else:
            print(f"[OK]   {package.name}: 结构与契约一致")
        if drift and not args.quiet_drift:
            for item in drift[:6]:
                print(f"       · {item}")
            if len(drift) > 6:
                print(f"       · … 另有 {len(drift) - 6} 项")

    print(f"\n共 {len(packages)} 包：硬失败 {failed}，漂移项 {drift_total}")
    if failed:
        return 1
    if args.strict and drift_total:
        print("--strict：漂移视为失败")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
