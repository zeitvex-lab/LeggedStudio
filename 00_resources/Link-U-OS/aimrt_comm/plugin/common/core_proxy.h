// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/interface/aimrt_module_cpp_interface/core.h"
#include "src/runtime/core/aimrt_core.h"

namespace aimrte::plugin
{
class CoreProxy
{
 public:
  explicit CoreProxy(aimrt::runtime::core::AimRTCore* core);

  ~CoreProxy() = default;

  const aimrt::runtime::core::module::CoreProxy& Get() const
  {
    return core_proxy_;
  }

  aimrt::runtime::core::module::CoreProxy& Get()
  {
    return core_proxy_;
  }

  aimrt::CoreRef GetRef() const
  {
    return aimrt::CoreRef{core_proxy_.NativeHandle()};
  }

  aimrt::runtime::core::AimRTCore* RawPtr()
  {
    return core_ptr_;
  }

  const aimrt::runtime::core::AimRTCore* RawPtr() const
  {
    return core_ptr_;
  }

 private:
  aimrt::runtime::core::AimRTCore* core_ptr_ = nullptr;
  aimrt::runtime::core::module::CoreProxy core_proxy_;
  aimrt::runtime::core::util::ModuleDetailInfo module_info_;
};

}  // namespace aimrte::plugin
