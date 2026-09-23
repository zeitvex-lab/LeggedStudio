"""机器人包定位（**唯一实现**）：``robot_id`` → 包根 / preset 条目。

## 为什么单独有这一层（2026-09-19 实测取证）

"包根从哪来"此前在三处各写一遍，规则还不一样：

| 输入 | 部署域（``deploy_pack``） | 仿真域（``simulation_browser``） |
|---|---|---|
| ``unitree_go2`` | ✅ 包根 | ✅ 包根 |
| ``zex_w``（下划线写法） | ❌ NotFound | ✅ ``assets/robots/zex-w`` |
| ``no_such_robot`` | ``RobotPackageNotFound`` | ``HTTPException(404)`` |

`zex-w` 是全仓唯一带连字符的 ``robot_id``，而页面/CLI 里手写下划线是常态 ——
于是同一台机器"浏览器能跑、部署包导不出"，而两边的报错都不提"你写的 id 差一个符号"。

收口成一份后，**各域只保留自己的前置条件**（仿真域要求包内有 MJCF 模型、
部署域要求契约真值存在），定位规则与异常类型不再各说各话。

## 命名口径

* ``normalize_robot_id``：把 ``_``/``-`` 与大小写抹平，用于**匹配**（不用于拼路径，
  磁盘上目录名以真实存在者为准）；
* ``resolve_package_entry``：返回 ``(canonical_id, root, preset)`` —— canonical id 用于
  拼浏览器 URL/落盘目录名，root 用于读文件。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

#: 视为同一台机器的分隔符（``zex-w`` / ``zex_w`` / ``ZEX-W`` 等价）。
_ALIAS_SEPARATORS = {ord("-"): "_", ord("_"): "_"}


class RobotPackageNotFound(FileNotFoundError):
    """包不存在 / 包根缺失。

    继承 ``FileNotFoundError`` 是**有意的**（沿用 ``deploy_pack`` 的既有契约）：
    控制面统一把这一类映射 404，调度方不必知道包解析细节；CLI 用 ``robot_id`` /
    ``attempted`` 组织中文提示，不吃异常字符串。

    刻意不做 HTTP 化：CLI 与无头工具也要 catch 它。各入口翻成自己的形态
    （``HTTPException(404)`` / 退出码 1 / 报告里的一条 problem），措辞由入口组织。
    """

    def __init__(self, robot_id: str, tried: list[str] | None = None, *, preset_resolved: bool = False) -> None:
        self.robot_id = robot_id
        self.tried = list(tried or [])
        #: preset 是否解析到了（True = 登记在册但包根缺失 ⇒ 安装损坏；False = 这台机器没登记过）
        self.preset_resolved = bool(preset_resolved)
        self.attempted = Path(self.tried[-1]) if self.tried else None
        detail = f"robot package not found: {robot_id!r}"
        if self.tried:
            detail += f"（已尝试：{', '.join(self.tried)}）"
        super().__init__(detail)


def normalize_robot_id(value: str) -> str:
    """归一化用于**比较**的 robot id：大小写 + ``_``/``-`` 抹平。"""

    return str(value or "").strip().lower().translate(_ALIAS_SEPARATORS)


def _find_preset(robot_id: str) -> dict[str, Any] | None:
    from backend.robot_presets import get_robot_preset, list_robot_presets

    preset = get_robot_preset(robot_id)
    if preset is not None:
        return preset
    normalized = normalize_robot_id(robot_id)
    return next(
        (item for item in list_robot_presets()
         if isinstance(item, dict) and normalize_robot_id(str(item.get("robot_id") or "")) == normalized),
        None,
    )


def resolve_package_entry(robot_id: str) -> tuple[str, Path, dict[str, Any]]:
    """解析为 ``(canonical_id, package_root, preset)``；失败抛 :class:`RobotPackageNotFound`。

    解析顺序（命中即停）：

    1. ``robot_id`` **精确**命中 preset；
    2. 归一后命中 preset（``zex_w`` → ``zex-w``）—— 与人工在页面/CLI 里的写法对齐；
    3. preset 的 ``robot_package.package_root`` 存在 ⇒ 用之（workspace 副本优先）；
    4. 否则回落 ``assets/robots/<robot_id>``，并再试一遍归一后的目录名（磁盘上真实存在者为准）。
    """

    wanted = str(robot_id or "").strip()
    if not wanted:
        raise RobotPackageNotFound(robot_id, ["robot_id 为空"])

    preset = _find_preset(wanted)
    tried: list[str] = []
    if preset:
        canonical = str(preset.get("robot_id") or wanted)
        root_value = str(((preset.get("robot_package") or {}).get("package_root")) or "")
        if root_value:
            root = Path(root_value)
            tried.append(str(root))
            if root.exists():
                return canonical, root.resolve(), preset
        fallback = ROOT / "assets" / "robots" / canonical
        tried.append(str(fallback))
        if fallback.exists():
            return canonical, fallback.resolve(), preset

    # 无 preset（外部/未登记目录）也要能定位：目录名精确 → 归一后匹配。
    exact = ROOT / "assets" / "robots" / wanted
    tried.append(str(exact))
    if exact.is_dir():
        return wanted, exact.resolve(), preset or {}
    robots_root = ROOT / "assets" / "robots"
    if robots_root.is_dir():
        normalized = normalize_robot_id(wanted)
        match = next(
            (item for item in sorted(robots_root.iterdir())
             if item.is_dir() and normalize_robot_id(item.name) == normalized),
            None,
        )
        if match is not None:
            return match.name, match.resolve(), preset or {}
    raise RobotPackageNotFound(wanted, tried, preset_resolved=bool(preset))


def resolve_package_root(robot_id: str) -> Path:
    """只要包根时的薄封装（``deploy_pack`` 等处按名 re-export 本函数）。"""

    return resolve_package_entry(robot_id)[1]


def _read_contract(path: Path) -> dict[str, Any] | None:
    """读一份 JSON 契约（解析失败/非对象一律 ``None``，不抛）。"""

    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _contract_view(package_dir: Path) -> dict[str, Any] | None:
    """读包的**契约视图**（v2 视图语义）：``contract_legacy_v2.json`` 优先，其次清单指认的 ``contract_path``。

    刻意**不做形状转换**：会话/仿真入口把这份 data 直接喂给 v2 形状的模型
    （``ContractLegacyV2``），拿真值契约冒充只会得到一堆校验错误。
    只有真值契约、没有 v2 视图的包在这里反查不到 —— 这是如实，不是静默降级。
    """

    candidate = package_dir / "contract_legacy_v2.json"
    if candidate.is_file():
        return _read_contract(candidate)
    manifest = package_dir / "robot_package.json"
    if manifest.is_file():
        payload = _read_contract(manifest)
        declared = str((payload or {}).get("contract_path") or "")
        if declared:
            target = package_dir / declared
            if target.is_file():
                return _read_contract(target)
    return None


def robot_definition(robot_id: str) -> dict[str, Any] | None:
    """会话/仿真入口用的"机器人定义"：**preset 优先，其次按包内契约反查工作区包**。

    与 :func:`resolve_package_entry` 的两点区别都是有意的：

    * **quiet**：找不到返回 ``None``，由调用方决定 404 措辞（仿真会话允许"先用请求里
      自带的 contract 建会话"，不能在这里就抛）；
    * **反查**：导入的包不在 preset 表里，只能按包内契约的 ``robot_id`` 找。

    返回形状沿用既有契约（调用方按 v2 视图读字段）::

        {"robot_id", "family", "contract", "asset_path"}

    取证（2026-09-19）：这段扫描此前在 ``simulation_api`` 里自带一份，硬编码
    ``<repo>/workspace/packages``（**不认** ``LEGGED_STUDIO_WORKSPACE`` ——
    多实例 / e2e 测试下会去错的目录找包），且只认 ``contract_legacy_v2.json``。
    """

    from backend.paths import packages_root

    wanted = str(robot_id or "").strip()
    if not wanted:
        return None

    preset = _find_preset(wanted)
    if preset is not None:
        return preset

    root = packages_root()
    if not root.is_dir():
        return None
    normalized = normalize_robot_id(wanted)
    for package_dir in sorted(item for item in root.iterdir() if item.is_dir()):
        contract = _contract_view(package_dir)
        if not contract:
            continue
        names = {normalize_robot_id(str(contract.get("robot_id") or "")), normalize_robot_id(package_dir.name)}
        if normalized in names:
            declared = str((contract.get("urdf") or {}).get("path") or "")
            return {
                "robot_id": str(contract.get("robot_id") or package_dir.name),
                "family": contract.get("family") or package_dir.name,
                "contract": contract,
                # 与 ``package_records.build_package_record`` 的 ``asset_path`` 同口径（**绝对路径**）：
                # 它表示"模型文件在哪"，相对路径是半个答案（cwd 一变就错）。
                "asset_path": str((package_dir / declared).resolve()) if declared else "",
            }
    return None


__all__ = [
    "RobotPackageNotFound",
    "normalize_robot_id",
    "resolve_package_entry",
    "resolve_package_root",
    "robot_definition",
]
