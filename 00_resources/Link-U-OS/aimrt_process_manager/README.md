English | [中文](README.zh_CN.md)

# aimrt_process_manager

## Core Responsibilities

  - Used after a large package starts, to launch all processes based on the module configuration and environment variable information in the configuration file.
  - During startup, basic environment variable information is pre-loaded, requiring no additional configuration.
  - If a process encounters an issue during execution, it will determine whether to exit and update its internal state.
  - Supports the `aimstudio` tool for starting and stopping modules, as well as viewing the current process status.

## Common operations

![View current process status](./document/cn/image/show_status.jpg)
- View current process status


![Start the module on x86 or orin](./document/cn/image/start_app.jpg)
- Start the module on x86 or orin


![Stop the module on x86 or orin](./document/cn/image/stop_app.jpg)
- Stop the module on x86 or orin



## Documentation

 [Quick Start Guide](document/en/index.md)
