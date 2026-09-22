// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "cpu.h"

#include <cstdlib>
#include <cstring>
#include <fstream>
#include "src/hds/interface.h"

namespace aima::monitor {

#define BUFFSIZE 512

const std::tuple<double, double, double, double> cpu::cal_occupy(const CPU_OCCUPY* c1, const CPU_OCCUPY* c2) {
  double t1, t2;
  double id, sd;
  double cpu_used, cpu_sys, cpu_user, cpu_idle;

  t1 = static_cast<double>(c1->user + c1->nice + c1->system + c1->idle);
  t2 = static_cast<double>(c2->user + c2->nice + c2->system + c2->idle);

  auto user = static_cast<double>(c2->user + c2->nice - c1->user - c1->nice);
  auto sys = static_cast<double>(c2->system - c1->system);
  auto idle = static_cast<double>(c2->idle - c1->idle);
  cpu_used = (100.0 * (user + sys) / (t2 - t1));
  cpu_sys = (100.0 * sys / (t2 - t1));
  cpu_user = (100.0 * user / (t2 - t1));
  cpu_idle = (100.0 * idle / (t2 - t1));
  return std::make_tuple(cpu_used, cpu_user, cpu_sys, cpu_idle);
}

void cpu::get_cpuoccupy(std::vector<CPU_OCCUPY>& cpus, CPU_OCCUPY& total_cpu,
                        SYSTEM_SWITCH& system_switch) {
  char buff[BUFFSIZE];
  FILE* fd;
  CPU_OCCUPY cpu;
  cpus.clear();

  fd = fopen("/proc/stat", "r");
  if (fd == NULL) {
    perror("Failed to open /proc/stat");
    exit(EXIT_FAILURE);
  }

  while (fgets(buff, sizeof(buff), fd) != NULL) {
    if (strncmp(buff, "cpu", 3) == 0) {
      sscanf(buff, "%s %u %u %u %u", cpu.name, &cpu.user, &cpu.nice, &cpu.system, &cpu.idle);
      if (isdigit(cpu.name[3])) {
        cpus.push_back(cpu);
      } else if (strcmp(cpu.name, "cpu") == 0) {
        total_cpu = cpu;  // Storing total CPU stats
      }
    } else if (strncmp(buff, "intr", 4) == 0) {
      // 处理器中断次数
      sscanf(buff, "%*s %lld", &system_switch.interrupts);
    }
  }
  fclose(fd);

  for (size_t cpu_id = 0; cpu_id < cpus.size(); ++cpu_id) {
    std::string freq_file_name = fmt::format("/sys/devices/system/cpu/cpu{}/cpufreq/scaling_cur_freq", cpu_id);
    fd = fopen(freq_file_name.c_str(), "r");
    if (fd == nullptr) {
      AIMRTE_WARN("Failed to open {}", freq_file_name);
      continue;
    }
    if (fgets(buff, sizeof(buff), fd) == nullptr) {
      AIMRTE_WARN("Failed to read {}", freq_file_name);
      fclose(fd);
      continue;
    }
    cpus[cpu_id].freq_mhz = std::stoul(buff) / 1000;
    fclose(fd);
  }
}

void cpu::get_cpu_modelname() {
  std::ifstream cpuinfo("/proc/cpuinfo");
  std::string line;
  std::regex model_regex("model name\\s*:\\s*(.*)");

  while (std::getline(cpuinfo, line)) {
    std::smatch match;
    if (std::regex_match(line, match, model_regex)) {
      if (match.size() > 1) {
        std::string model_name = match[1].str();
        strncpy(cpu_model_, model_name.c_str(), sizeof(cpu_model_) - 1);
        cpu_model_[sizeof(cpu_model_) - 1] = '\0';  // Ensure null-termination
        return;
      }
    }
  }
}

cpu::cpu() {
  get_cpuoccupy(cpu_last_, total_last_, system_switch_last_);
}

bool cpu::Initialize(const YAML::Node& config) {
  if (config["max_usage"]) {
    max_usage_ = config["max_usage"].as<float>();
    AIMRTE_INFO("set cpu max usage:{}", max_usage_);
  }
  return true;
}

bool cpu::Start() {
  get_cpu_modelname();
  AIMRTE_INFO("get cpu model name:{}", cpu_model_);
  return true;
}

void cpu::Shutdown() {}

void cpu::DiagnoseOnce() {
  get_cpuoccupy(cpu_current_, total_current_, system_switch_current_);
  auto cpu_usage_tuple = cal_occupy(&total_last_, &total_current_);
  double total_usage = std::get<0>(cpu_usage_tuple);

#if defined(__x86_64__) || defined(_M_X64) || defined(__i386__) || defined(_M_IX86)
  if (total_usage >= max_usage_) {
    AIMRTE_ERROR("Total cpu usage:{} over limit:{}", total_usage, max_usage_);
  }
#else
  if (total_usage >= max_usage_) {
    AIMRTE_ERROR("Total cpu usage:{} over limit:{}", total_usage, max_usage_);
  }
#endif

  double total_freq_mhz = 0;
  for (size_t i = 0; i < cpu_current_.size(); ++i) {
    total_freq_mhz += cpu_current_[i].freq_mhz;
  }

  aimdk::protocol::CpuUsage cpu_usage_msg;

  for (size_t i = 0; i < cpu_current_.size(); ++i) {
    auto tuple = cal_occupy(&cpu_last_[i], &cpu_current_[i]);
    double cpu_usage = std::get<0>(tuple);
    // Add to protocol message
    auto& per_cpu_usage = *cpu_usage_msg.add_cpu_infos();
    per_cpu_usage.set_cpuid(i);
    per_cpu_usage.set_usage(static_cast<int>(cpu_usage));
    per_cpu_usage.set_freq_mhz(static_cast<int>(cpu_current_[i].freq_mhz));
    per_cpu_usage.set_temp(cpu_current_[i].temp);
    per_cpu_usage.set_usage_usr_space(static_cast<int>(std::get<1>(tuple)));
    per_cpu_usage.set_usage_sys_space(static_cast<int>(std::get<2>(tuple)));
    per_cpu_usage.set_usage_idle(static_cast<int>(std::get<3>(tuple)));
  }

  cpu_usage_msg.set_avg_freq_mhz(static_cast<int>(total_freq_mhz / cpu_current_.size()));
  cpu_usage_msg.set_interrupts(system_switch_current_.interrupts - system_switch_last_.interrupts);
  PubCpuData(cpu_usage_msg);

  cpu_last_ = cpu_current_;
  total_last_ = total_current_;
  system_switch_last_ = system_switch_current_;
}

void cpu::PubCpuData(const aimdk::protocol::CpuUsage& msg) {
  aimdk::protocol::SystemStatusChannel status_channel;
  status_channel.set_gist_msg_type(aimdk::protocol::SystemMsgType_CPU_USAGE);
  status_channel.mutable_cpu_usage()->CopyFrom(msg);

  if (res_.local.local_pub.IsValid()) {
    auto ctx = aimrte::ctx::init::GetCorePtr();
    ctx->Publish(res_.local.local_pub, status_channel);
  } else {
    AIMRTE_ERROR("Local publisher is not set, cannot publish CPU data.");
  }
}
}  // namespace aima::monitor
