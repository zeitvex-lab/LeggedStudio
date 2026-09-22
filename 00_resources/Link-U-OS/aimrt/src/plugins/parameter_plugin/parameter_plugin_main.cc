// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#include "src/interface/aimrt_core_plugin_interface/aimrt_core_plugin_main.h"
#include "src/plugins/parameter_plugin/parameter_plugin.h"

extern "C" {

aimrt::AimRTCorePluginBase* AimRTDynlibCreateCorePluginHandle() {
  return new aimrt::plugins::parameter_plugin::ParameterPlugin();
}

void AimRTDynlibDestroyCorePluginHandle(const aimrt::AimRTCorePluginBase* plugin) {
  delete plugin;
}
}
