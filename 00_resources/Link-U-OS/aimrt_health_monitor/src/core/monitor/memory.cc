// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "memory.h"
#include <cstdint>
#include <fstream>
#include <vector>
#include "src/hds/interface.h"
namespace aima::monitor {
// 获取系统内存使用情况
const std::tuple<int, int, int, int> memory::get_memory_usage() {
  std::ifstream meminfo_file("/proc/meminfo");
  std::string line;
  int total_mem = 0, free_mem = 0;
  int swap_mem = 0, swap_free = 0;
  // 读取meminfo文件中的总内存和空闲内存信息
  while (std::getline(meminfo_file, line)) {
    if (line.find("MemTotal") != std::string::npos) {
      sscanf(line.c_str(), "MemTotal: %d", &total_mem);
    } else if (line.find("MemAvailable") != std::string::npos) {
      sscanf(line.c_str(), "MemAvailable: %d", &free_mem);
    } else if (line.find("SwapTotal") != std::string::npos) {
      sscanf(line.c_str(), "SwapTotal: %d", &swap_mem);
    } else if (line.find("SwapFree") != std::string::npos) {
      sscanf(line.c_str(), "SwapFree: %d", &swap_free);
    }
  }
  meminfo_file.close();

  return std::make_tuple(total_mem / 1024, free_mem / 1024, swap_mem / 1024, swap_free / 1024);
}

bool memory::Initialize(const YAML::Node& config) {
  if (config["max_usage"]) {
    max_usage_ = config["max_usage"].as<float>();
    AIMRTE_INFO("set memory max useage:{}", max_usage_);
  }
  return true;
}

bool memory::Start() {
  return true;
}

void memory::Shutdown() {}

void memory::DiagnoseOnce() {
  // 获取内存使用数据，单位为MB
  auto memory_tuple = get_memory_usage();
  auto total_mem = std::get<0>(memory_tuple);
  auto free_mem = std::get<1>(memory_tuple);
  auto swap_mem = std::get<2>(memory_tuple);
  auto swap_free = std::get<3>(memory_tuple);
  // 计算内存使用率
  float current_useage = 100.0 - (free_mem * 1.0 / total_mem * 100.0);
  float swap_usage = (swap_mem == 0) ? 0.0 : (100.0 - (swap_free * 1.0 / swap_mem * 100.0));
#if defined(__x86_64__) || defined(_M_X64) || defined(__i386__) || defined(_M_IX86)
  if (current_useage >= max_usage_) {
    AIMRTE_ERROR("memory usage:{} over limit:{}", current_useage, max_usage_);
  }
#else
  if (current_useage >= max_usage_) {
    AIMRTE_ERROR("memory usage:{} over limit:{}", current_useage, max_usage_);
  }
#endif

  aimdk::protocol::MemoryUsage memeory_usage_msg;
  memeory_usage_msg.set_usage(current_useage);
  memeory_usage_msg.set_swap_usage(swap_usage);
  memeory_usage_msg.set_total_mem_mb(total_mem);
  memeory_usage_msg.set_available_mem_mb(free_mem);
  PubMemData(memeory_usage_msg);
}

void memory::PubMemData(const aimdk::protocol::MemoryUsage& msg) {
  aimdk::protocol::SystemStatusChannel status_channel;
  status_channel.set_gist_msg_type(aimdk::protocol::SystemMsgType_MEMORY_USAGE);
  status_channel.mutable_memory_usage()->CopyFrom(msg);

  if (res_.local.local_pub.IsValid()) {
    auto ctx = aimrte::ctx::init::GetCorePtr();
    ctx->Publish(res_.local.local_pub, status_channel);
  } else {
    AIMRTE_ERROR("Local publisher is not set for GpuUsage");
  }
}
}  // namespace aima::monitor