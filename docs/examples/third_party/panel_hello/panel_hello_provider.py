"""示范插件的**实现**（第三方代码）：一个纯数据函数，清单用真 ``module:attr`` 指过来。

协议：``docs/plugin-protocol.md``。为什么必须"纯数据"——CLI 投影与首页卡片用的是
**同一个**函数，打印/退出码那套属于脚本，不属于 provider。
"""


def hello_summary() -> dict:
    """返回 JSON 可序列化的读数（不打印、不设退出码、不读环境变量）。"""
    return {
        "greeting": "hello from a third-party panel",
        "declared_panels": 1,
        "source": "docs/examples/third_party/panel_hello",
    }
