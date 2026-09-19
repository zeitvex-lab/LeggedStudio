"""跨域共享的 **API 路径约定**（单一来源）。

## 为什么单独有这一层

"浏览器包资产 URL"是跨域契约：控制面 5 处要拼、产物域要**反解**（声明里可能是 URL
形式）、离线引导层还要在 JS 里再反解一次。此前每个点自己写一遍字面量，于是：

* 前缀换一次要改六处（含嵌在 Python 字符串里的 JS 正则）；
* 路径归一规则还不一样 —— ``health_api`` 做了反斜杠归一，``simulation_api`` 没有；
* 产物域要引用它就得 import 仿真域（`backend.simulation_browser` → fastapi），
  一个路径常量不该把两个域耦合起来。

所以常量与两个拼装函数放在这里（**零业务依赖**，谁都能 import），
各域只负责"什么时候用"，不负责"URL 长什么样"。
"""

from __future__ import annotations

#: 浏览器包资产 URL 前缀：``<prefix>/<robot_id>/<包内相对路径>``。
#: 离线引导层（``bundle_export`` 生成的 JS）也用同一形状做反解，改这里即全链一致。
BROWSER_PACKAGE_URL_PREFIX = "/api/simulation/browser-package"


def browser_package_url(robot_id: str, relative_path: str) -> str:
    """包内相对路径 → 浏览器包 URL。

    反斜杠归一：声明里的路径可能来自 Windows 手写（``simulation\\policies\\x.onnx``），
    不归一会让浏览器请求 404，而报错只显示"策略下载失败"，指向性极差。
    """

    normalized = str(relative_path).replace(chr(92), "/").lstrip("/")
    return f"{BROWSER_PACKAGE_URL_PREFIX}/{robot_id}/{normalized}"


def browser_package_url_prefix(robot_id: str) -> str:
    """某机型的 URL 前缀（含尾斜杠）：``base_url`` 与离线引导层反解共用同一形状。"""

    return f"{BROWSER_PACKAGE_URL_PREFIX}/{robot_id}/"


__all__ = [
    "BROWSER_PACKAGE_URL_PREFIX",
    "browser_package_url",
    "browser_package_url_prefix",
]
