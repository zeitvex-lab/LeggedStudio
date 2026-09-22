// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/interface/aimrt_module_cpp_interface/module_base.h"
#include <memory>

namespace aimrte::program_details
{
class NamedModule final : public aimrt::ModuleBase
{
 public:
  NamedModule(const std::string_view& name, std::shared_ptr<ModuleBase> impl)
      : name_(name), impl_(std::move(impl))
  {
  }

  ~NamedModule() override = default;

  aimrt::ModuleInfo Info() const noexcept override
  {
    aimrt::ModuleInfo info = impl_->Info();
    info.name              = name_;
    return info;
  }

  bool Initialize(const aimrt::CoreRef core) noexcept override
  {
    return impl_->Initialize(core);
  }

  bool Start() noexcept override
  {
    return impl_->Start();
  }

  void Shutdown() noexcept override
  {
    impl_->Shutdown();
  }

 private:
  // 注册时的模块名称
  std::string_view name_;

  // 创建出来的模块
  std::shared_ptr<ModuleBase> impl_;
};
}  // namespace aimrte::program_details
