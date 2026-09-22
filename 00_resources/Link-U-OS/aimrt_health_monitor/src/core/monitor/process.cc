// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "process.h"
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
#include "src/utils/execute.h"
#include "src/utils/string.h"

namespace aima::monitor {

ProcessInfo::ProcessInfo(const std::string& app_name, const std::string& pid) {
  app_name_ = app_name;
  pid_ = pid;
  mem_total_ = GetMemoryTotal();
}

uint64_t ProcessInfo::GetMemoryUsageKb() {
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

uint64_t ProcessInfo::GetMemoryTotal() {
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

float ProcessInfo::GetMemoryUsagePercent() {
  auto mem_total = GetMemoryTotal();
  auto mem_usage_kb = GetMemoryUsageKb();
  return (mem_total == 0) ? 0.0f : (mem_usage_kb * 100.0f) / mem_total;
}

uint64_t ProcessInfo::GetThreadCount() {
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

float ProcessInfo::GetCpuUsagePercent() {
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

int32_t ProcessInfo::GetSchedulerPriority() {
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

int32_t ProcessInfo::GetGuardThreadTid(std::string &name) {
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

std::string ProcessInfo::GetAppName() const { return app_name_; }

std::string ProcessInfo::GetPid() const { return pid_; }

bool process::Initialize(const YAML::Node& config) {
  if (config["apps"]) {
    app_names_ = config["apps"].as<std::vector<std::string>>();
    AIMRTE_INFO("process: set process monitor for apps: {}", app_names_);
  }
  return true;
}

bool process::Start() {
  return true;
}

void process::Shutdown() {}

void process::DiagnoseOnce() {
  const auto get_pid = [](const std::string& app_name) -> std::string {
    std::string pid;
    if (aimrte::utils::Execute(fmt::format("pidof {}", app_name), pid) != 0 || pid.empty()) {
      AIMRTE_WARN("process: get pid of {} failed", app_name);
      return std::string();
    }
    auto items = aimrte::utils::SplitTrim(pid, ' ');
    if (items.empty()) {                  
      AIMRTE_WARN("process: get pid of {} failed", app_name);
      return std::string();
    }
    pid = items[0];
    AIMRTE_INFO("process: get pid of {} success, pid is {}", app_name, pid);
    return pid;
  };
  if (app_infos_.empty()) {
    for (const auto& app_name : app_names_) {
      std::string pid = get_pid(app_name);
      if (pid.empty()) {
        AIMRTE_WARN("process: get pid of {} failed", app_name);
        continue;
      }
      AIMRTE_INFO("process: get pid of {} success, pid is {}", app_name, pid);
      app_infos_.emplace_back(app_name, pid);
    }
  }

  aimdk::protocol::ProcessList process_list_msg;
  for (auto& info : app_infos_) {
    process_list_msg.add_app_infos()->set_app_name(info.GetAppName());
    process_list_msg.mutable_app_infos()->rbegin()->set_cpu_usage(info.GetCpuUsagePercent());
    process_list_msg.mutable_app_infos()->rbegin()->set_mem_usage(info.GetMemoryUsagePercent());
    process_list_msg.mutable_app_infos()->rbegin()->set_pid(std::stoi(info.GetPid()));
    process_list_msg.mutable_app_infos()->rbegin()->set_thread_count(info.GetThreadCount());
    process_list_msg.mutable_app_infos()->rbegin()->set_fd_count(0);
  }
  AIMRTE_DEBUG("process: process_list_msg: {}", aimrt::Pb2CompactJson(process_list_msg));
  PubProcessData(process_list_msg);
}

void process::PubProcessData(const aimdk::protocol::ProcessList& msg) {
  aimdk::protocol::SystemStatusChannel status_channel;
  status_channel.set_gist_msg_type(aimdk::protocol::SystemMsgType_PROCESS_LIST);
  status_channel.mutable_process_list()->CopyFrom(msg);

  if (res_.local.local_pub.IsValid()) {
    auto ctx = aimrte::ctx::init::GetCorePtr();
    ctx->Publish(res_.local.local_pub, status_channel);
  } else {
    AIMRTE_DEBUG("Local publisher is not set for process");
  }
}

}  // namespace aima::monitor