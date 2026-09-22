// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#include "process_info.h"
#include <sys/resource.h>
#include <unistd.h>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <thread>

namespace aimrt::plugins::viz_plugin {

void ProcessInfoManager::Initialize(std::string pid) {
  pid_ = pid;
  mem_total_ = GetMemoryTotal();
}
uint64_t ProcessInfoManager::GetMemoryUsageKb() {
  std::string stat_path = "/proc/" + pid_ + "/status";
  std::ifstream stat_file(stat_path);

  if (!stat_file.is_open()) {
    return 0;
  }

  std::string line;
  while (std::getline(stat_file, line)) {
    if (line.find("VmRSS:") != std::string::npos) {
      std::istringstream iss(line);
      std::string name;
      uint64_t memory_kb;
      std::string unit;

      iss >> name >> memory_kb >> unit;
      return memory_kb;
    }
  }

  return 0;
}

uint64_t ProcessInfoManager::GetMemoryTotal() {
  std::ifstream meminfo_file("/proc/meminfo");
  if (!meminfo_file.is_open()) {
    return 0;
  }
  std::string line;
  while (std::getline(meminfo_file, line)) {
    if (line.rfind("MemTotal:", 0) == 0) {
      std::istringstream iss(line);
      std::string name;
      uint64_t total_memory_kb;
      std::string unit;

      iss >> name >> total_memory_kb >> unit;
      return total_memory_kb;
    }
  }
  return 0;
}

uint64_t ProcessInfoManager::GetThreadCount() {
  std::string status_path = "/proc/" + pid_ + "/status";
  std::ifstream status_file(status_path);

  if (!status_file.is_open()) {
    return 0;
  }

  std::string line;
  while (std::getline(status_file, line)) {
    if (line.find("Threads:") != std::string::npos) {
      std::istringstream iss(line);
      std::string name;
      uint64_t thread_count;

      iss >> name >> thread_count;
      return thread_count;
    }
  }

  return 0;
}

float ProcessInfoManager::GetCpuUsagePercent() {
  auto readProcStat = [this](int64_t &utime, int64_t &stime) {
    std::string stat_path = "/proc/" + pid_ + "/stat";
    std::ifstream stat_file(stat_path);

    if (!stat_file.is_open()) {
      return false;
    }

    std::string line;
    if (std::getline(stat_file, line)) {
      std::istringstream iss(line);
      std::string value;
      for (int i = 0; i < 13; ++i) {
        iss >> value;
      }
      iss >> utime >> stime;
      return true;
    }

    return false;
  };

  int64_t utime1 = 0, stime1 = 0;
  int64_t current_time = std::chrono::duration_cast<std::chrono::milliseconds>(
                             std::chrono::steady_clock::now().time_since_epoch())
                             .count();

  if (!readProcStat(utime1, stime1)) {
    return 0.0f;
  }

  if (prev_stime_ == -1 || prev_utime_ == -1 || last_time_ == 0) {
    prev_stime_ = stime1;
    prev_utime_ = utime1;
    last_time_ = current_time;
    return 0.0f;
  }

  uint64_t total_time = (utime1 + stime1) - (prev_stime_ + prev_utime_);
  uint64_t time_delta = current_time - last_time_;

  prev_stime_ = stime1;
  prev_utime_ = utime1;
  last_time_ = current_time;

  long clk_tck = sysconf(_SC_CLK_TCK);
  // long num_cpus = sysconf(_SC_NPROCESSORS_ONLN);

  float cpu_usage = ((float)total_time / clk_tck) / (time_delta / 1000.0f) * 100.0f;

  return cpu_usage;
}

int32_t ProcessInfoManager::GetSchedulerPriority() {
  std::string stat_path = "/proc/" + pid_ + "/stat";
  std::ifstream stat_file(stat_path);

  if (!stat_file.is_open()) {
    return 0;
  }

  std::string line;
  if (std::getline(stat_file, line)) {
    std::istringstream iss(line);
    std::string value;

    for (int i = 0; i < 17; ++i) {
      iss >> value;
    }

    int32_t priority;
    iss >> priority;

    return priority;
  }

  return 0;
}

int32_t ProcessInfoManager::GetGuardThreadTid(std::string &name) {
  std::string stat_path = "/proc/" + pid_ + "/task/";
  for (const auto &entry : std::filesystem::directory_iterator(stat_path)) {
    if (entry.is_directory()) {
      std::string tid_name_path = stat_path + entry.path().filename().string() + "/comm";
      std::ifstream tid_name_file(tid_name_path);
      if (tid_name_file.is_open()) {
        std::string tid_name;
        tid_name_file >> tid_name;
        if (tid_name.find(name) != std::string::npos) {
          return std::stoi(entry.path().filename().string());
        }
      }
    }
  }
  return 0;
}

void ProcessInfoManager::DoUpdate(NodeDynamicInfo &node_dynamic_info) {
  if (pid_.empty()) return;
  node_dynamic_info.cpu_usage_percent = GetCpuUsagePercent();
  node_dynamic_info.memory_usage_kb = GetMemoryUsageKb();
  node_dynamic_info.memory_usage_percent = (mem_total_ == 0) ? 0.0f : (node_dynamic_info.memory_usage_kb * 100.0f) / mem_total_;
  node_dynamic_info.thread_count = GetThreadCount();
  node_dynamic_info.scheduler_priority = GetSchedulerPriority();
}

}  // namespace aimrt::plugins::viz_plugin