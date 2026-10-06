"""插件内核 v1 兼容门面——本体已升级为 :mod:`plugins.runtime`（``00_know/08`` v3.0 Phase 1）。

v2 内核（服务上下文 / 事件五模式 / ``mount`` 拓扑装载 / patch 整行替换）保留 v1 的
全部导出面与语义；``backend/test_plugin_core.py``（v1 回归锁）全绿即兼容证明。
新代码请直接消费 :mod:`plugins.runtime`。
"""

from plugins.runtime import Context, Entry, PluginError, apply_patch, load_entries, merge_entries

__all__ = ["PluginError", "Entry", "Context", "load_entries", "merge_entries", "apply_patch"]
