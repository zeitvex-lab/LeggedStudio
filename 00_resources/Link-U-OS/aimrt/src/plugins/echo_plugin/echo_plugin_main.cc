// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#include "src/interface/aimrt_core_plugin_interface/aimrt_core_plugin_main.h"
#include "src/plugins/echo_plugin/echo_plugin.h"

extern "C" {

aimrt::AimRTCorePluginBase* AimRTDynlibCreateCorePluginHandle() {
  return new aimrt::plugins::echo_plugin::EchoPlugin();
}

void AimRTDynlibDestroyCorePluginHandle(const aimrt::AimRTCorePluginBase* plugin) {
  delete plugin;
}
}
