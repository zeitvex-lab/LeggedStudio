// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/program/app_mode/app_mode.h"
#include "example/program/common/my_module.h"

/**
 * @brief 定义了 main 函数，并注册了两个同类型模块。
 *        源码编译、并启动本程序时，先执行配置部署目标：example-program-app_mode_install-SETUP_ALL
 *        再进入本程序所在目录，带着参数
 *          --cfg_file_path=../config/example/program/app_mode_config.yaml
 *        执行本程序。
 */
AIMRTE_APP_MAIN(
  ("MyModule1", example::program::MyModule(1, 2)),
  ("MyModule2", example::program::MyModule(3, 4)))
