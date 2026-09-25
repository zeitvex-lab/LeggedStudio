#!/usr/bin/env python3
"""技能层迁移等价性取证：dump 一个机型技能任务的 env_cfg / runner_cfg 全字段。

**每次技能上移（包内 → 族 Kit）都用它取证**：迁移前后各 dump 一份，`--diff` 逐字段比。
判据是"字段逐项一致"，而不是"测试过了"——上移是纯搬运，任何字段变化都要解释。

用法（同一脚本跑迁移前后两份代码，再逐字段 diff）：

    # 迁移前（HEAD 的包拷到临时树）
    python tools/audit_skill_lift_equivalence.py \
        --package-root /tmp/go2_before/assets/robots/unitree_go2 \
        --source-root  /tmp/go2_before/assets/robots/unitree_go2/training/source \
        --out  workspace/validation/go2-skill-cfg-before.json

    # 迁移后（工作树）
    python workspace/validation/dump_skill_cfgs.py \
        --package-root assets/robots/unitree_go2 \
        --source-root  assets/robots/unitree_go2/training/source \
        --out  workspace/validation/go2-skill-cfg-after.json

    python workspace/validation/dump_skill_cfgs.py --diff <before> <after>

口径：
* 入口**按 profile 声明**取（`entrypoints.env/runner`），所以"入口没动"本身也被验到；
* dump 是 dataclass 全字段递归展开（含嵌套 dataclass / tuple / dict / callable / tensor），
  逐个对象带类型名；
* **模块路径归一**（`--diff` 时）：技能实现从 `go2_skills.*` 搬到
  `quadruped_kit/skills/*` 属计划的搬迁，归一表见 `_canon()`；
  归一前后**两份 diff 都打印**，不藏原始差异。
* 归一同时作用于**字符串值里的模块路径**：rsl_rl 的 `actor.class_name` /
  `algorithm.class_name` 就是"模块:符号"字符串，搬迁后必然改名（2026-09-25
  parkour 上移实况）。值是"从类对象派生"的，故归一而不是重新发明一个字面量。
* job 的模块项默认按 go2 技能包（`go2_skills/<rel>`）解析；技能不在 `go2_skills/`
  下时（如 parkour 在 `...go2/tasks/parkour/...`）以 `local_tasks.` 开头写**绝对模块路径**；
  纯点路径（无 `/`，如 `go2w_velocity.env_cfgs`，2026-09-25 go2w 技能上移实况）同样
  按**绝对模块路径**解析——包侧源码根已在 `--source-root` 里，模块名即入口声明名。
* 姿态归一（`/init_state/joint_pos` 的 `@resolved`）默认用 go2 契约的关节序；其它机型
  用 `--joint-order`（`robot:<robot_id>` 从该机型契约 `action.joint_order` 读，或直接给
  JSON 列表）。默认值保持历史行为，未传时结论只对 go2 同序关节有意义。
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_JOBS = (
    ("jump_env", "jump/config.py", "make_jump_env_cfg", {"play": False}),
    ("jump_env_play", "jump/config.py", "make_jump_env_cfg", {"play": True}),
    ("trot_env", "trot/config.py", "make_trot_env_cfg", {"play": False}),
    ("jump_runner", "jump/config.py", "make_jump_runner_cfg", {}),
    ("trot_runner", "trot/config.py", "make_trot_runner_cfg", {}),
)

_OLD = "local_tasks.robots.unitree.go2.tasks.go2_skills."
_OLD_PARKOUR = "local_tasks.robots.unitree.go2.tasks.parkour."
_NEW = "adapters.mjlab.kits.quadruped_kit.skills."
_NEW_PARKOUR = "adapters.mjlab.kits.quadruped_kit.skills.parkour."
#: parkour 的**包内入口 stub 不搬迁**（profile 的 entrypoints 指向它），故单独标出：
#: 归一后两侧都是 `ENTRY.parkour.config.*`，差异只剩"真搬走的那几段"。
_ENTRY_PARKOUR = "local_tasks.robots.unitree.go2.tasks.parkour.config."
#: velocity 上移：机械功率核从包内 mdp 搬到族级 mdp 并去掉机型前缀
#: （`go2_dof_power_penalty` → `dof_power_penalty`）。两侧归一成同一串。
_OLD_DOF_POWER = (
    "local_tasks.robots.unitree.go2.mdp.rewards:go2_dof_power_penalty"
)
_NEW_DOF_POWER = (
    "adapters.mjlab.kits.quadruped_kit.skills.mdp.rewards:dof_power_penalty"
)
_CANON_DOF_POWER = "SKILL.mdp.rewards:dof_power_penalty"

#: WTW（周期步态先验）上移：包内 `...tasks.locomotion.wtw_mdp` 整段搬到族级
#: `...skills.wtw.mdp`（同名函数，机器事实改走绑定派生）。
_OLD_WTW_MDP = "local_tasks.robots.unitree.go2.tasks.locomotion.wtw_mdp"
_NEW_WTW_MDP = "adapters.mjlab.kits.quadruped_kit.skills.wtw.mdp"
_CANON_WTW_MDP = "SKILL.wtw.mdp"


def _canon(module: str) -> str:
    """模块路径归一表（只归一**计划中的搬迁**，不改任何值）。"""
    text = str(module or "")
    text = text.replace(_ENTRY_PARKOUR, "ENTRY.parkour.config.")
    text = text.replace(_OLD, "SKILL.").replace(_NEW, "SKILL.")
    # velocity 上移的功率核：包内名字 → 族级名字（同一实现，见 skills/mdp/rewards.py）
    text = text.replace(_OLD_DOF_POWER, _CANON_DOF_POWER).replace(
        _NEW_DOF_POWER, _CANON_DOF_POWER
    )
    # WTW 上移：包内 wtw_mdp → 族级 skills/wtw/mdp.py（同一实现）
    text = text.replace(_OLD_WTW_MDP, _CANON_WTW_MDP).replace(
        _NEW_WTW_MDP, _CANON_WTW_MDP
    )
    # parkour（越障）上移：装配/模型/地形从包内 `...tasks.parkour.*` 搬到族级
    # `...skills.parkour.*`（`config/` 是薄委托，不在此列）。
    text = text.replace(_OLD_PARKOUR, "SKILL.parkour.").replace(_NEW_PARKOUR, "SKILL.parkour.")
    # 技能内 mdp 包：旧 `trot/mdp/*`、`jump/mdp/*` → 新统一 `skills/mdp/*`
    text = (
        text.replace("SKILL.trot.mdp.rewards", "SKILL.rewards.trot")
        .replace("SKILL.jump.mdp.rewards", "SKILL.rewards.jump")
        .replace("SKILL.trot.rewards", "SKILL.rewards.trot")
        .replace("SKILL.jump.rewards", "SKILL.rewards.jump")
    )
    text = text.replace("SKILL.upstream.rl", "SKILL.mdp.rl").replace("SKILL.shared.", "SKILL.mdp.")
    # backflip（特技）上移：`backflip/mdp/*` 三个模块摊平到 `skills/backflip/*`
    # （命令/观测/奖励各自成模块，与 trot/jump 的 `mdp/` 层级不同，故单独归一）。
    for mod in ("commands", "observations", "rewards", "events", "terminations"):
        text = text.replace(f"SKILL.backflip.mdp.{mod}", f"SKILL.backflip.{mod}")
    text = text.replace("SKILL.backflip.mdp.", "SKILL.backflip.")
    # backflip 的摩擦分桶核改用族级共享实现（同一函数，原先在包内 backflip/mdp/events.py）
    text = text.replace(
        "SKILL.backflip.events:source_friction_buckets",
        "SKILL.mdp.events:source_friction_buckets",
    )
    for skill in ("trot", "jump"):
        for mod in ("observations", "commands", "curriculums", "events"):
            text = text.replace(f"SKILL.{skill}.mdp.{mod}", f"SKILL.mdp.{mod}")
        text = text.replace(f"SKILL.{skill}.mdp.", f"SKILL.mdp.")
    return text


def _dump(value, *, owner: str | None = None):
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            "__type__": type(value).__name__,
            "__module__": _canon(type(value).__module__),
            **{
                field.name: _dump(getattr(value, field.name))
                for field in dataclasses.fields(value)
            },
        }
    if isinstance(value, (list, tuple)):
        return [_dump(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _dump(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    # 函数 / 类：记（归一后的）模块与限定名 —— 只用名字，不比较对象身份。
    if callable(value):
        return {
            "__callable__": f"{_canon(getattr(value, '__module__', ''))}:"
            f"{getattr(value, '__qualname__', value)}"
        }
    if hasattr(value, "shape") and hasattr(value, "tolist"):
        return {"__tensor__": value.tolist()}
    return {"__repr__": f"{type(value).__name__}:{value!r}"}


def _module_name(rel_module: str) -> str:
    """job 的模块项 → 可导入的模块名。

    默认按 go2 技能包解析（`jump/config.py` → `...go2_skills.jump.config`）；
    以 `local_tasks.` 开头、或是**纯点路径**（无 `/`，如 `go2w_velocity.env_cfgs`）
    时按**绝对模块路径**解析（技能不在 `go2_skills/` 下的情形，如 parkour：
    `...go2/tasks/parkour/config/go2/env_cfgs.py`；go2w：
    `go2w_velocity.env_cfgs`，包侧源码根由 `--source-root` 提供）。
    """
    dotted = rel_module.replace("/", ".").removesuffix(".py")
    if dotted.startswith("local_tasks.") or ("/" not in rel_module and "." in rel_module):
        return dotted
    return f"local_tasks.robots.unitree.go2.tasks.go2_skills.{dotted}"


def _load_callable(source_root: Path, rel_module: str, name: str):
    import importlib

    module = importlib.import_module(_module_name(rel_module))
    return getattr(module, name)


def _parse_jobs(raw: str) -> tuple:
    """把 `--jobs` 的 JSON 解析成 job 条目。

    形如 `[["jump_env","jump/config.py","make_jump_env_cfg",{"play":false}], ...]`；
    既有的 `_JOBS` 是 go2 的 trot/jump 默认值，其它技能/机型上移时用本参数覆盖。
    """
    data = json.loads(raw)
    jobs = []
    for item in data:
        label, module_rel, factory = str(item[0]), str(item[1]), str(item[2])
        kwargs = item[3] if len(item) > 3 else {}
        jobs.append((label, module_rel, factory, kwargs))
    if not jobs:
        raise ValueError("--jobs 解析后为空")
    return tuple(jobs)


def run(package_root: Path, source_root: Path, out: Path, *, jobs: tuple = _JOBS) -> None:
    for path in (str(package_root.resolve()), str(source_root.resolve())):
        if path not in sys.path:
            sys.path.insert(0, path)
    if str(ROOT) not in sys.path:
        sys.path.append(str(ROOT))

    dump = {}
    for label, module_rel, factory, kwargs in jobs:
        func = _load_callable(source_root, module_rel, factory)
        dump[label] = {"entry": f"{_module_name(module_rel)}:{factory}", "value": _dump(func(**kwargs))}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dump, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")


def _flatten(value, prefix: str = "", *, joint_order: tuple[str, ...] = ()) -> dict[str, str]:
    flat: dict[str, str] = {}
    if isinstance(value, dict):
        if prefix.endswith("/init_state/joint_pos") and joint_order:
            # 归一 R2：默认姿的**写法**可不同（源用 `.*calf_joint` 这类角色正则，
            # 族级绑定按"同角色各腿同值则压成正则"重排），但解析结果必须逐关节一致。
            # 这里用与 mjlab `resolve_matching_names_values` 同口径的 fullmatch 解析后比较。
            flat[prefix + "/@resolved"] = json.dumps(
                {joint: _resolve_pose(value, joint) for joint in joint_order},
                ensure_ascii=False,
                sort_keys=True,
            )
            return flat
        if "__type__" in value:
            flat[f"{prefix}/@type"] = value["__type__"]
            flat[f"{prefix}/@module"] = value["__module__"]
        if "__callable__" in value:
            # 函数/类以（归一后的）"模块:限定名"参与比对：**同名搬迁**由 `_canon()` 归一，
            # 真搬迁（如 go2 的功率核上移到族级 mdp）在归一表里成对登记 —— 漏登记就判红，
            # 不会被"__ 开头一律跳过"静默吞掉。
            flat[f"{prefix}/@callable"] = _canon(str(value["__callable__"]))
            return flat
        for key, item in value.items():
            if key.startswith("__"):
                continue
            flat.update(_flatten(item, f"{prefix}/{key}", joint_order=joint_order))
        return flat
    if isinstance(value, list):
        for index, item in enumerate(value):
            flat.update(_flatten(item, f"{prefix}[{index}]", joint_order=joint_order))
        return flat
    if isinstance(value, str):
        # 字符串里的模块路径同表归一（rsl_rl 的 class_name 是"模块:符号"字符串）。
        value = _canon(value)
    flat[prefix] = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return flat


def _resolve_pose(pose: dict, joint: str):
    """按 mjlab 口径解析 `joint_pos` 模式串（精确名优先，再 fullmatch）。"""
    import re

    if joint in pose:
        return pose[joint]
    for key, value in pose.items():
        try:
            if re.fullmatch(key, joint):
                return value
        except re.error:  # 不是正则的键：按字面名比
            if key == joint:
                return value
    return None


def _joint_order(raw: str | None = None) -> tuple[str, ...]:
    """姿态归一用的关节序。

    不传 = 历史行为（go2 契约 `action.joint_order`）；`robot:<robot_id>` 从
    `assets/robots/<robot_id>/contract.json` 的 `action.joint_order` 读；其它字符串
    按 JSON 列表解析。机型入口上移时用 `--joint-order robot:<机型>` 让
    `/init_state/joint_pos/@resolved` 覆盖**该机型自己的全部关节**（默认 go2 序只覆盖
    go2 的 12 个关节名，对轮足等异序机型会漏掉轮关节的姿态比对）。
    """
    if raw:
        if raw.startswith("robot:"):
            robot_id = raw.split(":", 1)[1]
            contract = json.loads(
                (ROOT / "assets" / "robots" / robot_id / "contract.json").read_text(encoding="utf-8-sig")
            )
            return tuple(str(name) for name in contract["action"]["joint_order"])
        return tuple(str(name) for name in json.loads(raw))
    contract = json.loads(
        (ROOT / "assets" / "robots" / "unitree_go2" / "contract.json").read_text(encoding="utf-8-sig")
    )
    return tuple(contract["action"]["joint_order"])


def diff(before_path: Path, after_path: Path, *, joint_order: str | None = None) -> int:
    order = _joint_order(joint_order)
    before = _flatten(json.loads(before_path.read_text(encoding="utf-8-sig")), joint_order=order)
    after = _flatten(json.loads(after_path.read_text(encoding="utf-8-sig")), joint_order=order)
    keys = sorted(set(before) | set(after))
    raw_changed = [(key, before.get(key, "<缺>"), after.get(key, "<缺>")) for key in keys if before.get(key) != after.get(key)]
    print(f"字段总数（归一后）：{len(keys)}；不一致：{len(raw_changed)}")
    for key, was, now in raw_changed:
        print(f"  - {key}: {was} → {now}")
    return 1 if raw_changed else 0


def self_test() -> int:
    """自检：门禁本身会不会红。三条——归一有效、差异必抓、同值不误报。"""
    problems: list[str] = []
    pairs = [
        ("local_tasks.robots.unitree.go2.tasks.go2_skills.jump.mdp.rewards",
         "adapters.mjlab.kits.quadruped_kit.skills.jump.rewards"),
        ("local_tasks.robots.unitree.go2.tasks.go2_skills.shared.actions",
         "adapters.mjlab.kits.quadruped_kit.skills.mdp.actions"),
        # velocity：功率核 `go2_dof_power_penalty` → 族级 `dof_power_penalty`（同实现）
        ("local_tasks.robots.unitree.go2.mdp.rewards:go2_dof_power_penalty",
         "adapters.mjlab.kits.quadruped_kit.skills.mdp.rewards:dof_power_penalty"),
        # parkour：包内 `...tasks.parkour.mdp` ↔ 族级 `...skills.parkour.mdp`
        ("local_tasks.robots.unitree.go2.tasks.parkour.mdp.rewards",
         "adapters.mjlab.kits.quadruped_kit.skills.parkour.mdp.rewards"),
        ("local_tasks.robots.unitree.go2.tasks.parkour.rl.pie_model:PIEActorModel",
         "adapters.mjlab.kits.quadruped_kit.skills.parkour.rl.pie_model:PIEActorModel"),
        # WTW：包内 `...locomotion.wtw_mdp` ↔ 族级 `...skills.wtw.mdp`
        ("local_tasks.robots.unitree.go2.tasks.locomotion.wtw_mdp:quad_periodic_gait",
         "adapters.mjlab.kits.quadruped_kit.skills.wtw.mdp:quad_periodic_gait"),
    ]
    for old, new in pairs:
        if _canon(old) != _canon(new):
            problems.append(f"归一失效：{old} → {_canon(old)}，{new} → {_canon(new)}")
    if _resolve_pose({".*calf_joint": 0.3}, "FL_calf_joint") != 0.3:
        problems.append("姿态正则解析失效（`.*calf_joint` 应能解析到 FL_calf_joint）")
    if _module_name("local_tasks.a.b.py") != "local_tasks.a.b":
        problems.append("绝对模块路径解析失效（以 local_tasks. 开头时不该再拼 go2_skills 前缀）")
    if _module_name("jump/config.py") != "local_tasks.robots.unitree.go2.tasks.go2_skills.jump.config":
        problems.append("默认 job 模块解析失效（相对项应拼到 go2_skills 命名空间）")

    with tempfile.TemporaryDirectory() as tmp:
        same_a, same_b, changed = (Path(tmp) / name for name in ("a.json", "b.json", "c.json"))
        payload = {"env": {"k": 1, "nested": [{"v": "x"}]}}
        same_a.write_text(json.dumps(payload), encoding="utf-8")
        same_b.write_text(json.dumps(payload), encoding="utf-8")
        changed.write_text(json.dumps({"env": {"k": 2, "nested": [{"v": "x"}]}}), encoding="utf-8")
        if diff(same_a, same_b) != 0:
            problems.append("同值被误报为差异")
        if diff(same_a, changed) != 1:
            problems.append("真差异没被抓到（门禁不会红）")

    if problems:
        print("[self-test] 失败：")
        for item in problems:
            print(f"  - {item}")
        return 1
    print("[self-test] OK：归一有效、真差异必抓、同值不误报")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--diff", nargs=2, type=Path, metavar=("BEFORE", "AFTER"))
    parser.add_argument("--jobs", type=str,
                        help="覆盖默认 job 条目（JSON：[[label, module_rel, factory, kwargs], ...]）——"
                             "默认是 go2 的 trot/jump，其它技能上移时用它指定；module_rel 支持"
                             "路径形式（`jump/config.py`，按 go2_skills 命名空间解析）与绝对模块名"
                             "（`go2w_velocity.env_cfgs`）两种写法")
    parser.add_argument("--joint-order", type=str, default=None,
                        help="姿态归一用的关节序：`robot:<robot_id>` 从该机型契约 action.joint_order "
                             "读，或直接给 JSON 列表；默认 go2（历史行为）")
    parser.add_argument("--self-test", action="store_true", help="自检归一与 diff 判据（不碰训练栈）")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.diff:
        return diff(*args.diff, joint_order=args.joint_order)
    if not (args.package_root and args.source_root and args.out):
        parser.error("需要 --package-root / --source-root / --out，或 --diff BEFORE AFTER")
    jobs = _parse_jobs(args.jobs) if args.jobs else _JOBS
    run(args.package_root, args.source_root, args.out, jobs=jobs)
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    sys.exit(main())
