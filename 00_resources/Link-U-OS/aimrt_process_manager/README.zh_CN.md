[English](README.md) | 中文

# aimrt_process_manager

## 核心职责
  - 用于大包启动后，根据配置文件中模块的配置和环境变量信息，启动所有进程
  - 启动过程中，会预先加载基本的环境变量信息，无需额外配置
  - 当进程运行过程中出现问题，会判断是否退出，并更新内部状态
  - 支持`aimstudio`工具对模块进行启动和停止，以及查看当前进程状态

## 常用操作

![查看当前进程状态](./document/cn/image/show_status.jpg)
- 查看当前进程状态


![启动x86(或orin)上的模块](./document/cn/image/start_app.jpg)
- 启动x86(或orin)上的模块


![停止x86(或orin)上的模块](./document/cn/image/stop_app.jpg)
- 停止x86(或orin)上的模块



## 文档

 [快速开始指南](document/cn/index.md)
