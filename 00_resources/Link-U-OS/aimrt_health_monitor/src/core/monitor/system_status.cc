// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./system_status.h"
#include <nlohmann/json.hpp>

namespace aima::monitor {

bool system_status::Initialize(const YAML::Node& config) {
  res_.local.local_sub.WhenInit().SubscribeInline([this](const aimdk::protocol::SystemStatusChannel& msg) -> aimrt::co::Task<void> {
    UpdateSystemStatus(msg);
    co_return;
  });
  return true;
}

bool system_status::Start() { return true; }

void system_status::Shutdown() {}

void system_status::UpdateSystemStatus(const aimdk::protocol::SystemStatusChannel& msg)
{
  switch (msg.gist_msg_type()) {
    case aimdk::protocol::SystemMsgType_BATTERY_USAGE: {
      system_status_.mutable_battery_usage()->CopyFrom(msg.battery_usage());
      break;
    }
    case aimdk::protocol::SystemMsgType_CPU_USAGE: {
      system_status_.mutable_cpu_usage()->CopyFrom(msg.cpu_usage());
      break;
    }
    case aimdk::protocol::SystemMsgType_MEMORY_USAGE: {
      system_status_.mutable_memory_usage()->CopyFrom(msg.memory_usage());
      break;
    }
    case aimdk::protocol::SystemMsgType_DISK_USAGE: {
      system_status_.mutable_disk_usage()->CopyFrom(msg.disk_usage());
      break;
    }
    case aimdk::protocol::SystemMsgType_NETWORK_USAGE: {
      system_status_.mutable_network_usage()->CopyFrom(msg.network_usage());
      break;
    }
    case aimdk::protocol::SystemMsgType_HEARTBEAT_LIST: {
      system_status_.mutable_heartbeat_list()->CopyFrom(msg.heartbeat_list());
      break;
    }
    case aimdk::protocol::SystemMsgType_PROCESS_LIST: {
      system_status_.mutable_process_list()->CopyFrom(msg.process_list());
      break;
    }
    case aimdk::protocol::SystemMsgType_GPU_USAGE: {
      system_status_.mutable_gpu_usage()->CopyFrom(msg.gpu_usage());
      break;
    }
    default:
      AIMRTE_WARN("Unknown system status message type: {}", msg.gist_msg_type());
      break;
  }
}

void system_status::DiagnoseOnce() {
  auto ctx = aimrte::ctx::init::GetCorePtr();
  ctx->LetMe();

  // 发布系统状态
  system_status_.set_timestamp(aimrte::utils::GetCurrentTimestamp());

  auto& system_status_pub = res_.regular.system_status_pub;
  if (system_status_pub.IsValid()) {
    ctx->Publish(system_status_pub, system_status_);
    AIMRTE_DEBUG("Pub system status {}", aimrt::Pb2CompactJson(system_status_));
  } else {
    AIMRTE_DEBUG("Pub system status failed");
  }

  // 上报各个模块的系统状态
  if (event_counter_ % 10 == 0) {
    ReportCpuUsage();
    ReportMemoryUsage();
    ReportGpuUsage();
    ReportDiskUsage();
    ReportProcessState();
  }
  ++event_counter_;
}

void system_status::ReportCpuUsage() {
  double total_cpu_usage = 0.0, total_sys_usage = 0.0, total_user_usage = 0.0;
  int avg_usage = 0, sys_usage = 0, user_usage = 0, interrupts = 0;
  std::for_each(system_status_.cpu_usage().cpu_infos().begin(),
                system_status_.cpu_usage().cpu_infos().end(),
                [&total_cpu_usage, &total_user_usage, &total_sys_usage](const aimdk::protocol::CpuCoreUsage& cpu_info) {
                  total_cpu_usage += static_cast<double>(cpu_info.usage());
                  total_sys_usage += static_cast<double>(cpu_info.usage_sys_space());
                  total_user_usage += static_cast<double>(cpu_info.usage_usr_space());
                });
  avg_usage = static_cast<int>(total_cpu_usage / system_status_.cpu_usage().cpu_infos().size());
  sys_usage = static_cast<int>(total_sys_usage / system_status_.cpu_usage().cpu_infos().size());
  user_usage = static_cast<int>(total_user_usage / system_status_.cpu_usage().cpu_infos().size());
  interrupts = system_status_.cpu_usage().interrupts();
  AIMRTE_DEBUG("ReportToCloud cpu usage {}% user_usage {}% interrupts {}", avg_usage, user_usage, interrupts);
  std::stringstream ss1, ss2, ss3, ss4;
  ss1 << avg_usage;
  ss2 << sys_usage;
  ss3 << user_usage;
  ss4 << interrupts;

  // 构造TOP10进程数据
  aimdk::protocol::AppHeartBeatList process_heartbeats = system_status_.heartbeat_list();
  // 按照CPU使用率降序排序
  std::sort(process_heartbeats.mutable_app_hearbeats()->begin(),
            process_heartbeats.mutable_app_hearbeats()->end(),
            [](const aimdk::protocol::AppHeartBeatInfo& a, const aimdk::protocol::AppHeartBeatInfo& b) {
              return a.cpu_usage() > b.cpu_usage();
            });
  // 只保留前10个进程

  nlohmann::json top_10_processes_json;
  for (size_t i = 0; i < 10 && i < process_heartbeats.app_hearbeats_size(); ++i) {
    const auto& process = process_heartbeats.app_hearbeats(i);
    nlohmann::json process_json;
    process_json["PID"] = process.pid();
    process_json["process_name"] = process.app_name();
    process_json["CPU_occu_rate"] = fmt::format("{:.1f}%", process.cpu_usage());
    process_json["total_threads"] = process.thread_count();
    top_10_processes_json["process_detail"].push_back(process_json);
  }
  AIMRTE_DEBUG("ReportToCloud top 10 processes: {}", top_10_processes_json.dump(2));
  std::stringstream detail_json_ss;
  detail_json_ss << top_10_processes_json.dump(-1);
}

void system_status::ReportMemoryUsage() {
  std::stringstream ss1, ss2, ss3, ss4;
  ss1 << static_cast<int>(system_status_.memory_usage().usage());
  ss2 << static_cast<int>(system_status_.memory_usage().swap_usage());
  ss3 << system_status_.memory_usage().total_mem_mb() / 1024;
  ss4 << system_status_.memory_usage().available_mem_mb() / 1024;
  AIMRTE_DEBUG("ReportToCloud memory usage {} swap usage {} total mem size {} available mem size {}",
               ss1.str(), ss2.str(), ss3.str(), ss4.str());

  // 构造TOP10进程数据
  aimdk::protocol::AppHeartBeatList process_heartbeats = system_status_.heartbeat_list();
  // 按照Memory使用率降序排序
  std::sort(process_heartbeats.mutable_app_hearbeats()->begin(),
            process_heartbeats.mutable_app_hearbeats()->end(),
            [](const aimdk::protocol::AppHeartBeatInfo& a, const aimdk::protocol::AppHeartBeatInfo& b) {
              return a.cpu_usage() > b.cpu_usage();
            });
  // 只保留前10个进程
  nlohmann::json top_10_processes_json;
  for (size_t i = 0; i < 10 && i < process_heartbeats.app_hearbeats_size(); ++i) {
    const auto& process = process_heartbeats.app_hearbeats(i);
    nlohmann::json process_json;
    process_json["PID"] = process.pid();
    process_json["process_name"] = process.app_name();
    process_json["memory_usage"] = fmt::format("{:.1f}MB", process.mem_usage_kb() / 1024);  // Convert KB to MB
    process_json["total_threads"] = process.thread_count();
    top_10_processes_json["process_detail"].push_back(process_json);
  }
  AIMRTE_DEBUG("ReportToCloud top 10 processes: {}", top_10_processes_json.dump(2));
  std::stringstream detail_json_ss;
  detail_json_ss << top_10_processes_json.dump(-1);
}

void system_status::ReportGpuUsage() {
  int gpu_usage = 0, mem_usage = 0;
  int bandwith_usage = 0, temp = 0;
  aimdk::protocol::GPUPowerMode gpu_power_mode = aimdk::protocol::GPUPowerMode::GPUPowerMode_UNKNOWN;
  if (system_status_.gpu_usage().gpu_infos_size() > 0) {
    gpu_usage = static_cast<int>(system_status_.gpu_usage().gpu_infos(0).gpu_usage());
    mem_usage = static_cast<int>(system_status_.gpu_usage().gpu_infos(0).gpu_mem_use_percent());
    bandwith_usage = static_cast<int>(system_status_.gpu_usage().gpu_infos(0).mem_bandwidth_useage());
    temp = system_status_.gpu_usage().gpu_infos(0).temp();
    gpu_power_mode = system_status_.gpu_usage().gpu_infos(0).power_mode();
  }
  std::stringstream ss1, ss2, ss3, ss4, ss5;
  ss1 << gpu_usage;
  ss2 << mem_usage;
  ss3 << bandwith_usage;
  ss4 << temp;
  ss5 << aimdk::protocol::GPUPowerMode_Name(gpu_power_mode);
  AIMRTE_DEBUG("ReportToCloud gpu usage {} video mem usage {} bandwidth usage {} gpu temp {} gpu power mode {}",
               ss1.str(), ss2.str(), ss3.str(), ss4.str(), ss5.str());
}

void system_status::ReportDiskUsage() {
  float max_disk_usage = 0.0;
  float read_rate_mbs = 0.0, write_rate_mbs = 0.0;
  uint64_t read_times = 0, write_times = 0;
  uint64_t read_await = 0, write_await = 0;
  std::for_each(system_status_.disk_usage().partition_infos().begin(),
                system_status_.disk_usage().partition_infos().end(),
                [&](const aimdk::protocol::PartitionUsage& part_usage) {
                  if (part_usage.usage() > max_disk_usage) {
                    max_disk_usage = part_usage.usage();
                  }
                  read_rate_mbs += part_usage.read_mbs();
                  write_rate_mbs += part_usage.write_mbs();
                  read_times += part_usage.read_times();
                  write_times += part_usage.write_times();
                  read_await += part_usage.read_await_us_total();
                  write_await += part_usage.write_await_us_total();
                });
  AIMRTE_DEBUG("ReportToCloud disk usage {:.1f}% read rate {:.1f}MB/s write rate {:.1f}MB/s read times {} write times {} read await {}ms write await {}ms",
               max_disk_usage, read_rate_mbs, write_rate_mbs, read_times, write_times,
               read_await / 1000, write_await / 1000);  // Convert microseconds to milliseconds
  std::stringstream ss1, ss2, ss3, ss4, ss5, ss6, ss7;
  ss1 << static_cast<int>(max_disk_usage);
  ss2 << static_cast<int>(read_rate_mbs);
  ss3 << static_cast<int>(write_rate_mbs);
  ss4 << read_times;
  ss5 << write_times;
  ss6 << read_await / 1000;  // Convert microseconds to milliseconds
  ss7 << read_await / 1000;
}

void system_status::ReportProcessState()
{
  // 构造全量进程数据
  aimdk::protocol::AppHeartBeatList process_heartbeats = system_status_.heartbeat_list();
  // 按照CPU使用率降序排序
  std::sort(process_heartbeats.mutable_app_hearbeats()->begin(),
            process_heartbeats.mutable_app_hearbeats()->end(),
            [](const aimdk::protocol::AppHeartBeatInfo& a, const aimdk::protocol::AppHeartBeatInfo& b) {
              return a.cpu_usage() > b.cpu_usage();
            });

  nlohmann::json all_processes_json;
  for (size_t i = 0; i < process_heartbeats.app_hearbeats_size(); ++i) {
    const auto& process = process_heartbeats.app_hearbeats(i);
    nlohmann::json process_json;
    process_json["PID"] = process.pid();
    process_json["process_name"] = process.app_name();
    process_json["CPU_occu_rate"] = fmt::format("{:.1f}%", process.cpu_usage());
    process_json["memory_usage"] = fmt::format("{:.1f}MB", process.mem_usage_kb() / 1024);  // Convert KB to MB
    process_json["total_threads"] = process.thread_count();
    all_processes_json["process_detail"].push_back(process_json);
  }
  AIMRTE_DEBUG("ReportToCloud all processes: {}", all_processes_json.dump(2));
  std::stringstream detail_json_ss;
  detail_json_ss << all_processes_json.dump(-1);
}
}  // namespace aima::monitor