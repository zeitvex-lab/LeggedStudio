// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./core_proxy.h"

namespace aimrte::plugin
{
CoreProxy::CoreProxy(aimrt::runtime::core::AimRTCore* core)
    : core_ptr_(core), core_proxy_(aimrt_module_info_t{.name = {"core"}})
{
  module_info_ = aimrt::runtime::core::util::ModuleDetailInfo{
    .name = "core",
  };

  core_proxy_.SetConfigurator(core->GetConfiguratorManager().GetConfiguratorProxy(module_info_).NativeHandle());
  core_proxy_.SetAllocator(core->GetAllocatorManager().GetAllocatorProxy(module_info_).NativeHandle());
  core_proxy_.SetExecutorManager(core->GetExecutorManager().GetExecutorManagerProxy(module_info_).NativeHandle());
  core_proxy_.SetLogger(core->GetLoggerManager().GetLoggerProxy(module_info_).NativeHandle());
  core_proxy_.SetRpcHandle(core->GetRpcManager().GetRpcHandleProxy(module_info_).NativeHandle());
  core_proxy_.SetChannelHandle(core->GetChannelManager().GetChannelHandleProxy(module_info_).NativeHandle());
  core_proxy_.SetParameterHandle(core->GetParameterManager().GetParameterHandleProxy(module_info_).NativeHandle());
}
}  // namespace aimrte::plugin
