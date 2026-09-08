# 文档索引

Legged Studio 文档分四层：**产品层**（愿景/定位/路线）、**架构层**（系统结构与数据流）、**子系统层**（桌面/Web/机器人包/适配器/后端）、**附录**（专项记录与工具说明）。

## 产品层

| 文档 | 内容 | 读者 |
|---|---|---|
| [PRODUCT_VISION.md](PRODUCT_VISION.md) | 产品愿景、闭环工作流、当前发布状态、产品边界、验收标准 | 所有人 |
| [ROADMAP.md](ROADMAP.md) | 现状盘点（基于代码核实）、缺口清单、三条发展路线（入门工具/生态平台/研究台架）与共同地基任务 | 维护者 |
| [ECOSYSTEM_PLAN.md](ECOSYSTEM_PLAN.md) | 生态平台路线（路线 B）的展开：插件协议 v1、tasks-core 平台化、分发、第二后端的分阶段实施 | 维护者 |

## 架构层

| 文档 | 内容 | 读者 |
|---|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 真实系统架构：进程模型、三层训练体系（generic/精简源/local_tasks 全框架）、契约体系、数据流、资产家底 | 开发者（先读这篇） |

## 子系统层

| 文档 | 内容 |
|---|---|
| [DESKTOP_APP.md](DESKTOP_APP.md) | Electron 启动器：启动流程、路径解析、端口/Python 设置、打包与发布、故障排查 |
| [WEB_APP.md](WEB_APP.md) | Web 工作台：两种界面形态、五功能区、浏览器 sim2sim、urdf-viewer、API 概览 |
| [ROBOT_PACKAGE.md](ROBOT_PACKAGE.md) | 机器人包工程手册：目录布局、capabilities、MJCF 标准、训练 profile、策略契约与 ONNX 元数据、验收、新机器人接入流程 |
| [DEEPROBOTICS_PORTING.md](DEEPROBOTICS_PORTING.md) | 云深处 Lite3/M20 移植记录：已落地项、待办、关键参数真值、风险清单 |
| [../backend/README.md](../backend/README.md) | 控制面 API 入口与关键端点 |
| [../adapters/mjlab/README.md](../adapters/mjlab/README.md) | MJLab 适配器：隔离环境、preflight、在线运行时 |
| [../tools/README.md](../tools/README.md) | 开发期工具链：全量训练验证器、模型转换、地形生成 |

## 附录

| 文档 | 内容 |
|---|---|
| [../web/sim2sim/optimizations.md](../web/sim2sim/optimizations.md) | sim2sim 查看器优化实施记录（mjswan 借鉴清单） |
| [../scripts/g1_parity_note.md](../scripts/g1_parity_note.md) | G1 浏览器/桌面 sim2sim 数值一致性（parity）验证方案（脚手架，未实现） |

## 文档维护约定

- **事实源优先级**：代码 > 本目录文档 > 仓库外文档。发现文档与代码不符，以代码为准并修订文档。
- **能力分级**：文档中所有能力声明必须区分「已验证 / 已内化 / 规划中」三级，禁止把规划写成已实现（沿用根 README「能力边界（诚实声明）」的口径）。
- **数字可核查**：机器人数、profile 数等硬数字必须能在代码里数出来（如 55 = `find assets/robots -path "*training/profiles*" -name "*.json" | wc -l`）。
- **版本锚定**：涉及运行时版本的内容以 `VERSION` 与 `docs/DESKTOP_APP.md` 的运行时表为准。
- **每个子系统文档自带边界声明**：写清"本模块不做什么"，防止能力越界表述扩散。
