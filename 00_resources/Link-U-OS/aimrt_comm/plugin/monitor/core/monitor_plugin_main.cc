// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/interface/aimrt_core_plugin_interface/aimrt_core_plugin_main.h"
#include "monitor_plugin.h"

extern "C" {

AIMRT_CORE_PLUGIN_EXPORT aimrt::AimRTCorePluginBase* AimRTDynlibCreateCorePluginHandle()
{
  return new aimrte::plugin::monitor::MonitorPlugin();
}

AIMRT_CORE_PLUGIN_EXPORT void AimRTDynlibDestroyCorePluginHandle(
  const aimrt::AimRTCorePluginBase* plugin)
{
  delete plugin;
}
}
