// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include <csignal>
#include <fstream>
#include <iostream>

#include "gflags/gflags.h"

#include "src/runtime/core/aimrt_core.h"
#include "core/util/version.h"

#include "src/module/process_manager_module.h"
#include "src/module/preparation.h"

DEFINE_string(cfg_file_path, "", "config file path");

DEFINE_string(dump_cfg_file_path, "./dump_cfg.yaml", "dump config file path");

using namespace aimrt::runtime::core;
using namespace process_manager;

AimRTCore* global_core_ptr = nullptr;

Preparation* global_preparation_ptr = nullptr;

void SignalHandler(int sig) {
  if (global_preparation_ptr && (sig == SIGINT || sig == SIGTERM)) {
    global_preparation_ptr->Shutdown();
  }

  if (global_core_ptr && (sig == SIGINT || sig == SIGTERM)) {
    global_core_ptr->Shutdown();
  }
}

int32_t main(int32_t argc, char** argv) {

  gflags::ParseCommandLineNonHelpFlags(&argc, &argv, true);

  signal(SIGINT, SignalHandler);
  signal(SIGTERM, SignalHandler);

  std::cout << "AimRT start, version: " << util::GetAimRTVersion() << std::endl;

  try
  {
    Preparation preparation;
    global_preparation_ptr = &preparation;

    // todo
    preparation.Init(FLAGS_cfg_file_path);
    preparation.Start();

    AimRTCore core;
    global_core_ptr = &core;

    AimRTCore::Options options;
    options.cfg_file_path = FLAGS_cfg_file_path;

    PMModule process_manager_module;

    core.GetModuleManager().RegisterModule(process_manager_module.Info().name, process_manager_module.NativeHandle());
    // 初始化前, 提前注册module
    core.Initialize(options);

    {
      std::ofstream ofs(FLAGS_dump_cfg_file_path, std::ios::trunc);
      ofs << core.GetConfiguratorManager().GetRootOptionsNode();
      ofs.close();
    }

    // 需要在 Start 之前, 将所有相关的资源都初始化好
    core.Start();

    global_core_ptr = nullptr;
  } catch(const std::exception& e) {
    std::cout << "AimRT run with exception and exit. " << e.what() << std::endl;
    return -1;
  }

  std::cout << "AimRT exit." << std::endl;
  return 0;
}
