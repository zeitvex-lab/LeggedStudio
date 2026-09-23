"""M1 Motion 注册表：把「Motion 参考动作」从散落在包里的文件变成**一等资源**。

## 为什么要有它

`01_项目定位` 的「内容模型 = 五份一等资源」里，**Motion 参考动作**（动作序列 + fps /
坐标系 / dof 布局 + 重定向血缘 + 许可）与 Morphology / Skill / Scenario / Policy 同级。
但本仓此前**只有文件、没有资源层**：`registry/packs/imitation_amp.json` 自己写着
「仓内 motion 注册表尚未建立，缺失时挂载会失败」。

本模块补的就是那一层，判据全部**从文件本身派生**（可复核），不靠人工填表：

* ``fps`` / ``dof_dim`` —— 直接读文件（pkl 的 ``fps`` / ``dof_pos``、npz 的 ``fps`` / ``joint_pos``）；
* ``dof_layout`` —— 由 dof 宽度命名（``unitree_dds_29``），依据是加载器的字段契约
  （tracking 侧的加载器文档串明写 "dof_pos (F, 29) joint angles, robot (DDS)
  joint order"）；
* ``lineage`` —— 出处与转换链（tracking 的 pkl 由 `LeggedGym-Ex` retarget 管线产出，
  raw 原文件不在仓，如实登记）；
* ``license`` —— 与 I5 同口径：**没有许可记录的 motion 不得进注册表**；许可确未取证时
  必须**显式登记**（``status: unresolved`` + 原因 + 依据），不许留空、也不许编一个。

**2026-09-23 族架构收敛（只留 8 机型）后的仓内实况**：`unitree_g1` 包整包删除，随它退场的
tracking（pkl，逐引擎变体）与 amp（npz）两侧数据**在仓内已一份不剩** —— 现存的 motion 数据
只有浏览器侧 CSV（`<包>/simulation/policies/*_motion.csv`）。两类训练侧布局的派生规则与
出处模板**作为机制保留**（重新引入参考动作库时直接复用），但出处指向 `00_resources` 里的
上游快照，不再指向已删除的包内路径。

## 布局（派生规则，写死在这里而不是散在各处）

1. ``tracking-variants``：``*_stageii{,.rawconv,_genesis,_isaacgym,_isaaclab}.pkl``
   —— 同一个动作的 raw 转换产物 + 逐仿真引擎重定向产物（**血缘就在这里**）；
2. ``amp-dirs``：``<...>/motions/<robot>/amp/<Group>/<name>.npz`` —— variant = 分组目录名；
3. ``browser-csv``：``<包>/simulation/policies/*_motion.csv`` —— 浏览器侧变体
   （variant = ``browser``，由 ``web/sim2sim/motion_loader.js`` 消费）；
4. ``flat``：其余（兜底，variant = ``default``）。

风格：纯 stdlib（numpy 仅按需 import，供读 npz）。
"""

from __future__ import annotations

import json
import pickle
import re
from pathlib import Path
from typing import Any

from contracts.validator import normalized_sha256
from backend.jsonio import read_json  # JSON 读取唯一实现

ROOT = Path(__file__).resolve().parents[1]
ROBOTS_DIR = ROOT / "assets" / "robots"
INDEX_PATH = ROOT / "registry" / "motions" / "index.json"
SCHEMA_VERSION = "motion-registry-1.0"

#: 每条 motion 必须有这些字段；缺任一项即拒（门禁判据）。
REQUIRED_FIELDS = (
    "id", "robot", "source", "format", "fps", "dof_layout", "dof_dim",
    "conventions", "lineage", "license", "files",
)
SUPPORTED_FORMATS = ("pkl", "npz", "csv")

#: tracking 布局的变体后缀 → 语义（`_stageii.rawconv.pkl` 是本仓转换出来的那份）。
TRACKING_VARIANTS = {
    "rawconv": "_stageii.rawconv.pkl",
    "genesis": "_stageii_genesis.pkl",
    "isaacgym": "_stageii_isaacgym.pkl",
    "isaaclab": "_stageii_isaaclab.pkl",
}
_TRACKING_STEM = re.compile(r"^(?P<clip>.+)_stageii(?:\.rawconv|_genesis|_isaacgym|_isaaclab)?\.pkl$")

#: 出处（可复核的原文位置 + 本仓转换脚本）。**2026-09-23 族架构收敛**：tracking 侧的数据
#: （连同包内证据文件与 `tools/convert_raw_motion_pkls.py` 这个一次性转换脚本）随
#: `unitree_g1` 包一起删除，所以出处改指 `00_resources` 里的上游快照；重新引入 tracking
#: 数据时按实测重填 evidence / conversion_script，不要照抄这段。
_TRACKING_LINEAGE = {
    "pipeline": "LeggedGym-Ex retarget（BSD-3-Clause）",
    "raw": None,
    "raw_note": "raw（AMASS stage-II）原文件不在仓内；仓内曾有的转换产物与逐引擎重定向产物已随 unitree_g1 包删除（2026-09-23）",
    "conversion_script": None,
    "evidence": [
        "00_resources/LeggedGym-Ex/legged_gym/utils/motion_loader.py",
    ],
}

#: 坐标系/四元数约定（**只写有据可查的**；查不到就写"未取证"，不猜）。
_TRACKING_CONVENTIONS = {
    "root_pos": "world",
    "root_rot": "xyzw",
    "dof_order": "unitree DDS joint order",
    "note": "mjlab / MuJoCo 用 wxyz，加载时换序（见 tracking 侧 motion_loader.py 文档串）",
}
#: AMP（npz）布局的约定：键名带 `_w` 后缀 = world 系；四元数序未取证（**仓内当前无此类数据**，
#: 随 unitree_g1 包删除；模板保留供重新引入时使用）。
_AMP_CONVENTIONS = {
    "note": "键名带 `_w` 后缀 = world 系；**四元数序未取证**（`body_quat_w` 不含序信息，不猜）",
}
#: 浏览器侧 CSV（现存唯一的 motion 布局）：列布局与坐标系以**包内声明**为准，不在这里写死
#: 一份（`motion_params.csv_layout` / `ref_axis`，见 :func:`_declared_browser_sources`）。
_BROWSER_CONVENTIONS = {
    "note": "无表头的逐帧 CSV（root 位姿 + 关节角）；列布局 / 参考系 / 四元数序以包内策略声明的 "
            "`motion_params`（`csv_layout` / `ref_axis`）为准 —— 本模块不替它猜",
}

#: 许可：与 I5 的许可门同口径。
_TRACKING_LICENSE = {
    "status": "declared",
    "spdx": "BSD-3-Clause",
    "applies_to": "retarget 产物（LeggedGym-Ex 管线）",
    "evidence": "00_resources/LeggedGym-Ex/LICENSE",
    "upstream_dataset": {
        "name": "AMASS stage-II（文件名 `_stageii` 所指）",
        "status": "unresolved",
        "reason": "上游数据集许可是独立的（AMASS 系通常限学术/非商用），本仓未取证 —— 不含在 BSD-3 之内",
    },
}
#: AMP npz 布局的出处模板（**仓内当前无此类数据**；出处指向 00_resources 的上游快照）。
_AMP_LINEAGE = {
    "pipeline": "AMP（HumanoidVerse / AMP_mjlab 系）",
    "raw": None,
    "raw_note": "数据直接以 npz 形式入库，仓内无更上游的原始来源；含此类数据的 unitree_g1 包已于 2026-09-23 删除",
    "conversion_script": None,
    "evidence": [
        "00_resources/AMP_mjlab/src/tasks/amp_loco/config/g1/rl_cfg.py",
    ],
}
#: AMP npz 布局的许可模板（**仓内当前无此类数据**；出处指向 00_resources 的上游快照）。
_AMP_LICENSE = {
    "status": "unresolved",
    "spdx": None,
    "reason": "AMP 动作 npz 数据本身的出处与许可未取证（上游 `AMP_mjlab` 源码注释只声明其 rsl_rl "
              "分支为 BSD-3-Clause，数据本身没写）；含此类数据的 unitree_g1 包已于 2026-09-23 删除",
    "evidence": [
        "00_resources/AMP_mjlab/src/tasks/amp_loco/config/g1/rl_cfg.py",
    ],
}


def _read_json(path: Path) -> Any:
    """读 JSON；缺失 / 坏内容一律 ``None``（实现见 ``backend.jsonio``）。"""

    return read_json(path, default=None)


def _sha256(path: Path) -> str | None:
    try:
        # B39 口径（2026-09-17 对齐）：规范化内容哈希（CRLF → LF）。5 个浏览器 CSV 是文本文件，
        # Windows 检出是 CRLF，原始字节哈希会与注册表里按 LF 记的值必然不符。
        #
        # **前提修正（2026-09-19 实测）**：别把"二进制逐字节等价"当成前提 ——
        # MB 级二进制几乎必然出现 0D 0A 字节对（实测本仓 50 个 onnx **全都**出现），
        # 所以归一会**改变**二进制的哈希值。这是有意取舍："一个工件只有一个哈希"
        # 优先于"二进制完整性最强"；代价是 0D 0A ↔ 0A 的改动会被掩盖，选型时须知道。
        return normalized_sha256(path.read_bytes())
    except OSError:
        return None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _scalar(value: Any) -> float | None:
    """从 pkl/npz 的标量（可能是 0 维数组或单元素数组）取数。"""

    try:
        import numpy as np

        return float(np.asarray(value).reshape(-1)[0])
    except Exception:
        try:
            return float(value)
        except Exception:
            return None


def _shape_of(value: Any) -> tuple[int, ...] | None:
    try:
        import numpy as np

        return tuple(np.asarray(value).shape)
    except Exception:
        return None


def _read_motion_meta(path: Path) -> dict[str, Any]:
    """读一份 motion 文件的元信息（fps / dof 宽度 / 帧数）——**派生自文件本身**。"""

    suffix = path.suffix.lower()
    try:
        if suffix == ".pkl":
            with path.open("rb") as handle:
                payload = pickle.load(handle)
            dof = _shape_of(payload.get("dof_pos"))
            frames = _shape_of(payload.get("root_pos"))
            return {
                "fps": _scalar(payload.get("fps")),
                "dof_dim": dof[1] if dof and len(dof) > 1 else None,
                "frames": frames[0] if frames else None,
            }
        if suffix == ".npz":
            import numpy as np

            with np.load(path) as payload:
                dof = _shape_of(payload["joint_pos"]) if "joint_pos" in payload.files else None
                frames = _shape_of(payload["joint_pos"])
                return {
                    "fps": _scalar(payload["fps"]) if "fps" in payload.files else None,
                    "dof_dim": dof[1] if dof and len(dof) > 1 else None,
                    "frames": frames[0] if frames else None,
                }
        if suffix == ".csv":
            # 浏览器格式：**无表头**，列布局 [root_pos(3), root_quat_xyzw(4), dof_pos(N)]
            # （web/sim2sim/motion_loader.js 的解析口径）。**fps 不在文件里** —— 浏览器的
            # loader 默认 50，所以这里如实记 None 并带一句说明，不替它编一个 fps。
            with path.open("r", encoding="utf-8-sig") as handle:
                rows = 0
                columns = 0
                for line in handle:
                    if not line.strip():
                        continue
                    if rows == 0:
                        columns = len(line.split(","))
                    rows += 1
            return {
                # 浏览器 CSV **文件里没有 fps**；这里登记的是**浏览器 loader 的缺省值**，出处可查：
                # `web/sim2sim/motion_loader.js:95` `this.fps = Number(motionParams?.fps ?? 50.0)`。
                # 校验器要求 fps 为正数是对的（fps 决定 dt），所以不能留 None —— 但要写清它是"缺省"而非"实测"。
                "fps": 50.0,
                "fps_note": "文件无 fps 元信息；登记的是浏览器 loader 缺省（motion_loader.js:95 fps ?? 50.0）",
                "dof_dim": columns - 7 if columns > 7 else None,
                "frames": rows,
                "columns": columns,
            }
    except Exception as exc:  # 读不出来如实记原因，不崩
        return {"fps": None, "dof_dim": None, "frames": None, "error": f"{type(exc).__name__}: {exc}"}
    return {"fps": None, "dof_dim": None, "frames": None}


def _layout_of(path: Path) -> tuple[str, str, str | None]:
    """判定 ``(layout, variant, clip_stem)`` —— 规则见模块文档串。"""

    name = path.name
    match = _TRACKING_STEM.match(name)
    if match and path.parent.name == "tracking":
        variant = "raw"
        for key, suffix in TRACKING_VARIANTS.items():
            if name.endswith(suffix):
                variant = key
                break
        return "tracking-variants", variant, match.group("clip") + "_stageii"
    if path.parent.parent.name == "amp":
        return "amp-dirs", path.parent.name, path.stem
    # 浏览器侧：`<包>/simulation/policies/*_motion.csv`（`motion_loader.js` 吃的那种）
    if path.suffix.lower() == ".csv" and path.parent.name == "policies":
        return "browser-csv", "browser", path.stem[: -len("_motion")] if path.stem.endswith("_motion") else path.stem
    return "flat", "default", path.stem


def iter_motion_files() -> list[Path]:
    """扫描机器人包内的 motion 数据文件。

    两处口径（都是**结构判定**，不靠文件名猜）：

    * 训练侧：``<包>/training/source/**/motions/**``（tracking 的 pkl / amp 的 npz）；
    * 浏览器侧：``<包>/simulation/policies/*_motion.csv``（`motion_loader.js` 吃的 CSV）。

    2026-09-16（M2）补第二处：此前只认路径里含 ``motions/`` 的，于是**浏览器格式变体一个都没进注册表** ——
    三侧（训练 tracking / 训练 amp / 浏览器）里有一侧的数据在索引之外，"同一 motion 的多格式版本由
    注册表统一索引"这句话就不成立。
    """

    found: list[Path] = []
    for package in sorted(ROBOTS_DIR.iterdir()) if ROBOTS_DIR.is_dir() else []:
        if not package.is_dir():
            continue
        for candidate in sorted(package.rglob("*")):
            if not candidate.is_file() or candidate.suffix.lower() not in (".pkl", ".npz", ".csv"):
                continue
            if "motions" in candidate.parts:
                found.append(candidate)
            elif candidate.suffix.lower() == ".csv" and candidate.parent.name == "policies" and "simulation" in candidate.parts:
                found.append(candidate)
    return found


def _source_of(path: Path) -> str:
    """``training/source/<source_pkg>/...`` 里的 ``<source_pkg>``（取不到就如实写 unknown）。"""

    parts = path.relative_to(ROBOTS_DIR).parts
    if "source" in parts:
        index = parts.index("source")
        if index + 1 < len(parts):
            return parts[index + 1]
    return "unknown"


def _source_short(robot: str, source: str) -> str:
    """给 id 用的短名：去掉与机型重复的前缀（``unitree_go2`` + ``go2_amp`` → ``amp``）。

    纯粹是可读性；``source`` 字段仍记**完整包名**（真值不缩短），所以不会出现"id 好看了但真值丢了"。
    """

    token = robot.split("_")[-1]
    if token and source != token:
        for prefix in (f"{token}_", f"{token}-"):
            if source.startswith(prefix):
                return source[len(prefix):] or source
    return source


def _declared_browser_sources() -> dict[tuple[str, str], str]:
    """``(包名, motion_csv 文件名) → 声明该 motion 的策略 ``source`` 文字``。

    真值来自**包内** ``simulation/config.json``（与 :func:`declared_browser_motions` 同一处），
    这样浏览器侧条目的出处/许可是从声明读出来的，而不是在派生代码里替它编一段。
    """

    sources: dict[tuple[str, str], str] = {}
    for package in sorted(ROBOTS_DIR.iterdir()) if ROBOTS_DIR.is_dir() else []:
        payload = _read_json(package / "simulation" / "config.json")
        if not isinstance(payload, dict):
            continue
        for policy in payload.get("policies") or []:
            if not isinstance(policy, dict):
                continue
            motion = policy.get("motion_params") or (policy.get("contract") or {}).get("motion_params") or {}
            csv_value = (motion or {}).get("motion_csv")
            if not csv_value:
                continue
            sources[(package.name, Path(str(csv_value)).name)] = str(policy.get("source") or "")
    return sources


def derive() -> dict[str, Any]:
    """从磁盘派生注册表内容（**纯派生**，不读已有 index）。"""
    clips: dict[tuple[str, str, str], dict[str, Any]] = {}
    for path in iter_motion_files():
        layout, variant, clip = _layout_of(path)
        robot = path.relative_to(ROBOTS_DIR).parts[0]
        source = _source_of(path)
        key = (robot, source, clip)
        entry = clips.get(key)
        if entry is None:
            meta = _read_motion_meta(path)
            entry = clips[key] = {
                "id": f"{_slug(robot)}-{_slug(_source_short(robot, source))}-{_slug(clip)}",
                "robot": robot,
                "source": source,
                "format": path.suffix.lower().lstrip("."),
                "layout": layout,
                "fps": meta["fps"],
                "dof_dim": meta["dof_dim"],
                "dof_layout": f"unitree_dds_{meta['dof_dim']}" if meta["dof_dim"] else None,
                "frames_min": meta["frames"],
                "files": {},
            }
        # 同一 clip 的多份产物帧数可能不同（逐引擎重定向），记**范围**而不是随便取一个
        meta = _read_motion_meta(path)
        if meta["frames"] is not None:
            entry["frames_min"] = min(entry["frames_min"] or meta["frames"], meta["frames"])
            entry["frames_max"] = max(entry.get("frames_max") or meta["frames"], meta["frames"])
        entry["files"][variant] = {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
            "frames": meta["frames"],
        }
        if entry["fps"] is None and meta["fps"] is not None:
            entry["fps"] = meta["fps"]
        if entry["dof_dim"] is None and meta["dof_dim"] is not None:
            entry["dof_dim"] = meta["dof_dim"]
            entry["dof_layout"] = f"unitree_dds_{meta['dof_dim']}"

    declared_sources = _declared_browser_sources()
    for entry in clips.values():
        entry["files"] = {key: entry["files"][key] for key in sorted(entry["files"])}
        layout = entry["layout"]
        if layout == "tracking-variants":
            entry["conventions"] = dict(_TRACKING_CONVENTIONS)
            entry["lineage"] = dict(_TRACKING_LINEAGE)
            entry["license"] = dict(_TRACKING_LICENSE)
        elif layout == "browser-csv":
            # 浏览器侧 CSV：出处/许可**不许在这里编** —— 真值是包内策略声明的 `source`
            # （`motion_params.motion_csv` 所在的那条策略），evidence 指回声明文件本身。
            csv_name = next(iter(entry["files"].values()))["path"].rsplit("/", 1)[-1]
            declared = declared_sources.get((entry["robot"], csv_name)) or ""
            config_path = f"assets/robots/{entry['robot']}/simulation/config.json"
            entry["conventions"] = dict(_BROWSER_CONVENTIONS)
            entry["lineage"] = {
                "pipeline": "浏览器侧随包 demo 动作（`simulation/policies/*_motion.csv`，"
                            "由 `web/sim2sim/motion_loader.js` 消费）",
                "raw": None,
                "raw_note": "数据以 CSV 形式直接入库，仓内无更上游的原始来源",
                "conversion_script": None,
                "evidence": [config_path],
            }
            entry["license"] = {
                "status": "unresolved",
                "spdx": None,
                "reason": "随包 demo 动作数据：出处见包内策略声明的 source"
                          + (f"（{declared}）" if declared else "（包内声明未写 source）")
                          + "，**该动作数据本身的许可与再分发条件未取证**",
                "evidence": [config_path],
            }
        else:
            entry["conventions"] = dict(_AMP_CONVENTIONS)
            entry["lineage"] = dict(_AMP_LINEAGE)
            entry["license"] = dict(_AMP_LICENSE)
        if "frames_max" not in entry:
            entry["frames_max"] = entry["frames_min"]

    entries = [clips[key] for key in sorted(clips)]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "tools/audit_motions.py --apply",
        "rules": {
            "scan": "assets/robots/<package>/**/motions/** 下的 .pkl/.npz（训练侧）"
                    " + assets/robots/<package>/simulation/policies/*_motion.csv（浏览器侧，M2 补）",
            "derive": "fps / dof_dim / frames 从文件本身读出；dof_layout 由 dof 宽度命名",
            "license": "与 I5 同口径：缺许可记录不得进注册表；确未取证须显式 status=unresolved + 依据",
        },
        "counts": {
            "clips": len(entries),
            "files": sum(len(entry["files"]) for entry in entries),
        },
        "motions": entries,
    }


def validate(entry: dict[str, Any]) -> list[str]:
    """单条 motion 的字段校验（缺字段/类型错/非正 fps → 问题清单）。"""

    problems: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in entry or entry[field] in (None, {}, []):
            problems.append(f"缺字段 {field}")
    if entry.get("format") not in SUPPORTED_FORMATS:
        problems.append(f"format {entry.get('format')!r} 不在 {SUPPORTED_FORMATS}")
    fps = entry.get("fps")
    if not isinstance(fps, (int, float)) or fps <= 0:
        problems.append(f"fps 必须为正数，得到 {fps!r}")
    if entry.get("dof_layout") and not re.match(r"^[a-z0-9_]+_\d+$", str(entry["dof_layout"])):
        problems.append(f"dof_layout {entry['dof_layout']!r} 形状不合法（应形如 unitree_dds_29）")
    license_block = entry.get("license") or {}
    if not license_block.get("spdx") and license_block.get("status") != "unresolved":
        problems.append("license 既没有 spdx，也没有显式 status=unresolved（不许留空、也不许编）")
    if license_block.get("status") == "unresolved" and not license_block.get("reason"):
        problems.append("license 标了 unresolved 却没写原因")
    files = entry.get("files") or {}
    if not files:
        problems.append("files 为空（motion 条目必须至少指向一份数据）")
    for variant, item in files.items():
        if not item.get("sha256") or not item.get("path"):
            problems.append(f"files[{variant}] 缺 path/sha256")
    return problems


def audit() -> dict[str, Any]:
    """对账：``registry/motions/index.json`` 的声明 vs 磁盘实测。"""

    derived = derive()
    recorded = _read_json(INDEX_PATH)
    problems: list[str] = []
    if not isinstance(recorded, dict):
        return {
            "ok": False,
            "clips": derived["counts"]["clips"],
            "files": derived["counts"]["files"],
            "problems": [f"缺 {INDEX_PATH.relative_to(ROOT).as_posix()}（先跑 tools/audit_motions.py --apply）"],
        }
    declared = {str(item.get("id")): item for item in (recorded.get("motions") or []) if isinstance(item, dict)}
    for entry in derived["motions"]:
        problems.extend(f"{entry['id']}: {item}" for item in validate(entry))
        found = declared.get(entry["id"])
        if found is None:
            problems.append(f"{entry['id']}: 注册表未覆盖（磁盘上有这份 motion）")
            continue
        for field in ("robot", "source", "format", "fps", "dof_dim", "dof_layout"):
            if found.get(field) != entry[field]:
                problems.append(f"{entry['id']}: {field} 与实测不符（注册表 {found.get(field)!r} vs 实测 {entry[field]!r}）")
        declared_files = found.get("files") or {}
        for variant, item in entry["files"].items():
            actual = declared_files.get(variant)
            if actual is None:
                problems.append(f"{entry['id']}: 缺变体 {variant}")
                continue
            if actual.get("sha256") != item["sha256"]:
                problems.append(f"{entry['id']}/{variant}: 内容已变（sha256 不符）—— 数据被换过或需重新 --apply")
    extra = sorted(set(declared) - {entry["id"] for entry in derived["motions"]})
    if extra:
        problems.append(f"注册表里有磁盘上已不存在的 motion：{', '.join(extra)}")
    if recorded.get("counts", {}).get("clips") != derived["counts"]["clips"]:
        problems.append(
            f"条目数变了（注册表 {recorded.get('counts', {}).get('clips')} vs 实测 {derived['counts']['clips']}）——两侧一起改"
        )

    gaps = [
        {"id": entry["id"], "reason": (entry.get("license") or {}).get("reason", "")}
        for entry in derived["motions"] if not (entry.get("license") or {}).get("spdx")
    ]
    # M2：三侧消费对账（消费的必须在册 / 声明的必须存在）并进同一份 problems ——
    # CI 与 `verify motions` 都读这一处，不另开一个门禁入口。
    consumers = consumer_audit()
    problems.extend(consumers["problems"])
    return {
        "ok": not problems,
        "clips": derived["counts"]["clips"],
        "files": derived["counts"]["files"],
        "license_gaps": gaps,
        "consumers": {
            "counts": consumers["counts"],
            "declared_browser": consumers["declared"],
            "unclaimed": consumers["unclaimed"],
            "labels": consumers["labels"],
        },
        "problems": problems,
    }


# --------------------------------------------------------------------------------------
# M2：三侧消费对账（"不许各处各写一份路径"）
# --------------------------------------------------------------------------------------
#: 三侧消费方的**结构口径**（不看文件名猜、也不解析源码里的路径字面值）：
#:   * ``tracking`` —— ``<包>/training/source/**/motions/**`` 下的 pkl（DeepMimic tracking 的参考动作）
#:   * ``amp``      —— 同上目录下的 npz（AMP 的参考动作；`g1_amp` 的 `_MOTION_DATA_DIR` 指向它）
#:   * ``browser``  —— ``<包>/simulation/policies/*_motion.csv``，由包内契约的
#:                     ``motion_params.motion_csv`` 声明并被打包接口服务
CONSUMER_LABELS = {
    "tracking": "训练侧 tracking（motion_loader.py 的 glob *.pkl）",
    "amp": "训练侧 amp（`<包>/training/source/**/motions/**` 下的 npz）",
    "browser": "浏览器侧（web/sim2sim/motion_loader.js 的 CSV）",
}


def _consumer_of(path: Path) -> str:
    if path.suffix.lower() == ".csv" and "simulation" in path.parts:
        return "browser"
    if path.suffix.lower() == ".npz":
        return "amp"
    return "tracking"


def declared_browser_motions() -> list[dict[str, Any]]:
    """包内契约声明的浏览器运动（`motion_params.motion_csv`）——**声明**，不是实测。"""

    declared: list[dict[str, Any]] = []
    for package in sorted(ROBOTS_DIR.iterdir()) if ROBOTS_DIR.is_dir() else []:
        config = package / "simulation" / "config.json"
        if not config.is_file():
            continue
        try:
            payload = _read_json(config)
        except Exception:
            continue
        for policy in payload.get("policies") or []:
            if not isinstance(policy, dict):
                continue
            motion = policy.get("motion_params") or policy.get("contract", {}).get("motion_params") or {}
            csv_value = (motion or {}).get("motion_csv")
            if not csv_value:
                continue
            declared.append({
                "package": package.name,
                "policy_id": policy.get("id"),
                "motion_csv": str(csv_value),
                "exists": (package / str(csv_value)).is_file(),
            })
    return declared


def consumer_audit() -> dict[str, Any]:
    """三侧引用与注册表对账：**消费的必须在册，在册的要说得清谁在消费**。

    判据（M2）：
    1. 三侧实际存在的 motion 数据文件 **必须都在注册表里**（否则"统一索引"名不副实）；
    2. 包内契约声明的 `motion_csv` **必须存在且已注册**（否则浏览器侧启动即 404，
       而页面只会 `console.warn` 一句 —— 静默失败）；
    3. 注册表里**没有任何消费方**的条目要如实列出来（可能是只索引未接线的数据），
       但**不判红**：那是"登记了但没消费"，与"消费了没登记"是两码事。
    """

    index = load_index()
    indexed = {str(entry.get("id")): entry for entry in index.values()}
    indexed_files: set[str] = set()
    for entry in index.values():
        # `files` 是 **dict**：`{变体名: {path, sha256, bytes, frames}}`（M1 定的形状）
        for item in (entry.get("files") or {}).values():
            value = str((item or {}).get("path") or "") if isinstance(item, dict) else str(item or "")
            if value:
                indexed_files.add(value)

    problems: list[str] = []
    on_disk: dict[str, list[str]] = {"tracking": [], "amp": [], "browser": []}
    for path in iter_motion_files():
        relative = path.relative_to(ROOT).as_posix()
        on_disk[_consumer_of(path)].append(relative)
        if relative not in indexed_files:
            problems.append(f"{relative}：三侧在用但它不在注册表里（跑 tools/audit_motions.py --apply 重新派生）")

    declared = declared_browser_motions()
    for item in declared:
        if not item["exists"]:
            problems.append(
                f"{item['package']} 的策略 {item['policy_id']} 声明了 motion_csv "
                f"{item['motion_csv']!r}，但包内**没有这个文件** ⇒ 浏览器侧启动即 404（页面只 console.warn）"
            )
            continue
        relative = (ROBOTS_DIR / item["package"] / item["motion_csv"]).relative_to(ROOT).as_posix()
        if relative not in indexed_files:
            problems.append(f"{relative}：被契约声明为浏览器运动，但不在注册表里")

    consumed = {value for values in on_disk.values() for value in values}
    unclaimed = sorted(value for value in indexed_files if value not in consumed)

    return {
        "ok": not problems,
        "problems": problems,
        "counts": {name: len(values) for name, values in on_disk.items()},
        "declared": declared,
        "unclaimed": unclaimed,
        "labels": CONSUMER_LABELS,
    }


def load_index() -> dict[str, dict[str, Any]]:
    """读回注册表：``motion id`` → 条目（未生成时返回空字典）。"""

    recorded = _read_json(INDEX_PATH)
    if not isinstance(recorded, dict):
        return {}
    return {str(item.get("id")): dict(item) for item in (recorded.get("motions") or []) if isinstance(item, dict)}


def apply_registry() -> dict[str, Any]:
    """按实测重写 ``registry/motions/index.json``（**显式动作**）。"""

    payload = derive()
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
