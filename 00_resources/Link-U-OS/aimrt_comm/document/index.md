# 目录

AimRTe（AimRT extension）是在 AimRT 之上的工程化封装与增强层。本目录页用于把仓库内**分散在 README / example / src** 的说明统一收拢，作为阅读与查找入口。

- **概览**
  - [AimRTe 简介（仓库 README）](../README.zh_CN.md)
  - [English README](../README.md)

- **快速上手 / 示例**
  - [示例总览（example/README.md）](../example/README.md)
  - **按主题阅读**
    - [模块（module）：生命周期 / 通信 / 执行器 / 日志 / 配置](../example/module/README.md)
    - [程序（program）：app_mode 与 pkg_mode](../example/program/README.md)
    - [配置（cfg）：配置 DSL / 后端定义 / 嵌套配置 / 类型转换 / 自动配置](../example/cfg/README.md)

- **可运行的配置与脚本入口（推荐）**
  - **cfg demos**
    - 配置文件：`config/example/cfg/`（如 `cfg_demo1_config.yaml` 等）
    - 启动脚本：`scripts/example/cfg/`（如 `run_demo1_module.sh` 等）
  - **program demos**
    - 配置文件：`config/example/program/`（`app_mode_config.yaml` / `pkg_mode_config.yaml`）
    - 启动脚本：`scripts/example/program/`（`run_app_mode.sh` / `run_pkg_mode.sh`）
  - **module ping/pong demos**
    - 启动脚本：`scripts/example/ping/run_ping_module.sh`、`scripts/example/pong/run_pong_module.sh`

- **源码与工程（进阶阅读）**
  - **模块系统**：`src/module/`（模块配置、资源管理、模块生命周期）
  - **运行入口**：`src/main/`（主程序入口）、`src/program/`（program 模式实现）
  - **运行时上下文**：`src/ctx/`（运行循环、资源封装、Run/Cfg 等）

- **贡献与规范**
  - [CONTRIBUTING（中文）](../CONTRIBUTING.zh_CN.md)
  - [CONTRIBUTING（English）](../CONTRIBUTING.md)

---

- **常用入口（TL;DR）**
  - 想看“怎么写模块”：先读 `example/module/README.md`
  - 想看“怎么组织进程 / app_mode/pkg_mode”：读 `example/program/README.md`
  - 想看“配置怎么写 / 怎么合并补丁”：读 `example/cfg/README.md`，并配合 `config/example/*` 与 `scripts/example/*` 直接跑起来
