// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/program/pkg_mode/pkg_mode.h"
#include "example/program/common/my_module.h"

/**
 * @brief 注册了两个同类型模块，由 AimRT 启动。
 *        先执行配置部署目标 example-program-pkg_mode_install-SETUP_ALL，
 *        再进入到 aimrt_main 所在目录下，执行：
 *          aimrt_runtime_main --cfg_file_path=../config/example/program/pkg_mode_config.yaml
 */
AIMRTE_PKG_MAIN(
  ("MyModule1", example::program::MyModule(1, 2)),
  ("MyModule2", example::program::MyModule(3, 4)))
