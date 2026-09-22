# 第一章 快速开始

## 1.1 项目介绍

AimRT Viz 是一款面向由 AimRT 节点构建的系统的可视化运行时观测工具，可直观展示各节点及其关联关系，助力系统的监控与分析。


## 1.2 安装说明

### 1.2.1 环境与依赖

* 环境（参考 AimRT 安装与引用， 以选择合适的开发环境）
    * cmake 3.24+
    * gcc 11.4+
    * clang 15.0+
    * 包管理器: pnpm 8.7.0+
    * 操作系统： 推荐 Ubuntu 22.04


### 1.2.2 构建并安装

```bash
./build.sh
```

### 1.2.3 运行示例


* 端侧系统启动

```bash
cd src/examples/viz/install/linux/bin
./start_all_example.sh &           # 启动示例节点（含 viz_plugin）
./start_examples_viz_module.sh     # 启动 VizModule（HTTP 暴露 50090）
```

* 前端启动

```bash
cd src/tools/viz_web
pnpm install
pnpm dev
```

打开浏览器访问本地开发地址，输入 `127.0.0.1:50090` 连接即可。


## 项目结构

```text
AiMRT_VIZ
├── build.sh
├── cmake/
├── document/
├── src/
│   ├── CMakeLists.txt
│   ├── examples/
│   ├── module/
│   ├── pkg/
│   ├── plugins/
│   ├── protocols/
│   └── tools/viz_web/
├── test.sh
├── VERSION
└── CMakeLists.txt
```