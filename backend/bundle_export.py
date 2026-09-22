"""B12：导出五类粒度（Morphology / Skill / Scenario / Policy / Bundle）+ 一套 hash 纪律。

## 为什么要有它

愿景的「导入导出分五类粒度」此前只有两种形态、且各自为政：

* **Skill** —— `backend/skill_pack.py`（自包含 JSON，每条 recipe 带 sha256）；
* **Policy** —— `backend/policy_artifacts.py`（出库目录 + `policies/index.json` 的 hash）；
* **整包项目** —— `backend/project_api.py` 的 zip（**manifest 里没有哈希**，无法验证内容）。

缺的三类正是最需要"能搬走"的三类：**Morphology 包**（形态 + 契约）、**Scenario 包**、
以及把它们串起来的 **Bundle**（Pack 引用 + **被引用物的离线副本** + 哈希）。本模块补上它们，
并且把五类收进**同一份 manifest 与同一套校验**：

    <out_dir>/manifest.json      ← schema=capability-export-1.0，逐条 {path, sha256, bytes, role}
    <out_dir>/<payload...>       ← 副本（离线可用的部分）

## 三条判据（写死在这里，调用方只读结论）

1. **导出即自证**：manifest 里每条都带 sha256 与字节数，`verify_export()` 逐条重算 ——
   "搬过去之后内容变了" 必须能被发现；
2. **不许有幽灵文件**：目录里出现 manifest 未登记的 payload 文件即判红（导出物 = manifest 说的那些，
   多一个少一个都算不一致）；
3. **五类各自可独立导出、独立 verify**：`REQUIRED_ROLES` 规定每类**至少要有哪些角色**，
   缺角色即拒（"导出了个空包但退出码 0" 是最坏的一种绿）。

## 与 Pack schema 的关系（不另立第二套形状）

Pack 的 `morphology_ref / skill_ref / scenario_ref / policy_ref` 用的是
`capability-pack-1.0.schema.json` 的 `$defs.ref`（`{id, version?, path?, sha256?}`，
`additionalProperties: false`）。Bundle 的 `refs` **原样沿用这个形状** —— 引用与副本并存时，
`sha256` 同时锁定"引用指向的那份"与"我们副本里的那份"。

风格：纯 stdlib（Scenario 校验复用 `contracts.scenario_contract`，Skill 复用 `backend.skill_pack`）。
"""

from __future__ import annotations

import json
import shutil
from backend.api_routes import BROWSER_PACKAGE_URL_PREFIX, browser_package_url_prefix
from contracts.validator import normalized_sha256  # noqa: E402  (归一摘要唯一实现)
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
PACKS_DIR = ROOT / "packs"
ROBOTS_DIR = ROOT / "assets" / "robots"

MANIFEST_SCHEMA = "capability-export-1.0"
MANIFEST_NAME = "manifest.json"
#: Scenario 包里的场景文件名（导出与导入**必须同名**，故取常量而不是各写各的字面量）。
SCENARIO_FILE = "scenario.json"
#: 任务插件包里的插件声明文件名（**与注册表同一份契约**，见 `export_task_plugin`）。
TASK_PLUGIN_FILE = "task-plugin.json"
EXPORT_KINDS = ("morphology", "skill", "scenario", "policy", "bundle", "task_plugin")

#: 每类导出的**必需角色**（verify 据此判"到底导出了这一类没有"）。
REQUIRED_ROLES: dict[str, frozenset[str]] = {
    "morphology": frozenset({"package_manifest", "contract"}),
    "skill": frozenset({"skill"}),
    "scenario": frozenset({"scenario"}),
    "policy": frozenset({"policy"}),
    # Bundle 要能"在干净机器上跑起来"（R1/R2）⇒ 必须带**运行配置** simulation/config.json：
    # 没有它，PackageContract 建不起来，策略条目/执行器接口/初始高度全都无从谈起。
    "bundle": frozenset({"pack", "package_manifest", "contract", "simulation_config"}),
    "task_plugin": frozenset({"task_plugin"}),
}

#: 拷贝时跳过的目录（与导入侧同口径：VCS 元数据与字节码缓存不属于资产）。
_SKIP_DIRS = frozenset({".git", "__pycache__", ".venv", "node_modules"})


from backend.paths import workspace_root as _workspace_root  # 唯一实现见 backend/paths.py
from backend.jsonio import load_json, read_json, write_json  # JSON 读写唯一实现



def _sha256(path: Path) -> str:
    """规范化内容哈希：委托 ``contracts.validator.normalized_sha256``（**唯一实现**）。

    这个值既写进离线包 manifest、又在 verify 时重算比对 —— 用原始字节会让
    "Windows 上打出来的包、在另一台机器 verify"必然失败（包内文本是 CRLF），
    而那正是离线包最常见的用法（打包机上验、目标机上跑）。
    """
    return normalized_sha256(path.read_bytes())


def _read_json(path: Path) -> Any:
    """严格读（异常原样抛）—— 实现见 ``backend.jsonio``。"""

    return load_json(path)


def _write_json(path: Path, payload: Any) -> None:
    """写 JSON（格式化规则见 ``contracts/jsonio``）。"""

    write_json(path, payload)


def _safe_relative(value: str) -> Path:
    candidate = Path(str(value).replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ValueError(f"非法路径（禁止绝对路径与 .. 越界）：{value}")
    return candidate


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def ref(*, id: str, path: Path | None = None, version: str | None = None) -> dict[str, Any]:
    """构造 Pack schema 的 `$defs.ref` 形状（引用与副本共用同一个形状）。"""

    payload: dict[str, Any] = {"id": id}
    if version:
        payload["version"] = version
    if path is not None and path.is_file():
        payload["path"] = _repo_relative(path)
        payload["sha256"] = _sha256(path)
    return payload


class ExportWriter:
    """把文件拷进导出目录并登记 manifest 条目（**所有类目共用**，避免五套哈希写法）。"""

    def __init__(self, out_dir: Path, kind: str) -> None:
        self.out_dir = Path(out_dir)
        self.kind = kind
        self.entries: list[dict[str, Any]] = []
        self.notes: list[str] = []

    def copy(self, src: Path, relative: str, *, role: str) -> Path:
        if not src.is_file():
            raise FileNotFoundError(f"{role} 源文件不存在：{src}")
        target = self.out_dir / _safe_relative(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        self.entries.append({
            "path": target.relative_to(self.out_dir).as_posix(),
            "sha256": _sha256(target),
            "bytes": target.stat().st_size,
            "role": role,
            "source": _repo_relative(src),
        })
        return target

    def write_json(self, payload: Any, relative: str, *, role: str) -> Path:
        target = self.out_dir / _safe_relative(relative)
        _write_json(target, payload)
        self.entries.append({
            "path": target.relative_to(self.out_dir).as_posix(),
            "sha256": _sha256(target),
            "bytes": target.stat().st_size,
            "role": role,
            "source": None,
        })
        return target

    def write_text(self, text: str, relative: str, *, role: str) -> Path:
        target = self.out_dir / _safe_relative(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        self.entries.append({
            "path": target.relative_to(self.out_dir).as_posix(),
            "sha256": _sha256(target),
            "bytes": target.stat().st_size,
            "role": role,
            "source": None,
        })
        return target

    def finish(
        self,
        *,
        refs: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
        emit: bool = True,
    ) -> dict[str, Any]:
        """收尾：写 ``manifest.json``（``emit=False`` 时只返回 manifest，供**嵌套导出**用）。

        嵌套导出（Bundle 里的 morphology/skill/...）**不写自己的 manifest** ——
        一个导出物只该有一份清单，多出来的嵌套清单既是冗余，也会让"幽灵文件"检查失去意义
        （任何名为 manifest.json 的文件都会被豁免）。嵌套的 notes 由调用方并进外层清单。
        """

        from backend.version import get_version

        manifest: dict[str, Any] = {
            "schema_version": MANIFEST_SCHEMA,
            "kind": self.kind,
            "product_version": get_version(),
            "entries": sorted(self.entries, key=lambda item: item["path"]),
            "refs": refs or {},
            "notes": self.notes,
        }
        if extra:
            manifest.update(extra)
        if emit:
            _write_json(self.out_dir / MANIFEST_NAME, manifest)
        return manifest


# 包根解析的**单一实现**在 `backend/robot_packages.py`（训练安装与导出必须指向同一个包）。
from backend.robot_packages import robot_package_root  # noqa: E402  (模块末尾导入，避免循环依赖)


def _model_files(package_root: Path, manifest: dict[str, Any]) -> list[tuple[Path, str]]:
    """包清单里登记的模型与网格文件（`model.path` 与 `model.assets_path` 两条线索）。"""

    model = manifest.get("model") or {}
    found: list[tuple[Path, str]] = []
    declared = model.get("path")
    if declared:
        candidate = package_root / _safe_relative(declared)
        if candidate.is_file():
            found.append((candidate, candidate.relative_to(package_root).as_posix()))
    assets_path = model.get("assets_path")
    if assets_path:
        directory = package_root / _safe_relative(assets_path)
        if directory.is_dir():
            for file in sorted(directory.rglob("*")):
                if file.is_file() and not (_SKIP_DIRS & set(file.parts)):
                    found.append((file, file.relative_to(package_root).as_posix()))
    return found


def export_morphology(
    robot_id: str, out_dir: Path | str, *, emit_manifest: bool = True, prefix: str = "morphology/",
) -> dict[str, Any]:
    """**Morphology 包**：形态与契约（`robot_package.json` + `contract.json` + `contract_legacy_v2.json` + 模型/网格）。

    有意**不含** `training/`（训练源码）与策略权重 —— 那些属别的粒度（Skill / Policy / Bundle），
    把它们塞进形态包会让"形态包"变成一个含糊的大包（也就没法单独校验形态是否可渲染/可加载）。
    """

    package_root = robot_package_root(robot_id)
    if not package_root.is_dir():
        raise FileNotFoundError(f"机器人包不存在：{package_root}")
    writer = ExportWriter(Path(out_dir), "morphology")
    package_manifest = package_root / "robot_package.json"
    writer.copy(package_manifest, f"{prefix}robot_package.json", role="package_manifest")
    manifest_data = _read_json(package_manifest)
    for name, role in (("contract.json", "contract"), ("contract_legacy_v2.json", "contract_legacy_v2")):
        source = package_root / name
        if source.is_file():
            writer.copy(source, f"{prefix}{name}", role=role)
        else:
            writer.notes.append(f"{name} 不存在（形态可渲染但语义层不完整）")
    for source, relative in _model_files(package_root, manifest_data):
        writer.copy(source, f"{prefix}{relative}", role="model")
    return writer.finish(refs={"morphology": ref(id=robot_id, path=package_root / "contract.json")}, emit=emit_manifest)


def export_skill(recipe_id: str, out_dir: Path | str, *, emit_manifest: bool = True) -> dict[str, Any]:
    """**Skill 包**：复用 `backend/skill_pack.export_pack`（自包含 JSON），导出前先自校验。"""

    from backend import skill_pack

    payload = skill_pack.export_pack(recipe_id)
    check = skill_pack.verify_pack(payload)
    if not check.get("ok", False):
        raise ValueError(f"技能包自校验未通过：{check.get('problems')}")
    writer = ExportWriter(Path(out_dir), "skill")
    writer.write_json(payload, "skill.json", role="skill")
    return writer.finish(
        refs={"skill": {"id": recipe_id, "version": str(payload.get("recipe_version") or "") or None}},
        emit=emit_manifest,
    )


def scenario_map_references(contract) -> dict[str, Any]:
    """场景引用的地图**能不能随包走**（H5 已登记的诚实边界 C4）。

    规则与**运行时解析器同源**（`backend/simulation_resolver.py` 按
    `assets/maps/<map_id>.xml` 解析）：`assets/maps/` 是**产品自带的公共地图库**
    （`_index.json` 登记 + 随浏览器载荷下发，见 `simulation_browser.common_map_entries`）
    ⇒ 引用库内地图的场景在任何人机器上都能跑，**无需带**。

    引用**库外**东西则不然（自加的 `map_id`、或 `terrain.xml_path` 指向的文件）：
    不带走就必然在接收方跑不起来——所以导出期**二选一**（本函数只判定，不落盘）：

    * 库内 id ⇒ `shipped=True`，无文件要带；
    * 库外但本地确有该文件 ⇒ 计划复制进包 `maps/<名字>`（`shipped=False` + 说明，
      接收方需把该文件放进自己的 `assets/maps/<id>.xml`）；
    * 库外且**找不到文件** ⇒ **拒绝**（fail-closed：宁可现在报错，也不产出一个
      注定跑不起来的包——"分享即可跑"不成立时要说出来，不能让包看起来是好的）。
    """

    from backend.simulation_browser import MAPS_ROOT, common_map_entries

    map_id = str(getattr(contract, "map_id", "") or "flat")
    library = {str(entry.get("id")) for entry in common_map_entries()}
    if map_id in library and (MAPS_ROOT / f"{map_id}.xml").is_file():
        return {"id": map_id, "source": "common-map-library", "shipped": True, "files": [],
                "hint": "引用的是产品自带公共地图库里的地图，接收方无需额外文件"}

    terrain = getattr(contract, "terrain", None)
    explicit = str(getattr(terrain, "xml_path", "") or "") if terrain is not None else ""
    candidates: list[Path] = []
    if explicit:
        raw_path = Path(explicit).expanduser()
        candidates.append(raw_path if raw_path.is_absolute() else (ROOT / raw_path))
    candidates.append(MAPS_ROOT / f"{map_id}.xml")
    found = next((path for path in candidates if path.is_file()), None)
    if found is None:
        where = f"（`terrain.xml_path={explicit}`）" if explicit else ""
        raise ValueError(
            f"场景引用的地图 {map_id!r}{where} 既不在公共地图库 assets/maps/（_index.json 登记），"
            f"本地也没有对应文件 ⇒ 导出后接收方必然跑不起来。二选一：① 把该 XML 放进 "
            f"assets/maps/ 并登记进 _index.json（这样所有包共享）；② 先把它放到本地可确定的路径"
            f"（留档后自行随包发给接收方并按 maps/ 放置）。拒绝导出而不是产出一个坏包。"
        )
    return {"id": map_id, "source": "packaged-with-scenario", "shipped": False,
            "files": [{"src": found, "relative": f"maps/{found.name}"}],
            "hint": f"该地图不在公共地图库：已随包携带 maps/{found.name}，"
                    f"接收方需把它放进自己的 assets/maps/{map_id}.xml（或按包声明同名 id）"}


def export_scenario(scenario_path: Path | str, out_dir: Path | str, *, emit_manifest: bool = True) -> dict[str, Any]:
    """**Scenario 包**：场景契约 JSON（导出前用 `ScenarioContract` 校验，fail-closed）。

    并核验**地图可分享性**（C4）：库内地图无需带；库外地图复制进包并附放置说明；
    找不到就拒绝导出（`scenario_map_references`）——**判定在写盘之前**，不留半成品。
    """

    from contracts.scenario_contract import ScenarioContract

    source = Path(scenario_path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"场景文件不存在：{source}")
    raw = _read_json(source)
    if not isinstance(raw, dict):
        raise ValueError(f"场景文件不是 JSON 对象：{source}")
    contract = ScenarioContract(**raw)  # 校验失败就抛（不导出半成品）
    map_ref = scenario_map_references(contract)   # 同样在写盘前判定（fail-closed）
    writer = ExportWriter(Path(out_dir), "scenario")
    writer.write_json(contract.to_payload(), SCENARIO_FILE, role="scenario")
    for item in map_ref.get("files") or []:
        writer.copy(Path(item["src"]), str(item["relative"]), role="map")
    if not map_ref.get("shipped"):
        writer.notes.append(str(map_ref.get("hint") or ""))
    payload = {k: v for k, v in map_ref.items() if k != "files"}
    return writer.finish(refs={"scenario": {"id": contract.scenario_id}, "map": payload}, emit=emit_manifest)


def import_scenario(
    source: Path | str, *, dest: Path | str | None = None, force: bool = False
) -> dict[str, Any]:
    """**导入 Scenario 包** —— H5「Scenario 包可导出/导入」的导入半边（此前只有导出）。

    认**三种**实际会被人递过来的形态（不要求对方先转格式）：

    * ``export_dir``：场景导出目录（`manifest.json` + `scenario.json`，即 `export_scenario` 的产物）；
    * ``bundle_embedded``：Bundle 导出目录里内嵌的场景（`scenario/scenario.json`，无自己的 manifest）；
    * ``bare_json``：裸场景 JSON 文件（手写/从别处贴来的也认）。

    三条判据（**fail-closed**，与导出口同一套）：

    1. 只要源目录里有 `manifest.json`，就**先验完整性** —— 委托 :func:`verify_export`，
       **不另写一套**（第二套校验实现正是本仓反复出现的漂移源）；不过就拒绝导入。
       这条的意义就在于"从别处拷来的包"：损坏/被改过的包不该被当成可信场景跑起来。
    2. 场景本身必须过 ``ScenarioContract`` —— 与 :func:`export_scenario` **同一道闸**，
       否则"能导出不能导入"或反之都会出现。
    3. 形态不对（例如拿 Policy 导出物当场景）时**明确报错并说明原因**，不做任何猜测性兼容。

    ``dest`` 给了就把**规范化后**的载荷落盘（目录则落 ``scenario.json``），默认不覆盖已存在文件
    （要覆盖得显式 ``force=True``）——导入是"放进工作区"的动作，静默覆盖别人的场景是不可接受的。
    """

    from contracts.scenario_contract import ScenarioContract

    origin = Path(source).expanduser()
    if not origin.exists():
        raise FileNotFoundError(f"导入源不存在：{origin}")

    integrity: dict[str, Any] | None = None
    form = ""
    scenario_file: Path | None = None

    if origin.is_file():
        form, scenario_file = "bare_json", origin
    elif (origin / MANIFEST_NAME).is_file():
        integrity = verify_export(origin)
        if not integrity.get("ok"):
            raise ValueError(f"场景包完整性校验未通过（拒绝导入）：{integrity.get('problems')}")
        kind = str(integrity.get("kind") or "")
        if kind == "scenario":
            form, scenario_file = "export_dir", origin / SCENARIO_FILE
        elif (origin / "scenario" / SCENARIO_FILE).is_file():
            # Bundle：整包已过 verify_export（比只看场景文件更严），场景是它的内嵌件。
            form, scenario_file = "bundle_embedded", origin / "scenario" / SCENARIO_FILE
        else:
            raise ValueError(
                f"{kind!r} 导出物里没有场景（只有 scenario 导出物或含 scenario/ 的 Bundle 才有）：{origin}"
            )
    elif (origin / "scenario" / SCENARIO_FILE).is_file():
        form, scenario_file = "scenario_dir", origin / "scenario" / SCENARIO_FILE
    else:
        raise ValueError(
            f"认不出这是场景（既不是 {SCENARIO_FILE}、也不是含它的导出目录/Bundle）：{origin}"
        )

    assert scenario_file is not None
    if not scenario_file.is_file():
        raise ValueError(f"场景包缺 {SCENARIO_FILE}：{scenario_file}")
    raw = _read_json(scenario_file)
    if not isinstance(raw, dict):
        raise ValueError(f"场景文件不是 JSON 对象：{scenario_file}")
    contract = ScenarioContract(**raw)  # 与导出口同一道闸：校验失败就抛
    payload = contract.to_payload()

    written: str | None = None
    if dest is not None:
        target = Path(dest).expanduser()
        if target.is_dir() or target.suffix == "":
            target = target / SCENARIO_FILE
        if target.exists() and not force:
            raise FileExistsError(f"目标已存在（要覆盖请显式 force=True）：{target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_json(target, payload)
        written = _repo_relative(target)

    return {
        "ok": True,
        "form": form,
        "source": _repo_relative(origin),
        "scenario_file": _repo_relative(scenario_file),
        "scenario": payload,
        "scenario_id": contract.scenario_id,
        "schema_version": contract.schema_version,
        "integrity": integrity,
        "written": written,
    }


def export_task_plugin(plugin_id: str, out_dir: Path | str, *, emit_manifest: bool = True) -> dict[str, Any]:
    """**任务插件包**：把注册表里的一条任务插件**原样**导出（含 `evidence` 与传感器需求）。

    为什么要它（用户指令里的"一键导入导出"）：任务插件的**实例化产物**（一份场景）本来就随
    Scenario 包走，但**插件定义本身**原先只能在仓内注册表里改 —— 别人写好的任务（要哪些传感器、
    自动填哪些字段、挂哪些判据）没有"拿走一份"的形态。导出的是**注册表里的同一份**（不重抄，
    `backend.task_plugins.task_plugin()` 取的就是加载后的对象），且未注册的 id **fail-closed**。
    """

    from backend.task_plugins import task_plugin as _task_plugin

    plugin = _task_plugin(plugin_id)                  # 未知名 ⇒ 带可用清单的失败
    writer = ExportWriter(Path(out_dir), "task_plugin")
    writer.write_json(plugin.model_dump(), TASK_PLUGIN_FILE, role="task_plugin")
    return writer.finish(
        refs={"task_plugin": {"id": plugin.plugin_id, "version": plugin.version,
                              "task_type": plugin.task_type,
                              "sensors": [s.plugin_id for s in plugin.sensors]}},
        emit=emit_manifest,
    )


def import_task_plugin(
    source: Path | str, *, dest: Path | str | None = None, force: bool = False
) -> dict[str, Any]:
    """**导入任务插件包** —— 与 :func:`import_scenario` 同一套纪律（不另写第二套校验）。

    认两种形态：**导出目录**（`manifest.json` + `task-plugin.json`，先验完整性）与**裸 JSON**。
    校验走 :func:`contracts.task_plugin_contract.validate_task_plugin_payload` —— 与注册表加载
    **同一道闸**（未知传感器 id / 未知输出 / 缺证据都当场拒），所以"能导出不能导入"不会发生。
    ``dest`` 给了才落盘（目录则落 `task-plugin.json`），默认不覆盖已存在文件。
    """

    from contracts.task_plugin_contract import TaskPluginError, validate_task_plugin_payload

    origin = Path(source).expanduser()
    if not origin.exists():
        raise FileNotFoundError(f"导入源不存在：{origin}")

    integrity: dict[str, Any] | None = None
    form = ""
    plugin_file: Path | None = None
    if origin.is_file():
        form, plugin_file = "bare_json", origin
    elif (origin / MANIFEST_NAME).is_file():
        integrity = verify_export(origin)
        if not integrity.get("ok"):
            raise ValueError(f"任务插件包完整性校验未通过（拒绝导入）：{integrity.get('problems')}")
        kind = str(integrity.get("kind") or "")
        if kind != "task_plugin":
            raise ValueError(f"{kind!r} 导出物里没有任务插件（只有 task_plugin 导出物才有）：{origin}")
        form, plugin_file = "export_dir", origin / TASK_PLUGIN_FILE
    elif (origin / TASK_PLUGIN_FILE).is_file():
        form, plugin_file = "plugin_dir", origin / TASK_PLUGIN_FILE
    else:
        raise ValueError(f"认不出这是任务插件（既不是 {TASK_PLUGIN_FILE}、也不是含它的导出目录）：{origin}")

    assert plugin_file is not None
    raw = _read_json(plugin_file)
    try:
        plugin = validate_task_plugin_payload(raw)
    except TaskPluginError as exc:
        raise ValueError(f"任务插件声明不合法（拒绝导入）：{exc}") from exc

    written: str | None = None
    if dest is not None:
        target = Path(dest).expanduser()
        if target.is_dir() or target.suffix == "":
            target = target / TASK_PLUGIN_FILE
        if target.exists() and not force:
            raise FileExistsError(f"目标已存在（要覆盖请显式 force=True）：{target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_json(target, plugin.model_dump())
        written = _repo_relative(target)

    return {
        "ok": True,
        "form": form,
        "source": _repo_relative(origin),
        "plugin_file": _repo_relative(plugin_file),
        "plugin": plugin.model_dump(),
        "plugin_id": plugin.plugin_id,
        "schema_version": plugin.schema_version,
        "integrity": integrity,
        "written": written,
    }


def export_policy(
    artifact_id: str, out_dir: Path | str, *, out_dir_index: Path | None = None, emit_manifest: bool = True,
    prefix: str = "", onnx_path: str | None = None,
) -> dict[str, Any]:
    """**Policy 包**：复用 B10 出库产物（`artifact.json` + `deploy.yaml` + `policy.onnx`）。"""

    from backend import policy_artifacts as pa

    index = pa.load_index(out_dir_index) if out_dir_index else pa.load_index()
    entry = index.get(artifact_id)
    if entry is None:
        raise ValueError(f"出库索引里没有这个产物：{artifact_id}")
    artifact_dir = (out_dir_index or pa.OUT_DIR) / artifact_id
    if not artifact_dir.is_dir():
        raise FileNotFoundError(f"产物目录不存在：{artifact_dir}")
    writer = ExportWriter(Path(out_dir), "policy")
    for name, role in (("artifact.json", "policy_meta"), ("deploy.yaml", "policy_meta")):
        source = artifact_dir / name
        if source.is_file():
            writer.copy(source, f"{prefix}{name}", role=role)
        else:
            writer.notes.append(f"{name} 不存在")
    # 产物 onnx 的落点由**统一解析器**给（`policy_blob_path`）：安装进包之后真副本已搬进
    # `assets/robots/<robot>/simulation/policies/`（出库目录里只剩元数据），此时若仍 glob
    # 出库目录就会报"产物目录里没有 onnx"——而它其实好端端在包里。
    from backend.policy_artifacts import policy_blob_path

    blob = policy_blob_path(entry, index=index)
    onnx_files: list[Path] = []
    if blob is not None and Path(blob).is_file() and Path(blob).resolve() != (artifact_dir / Path(blob).name).resolve():
        onnx_files = [Path(blob)]
    if not onnx_files:
        onnx_files = sorted(artifact_dir.glob("*.onnx"))
    if not onnx_files:
        raise FileNotFoundError(f"产物解析不到 onnx（出库目录与包内都没有）：{artifact_dir}")
    for source in onnx_files:
        # onnx 的**落点可以是绝对口径**（Bundle 要让包内配置能解析到它，见 _policy_placement）；
        # 元数据（artifact.json/deploy.yaml）只跟着 prefix 走。两者混用会把文件名当目录前缀拼，
        # 产出 `policy.onnxartifact.json` 这类垃圾名（2026-09-16 实测踩到）。
        writer.copy(source, onnx_path or f"{prefix}{source.name}", role="policy")
    return writer.finish(refs={"policy": ref(id=artifact_id, path=onnx_files[0])}, emit=emit_manifest)


def export_bundle(
    pack_json: Path | str,
    out_dir: Path | str,
    *,
    artifact_id: str | None = None,
    scenario_path: Path | str | None = None,
    run_dir: Path | str | None = None,
    replay: bool = False,
    replay_steps: int = 60,
    out_dir_index: Path | None = None,
    quality: bool = False,
    quality_tier: str = "single",
    quality_min: float = 0.5,
    quality_steps: int = 200,
    with_player: bool = False,
) -> dict[str, Any]:
    """**Bundle**：Pack 引用 + **被引用物的离线副本** + 哈希（愿景原文口径）。

    组成：`pack.json`（原样副本）+ Morphology 三件 + Skill JSON +（可选）Scenario / Policy。
    Pack 里声明了 `policy_ref` 却**没有**可用副本时，如实记进 `unresolved`（**不假装完整**）：
    "包里少了被引用物"必须在 manifest 里看得见，而不是等用户在干净机器上打开才发现。
    """

    pack_path = Path(pack_json).expanduser()
    if not pack_path.is_file():
        raise FileNotFoundError(f"Pack 文件不存在：{pack_path}")
    pack = _read_json(pack_path)
    if not isinstance(pack, dict):
        raise ValueError(f"Pack 不是 JSON 对象：{pack_path}")

    writer = ExportWriter(Path(out_dir), "bundle")
    writer.copy(pack_path, "pack.json", role="pack")
    refs: dict[str, Any] = {
        "morphology": pack.get("morphology_ref"),
        "skill": pack.get("skill_ref"),
        "scenario": pack.get("scenario_ref"),
        "policy": pack.get("policy_ref"),
    }
    unresolved: list[dict[str, str]] = []

    morphology_id = str((pack.get("morphology_ref") or {}).get("id") or "")
    package_root: Path | None = None
    if morphology_id:
        # **Bundle = 可直接跑的包布局**：形态/契约/模型落在导出根（不再套 `morphology/` 子目录），
        # 于是 Bundle 根目录本身就是一个可被验收器/产出端消费的机器人包（R1 看、R2 用的前提）。
        package_root = robot_package_root(morphology_id)
        nested = export_morphology(morphology_id, Path(out_dir), emit_manifest=False, prefix="")
        writer.entries.extend(nested["entries"])
        writer.notes.extend(f"morphology: {note}" for note in nested.get("notes") or [])
        simulation_config = package_root / "simulation" / "config.json"
        if simulation_config.is_file():
            writer.copy(simulation_config, "simulation/config.json", role="simulation_config")
        else:
            unresolved.append({"role": "simulation_config", "reason": f"包内缺 simulation/config.json：{package_root}"})
    else:
        unresolved.append({"role": "package_manifest", "reason": "Pack 未声明 morphology_ref"})

    skill_ref = pack.get("skill_ref") or {}
    skill_id = str(skill_ref.get("id") or "")
    if skill_id:
        # 技能解析**只走 K4 注册表**（不猜 id 形态）：`registry/skills/index.json` 是权威清单。
        # 历史上 Pack 指向 `core/velocity@2.0`（无实体的 M1 命名），那时这里除了"如实记成
        # unresolved"没有别的诚实选择 —— 现在 Pack 由生成器解析出真 recipe id（带 path+sha256），
        # 于是 Bundle 能真的把被引用的技能装进去。
        try:
            from backend.skill_registry import skill_manifest

            known = {str(item.get("recipe_id")) for item in (skill_manifest().get("skills") or [])}
            if skill_id not in known:
                raise ValueError(f"技能注册表里没有 {skill_id!r}（登记在册：{sorted(known)}）")
            nested = export_skill(skill_id, Path(out_dir) / "skill", emit_manifest=False)
            writer.entries.append({**nested["entries"][0], "path": f"skill/{nested['entries'][0]['path']}"})
            writer.notes.extend(f"skill: {note}" for note in nested.get("notes") or [])
        except Exception as exc:
            unresolved.append({"role": "skill", "reason": f"{skill_id}: {type(exc).__name__}: {exc}"})
    else:
        unresolved.append({"role": "skill", "reason": "Pack 未声明 skill_ref"})

    scenario_target = scenario_path or (pack.get("scenario_ref") or {}).get("path")
    if scenario_target:
        try:
            nested = export_scenario(
                ROOT / str(scenario_target) if not Path(str(scenario_target)).is_absolute() else scenario_target,
                Path(out_dir) / "scenario", emit_manifest=False,
            )
            writer.entries.append({**nested["entries"][0], "path": f"scenario/{nested['entries'][0]['path']}"})
        except Exception as exc:
            unresolved.append({"role": "scenario", "reason": f"{scenario_target}: {type(exc).__name__}: {exc}"})
    else:
        writer.notes.append("Pack 未声明 scenario_ref，Bundle 不含场景")

    policy_ref = pack.get("policy_ref") or {}
    policy_id = artifact_id or str(policy_ref.get("id") or "")
    if policy_id:
        try:
            metadata_prefix, onnx_path, bound_entry = _policy_placement(
                package_root, policy_id, out_dir_index=out_dir_index,
            )
            nested = export_policy(
                policy_id, Path(out_dir), emit_manifest=False, prefix=metadata_prefix, onnx_path=onnx_path,
                out_dir_index=out_dir_index,
            )
            writer.entries.extend(nested["entries"])
            writer.notes.extend(f"policy: {note}" for note in nested.get("notes") or [])
            refs["policy"] = {
                **(refs.get("policy") or {}),
                "artifact_id": policy_id,
                "onnx_in_bundle": onnx_path,
                "bound_entry": bound_entry,
            }
            if bound_entry is None:
                writer.notes.append(
                    f"产物 {policy_id} 未绑定任何包内策略条目（artifact.json 无 policy_id）⇒ "
                    f"onnx 放在 {onnx_path}，需在包内配置里显式引用后才可被 --policy-id 解析"
                )
        except Exception as exc:
            unresolved.append({"role": "policy", "reason": f"{policy_id}: {type(exc).__name__}: {exc}"})
    else:
        writer.notes.append("Pack 未声明 policy_ref 且未指定 --artifact：Bundle 不含策略权重（形态/技能仍可复现）")

    if with_player:
        # I4：把离线播放器打进包（"无本仓库机器可打开试玩"）。放在策略之后：引导层要把
        # 包内策略路径写进 browser-config。
        if not morphology_id:
            unresolved.append({"role": "player", "reason": "Pack 未声明 morphology_ref，无法生成离线播放器"})
        else:
            try:
                info = export_player(
                    out_dir, writer, robot_id=morphology_id,
                    policy_rel=(refs.get("policy") or {}).get("onnx_in_bundle"),
                )
                writer.notes.append(
                    f"离线播放器已打入：{info['entry']}（{info['files']} 个文件）→ {info['how_to_open']}"
                )
            except Exception as exc:
                unresolved.append({"role": "player", "reason": f"{type(exc).__name__}: {exc}"})

    if quality:
        # **在导出物自身内**评测（package = 导出目录）：和 R2 同一原则 —— 证据必须来自这份包，
        # 而不是拿仓库里那套凑。报告落 `quality.json`，`verify bundle` 会汇报它的判据。
        from backend import quality_matrix

        onnx_in_bundle = (refs.get("policy") or {}).get("onnx_in_bundle")
        if not onnx_in_bundle:
            unresolved.append({"role": "quality", "reason": "Bundle 里没有策略（未给 --artifact 且 Pack 无 policy_ref），无法评测"})
        else:
            try:
                report = quality_matrix.run_quality(
                    package_dir=Path(out_dir), tier=quality_tier, policy=onnx_in_bundle,
                    steps=quality_steps, quality_min=quality_min,
                )
                writer.write_json(report, "quality.json", role="quality")
                verdict = quality_matrix.gate(report, min_score=quality_min)
                writer.notes.append(
                    f"质量门（{quality_tier}）：{'达标' if verdict['ok'] else '未达标'}"
                    f"（{verdict['score'] if verdict['score'] is None else round(verdict['score'], 4)}"
                    f" / 下限 {quality_min}）"
                )
                for blocker in verdict["blockers"]:
                    writer.notes.append(f"质量门未过：{blocker}")
            except Exception as exc:
                unresolved.append({"role": "quality", "reason": f"{type(exc).__name__}: {exc}"})

    if run_dir is not None or replay:
        # R1/R2/R3 一起出：R3 用**当时那套 venv**重算环境并逐项对账；
        # R2 只有 `--replay` 时才真跑（要适配器 venv + 几秒），否则如实记 not_run（未跑 ≠ 通过）。
        from backend import reproduce as rp

        replay_inputs = None
        if replay:
            onnx_in_bundle = (refs.get("policy") or {}).get("onnx_in_bundle")
            if onnx_in_bundle:
                # **在被导出的这份 Bundle 自身内跑**（package = 导出目录）：这才是
                # "Bundle 在干净机器可 R2" 的证据，而不是拿仓库里的包凑出来的一次运行。
                replay_inputs = {
                    "package_dir": Path(out_dir),
                    "policy": onnx_in_bundle,
                    "steps": replay_steps,
                }
            else:
                unresolved.append({"role": "replay", "reason": "Bundle 里没有策略（未给 --artifact 且 Pack 无 policy_ref），R2 无法跑"})
        report = rp.build_reproduction(run_dir=run_dir, bundle_dir=out_dir, replay=replay_inputs)
        writer.write_json(report, rp.REPRODUCE_NAME, role="reproduce")
        summary = rp.summarise(report)
        writer.notes.append(
            f"复现报告已附（{rp.REPRODUCE_NAME}）：R1回放={summary['R1_playback']} / "
            f"R2评测={summary['R2_evaluation']} / R3训练={summary['R3_training']}"
        )

    return writer.finish(refs=refs, extra={"unresolved": unresolved})


def _policy_placement(
    package_root: Path | None, artifact_id: str, *, out_dir_index: Path | None = None,
) -> tuple[str, str, str | None]:
    """产物在 Bundle 里该放哪：**优先放到包内配置声明的位置**（这样 `--policy-id` 能解析到它）。

    两种情形（2026-09-16 实测）：

    * 产物 `source_onnx` 已在某个包内（提升/B10 回挂之后）⇒ 放回同一相对路径，
      于是 Bundle 的 `simulation/config.json` + `--policy-id <id>` **在 Bundle 自身内**就能解析；
    * produced 产物（`<robot>__produced-<run_id>`，`artifact.json` 里**没有** `policy_id`）⇒
      它并未绑定到任何包内策略条目（实测：产物 onnx 的哈希与包内 4 条 onnx 全不匹配）——
      此时放到 `simulation/policies/<文件名>`，并如实记 `bound_entry=null`：
      **"训练产物回挂 Pack/策略条目"这一环至今没闭环**，不能假装它已经绑上了。

    ``package_root`` 为 None（Pack 没声明形态）时只按文件名放。
    """

    from backend import policy_artifacts as pa

    # 出库目录**必须可指定**：单元测试与"导出别人机器上的索引"都要能指到别处；
    # 写死默认目录会让"装进包但在另一个 out_dir"的产物解析不到（回挂的落点就退回兜底文件名）。
    index = pa.load_index(out_dir_index) if out_dir_index else pa.load_index()
    entry = index.get(artifact_id) or {}
    source = str(entry.get("source_onnx") or "")
    name = Path(source).name if source else "policy.onnx"
    if source and package_root is not None:
        # 统一解析入口（仓库相对 / 包内相对 / 安装时机器落点）——本函数自己拼 `ROOT / source`
        # 会在 source 是包内相对路径时判成"不在包内"，于是退化成兜底文件名（回挂白做）。
        resolved = pa.policy_blob_path({"artifact_id": artifact_id}, index=index)
        if resolved is not None:
            try:
                # 产物已在包内（提升/B10 回挂之后）：落回同一相对路径 ⇒ Bundle 的 config 能解析到它，
                # `--policy-id` 在 Bundle 自身内即可用。
                return "policy/", resolved.resolve().relative_to(package_root.resolve()).as_posix(), str(entry.get("policy_id") or "") or None
            except ValueError:
                pass
    # produced 产物（未绑定任何包内策略条目）⇒ 放 simulation/policies/<文件名>，bound_entry=null
    return "policy/", f"simulation/policies/{name}", None


# --------------------------------------------------------------------------------------
# I4：离线播放器（把"可离线打开的 sim2sim 静态包"打进 Bundle）
#
# 为什么需要**引导层**而不是"拷一份网页就行"：`web/sim2sim/app.js` 启动时要问后端两件事 ——
# `GET /api/robots/presets`（有哪台机）与 `GET /api/simulation/browser-config/<robot>`
# （观测/控制/策略契约），其余是包内文件与 onnx。离线机器上没有后端，所以：
#   1. **配置形状由后端自己产出**（`simulation_api.browser_simulation_config`，asyncio.run 调用），
#      只把 URL 换成本地相对路径 —— 免得离线包与在线页面各长一套配置形状、日后必然漂移；
#   2. `offline-bootstrap.js` 在 app.js **之前**加载，拦 `fetch` 把这两个 API 就地答掉，
#      并把 `/api/simulation/browser-package/<robot>/<path>` 重写到包内文件；
#   3. 页面必须经 HTTP 打开（`file://` 下 fetch/模块/WebAssembly 都会被浏览器拦），
#      所以随包给一个 stdlib 的 `play/serve.py`，并补 `.wasm`/`.mjs` 的 MIME。
#
# 不打进包的部分：`web/sim2sim/{models,assets}`（演示自带的模型与资产，共 34MB）——
# Bundle 有自己的 `model/` 与策略，带进去只是让每个包白白大 34MB。
# --------------------------------------------------------------------------------------
PLAYER_DIR = "play"
PLAYER_ENTRY = f"{PLAYER_DIR}/index.html"
PLAYER_EXCLUDED = ("models", "assets")


def player_source_files() -> list[Path]:
    """要打进离线播放器的静态资源（相对 `web/sim2sim`，排除演示自带的 models/assets）。"""

    root = ROOT / "web" / "sim2sim"
    files: list[Path] = []
    for pattern in ("*.js", "*.css", "*.html"):
        files.extend(
            path for path in sorted(root.glob(pattern))
            if not path.name.endswith(".test.mjs")
            # index.html **不拷贝**：它是生成物（要注入引导层）。先拷一份到 manifest 再改写，
            # 会让 manifest 里出现两条同名条目、hash 对不上 ⇒ 导出自校验必红（2026-09-16 实测踩到）。
            and path.name != "index.html"
        )
    for sub in ("obs", "vendor"):
        files.extend(path for path in sorted((root / sub).rglob("*")) if path.is_file())
    return files


def _localise_urls(value: Any, robot_id: str) -> Any:
    """把后端给的 URL 换成本地相对路径（`../<包内路径>`）。

    只改 URL，不动其它字段 —— 形状来自后端，改动面越小越不容易漂。
    """

    prefix = browser_package_url_prefix(robot_id)
    if isinstance(value, str):
        if value.startswith(prefix):
            return f"../{value[len(prefix):]}"
        return value
    if isinstance(value, list):
        return [_localise_urls(item, robot_id) for item in value]
    if isinstance(value, dict):
        return {key: _localise_urls(item, robot_id) for key, item in value.items()}
    return value


def offline_payload(robot_id: str, *, policy_rel: str | None = None, preset: dict[str, Any] | None = None) -> dict[str, Any]:
    """离线引导层要答的两个响应：机器人列表 + browser-config（URL 已本地化）。"""

    import asyncio

    from backend.robot_presets import get_robot_preset

    preset = preset or get_robot_preset(robot_id) or {}
    canonical = str(preset.get("robot_id") or robot_id)
    presets = [{
        "robot_id": canonical,
        "family": preset.get("family") or canonical,
        "robot_package": {
            **(preset.get("robot_package") or {}),
            "browser_default": True,
        },
    }]

    from backend import simulation_api

    config = asyncio.run(simulation_api.browser_simulation_config(canonical))
    config = _localise_urls(config, canonical)
    if policy_rel:
        # 离线包里的策略就是这份 Bundle 自带的那个（在线时由 policies[] 选中）。
        config["policy"] = {
            **(config.get("policy") or {}),
            "disabled": False,
            "onnx_url": f"../{policy_rel}",
            "offline_note": "URL 由离线引导层改写为包内相对路径",
        }
    else:
        # 包里没策略：**必须置 disabled**，不能留着"指向仓库里某个模型"的 URL ——
        # 那个文件不在包里，离线机器上必然 404（页面会白等一个永远不来的 onnx）。
        # 这与页面 `?policy=off` 的口径一致（app.js 用 disabled 进手动模式）。
        config["policy"] = {
            **(config.get("policy") or {}),
            "disabled": True,
            "onnx_url": "",
            "offline_note": "包里没有策略：离线播放器进无策略（手动）模式",
        }
    return {"presets": presets, "configs": {canonical: config}, "robot": canonical}


def bootstrap_js(payload: dict[str, Any]) -> str:
    """生成拦截 `fetch` 的引导脚本（内联两份响应，不依赖任何网络）。"""

    body = json.dumps(payload, ensure_ascii=False)
    # 浏览器包 URL 的形状由 ``backend.api_routes`` 定义；这里只把它转义成 **JS 正则字面量**。
    # 此前这行是第二个（跨语言的）字面量：改前缀时 Python 侧改了、这段 JS 忘了，
    # 离线播放器就会把包内文件请求当"离线包不含该接口"回 501——一次典型的 silent break。
    asset_url_pattern = BROWSER_PACKAGE_URL_PREFIX.replace("/", chr(92) + "/")
    # Raw 字符串：下面 JS 里的 `\/` 是**给 JS 看的**转义，不该被 Python 再解释一遍
    # （不写 r 会有 SyntaxWarning: invalid escape sequence，且语义上误导读者）。
    return rf"""// 由 `backend/bundle_export.py` 生成：离线 sim2sim 引导层（I4）。
// 干什么：app.js 启动会问后端两件事（robots/presets、browser-config/<robot>），
// 这里就地答掉；包内文件走真实 fetch 的相对路径；其余 /api/* 明确回 501 而不是静默失败。
const OFFLINE = {body};
const json = (data, status = 200) => new Response(JSON.stringify(data), {{
  status, headers: {{ "Content-Type": "application/json" }},
}});
const realFetch = window.fetch.bind(window);
window.__LEGGED_OFFLINE__ = OFFLINE;
window.fetch = async (input, init) => {{
  const raw = typeof input === "string" ? input : (input && input.url) || String(input);
  const path = raw.replace(/^https?:\/\/[^/]+/, "").split("?")[0];
  if (path === "/api/robots/presets") return json({{ presets: OFFLINE.presets }});
  const configMatch = path.match(/^\/api\/simulation\/browser-config\/(.+)$/);
  if (configMatch) {{
    const key = decodeURIComponent(configMatch[1]);
    const config = OFFLINE.configs[key];
    if (config) return json(config);
    return json({{ detail: `离线包只含 ${{OFFLINE.robot}}：${{key}}` }}, 404);
  }}
  const assetMatch = path.match(/^{asset_url_pattern}/[^/]+\/(.+)$/);
  if (assetMatch) {{
    const local = `../${{assetMatch[1]}}`;
    console.info("[offline] 包内文件重写：", path, "->", local);
    return realFetch(local, init);
  }}
  if (path.startsWith("/api/")) {{
    console.warn("[offline] 离线包不含该接口：", path);
    return json({{ detail: `离线包不含 ${{path}}（该功能需要本机后端）`, offline: true }}, 501);
  }}
  return realFetch(input, init);
}};
console.info("[offline] sim2sim 离线播放器已就绪：", OFFLINE.robot);
"""


#: 随包本地服务脚本（仅 stdlib）：页面必须经 HTTP 打开（``file://`` 下 fetch/模块/wasm
#: 会被浏览器拦），并补 ``.wasm``/``.mjs`` 的 MIME（少了它 ``WebAssembly.instantiateStreaming``
#: 会因 MIME 不对而失败）；文档根设在 Bundle 根（页面里的 ``../...`` 才解析得到）。
#: 模板内嵌在本模块（与其余生成模板同惯例）——曾误写成从 /tmp 草稿文件读取，
#: 换机器即 ``FileNotFoundError``、整个 ``backend.bundle_export`` 无法 import。
SERVE_PY = '''#!/usr/bin/env python3
"""离线播放器本地服务（Legged Studio 导出物自带，仅 Python 标准库）。

用法（在导出物根目录）：

    python play/serve.py 8765

然后浏览器打开  http://localhost:8765/play/

为什么需要它：ES Module 与 fetch 在 ``file://`` 下会被浏览器拦；``.wasm``/``.mjs``
还必须有正确的 Content-Type（``WebAssembly.instantiateStreaming`` 对 MIME 很挑剔）。
文档根设在导出物根（play/ 的上一级），页面里的 ``../simulation/...`` 才解析得到。
"""

import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

#: 文档根 = 导出物根（play/ 的上一级）
ROOT = Path(__file__).resolve().parent.parent

#: 浏览器按 Content-Type 决定怎么消费：wasm 必须是 application/wasm；
#: .js/.mjs 必须是 text/javascript（Windows 注册表常把它们配成 text/plain）。
EXTRA_TYPES = {
    ".wasm": "application/wasm",
    ".mjs": "text/javascript",
    ".js": "text/javascript",
}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def guess_type(self, path):
        return EXTRA_TYPES.get(Path(str(path)).suffix.lower(), "") or super().guess_type(path)

    def end_headers(self):
        # 导出物是拷来拷去的静态物料：别让缓存遮住新包
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stdout.write("[serve] %s - %s\\n" % (self.address_string(), fmt % args))


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"服务根目录 {ROOT} -> http://localhost:{port}/play/  （Ctrl+C 停止）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\\n已停止。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def export_player(
    out_dir: Path | str,
    writer: "ExportWriter",
    *,
    robot_id: str,
    policy_rel: str | None = None,
) -> dict[str, Any]:
    """把离线播放器写进导出物（静态资源 + 引导层 + 服务脚本 + 入口页）。"""

    root = Path(out_dir)
    payload = offline_payload(robot_id, policy_rel=policy_rel)
    copied = 0
    for source in player_source_files():
        relative = source.relative_to(ROOT / "web" / "sim2sim").as_posix()
        role = "player" if "/" not in relative else "player_asset"
        writer.copy(source, f"{PLAYER_DIR}/{relative}", role=role)
        copied += 1

    writer.write_json(payload, f"{PLAYER_DIR}/offline-payload.json", role="player")
    writer.write_text(bootstrap_js(payload), f"{PLAYER_DIR}/offline-bootstrap.js", role="player")
    writer.write_text(SERVE_PY, f"{PLAYER_DIR}/serve.py", role="player")

    original = (ROOT / "web" / "sim2sim" / "index.html").read_text(encoding="utf-8")
    marker = '<script type="module"'
    if marker not in original:
        raise ValueError("web/sim2sim/index.html 里找不到应用入口 script 标签（页面结构变了？）")
    injected = original.replace(
        marker,
        '<script src="offline-bootstrap.js"></script>\n    ' + marker,
        1,
    )
    writer.write_text(injected, PLAYER_ENTRY, role="player")
    return {
        "entry": PLAYER_ENTRY,
        "files": copied + 4,
        "robot": payload["robot"],
        "policy": policy_rel,
        "how_to_open": f"python {PLAYER_DIR}/serve.py 8765 → http://localhost:8765/{PLAYER_DIR}/",
        "excluded": list(PLAYER_EXCLUDED),
    }


def verify_player(out_dir: Path | str) -> dict[str, Any] | None:
    """离线播放器的就绪情况（给 `verify bundle` 汇报；没有播放器返回 None）。"""

    root = Path(out_dir)
    entry = root / PLAYER_ENTRY
    if not entry.is_file():
        return None
    payload = _read_json(root / PLAYER_DIR / "offline-payload.json")
    problems: list[str] = []
    for required in ("offline-bootstrap.js", "serve.py"):
        if not (root / PLAYER_DIR / required).is_file():
            problems.append(f"缺 {PLAYER_DIR}/{required}")
    if payload is None:
        problems.append("缺 offline-payload.json（引导层答不出 browser-config，页面必然起不来）")
    else:
        config = ((payload.get("configs") or {}).get(payload.get("robot")) or {})
        policy_url = str((config.get("policy") or {}).get("onnx_url") or "")
        if policy_url.startswith("../"):
            target = (root / PLAYER_DIR / policy_url).resolve()
            if not target.is_file():
                problems.append(f"引导层指向的策略不在包里：{policy_url}")
    html = entry.read_text(encoding="utf-8")
    if html.find("offline-bootstrap.js") > html.find('<script type="module"'):
        problems.append("index.html 里引导层没有排在 app 之前（拦不住启动时的请求）")
    return {
        "present": True,
        "entry": PLAYER_ENTRY,
        "ready": not problems,
        "how_to_open": f"python {PLAYER_DIR}/serve.py 8765 → http://localhost:8765/{PLAYER_DIR}/",
        "problems": problems,
    }


def verify_export(out_dir: Path | str) -> dict[str, Any]:
    """校验一个导出目录：manifest schema + 必需角色 + 逐条 sha256 + 幽灵文件。

    判据全部来自**磁盘与 manifest 的对比**（不读导出时的内存状态），所以它对"从别处拷来的
    导出物"同样有效 —— 这正是 Bundle 要在干净机器上被信任的前提。
    """

    root = Path(out_dir).expanduser()
    problems: list[str] = []
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        return {"ok": False, "kind": None, "entries": 0, "problems": [f"缺 {MANIFEST_NAME}（不是导出物）：{root}"]}
    try:
        manifest = _read_json(manifest_path)
    except Exception as exc:
        return {"ok": False, "kind": None, "entries": 0, "problems": [f"{MANIFEST_NAME} 不可解析：{exc}"]}
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        problems.append(f"schema_version 应为 {MANIFEST_SCHEMA!r}，得到 {manifest.get('schema_version')!r}")
    kind = str(manifest.get("kind") or "")
    if kind not in EXPORT_KINDS:
        problems.append(f"未知 kind：{kind!r}")
        return {"ok": False, "kind": kind, "entries": 0, "problems": problems}

    entries = manifest.get("entries") or []
    registered: set[str] = set()
    for entry in entries:
        relative = str(entry.get("path") or "")
        try:
            target = root / _safe_relative(relative)
        except ValueError as exc:
            problems.append(f"{relative}: {exc}")
            continue
        registered.add(relative)
        if not target.is_file():
            problems.append(f"缺文件 {relative}（manifest 登记了但磁盘上没有）")
            continue
        actual = _sha256(target)
        if actual != entry.get("sha256"):
            problems.append(f"{relative}: sha256 与 manifest 不符（内容被改过）")
        if entry.get("bytes") is not None and target.stat().st_size != entry["bytes"]:
            problems.append(f"{relative}: 字节数与 manifest 不符")
        if not entry.get("role"):
            problems.append(f"{relative}: 缺 role")

    roles = {str(entry.get("role")) for entry in entries}
    for role in sorted(REQUIRED_ROLES[kind] - roles):
        problems.append(f"缺必需角色 {role}（这类导出至少要有 {sorted(REQUIRED_ROLES[kind])}）")

    ghost = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and path != manifest_path
        and not (_SKIP_DIRS & set(path.parts))
        and path.relative_to(root).as_posix() not in registered
    )
    if ghost:
        problems.append(f"存在 manifest 未登记的文件（幽灵文件）：{', '.join(ghost[:5])}")

    player = verify_player(root)
    quality = None
    quality_payload = _read_json(root / "quality.json") if (root / "quality.json").exists() else None
    if isinstance(quality_payload, dict):
        # 完整性 ≠ 质量：导出物自洽（ok）与"策略够不够好"是两件事，分开报（与 R1/R2/R3 同处理）。
        from backend import quality_matrix

        verdict = quality_matrix.gate(quality_payload)
        quality = {
            "tier": quality_payload.get("tier"),
            "score": verdict["score"],
            "min_score": verdict["min_score"],
            "ok": verdict["ok"],
            "blockers": verdict["blockers"],
        }

    reproduction = None
    reproduce_payload = _read_json(root / "reproduce.json") if (root / "reproduce.json").exists() else None
    if isinstance(reproduce_payload, dict):
        # 完整性 ≠ 可复现性：导出物自洽（ok）与"三档复现到什么程度"是两件事，分开报。
        from backend import reproduce as rp

        reproduction = rp.summarise(reproduce_payload)

    return {
        "ok": not problems,
        "kind": kind,
        "entries": len(entries),
        "roles": sorted(roles),
        "refs": manifest.get("refs") or {},
        "unresolved": manifest.get("unresolved") or [],
        "reproduction": reproduction,
        "quality": quality,
        "player": player,
        "problems": problems,
    }


def default_out_dir(kind: str, name: str) -> Path:
    """默认导出落点：``<workspace>/exports/<kind>-<name>``。"""

    return _workspace_root() / "exports" / f"{kind}-{name}"


def list_exports() -> list[dict[str, Any]]:
    """列出工作区里已有的导出物（供 CLI/页面展示）。"""

    root = _workspace_root() / "exports"
    if not root.is_dir():
        return []
    found: list[dict[str, Any]] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        report = verify_export(child)
        found.append({
            "name": child.name,
            "path": str(child),
            "kind": report.get("kind"),
            "entries": report.get("entries"),
            "ok": report.get("ok"),
            "unresolved": len(report.get("unresolved") or []),
        })
    return found


def iter_pack_files() -> Iterable[Path]:
    return sorted(PACKS_DIR.glob("*.pack.json")) if PACKS_DIR.is_dir() else []
