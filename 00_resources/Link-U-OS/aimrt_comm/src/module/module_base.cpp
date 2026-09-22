// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/common/util/string_util.h"

#include "./init.h"
#include "./module_base.h"

namespace aimrte::ctx
{
ModuleCfg ModuleBase::Configure(Cfg& cfg, std::string module_name)
{
  is_configured = true;

  ModuleCfg module_cfg(&cfg, &ctx_res_manager_, std::move(module_name));
  OnConfigure(module_cfg);
  return module_cfg;
}

aimrt::ModuleInfo ModuleBase::Info() const noexcept
{
  return {};  // 其中的 name 将由 AimRTe 的 app mode 设置，其他信息之后将由 CMake Kit 提供
}

bool ModuleBase::Initialize(const aimrt::CoreRef core) noexcept
{
  // 初始化模块上下文数据，以支撑模块调用 aimrte::ctx 的接口
  ctx_ptr_ = ctx::Init(core);
  global_logger = core.GetLogger();

  // 若模块配置流程没有执行过，则需要模拟配置初始化的过程，确保用户的配置流程被执行
  if (not is_configured) {
    is_configured = true;
    std::string name(core.Info().name);

    Cfg cfg(0, nullptr, name);
    cfg.SetModuleConfig(name, GetConfigYaml());

    ModuleCfg module_cfg(&cfg, &ctx_res_manager_, std::move(name));
    OnConfigure(module_cfg);
  }

  // 初始化资源
  ctx_res_manager_.Prepare(ctx_ptr_, GetInfo());
  ctx_res_manager_.Initialize();

  // 执行用户模块子类实现的初始化过程
  return OnInitialize();
}

bool ModuleBase::Start() noexcept
{
  ctx_ptr_->LetMe();
  return OnStart();
}

void ModuleBase::Shutdown() noexcept
{
  global_logger = aimrt::logger::LoggerRef(nullptr);
  ctx_ptr_->LetMe();
  ctx_ptr_->RequireToShutdown();
  OnShutdown();
}

std::shared_ptr<core::Context> ModuleBase::GetContextPtr() const
{
  return ctx_ptr_;
}

aimrt::CoreRef ModuleBase::GetCoreRef() const
{
  return core::Context::GetRawRef(*ctx_ptr_);
}

aimrt::ModuleInfo ModuleBase::GetInfo() const
{
  return GetCoreRef().Info();
}

YAML::Node ModuleBase::GetConfigYaml() const
try {
  const aimrt::configurator::ConfiguratorRef configurator_ref = GetCoreRef().GetConfigurator();
  if (not configurator_ref) {
    ctx::log().Error("Fail to get AimRT configurator for [{}] module !", GetInfo().name);
    return {};
  }

  const auto file_path = std::string(configurator_ref.GetConfigFilePath());
  if (file_path.empty()) {
    ctx::log().Error("[{}] module's config file path is empty !", GetInfo().name);
    return {};
  }

  return YAML::Load(aimrt::common::util::ReplaceEnvVars(Dump(YAML::LoadFile(file_path))));
} catch (const std::exception& ec) {
  ctx::log().Error("Fail to parse config as yaml for module [{}] !", GetInfo().name);
  return {};
}
}  // namespace aimrte::ctx
