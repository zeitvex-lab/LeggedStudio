"""JSON 读写（**唯一实现**，住在最底层）：统一编码口径与失败语义。

## 为什么要收口

JSON 读取在本仓有 **20 多份**逐字近似的小实现，而且**编码口径真的不一样**：

* ``utf-8-sig``（吃 BOM）：``resource_packs`` / ``robot_packages`` / ``skill_pack`` /
  ``skill_registry`` / ``bundle_export`` / ``reproduce`` / ``motion_registry`` / ``plugin_protocol`` …
* ``utf-8``（**吃不了 BOM**）：``policy_artifacts`` / ``training.runs``

BOM 不是理论问题：Windows 的编辑器、PowerShell 重定向、以及部分导出工具默认写 BOM。
带 BOM 的 ``policies/index.json`` 或 run 档案会让 ``json.loads`` 在**第一个字节**就抛
（``Expecting value: line 1 column 1``）—— 报错完全不指向"编码"，排查成本很高。

## 两个入口，语义各自明确

| 入口 | 缺失 / 坏 JSON / 编码错 | 适用 |
|---|---|---|
| :func:`load_json` | **原样抛** | 调用方要把它包成自己的域错误（``ResourcePackError`` 等） |
| :func:`read_json` | 返回 ``default``（可选 ``require`` 类型检查） | 调用方按"空清单 / 没有"继续 |

**各模块保留自己的薄封装**（``_load_json`` / ``_read_json``），把各自的语义写在名字旁边；
实现只有这一处 —— 与 ``contracts/validator.normalized_sha256`` 同一条纪律。

## 为什么住在 ``contracts/`` 而不是 ``backend/``

它要同时被**三处**复用：``backend/``（控制面）、``tools/``（门禁脚本）、``contracts/`` 自己
（``contract_loader``）。``contracts`` 是最底层且零第三方依赖，放这里才不会出现
"底层反向依赖控制面"——这与摘要口径（``normalized_sha256``）当初的落点选择一致。
``backend/jsonio.py`` 保留一行 re-export，既有 import 路径照旧可用。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

#: 读取编码：``utf-8-sig`` 会自动吃掉 BOM，对无 BOM 文件与 ``utf-8`` 完全等价。
JSON_ENCODING = "utf-8-sig"

T = TypeVar("T")


def load_json(path: Path | str) -> Any:
    """严格读 JSON：文件缺失、内容坏、编码错都**原样抛**（由调用方包装成语义化错误）。"""

    return json.loads(Path(path).read_text(encoding=JSON_ENCODING))


def read_json(path: Path | str, *, default: T = None, require: type | tuple[type, ...] | None = None) -> Any:
    """宽容读 JSON：任何失败返回 ``default``；给了 ``require`` 则类型不符也返回 ``default``。

    ``require`` 是为 ``robot_packages._read_json`` 这类"非对象即视为空清单"的既有语义准备的
    —— 语义留在调用方，实现留在这里。
    """

    try:
        payload = load_json(path)
    except (OSError, json.JSONDecodeError, ValueError):
        # ValueError 覆盖 UnicodeDecodeError（非 UTF-8 字节）
        return default
    if require is not None and not isinstance(payload, require):
        return default
    return payload


def write_json(path: Path | str, payload: Any, *, indent: int = 2, sort_keys: bool = False) -> None:
    """写 JSON（UTF-8、无 BOM、尾随换行）—— 仓内既有写法的形状。

    **不提供原子写**：原子性是另一件事（临时文件 + rename），需要它的模块自己封装，
    别把两件事混进一个函数里。
    """

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=indent, sort_keys=sort_keys) + "\n",
        encoding="utf-8",
    )


__all__ = ["JSON_ENCODING", "load_json", "read_json", "write_json"]
