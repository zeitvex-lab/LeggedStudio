// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/module/cfg_processor.h"
#include "src/module/module_base.h"
#include "src/program/details/named_module.h"
#include "src/runtime/interface/interface.h"
#include "src/sys/internal/config.h"
#include "gflags/gflags.h"
#include <csignal>
#include <iostream>

#include "./app_mode.h"

namespace aimrte::program_details
{
std::int32_t Main(std::int32_t argc, char** argv, const ModuleCreatorSpan& module_creators)
{
  NamedModulePtrList modules;
  for (auto& [name, module_creator] : module_creators) {
    modules.emplace_back(name, std::shared_ptr<aimrt::ModuleBase>(module_creator()));
  }

  Cfg cfg(argc, argv, {});

  if (not sys::config::EnableOnlineMode())
    cfg[cfg::backend::Log::console] = {};

  return Run(cfg, std::move(modules));
}
}  // namespace aimrte::program_details

namespace aimrte
{
DEFINE_bool(register_signal, true, "register handle for sigint and sigterm");
DEFINE_bool(ignroe_predefined_cfg, false, "ignore configuration that is predefined in code (misspelling, keep it for compatibility)");  // (yt): 拼错了，但是为了兼容性，留着先。
DEFINE_bool(ignore_predefined_cfg, false, "ignore configuration that is predefined in code");
DEFINE_int32(shutdown_after_seconds, 0, "shutdown after the given seconds");
DEFINE_string(patch_cfg_file_path, "", "Patch config file paths, they will patch after your main config file, you can set multiple files separated by comma.");
DEFINE_bool(dump_only, false, "Dump full config file then exit the program.");

runtime::ICore* g_core_ptr = nullptr;

static void SignalHandler(const int sig)
{
  if (g_core_ptr and (sig == SIGINT || sig == SIGTERM)) {
    std::cerr << "receive signal " << sig << ", require framework to shutdown." << std::endl;
    g_core_ptr->Shutdown();
    return;
  }

  raise(sig);
}

std::int32_t Run(Cfg& cfg, NamedModulePtrList modules)
{
  // 初始化minidump
  // aimrte::minidump::MinidumpManager::GetInstance().Initialize();

  // 处理配置的初始化
  Cfg::Processor cfg_processor(cfg);

  for (auto& [name, module_ptr] : modules) {
    auto aimrte_module_ptr = std::dynamic_pointer_cast<ctx::ModuleBase>(module_ptr);

    // 无法处理非 AimRTe 模块
    if (aimrte_module_ptr == nullptr)
      continue;

    cfg_processor.AddModuleConfig(aimrte_module_ptr->Configure(cfg, name));
  }

  // 设置用户补丁配置列表
  cfg_processor.SetUserPatchConfigFilePaths(utils::SplitTrim(FLAGS_patch_cfg_file_path, ','));

  // 设置框架配置
  cfg::details::CoreConfig core_config = cfg_processor.GetCoreConfig();

  // 是否使用 .dump 文件进行临时调试。如果程序还未执行过，.dump 文件不存在会导致报错。
  if (sys::config::EnableIgnorePredefinedCfgAndUseDumpFile()) {
    FLAGS_ignore_predefined_cfg = true;
    core_config.cfg_file_path   = core_config.dump_cfg_file_path;
    core_config.dump_cfg_file   = false;
  } else {
    // (yt): 拼错了，但为了兼容性，先留着。
    FLAGS_ignore_predefined_cfg =
      FLAGS_ignore_predefined_cfg or
      FLAGS_ignroe_predefined_cfg or
      sys::config::EnableIgnorePredefinedCfg();

    if (not FLAGS_ignore_predefined_cfg)
      core_config.cfg_file_path = cfg_processor.DumpFile();

    if (core_config.dump_cfg_file) {
      std::filesystem::copy_file(core_config.cfg_file_path, core_config.dump_cfg_file_path, std::filesystem::copy_options::overwrite_existing);
    }
  }

  AIMRTE(defer(
    if (not FLAGS_ignore_predefined_cfg)
      std::filesystem::remove(core_config.cfg_file_path);));

  if (FLAGS_dump_only) {
    const std::string& original_cfg_file_path = cfg_processor.GetCoreConfig().cfg_file_path;

    std::filesystem::copy_file(
      core_config.cfg_file_path,
      "./" + std::filesystem::path(original_cfg_file_path).filename().string() + ".dump",
      std::filesystem::copy_options::overwrite_existing);

    std::exit(0);
  }

  // 启动 AimRT
  std::cout << "AimRT start." << std::endl;

  runtime::Library core_lib;
  g_core_ptr = &core_lib.Ref();
  g_core_ptr->RegisterHook(
    runtime::State::kPostStart,
    []() {
      // 注册信号函数
      if (FLAGS_register_signal) {
        signal(SIGINT, SignalHandler);
        signal(SIGTERM, SignalHandler);
      }
    }
  );

  try {
    std::vector<std::unique_ptr<program_details::NamedModule>> named_modules;
    named_modules.reserve(modules.size());

    // 注册模块
    for (auto& [name, module_ptr] : modules) {
      g_core_ptr->RegisterModule(
        named_modules
          .emplace_back(
            std::make_unique<program_details::NamedModule>(name, std::move(module_ptr)))
          ->NativeHandle());
    }

    // 初始化框架
    g_core_ptr->Initialize(core_config.cfg_file_path);

    std::jthread immediately_shutdowm_th;

    if (FLAGS_shutdown_after_seconds != 0) {
      immediately_shutdowm_th = std::jthread([]() {
        std::this_thread::sleep_for(std::chrono::seconds(FLAGS_shutdown_after_seconds));
        if (g_core_ptr) {
          std::cerr << "shutdown by --shutdown_after_seconds=" << FLAGS_shutdown_after_seconds << " argument ..." << std::endl;
          g_core_ptr->Shutdown();
        }
      });
    }

    // 启动框架
    g_core_ptr->Start();
    g_core_ptr->WaitStarted();

    /// 框架将被阻塞，直到被关闭

    // 确保框架关闭
    g_core_ptr->Shutdown();
    g_core_ptr = nullptr;
  } catch (const std::exception& e) {
    std::cerr << "AimRT run with exception and exit. " << e.what() << std::endl;
    return -1;
  }

  std::cout << "AimRT exit." << std::endl;
  return 0;
}
}  // namespace aimrte
