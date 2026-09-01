# Legged Studio 协作状态

**更新时间**：2026-08-31

Claude 已结束当前工作，Codex 已接管项目文件。此前的文件所有权限制已解除；`backend/server.py` 作为 legacy 通信 fixture 保留，默认产品入口统一为 `backend/app.py:8000`。

## 当前模块边界

| 模块 | 状态 | 约束 |
|---|---|---|
| `backend/app.py` | 可运行 | 只读控制面，不 import 训练框架 |
| `contracts/` | 基础模型完成 | 后续 schema 必须有版本和 roundtrip test |
| `web/` | 资产工作台可运行 | 3D 能力通过 URDF Studio adapter 接入 |
| `electron/` | 已切换产品入口 | GUI 生命周期仍需人工验收 |
| MJLab worker | 待实现 | Python 3.12 独立进程，只交换 JSON/Artifact/事件 |

## 并行协作规则

- 每个智能体只修改明确分配的模块，跨模块先发消息同步。
- inventory JSON 是资产机器事实源；分类变更必须同步 scanner、Markdown、Contract、自检、API 和 UI。
- 不复制许可证未确认的参考项目源码到可分发产品。
- 不重新实现 URDF/MJCF parser、Three.js viewer、训练算法或评估 pipeline；优先做成熟项目 adapter。
- 合并前运行 backend tests、Contract selfcheck 和相关 JS/Python 语法检查。
