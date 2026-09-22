// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/module/health_monitor_module.h"
#include "src/core/monitor/register.hpp"

namespace aima::monitor {
void HealthMonitorModule::OnConfigure(aimrte::ctx::ModuleCfg& cfg)
{
  // config_ = GetConfigYaml();
  cfg.ConfigAndDefineByDefault(res_.regular);
  // cfg[aimrte::cfg::Ch::ros2].Def(res_.regular.system_status_pub, config_["system_status_topic"].as<std::string>());

  std::string system_status_topic_name = (aimrte::sys::GetSOCIndex() == 0) ? "/aima/hds/system_status_soc0" : "/aima/hds/system_status_soc1";
  cfg[aimrte::cfg::Ch::ros2].Def(res_.regular.system_status_pub, system_status_topic_name);
  cfg[aimrte::cfg::Ch::mqtt].Def(res_.mqtt);
  cfg[aimrte::cfg::Ch::local].Def(res_.local);
}

bool HealthMonitorModule::OnInitialize()
{
  config_ = GetConfigYaml();

  // Initialize monitors
  for (const auto& monitor : config_["monitor"]) {
    auto name = monitor["name"].as<std::string>();
    auto enable = monitor["enable"].as<bool>();
    auto rate = monitor["rate"].as<float>();
    AIMRTE_INFO("load monitor name:{} enable:{} rate:{}", name, enable, rate);
    if (!enable) {
      continue;
    }
    auto register_func = MonitorRegister::Instance()->GetRegisterFunc(name);
    if (register_func == nullptr) {
      AIMRTE_ERROR("monitor not found:{}", name);
      continue;
    }
    monitor_map_[name] = register_func();
    bool init = monitor_map_[name]->Initialize(monitor, res_);
    AIMRTE_INFO("monitor {} initialize {}", name, init ? "success" : "failed");
  }
  return true;
}

bool HealthMonitorModule::OnStart()
{
  // Start monitors
  for (auto& [name, monitor] : monitor_map_) {
    bool start = monitor->Start();
    AIMRTE_INFO("monitor {} start {}", name, start ? "success" : "failed");

    auto raw_monitor = monitor.get();
    aimrte::ctx::exe(res_.regular.work_thread_pool).Post(scope_, [this, raw_monitor]() -> aimrte::co::Task<void> {
      while (aimrte::ctx::Ok()) {
        raw_monitor->DiagnoseOnce();
        co_await aimrte::ctx::Sleep(std::chrono::milliseconds(static_cast<int>(1000 / raw_monitor->GetRate())));
      }
    });
  }
  return true;
}

void HealthMonitorModule::OnShutdown()
{
  for (auto& [name, monitor] : monitor_map_) {
    monitor->Shutdown();
  }
  aimrt::co::SyncWait(scope_.complete());
}
}
