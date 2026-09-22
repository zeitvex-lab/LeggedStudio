// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <vector>
#include "src/core/interface/i_monitor.h"
#include "yaml-cpp/yaml.h"

namespace aima::monitor {

struct CPU_OCCUPY {
  char name[16];
  unsigned int user;    // 用户模式
  unsigned int nice;    // 低优先级的用户模式
  unsigned int system;  // 内核模式
  unsigned int idle;    // 空闲处理器时间
  double freq_mhz;      // 处理器主频
  int temp{0};          // 处理器温度
};

struct SYSTEM_SWITCH {
  unsigned long long interrupts;  // 用户模式
};

class cpu : public IMonitor {
 private:
  float max_usage_{90};
  std::vector<CPU_OCCUPY> cpu_last_;
  std::vector<CPU_OCCUPY> cpu_current_;
  CPU_OCCUPY total_last_;
  CPU_OCCUPY total_current_;
  SYSTEM_SWITCH system_switch_last_;  // 系统中断/上下文切换次数
  SYSTEM_SWITCH system_switch_current_;
  char cpu_model_[128];

  // return (cpu_used_percent, user_percent, system_percent, idle_percent)
  const std::tuple<double, double, double, double> cal_occupy(const CPU_OCCUPY* c1, const CPU_OCCUPY* c2);
  void get_cpuoccupy(std::vector<CPU_OCCUPY>& cpus, CPU_OCCUPY& total_cpu, SYSTEM_SWITCH& system_switch);
  void get_cpu_modelname();

 public:
  cpu();
  ~cpu() = default;
  bool Initialize(const YAML::Node& config) override;
  bool Start() override;
  void Shutdown() override;
  void DiagnoseOnce() override;
  void PubCpuData(const aimdk::protocol::CpuUsage& msg);
};

REGISTER_MONITOR_IMPL(cpu);

}  // namespace aima::monitor
