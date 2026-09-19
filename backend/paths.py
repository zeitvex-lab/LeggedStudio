"""仓库 / 工作区路径约定（**唯一实现**）。

## 为什么收口（2026-09-19 取证）

``_workspace_root()`` 此前在 **7 处**各写一遍（``model_api`` / ``project_api`` /
``robot_packages`` / ``settings_api`` / ``bundle_export`` / ``quality_matrix`` / CLI），
而且**解析规则真的不一样**：

| 差异 | 后果（实测） |
|---|---|
| ``settings_api`` / CLI 做了 ``.strip()``，其余没做 | 环境变量尾部带空白（或换行）时，一部分模块解析成功、另一部分拿到畸形路径 |
| ``settings_api`` **没有** ``.resolve()`` | 环境变量给相对路径时，同一进程里"工作区根"出现两个不同字符串 —— 用 ``==`` 比较缓存键 / 前缀判断的代码会静默失配 |

同一环境变量必须解析出**同一个路径**，所以合并成这一份：``strip`` → ``expanduser``
→ 绝对化（``resolve``），环境变量为空则回落仓库 ``workspace/``。

## 用法

模块内调用点通常已叫 ``_workspace_root``；沿用该私有名委托到本模块即可
（``from backend.paths import workspace_root as _workspace_root``）——
**委托不是重复实现**，且能避开"局部变量与导入同名"的 LEGB 陷阱
（``robot_packages`` 里就有局部变量叫 ``workspace_root``）。
"""

from __future__ import annotations

import os
from pathlib import Path

#: 仓库根（``backend/`` 的上一级）。
REPO_ROOT = Path(__file__).resolve().parents[1]

#: 环境变量名：指向用户工作区（Electron 多实例 / e2e 测试都靠它切换）。
WORKSPACE_ENV = "LEGGED_STUDIO_WORKSPACE"

#: 环境变量名：指向运行期数据目录（Episode / 设置 / 模型白名单等）。
DATA_DIR_ENV = "LEGGED_STUDIO_DATA_DIR"


def repo_root() -> Path:
    """仓库根（与 ``REPO_ROOT`` 同一值；函数形式便于调用方统一风格）。"""

    return REPO_ROOT


def workspace_root() -> Path:
    """工作区根：``LEGGED_STUDIO_WORKSPACE``（strip → expanduser → 绝对化）> 仓库 ``workspace/``。

    ``strip`` 必须有：环境变量里一个尾随空格会让路径变成另一个目录（且不报错）。
    绝对化也必须有：相对路径形式下"同一根"会以多个字符串出现，缓存与前缀判断随之失配。
    """

    configured = os.environ.get(WORKSPACE_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return REPO_ROOT / "workspace"


def packages_root() -> Path:
    """工作区内的机器人包目录（``<workspace>/packages``）。"""

    return workspace_root() / "packages"


def data_dir(*, default: Path | None = None) -> Path:
    """**数据目录**（Episode / 设置 / 模型白名单等运行期数据的根）。

    统一的只是**解析规则**：``strip`` → ``expanduser`` → 绝对化，环境变量为空则用 ``default``。
    此前三处实现各缺一样，同一个环境变量在不同入口落到不同路径：

    * ``model_api``：默认值 ``Path("workspace").resolve()`` —— **相对 cwd**（换个目录启动，白名单范围就变了）；
    * ``episode_api``：不 strip、不 expanduser、不绝对化；
    * ``settings_api``：``.strip()`` 了但没 ``resolve``。

    **默认值刻意留给调用方**（``default=``）：它表达的是"这类数据的家在哪儿"
    （Episode 存档与设置文件本来就可以不同），不该被一个共用默认悄悄改掉。
    """

    configured = os.environ.get(DATA_DIR_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(default) if default is not None else workspace_root()


def api_path(path: Path | str) -> str:
    """**仓库相对 posix 路径**（不在仓库内时退回绝对路径）。

    前端与 API 用仓库相对形式传路径（``assets/robots/go2/model/robot.xml``），
    而磁盘上拿到的是绝对路径 —— 转换规则此前在 ``model_api`` 与 ``project_api``
    各写一份**逐字相同**的实现。

    回退分支也必须 ``as_posix()``：这些字符串会写进 JSON（``policy_ref.path``、
    ``asset_path``），反斜杠会让别处的路径解析按字面理解。
    """

    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


__all__ = [
    "DATA_DIR_ENV",
    "REPO_ROOT",
    "WORKSPACE_ENV",
    "api_path",
    "data_dir",
    "packages_root",
    "repo_root",
    "workspace_root",
]
