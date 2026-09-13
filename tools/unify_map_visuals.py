#!/usr/bin/env python3
"""统一 ``assets/maps/*.xml`` 的**视觉基调**：visual / skybox / groundplane / 光照。

**为什么需要它**：审计发现这 10 张图各写各的 ——

* ``apartment``：**完全没有** ``<visual>``（无 headlight / haze / 视角）也**没有 ``<light>``**；
* ``flat``：skybox 用 ``builtin="flat" rgb1="0 0 0"``（纯黑），headlight ``ambient 0.1`` / ``specular 0.9``；
* ``stairs`` / ``race_track`` 等：skybox 用 ``builtin="gradient"``，headlight ``ambient 0.3`` / ``specular 0``；
* ``relief`` / ``rough`` / ``slope``：缺 ``haze``；
* groundplane 的 ``reflectance`` 在 0.0 / 0.2 之间来回。

于是"同一套仿真在不同地图上观感不同"，而且改一处要改十处。

**统一到哪**：``00_resources/mjlab_new/mjlab/src/mjlab/scene/scene.xml`` —— mjlab 的**官方可视化
默认**（headlight ``0.6/0.3/0``、haze ``0.15 0.25 0.35 1``、``azimuth 135 elevation -25``）；
地面与光照取同一族参考实现 ``00_resources/parkour_mjlab`` 的场景口径（gradient skybox +
checker groundplane + 一盏 directional light）。

**唯一一处不照抄**：mjlab 用 ``shadowsize="8192"``，这里降到 **4096**（MuJoCo 自身默认）。
理由很实际：这些图要在**浏览器 WASM** 里跑，8192² 的阴影贴图代价过高；4096 已比现在
（多数文件根本没写 ``<quality>``）好得多。

**改视觉不许动物理**：``--apply`` 前后比对**物理指纹**（nbody/ngeom/nq/nv/nu/总质量），
不一致就回滚并拒绝 —— "统一贴图"不能顺手把碰撞体也改了。

用法::

    python tools/unify_map_visuals.py              # 只报告（CI：不一致即红）
    python tools/unify_map_visuals.py --apply      # 改写
    python tools/unify_map_visuals.py --json       # 机器可读
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAPS_DIR = ROOT / "assets" / "maps"

#: 统一口径的出处（写进报告，便于追溯"为什么是这几个数"）
UNIFIED_SOURCE = {
    "visual": "00_resources/mjlab_new/mjlab/src/mjlab/scene/scene.xml",
    "skybox_ground_light": "00_resources/parkour_mjlab/deploy/parkour/sim2sim/assets/scene_parkour.xml",
    "shadowsize_override": "mjlab 用 8192；此处降到 4096（MuJoCo 默认）以免浏览器 WASM 阴影贴图过重",
}

UNIFIED_VISUAL = """  <visual>
    <headlight diffuse="0.6 0.6 0.6" ambient="0.3 0.3 0.3" specular="0 0 0" />
    <rgba haze="0.15 0.25 0.35 1" />
    <global azimuth="135" elevation="-25" />
    <quality shadowsize="4096" />
  </visual>"""

UNIFIED_SKYBOX = (
    '    <texture type="skybox" builtin="gradient" rgb1="0.3 0.5 0.7" rgb2="0 0 0"'
    ' width="512" height="3072" />'
)
UNIFIED_GROUND_TEXTURE = (
    '    <texture type="2d" name="groundplane" builtin="checker" mark="edge"'
    ' rgb1="0.2 0.3 0.4" rgb2="0.1 0.2 0.3" markrgb="0.8 0.8 0.8"'
    ' width="300" height="300" />'
)
UNIFIED_GROUND_MATERIAL = (
    '    <material name="groundplane" texture="groundplane" texuniform="true"'
    ' texrepeat="5 5" reflectance="0.2" />'
)
UNIFIED_LIGHT = '    <light pos="0 0 3" dir="0 0 -1" directional="true" castshadow="true" />'

#: 库内统一的"地形"材质（**不新造颜色**：`slope` / `high_platforms` / `rough` 早已在用它）。
TERRAIN_MATERIAL_NAME = "terrain"
TERRAIN_MATERIAL_LINE = '    <material name="terrain" rgba="0.55 0.58 0.62 1" reflectance="0.05" />'

#: 材质里一旦出现这些字段，套上去就**不只是改外观**（会改接触摩擦/求解器/惯量）。
#: 拿它当"纯视觉材质"批量套 geom 之前必须拦下——否则"统一贴图"会顺手改物理。
MATERIAL_PHYSICS_FIELDS = ("friction", "solref", "solimp", "density", "armature", "margin")

_VISUAL_RE = re.compile(r"[ \t]*<visual>.*?</visual>\s*", re.DOTALL)
_SKYBOX_RE = re.compile(r"[ \t]*<texture[^>]*type=\"skybox\"[^>]*/>\s*")
_LIGHT_RE = re.compile(r"[ \t]*<light\b[^>]*/>\s*")
_GROUND_TEX_RE = re.compile(r"[ \t]*<texture[^>]*name=\"groundplane\"[^>]*/>\s*")
_GROUND_MAT_RE = re.compile(r"[ \t]*<material[^>]*name=\"groundplane\"[^>]*/>\s*")
_MUJOCO_OPEN_RE = re.compile(r"(<mujoco\b[^>]*>)")
_ASSET_OPEN_RE = re.compile(r"([ \t]*<asset>\s*\n)")
_WORLDBODY_OPEN_RE = re.compile(r"([ \t]*<worldbody>\s*\n)")
_TEXTURE_FILE_RE = re.compile(r"<texture\b[^>]*\bfile=\"([^\"]+)\"")
_GEOM_TAG_RE = re.compile(r"<geom\b[^>]*?/>", re.DOTALL)


def _geom_needs_material(tag: str) -> bool:
    """只有**既无 material 也无 rgba** 的 geom 才需要补——有颜色的不动它。"""
    return "material=" not in tag and "rgba=" not in tag


def terrain_material_is_visual_only(text: str) -> bool:
    """库内 ``terrain`` 材质是否**纯视觉**（不带物理字段）。

    这是"批量套材质"的安全前提：材质里若有 ``friction`` / ``solref`` 等，套到 181 个
    台阶 geom 上就变成了**物理变更**，而不是外观变更。
    """
    match = re.search(
        rf"<material\b[^>]*name=\"{TERRAIN_MATERIAL_NAME}\"[^>]*/>", text
    )
    if not match:
        return True  # 还没定义，由本工具按纯视觉版本写入
    return not any(field in match.group(0) for field in MATERIAL_PHYSICS_FIELDS)


def fill_geom_material(text: str) -> tuple[str, int]:
    """给"既无 material 也无 rgba"的 geom 套上库内统一 ``terrain`` 材质，返回 (新文本, 改动数)。

    **按行业惯例**：MuJoCo 官方 demo 与 mjlab / Menagerie 的场景，地形几何都会显式给
    材质或 rgba；什么都不写就是 ``geom.rgba`` 的默认中灰 ``0.5 0.5 0.5`` —— 与棋盘地面
    糊在一起，看不出台阶结构。本仓已有 ``terrain``（冷灰 0.55/0.58/0.62 + reflectance 0.05），
    直接复用，不再造第二种"地形色"。
    """
    added = 0

    def replace(match: re.Match) -> str:
        nonlocal added
        tag = match.group(0)
        if not _geom_needs_material(tag):
            return tag
        stripped = tag.rstrip()
        if not stripped.endswith("/>"):
            return tag
        added += 1
        return f'{stripped[:-2].rstrip()} material="{TERRAIN_MATERIAL_NAME}" />'

    out = _GEOM_TAG_RE.sub(replace, text)
    if added and f'name="{TERRAIN_MATERIAL_NAME}"' not in out and _ASSET_OPEN_RE.search(out):
        out = _ASSET_OPEN_RE.sub(
            lambda m: m.group(1) + TERRAIN_MATERIAL_LINE + "\n", out, count=1
        )
    return out, added


def missing_texture_files(text: str, base_dir: Path) -> list[str]:
    """列出 ``file="…"`` 引用了、但**磁盘上不存在**的贴图（相对 MJCF 所在目录解析）。

    这条检查是有来历的：``cross_slope.xml`` / ``cross_stairs.xml`` 引用了
    ``./imgs/label_{1,4,7,10}.png``，而 ``assets/maps/imgs/`` **从来没被一起拷过来**
    （贴图一直躺在 ``web/sim2sim/assets/go2/imgs/``）—— 于是这两张图**长期编译不过**，
    却没人发现。任何"贴图统一"如果不查这一项，等于把坏掉的东西统一成一样坏。
    """
    missing: list[str] = []
    for rel in _TEXTURE_FILE_RE.findall(text):
        if not (base_dir / rel).exists():
            missing.append(rel)
    return missing


def _normalize(text: str) -> str:
    """把连续空白压成单空格 —— 比较"语义相同、排版不同"的两个标签时用。"""
    return re.sub(r"\s+", " ", text).strip()


def map_files(directory: Path | None = None) -> list[Path]:
    return sorted((directory or MAPS_DIR).glob("*.xml"))


def inspect(text: str, base_dir: Path | None = None) -> dict[str, Any]:
    """报告一个文件里四类元素的现状 + 外部贴图是否齐全（纯文本分析，不改文件）。"""
    visual = _VISUAL_RE.search(text)
    light = _LIGHT_RE.search(text)
    skybox = _SKYBOX_RE.search(text)
    ground_tex = _GROUND_TEX_RE.search(text)
    ground_mat = _GROUND_MAT_RE.search(text)
    return {
        "has_visual": visual is not None,
        "visual_matches": bool(visual) and _normalize(visual.group(0)) == _normalize(UNIFIED_VISUAL),
        "has_light": light is not None,
        "light_matches": bool(light) and _normalize(light.group(0)) == _normalize(UNIFIED_LIGHT),
        "has_skybox": skybox is not None,
        "skybox_matches": bool(skybox)
        and _normalize(skybox.group(0)) == _normalize(UNIFIED_SKYBOX),
        "has_groundplane": ground_tex is not None or ground_mat is not None,
        "groundplane_matches": (
            (
                ground_tex is None
                or _normalize(ground_tex.group(0)) == _normalize(UNIFIED_GROUND_TEXTURE)
            )
            and (
                ground_mat is None
                or _normalize(ground_mat.group(0)) == _normalize(UNIFIED_GROUND_MATERIAL)
            )
        ),
        # 有 plane 几何体才算"需要地面材质"的地图；室内图（apartment）没有，就不该硬塞 checker 地面
        "uses_plane_geom": bool(re.search(r"<geom[^>]*type=\"plane\"", text)),
        "missing_textures": missing_texture_files(text, base_dir) if base_dir else [],
        # 既无 material 也无 rgba 的 geom 数 —— 它们渲染成 MuJoCo 默认中灰，看不出结构
        "bare_geoms": sum(1 for tag in _GEOM_TAG_RE.findall(text) if _geom_needs_material(tag)),
        "terrain_material_visual_only": terrain_material_is_visual_only(text),
    }


def unify_text(text: str, report: dict[str, Any]) -> str:
    """文本级定点替换：只碰 visual / skybox / groundplane / light，**不动 worldbody 的几何体**。

    刻意不用 ElementTree 重序列化：``race_track.xml`` 有 236 个 geom 挤在 21 行里，
    重排会把 48 KB 膨胀成几百 KB，diff 也彻底不可读。这里是"整块换整块"。
    """
    out = text

    # ① <visual>：有就整块换，没有就插到 <mujoco ...> 之后（视觉基调必须一致）
    if report["has_visual"]:
        out = _VISUAL_RE.sub(UNIFIED_VISUAL + "\n", out, count=1)
    else:
        out = _MUJOCO_OPEN_RE.sub(lambda m: m.group(1) + "\n" + UNIFIED_VISUAL, out, count=1)

    # ② skybox：有就换，没有插在 <asset> 开头
    if report["has_skybox"]:
        out = _SKYBOX_RE.sub(UNIFIED_SKYBOX + "\n", out, count=1)
    elif _ASSET_OPEN_RE.search(out):
        out = _ASSET_OPEN_RE.sub(lambda m: m.group(1) + UNIFIED_SKYBOX + "\n", out, count=1)

    # ③ groundplane：**只在该文件真的用了平面地面时才统一**（室内图不硬塞 checker 地面）
    if report["has_groundplane"]:
        if _GROUND_TEX_RE.search(out):
            out = _GROUND_TEX_RE.sub(UNIFIED_GROUND_TEXTURE + "\n", out, count=1)
        if _GROUND_MAT_RE.search(out):
            out = _GROUND_MAT_RE.sub(UNIFIED_GROUND_MATERIAL + "\n", out, count=1)
    elif report["uses_plane_geom"] and _ASSET_OPEN_RE.search(out):
        # 有平面地面却没定义材质：texture 与 material 必须**成对**插入（缺一个 MuJoCo 会拒编译）
        out = _ASSET_OPEN_RE.sub(
            lambda m: m.group(1)
            + UNIFIED_GROUND_TEXTURE
            + "\n"
            + UNIFIED_GROUND_MATERIAL
            + "\n",
            out,
            count=1,
        )

    # ④ <light>：有就换（统一方向与投影范围），没有就插在 <worldbody> 开头
    if report["has_light"]:
        out = _LIGHT_RE.sub(UNIFIED_LIGHT + "\n", out, count=1)
    elif _WORLDBODY_OPEN_RE.search(out):
        out = _WORLDBODY_OPEN_RE.sub(lambda m: m.group(1) + UNIFIED_LIGHT + "\n", out, count=1)

    return out


def physical_fingerprint(path: Path) -> dict[str, Any] | None:
    """物理指纹：改视觉**不许**动这些数（nbody/ngeom/nq/nv/nu/总质量）。"""
    try:
        import mujoco

        model = mujoco.MjModel.from_xml_path(str(path))
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    return {
        "nbody": int(model.nbody),
        "ngeom": int(model.ngeom),
        "nq": int(model.nq),
        "nv": int(model.nv),
        "nu": int(model.nu),
        "mass": round(float(model.body_mass.sum()), 6),
    }


def needs_unify(report: dict[str, Any]) -> bool:
    return (
        not (
            report["visual_matches"]
            and report["light_matches"]
            and report["skybox_matches"]
            and report["groundplane_matches"]
        )
        or bool(report.get("missing_textures"))
        or bool(report.get("bare_geoms"))
    )


def _both_uncompilable(before: Any, after: Any) -> bool:
    """两边都编译不过 ⇒ 是**预先存在**的问题（例如缺贴图），不是本工具改坏的。"""
    return (
        isinstance(before, dict)
        and isinstance(after, dict)
        and "error" in before
        and "error" in after
    )


def run(apply: bool = False, directory: Path | None = None) -> dict[str, Any]:
    base = directory or MAPS_DIR
    entries: list[dict[str, Any]] = []
    for path in map_files(directory):
        text = path.read_text(encoding="utf-8")
        report = inspect(text, base)
        entry: dict[str, Any] = {"file": path.name, **report}
        entry["needs_unify"] = needs_unify(report)
        # 只在**视觉真的不一致**时才改写；单纯"缺贴图"是资源问题，改写 XML 救不了它（要补文件），
        # 所以那种情况下只报告、不动文件（免得白白改一遍 mtime）。
        visual_mismatch = not (
            report["visual_matches"]
            and report["light_matches"]
            and report["skybox_matches"]
            and report["groundplane_matches"]
        )
        bare = int(entry.get("bare_geoms") or 0)
        if apply and not report.get("terrain_material_visual_only", True):
            # 安全前提：库内 terrain 材质若带物理字段，批量套 geom 就变成改物理，直接拒绝
            entry["applied"] = False
            entry["rejected"] = (
                "库内 terrain 材质带物理字段（friction/solref/solimp/density/armature/margin）；"
                "套到地形 geom 上会改接触摩擦，属于物理变更而非外观变更"
            )
        elif apply and (visual_mismatch or bare):
            before = physical_fingerprint(path)
            unified = unify_text(text, report) if visual_mismatch else text
            unified, filled = fill_geom_material(unified)
            entry["geoms_filled"] = filled
            path.write_text(unified, encoding="utf-8")
            after = physical_fingerprint(path)
            entry["physics_before"] = before
            entry["physics_after"] = after
            if before != after and not _both_uncompilable(before, after):
                path.write_text(text, encoding="utf-8")  # 真的把能编译的改坏了 → 回滚
                entry["applied"] = False
                entry["rejected"] = f"物理指纹变了：{before} → {after}"
            else:
                entry["applied"] = True
                if _both_uncompilable(before, after):
                    # 记下来：这张图**本来就**编译不过（缺贴图等），视觉统一救不了它
                    entry["pre_existing_error"] = before["error"]
            entry["needs_unify"] = not needs_unify(inspect(path.read_text(encoding="utf-8"), base))
        entries.append(entry)
    return {
        "directory": str(directory or MAPS_DIR),
        "applied": apply,
        "source": UNIFIED_SOURCE,
        "files": entries,
        "pending": [entry["file"] for entry in entries if entry["needs_unify"]],
        "rejected": [entry["file"] for entry in entries if entry.get("rejected")],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="统一地图视觉基调（visual/skybox/groundplane/light）")
    parser.add_argument("--apply", action="store_true", help="实际改写（默认只报告）")
    parser.add_argument("--directory", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run(apply=args.apply, directory=args.directory)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[{'APPLY' if args.apply else 'CHECK'}] {report['directory']}")
        for entry in report["files"]:
            marks = "".join(
                [
                    "V" if entry["visual_matches"] else "v",
                    "L" if entry["light_matches"] else "l",
                    "S" if entry["skybox_matches"] else "s",
                    "G" if entry["groundplane_matches"] else "g",
                ]
            )
            note = ""
            if entry.get("rejected"):
                note = f"  [拒绝] {entry['rejected']}"
            elif entry.get("applied"):
                note = "  → 已统一"
            elif entry["needs_unify"]:
                note = "  ← 待统一"
            if entry.get("missing_textures"):
                note += f"  [缺贴图] {entry['missing_textures']}"
            if entry.get("geoms_filled"):
                note += f"  [补地形材质 {entry['geoms_filled']} 个 geom]"
            elif entry.get("bare_geoms"):
                note += f"  [裸 geom {entry['bare_geoms']}]"
            if entry.get("pre_existing_error"):
                note += "  [本来就编译不过]"
            print(
                f"  {entry['file']:<20} visual={'有' if entry['has_visual'] else '无'}"
                f" light={'有' if entry['has_light'] else '无'}"
                f" skybox={'有' if entry['has_skybox'] else '无'}"
                f" 一致[{marks}]{note}"
            )
        print(f"  统一口径来源：{UNIFIED_SOURCE['visual']}")
        if report["rejected"]:
            print(f"  被拒（物理指纹变了）：{report['rejected']}")
        print(f"  待统一：{len(report['pending'])} / {len(report['files'])}  {report['pending']}")

    if report["rejected"]:
        return 3
    if not args.apply and report["pending"]:
        return 2  # CI 语义：视觉漂移即红
    return 0


if __name__ == "__main__":
    sys.exit(main())
