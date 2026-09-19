#!/usr/bin/env python3
"""把契约真值 的物理真值固化进包内 MJCF —— 消灭运行时"猴子补丁"（B-系列：单一真值）。

背景
----
此前有四处运行时补丁在**替包内资产擦屁股**，导致"工作台里看到的 MJCF"与"真正跑起来
的物理"不是同一份：

1. ``backend/simulation_browser.py::configure_browser_actuators`` 与
   ``adapters/mjlab/policy_acceptance.py::apply_actuator_rebuild``——同一逻辑两份实现，
   会把 ``<actuator>`` 整段删掉后按契约重建。b2w 这类资产 ``nu=0`` 却能跑，就是靠它。
2. ``load_package_model`` 编译前注入 ``armature`` / ``frictionloss``（覆盖 XML default）。
3. ``scene_physics_overrides`` 把 scene 的 ``<option>`` 搬到验收模型上（TRON1 事故驱动）。
4. ``model.opt.timestep`` 用契约 ``physics_hz`` 覆盖。

本工具把 1/2/3 固化成**资产的一次性事实**，运行时只留第 4 条——它不是补丁：契约
``control.physics_hz`` 是步长的唯一家，MJCF 不再声明 ``timestep``（避免"文件撒谎"）。

执行后
------
* ``model/robot.xml`` 自带 ``<option>``（**不含 timestep**），逐关节 ``armature`` /
  ``frictionloss`` 与 ``<actuator>`` 段（kp/kv/forcerange/mode）全部与契约逐项一致；
* ``simulation/*.xml`` 不再重复声明 ``<option>``——``<include>`` 里的 option 实测生效
  （见 :func:`python -c` 验证），物理真值只剩 ``model/robot.xml`` 一处；
  场景自身不 ``<include>`` 机器人的（自包含场景）**保持不动**，避免改坏场景。

安全性
------
* **fail-closed**：契约缺 ``effort`` / ``stiffness`` / ``damping`` 时直接报错，
  不沿用运行时那套 ``or 40.0 / or 20.0 / or 1.0`` 静默兜底（那正是"错但不报错"的来源）。
* 只重写**绑定到契约驱动关节**的执行器元素，其余（tendon/site 执行器等）原样保留。
* 幂等：重复执行不产生新差异；``--check`` 只报告并以退出码 1 结束（门禁用）。
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

OPTION_SELF_CLOSING = re.compile(r"[ \t]*<option\b([^>]*?)/>[ \t]*\n?")
OPTION_WITH_CHILD = re.compile(r"[ \t]*<option\b([^>]*?)>(.*?)</option>[ \t]*\n?", re.DOTALL)
ATTR_RE = re.compile(r'([A-Za-z_][\w.-]*)\s*=\s*"([^"]*)"')
#: 通用元素匹配。执行器段的标签不只有 motor/position/velocity——实测 g1 与 zex-w 用的是
#: ``<general>``，旧版只认前三种，于是把**已有**元素当成"缺失"再追加一遍（nu 翻倍 /
#: 重名报错）。教训：匹配要按"是否绑定契约关节"判断，不能按标签白名单。
TAG_RE = re.compile(r"<(?P<tag>[A-Za-z_][\w.-]*)\b(?P<attrs>[^>]*?)/?>")
ACTUATOR_BLOCK_RE = re.compile(r"(?P<head>[ \t]*<actuator\b[^>]*>)(?P<body>.*?)(?P<tail>[ \t]*</actuator>)", re.DOTALL)
INCLUDE_RE = re.compile(r'<include\b[^>]*file\s*=\s*"([^"]+)"')

OPTION_TRUTH_COMMENT = "  <!-- timestep 不在此声明：运行时统一取 contract.json control.physics_hz -->"
SCENE_OPTION_COMMENT = "  <!-- 物理真值已固化进 model/robot.xml（<include> 的 <option> 实测生效，此处不再重复声明） -->"


def _attrs(text: str) -> dict[str, str]:
    return {key: value for key, value in ATTR_RE.findall(text)}


def _fmt(value: object) -> str:
    if isinstance(value, float):
        text = f"{value:g}"
        return text
    return str(value)


def render_actuator(joint: str, params: dict, indent: str) -> str:
    """按契约参数渲染执行器元素（与浏览器/验收重建逻辑逐项同口径）。"""
    mode = str(params.get("mode") or "position")
    effort = params.get("effort")
    if effort is None:
        raise ValueError(f"{joint}: 契约缺 effort，无法固化 forcerange（不静默兜底）")
    effort = float(effort)
    forcerange = f'forcerange="{-effort:g} {effort:g}" forcelimited="true"'
    if mode == "torque":
        name = joint[: -len("_joint")] if joint.endswith("_joint") else joint
        return f'{indent}<motor name="{name}" joint="{joint}" gear="1" {forcerange} />'
    damping = params.get("damping")
    if damping is None:
        raise ValueError(f"{joint}: 契约缺 damping（mode={mode}），无法固化 kv（不静默兜底）")
    kv = _fmt(float(damping))
    if mode == "velocity":
        return f'{indent}<velocity name="{joint}" joint="{joint}" kv="{kv}" {forcerange} />'
    stiffness = params.get("stiffness")
    if stiffness is None:
        raise ValueError(f"{joint}: 契约缺 stiffness（mode=position），无法固化 kp（不静默兜底）")
    return (
        f'{indent}<position name="{joint}" joint="{joint}" '
        f'kp="{_fmt(float(stiffness))}" kv="{kv}" {forcerange} />'
    )


def merge_options(*option_texts: str | None) -> dict[str, str]:
    """合并机器人/场景的 ``<option>`` 属性；场景值优先（今天 scene-rooted 加载的口径）。"""
    merged: dict[str, str] = {}
    for text in option_texts:
        if not text:
            continue
        merged.update(_attrs(text))
    merged.pop("timestep", None)
    return merged


def _option_attrs(source: str) -> str | None:
    for regex in (OPTION_SELF_CLOSING, OPTION_WITH_CHILD):
        match = regex.search(source)
        if match:
            return match.group(1)
    return None


def _option_inner(source: str) -> str:
    match = OPTION_WITH_CHILD.search(source)
    return match.group(2).strip() if match else ""


#: 本工具写入的注释标记（幂等清理用：重复执行不会堆注释）
COMMENT_MARKERS = (OPTION_TRUTH_COMMENT.strip(), SCENE_OPTION_COMMENT.strip())


def _strip_option_and_comment(source: str) -> str:
    """移除既有 ``<option>`` 与本工具写入的注释（先清后写 = 幂等）。"""
    if OPTION_WITH_CHILD.search(source):
        source = OPTION_WITH_CHILD.sub("", source, count=1)
    elif OPTION_SELF_CLOSING.search(source):
        source = OPTION_SELF_CLOSING.sub("", source, count=1)
    for marker in COMMENT_MARKERS:
        source = re.sub(rf"[ \t]*{re.escape(marker)}[ \t]*\n?", "", source)
    return source


def _insert_after_compiler(source: str, text: str) -> str:
    """把文本插到 ``<compiler .../>`` 之后（MJCF 顶层顺序要求 option 紧跟 compiler）。"""
    anchor = re.compile(r"[ \t]*<compiler\b[^>]*/>[ \t]*\n")
    match = anchor.search(source)
    if match:
        return source[: match.end()] + text + source[match.end() :]
    header = re.compile(r"[ \t]*<mujoco\b[^>]*>[ \t]*\n")
    match = header.search(source)
    if match:
        return source[: match.end()] + text + source[match.end() :]
    return text + source


def _replace_option(source: str, *, attrs: dict[str, str], inner: str, comment: str) -> str:
    """把 ``<option>`` 规范化：注释 + 元素（无 timestep）。先清后写，保证幂等。"""
    stripped = _strip_option_and_comment(source)
    body = " ".join(f'{key}="{value}"' for key, value in attrs.items())
    if inner:
        element = f"  <option {body}>\n{inner}\n  </option>\n" if body else f"  <option>\n{inner}\n  </option>\n"
    else:
        element = f"  <option {body} />\n" if body else ""
    return _insert_after_compiler(stripped, f"{comment}\n{element}")


def bake_joint_constants(source: str, tables: dict) -> tuple[str, list[str]]:
    """就地补/改每个驱动关节的 ``armature`` / ``frictionloss``。

    **外科式**：只动这两个属性的值（或在其后插入），元素其余部分逐字节保留——早期版本
    重建整个元素，导致属性顺序与 ``/>`` 风格全变，35 KB 的模型出现上百行无意义 diff。
    """
    armature = tables["armature"]
    friction = tables["frictionloss"]
    changed = False

    def rewrite(match: re.Match[str]) -> str:
        nonlocal changed
        tag = match.group("tag")
        if tag == "freejoint":
            # freejoint **不接受** armature/frictionloss（MJCF schema 直接报错）。
            # 这里顺手清理早期版本误写的属性，使固化幂等且能自愈。
            element = match.group(0)
            cleaned = re.sub(r'\s+(?:armature|frictionloss)\s*=\s*"[^"]*"', "", element)
            if cleaned != element:
                changed = True
            return cleaned
        if tag != "joint":
            return match.group(0)
        element = match.group(0)
        attrs = _attrs(match.group("attrs"))
        name = attrs.get("name")
        if not name:
            return element
        lowered = name.lower()
        wanted: dict[str, str] = {}
        arm = armature.get(lowered, armature.get("__default__"))
        fric = friction.get(lowered, friction.get("__default__"))
        if arm is not None:
            wanted["armature"] = _fmt(float(arm))
        if fric is not None:
            wanted["frictionloss"] = _fmt(float(fric))
        if not wanted:
            return element

        new_element = element
        for key, value in wanted.items():
            pattern = re.compile(rf'(\b{key}\s*=\s*)"[^"]*"')
            found = pattern.search(new_element)
            if found:
                if found.group(0) != f'{key}="{value}"':
                    new_element = pattern.sub(lambda _m, v=value: f'{key}="{v}"', new_element, count=1)
            else:
                close = re.search(r"\s*/>", new_element)
                if close is None:
                    return element
                new_element = new_element[: close.start()] + f' {key}="{value}"' + new_element[close.start() :]
        if new_element != element:
            changed = True
        return new_element

    new_source = TAG_RE.sub(rewrite, source)
    return new_source, (["joint_constants"] if changed else [])


def bake_actuators(source: str, expanded: dict[str, dict], order: list[str]) -> tuple[str, list[str]]:
    """把 ``<actuator>`` 段重写为契约口径（只碰契约驱动关节，其余保留）。

    判定"是否属于契约关节"只看元素绑定的关节名（``joint`` / ``jointinparent``），
    与标签无关——否则 ``<general>`` 这类元素会被漏掉并造成重复追加。
    追加时按契约 ``action.joint_order`` 顺序（与运行时重建同口径）。
    """
    notes: list[str] = []
    match = ACTUATOR_BLOCK_RE.search(source)
    if match is None:
        lines = ["  <actuator>"]
        for joint in order:
            lines.append(render_actuator(joint, expanded[joint], "    "))
        lines.append("  </actuator>")
        block = "\n".join(lines) + "\n"
        anchor = re.search(r"[ \t]*<sensor\b", source) or re.search(r"</mujoco>", source)
        if anchor is None:
            raise ValueError("MJCF 缺 </mujoco>，无法插入 <actuator>")
        return source[: anchor.start()] + block + source[anchor.start() :], ["actuator_block_created"]

    body = match.group("body")
    replaced: set[str] = set()
    cursor = 0
    pieces: list[str] = []
    for element in TAG_RE.finditer(body):
        pieces.append(body[cursor : element.start()])
        cursor = element.end()
        attrs = _attrs(element.group("attrs"))
        joint = attrs.get("joint") or attrs.get("jointinparent")
        if joint is None or joint not in expanded:
            pieces.append(element.group(0))
            continue
        line_start = body.rfind("\n", 0, element.start()) + 1
        element_indent = body[line_start : element.start()]
        element_indent = element_indent if element_indent.strip() == "" else "    "
        pieces.append(render_actuator(joint, expanded[joint], element_indent))
        replaced.add(joint)
    pieces.append(body[cursor:])
    new_body = "".join(pieces)

    missing = [joint for joint in order if joint not in replaced]
    if missing:
        extra = "\n".join(render_actuator(joint, expanded[joint], "    ") for joint in missing)
        new_body = new_body.rstrip("\n") + "\n" + extra + "\n"
        notes.append(f"actuator_added:{len(missing)}")

    if new_body != body:
        notes.append("actuator_block")
    return source[: match.start("body")] + new_body + source[match.end("body") :], notes


def bake_package(package_dir: Path, *, write: bool) -> dict:
    """固化单个包；返回变更摘要（``changed`` 为 False 表示已是最新）。"""
    contract_path = package_dir / "contract.json"
    model_path = package_dir / "model" / "robot.xml"
    if not contract_path.is_file() or not model_path.is_file():
        return {"package": package_dir.name, "skipped": "缺 contract.json 或 model/robot.xml"}

    contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
    expanded = RoleResolver(contract).expand_actuator_profile()
    tables = joint_constant_tables(package_dir)
    scalars = physics_scalars(package_dir)

    sim_cfg_path = package_dir / "simulation" / "config.json"
    sim_cfg = json.loads(sim_cfg_path.read_text(encoding="utf-8-sig")) if sim_cfg_path.is_file() else {}
    scene_path = (package_dir / str(sim_cfg.get("scene_path"))) if sim_cfg.get("scene_path") else None

    model_text = model_path.read_text(encoding="utf-8-sig")
    scene_text = scene_path.read_text(encoding="utf-8-sig") if scene_path and scene_path.is_file() else None

    # 1) option：合并机器人/场景（场景优先），去掉 timestep
    attrs = merge_options(_option_attrs(model_text), _option_attrs(scene_text) if scene_text else None)
    inner = _option_inner(model_text) or (_option_inner(scene_text) if scene_text else "")
    new_model = _replace_option(model_text, attrs=attrs, inner=inner, comment=OPTION_TRUTH_COMMENT)

    order = [joint for joint in list((contract.get("action") or {}).get("joint_order") or expanded) if joint in expanded]

    # 2) 逐关节常量（对全部包都安全：运行时本来就强制注入契约值，固化 = 行为不变）
    new_model, _ = bake_joint_constants(new_model, tables)

    # 3) 执行器：**只固化"靠补丁活着"的包**。
    #    判据是 browser_actuator_rebuild：这些包的 MJCF 执行器段是坏的/空的（b2w nu=0），
    #    运行时（浏览器 + 验收各一份实现）本就把整段删掉按契约重建——固化 = 行为不变。
    #    反例（go1 的 kp=35 vs 契约 20、g1 的 <general>、wuji 的 _actuator 命名）：这些包
    #    **没有补丁**，MJCF 就是执行真值，用契约覆盖会**真的改变物理**。此时不动，
    #    差异交由校验器显式报出（"契约与 MJCF 漂移"是事实，不能靠覆盖掩盖）。
    actuator_baked = False
    if sim_cfg.get("browser_actuator_rebuild"):
        new_model, _ = bake_actuators(new_model, expanded, order)
        actuator_baked = True

    outs: list[tuple[Path, str]] = []
    if new_model != model_text:
        outs.append((model_path, new_model))

    # 4) 场景不再声明 option（仅在场景 include 机器人时；自包含场景保持不动）
    if scene_text and _option_attrs(scene_text):
        includes = INCLUDE_RE.findall(scene_text)
        robot_included = any(Path(rel).name == model_path.name for rel in includes)
        if robot_included:
            stripped = OPTION_WITH_CHILD.sub("", scene_text, count=1) if OPTION_WITH_CHILD.search(scene_text) else scene_text
            stripped = OPTION_SELF_CLOSING.sub("", stripped, count=1)
            stripped = _insert_scene_comment(stripped)
            if stripped != scene_text:
                outs.append((scene_path, stripped))

    if write:
        for path, text in outs:
            path.write_text(text, encoding="utf-8")

    return {
        "package": package_dir.name,
        "physics_hz": scalars.get("physics_hz"),
        "actuated": len(expanded),
        "option": attrs,
        "actuator_baked": actuator_baked,
        "changed": bool(outs),
        "files": [str(path.relative_to(package_dir)) for path, _ in outs],
    }


def _insert_scene_comment(source: str) -> str:
    match = re.search(r"[ \t]*<compiler\b[^>]*/>[ \t]*\n", source)
    if match:
        return source[: match.end()] + SCENE_OPTION_COMMENT + "\n" + source[match.end() :]
    return SCENE_OPTION_COMMENT + "\n" + source


def iter_packages(root: Path, only: str | None) -> list[Path]:
    packages = sorted(path for path in (root / "assets" / "robots").iterdir() if (path / "contract.json").is_file())
    if only:
        packages = [path for path in packages if path.name == only]
    return packages


def main() -> int:
    parser = argparse.ArgumentParser(description="把契约真值 物理真值固化进包内 MJCF")
    parser.add_argument("--check", action="store_true", help="只报告差异（有差异则退出码 1），不写文件")
    parser.add_argument("--only", default=None, help="只处理指定机器人包目录名")
    parser.add_argument("--quiet", action="store_true", help="只打印有变更的包")
    args = parser.parse_args()

    reports = []
    for package in iter_packages(ROOT, args.only):
        try:
            reports.append(bake_package(package, write=not args.check))
        except Exception as exc:  # fail-closed：固化不了就报错，不静默跳过
            print(f"[FAIL] {package.name}: {type(exc).__name__}: {exc}")
            return 2

    changed = [report for report in reports if report.get("changed")]
    for report in reports:
        if args.quiet and not report.get("changed"):
            continue
        mark = "CHANGED" if report.get("changed") else "clean"
        detail = report.get("skipped") or report.get("files") or ""
        act = "执行器:契约固化" if report.get("actuator_baked") else "执行器:MJCF为准(未动)"
        print(f"[{mark}] {report['package']:<24} {act:<20} {detail}")

    print(f"\n共 {len(reports)} 包，需固化 {len(changed)} 包")
    if args.check and changed:
        print("存在未固化差异：请运行 `python tools/bake_mjcf_physics.py` 后重新检查")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
