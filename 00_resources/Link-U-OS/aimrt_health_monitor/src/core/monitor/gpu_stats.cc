// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "gpu_stats.h"
#include "src/utils/execute.h"

#if defined(__x86_64__) || defined(_M_X64) || defined(__i386__) || defined(_M_IX86)
// do nothing for x86_64
#else

namespace aima::monitor {

// 获取GPU设备使用情况
void gpu_stats::get_gpu_info(GpuStatsInfo& gpu_info) {
  std::string result;
  if (ExecuteCmd("timeout 1.5s tegrastats", result) != 0) {
    AIMRTE_ERROR("Failed to get gpu info: {}", result);
    return;
  }
  AIMRTE_DEBUG("Get gpu info success: {}", result);
  gpu_current_.gpu_usage = get_gpu_usage(result);
  gpu_current_.gpu_mem_usage = get_gpu_mem_usage(result);
  gpu_current_.gpu_temp = get_gpu_temp(result);
  gpu_current_.gpu_power_mode = get_gpu_power_mode(result);
}

float gpu_stats::get_gpu_usage(const std::string& tegrastats_str)
{
  std::smatch matches;
  if (!std::regex_search(tegrastats_str, matches, std::regex{R"(GR3D_FREQ (\d+))"}) || matches.size() < 2) {
    AIMRTE_ERROR("Failed to get gpu usage: {}", tegrastats_str);
    return 0.0f;
  }
  float usage = std::stof(matches[1]);
  AIMRTE_DEBUG("GPU usage: {}", usage);
  return usage;
}

float gpu_stats::get_gpu_mem_usage(const std::string& tegrastats_str)
{
  std::smatch matches;
  if (!std::regex_search(tegrastats_str, matches, std::regex{R"(RAM (\d+)/(\d+)MB)"}) || matches.size() < 3) {
    AIMRTE_ERROR("Failed to get gpu mem usage: {}", tegrastats_str);
    return 0.0f;
  }
  float ram_used = std::stof(matches[1]);
  float ram_total = std::stof(matches[2]);
  float ram_usage = ram_used * 100 / ram_total;
  AIMRTE_DEBUG("GPU mem usage: {}, {}/{}MB", ram_usage, ram_used, ram_total);
  return ram_usage;
}

float gpu_stats::get_gpu_temp(const std::string& tegrastats_str)
{
  std::smatch matches;
  if (!std::regex_search(tegrastats_str, matches, std::regex{R"(gpu@([0-9]+(?:\.[0-9]*)?)C)"}) || matches.size() < 2) {
    AIMRTE_ERROR("Failed to get gpu temp: {}", tegrastats_str);
    return 0.0f;
  }
  float temp = std::stof(matches[1]);
  AIMRTE_DEBUG("GPU temp: {}", temp);
  return temp;
}

GPUPowerMode gpu_stats::get_gpu_power_mode(const std::string& tegrastats_str)
{
  std::smatch matches;
  if (!std::regex_search(tegrastats_str, matches, std::regex{R"(VDD_GPU_SOC (\d+)mW)"}) || matches.size() < 2) {
    AIMRTE_ERROR("Failed to get gpu power: {}", tegrastats_str);
    return GPUPowerMode::GPUPowerMode_UNKNOWN;
  }
  float power = std::stof(matches[1]);
  GPUPowerMode power_mode = GPUPowerMode::GPUPowerMode_UNKNOWN;
  if (power > 0.0f && power <= 5000) {
    power_mode = GPUPowerMode::GPUPowerMode_5W;
  } else if (power > 5000 && power <= 10000) {
    power_mode = GPUPowerMode::GPUPowerMode_10W;
  } else if (power > 10000 && power <= 15000) {
    power_mode = GPUPowerMode::GPUPowerMode_15W;
  } else if (power > 15000) {
    power_mode = GPUPowerMode::GPUPowerMode_MAXN;
  }
  AIMRTE_DEBUG("GPU power: {}, {}", power, power_mode);
  return power_mode;
}

bool gpu_stats::Initialize(const YAML::Node& config) {
  return true;
}

bool gpu_stats::Start() {
  // 获取初始的GPU统计信息
  AIMRTE_INFO("gpu_stats start");
  get_gpu_info(gpu_current_);
  return true;
}

void gpu_stats::Shutdown() {}

void gpu_stats::DiagnoseOnce() {
  get_gpu_info(gpu_current_);

  // 获取正在使用 GPU 的进程列表
  aimdk::protocol::GpuUsage gpu_usage_msg;

  auto& gpu_device_info = *gpu_usage_msg.add_gpu_infos();
  gpu_device_info.set_gpu_usage(gpu_current_.gpu_usage);
  gpu_device_info.set_gpu_mem_use_percent(gpu_current_.gpu_mem_usage);
  gpu_device_info.set_mem_bandwidth_useage(0.0f);
  gpu_device_info.set_temp(gpu_current_.gpu_temp);
  gpu_device_info.set_power_mode(gpu_current_.gpu_power_mode);

  PubGpuData(gpu_usage_msg);
}

void gpu_stats::PubGpuData(const aimdk::protocol::GpuUsage& msg) {
  aimdk::protocol::SystemStatusChannel status_channel;
  status_channel.set_gist_msg_type(aimdk::protocol::SystemMsgType_GPU_USAGE);
  status_channel.mutable_gpu_usage()->CopyFrom(msg);

  if (res_.local.local_pub.IsValid()) {
    auto ctx = aimrte::ctx::init::GetCorePtr();
    ctx->Publish(res_.local.local_pub, status_channel);
  } else {
    AIMRTE_ERROR("Local publisher is not set for GpuUsage");
  }
}

int gpu_stats::ExecuteCmd(const std::string &cmd, std::string &result)
{
  try {
    char buffer[255];
    FILE *pipe = popen(cmd.c_str(), "r");
    if (!pipe) {
      result = "popen failed!";
      return 1;
    }
    while (fgets(buffer, sizeof(buffer), pipe)) {
      result += buffer;
      std::string_view line(buffer);
      if (line.starts_with("OK")) {
        break;
      }
    }
    int status = pclose(pipe);
    if (status != 0) {
      int exitCode = WEXITSTATUS(status);
      if (exitCode != 124) {
        result = "Command executed failed with status: " + std::to_string(status) + ", exit status: " + std::to_string(exitCode);
      }
      return (exitCode == 124) ? 0 : exitCode;  // cmd使用timeout会返回错误码124，不认为是失败
    }
    return 0;
  } catch (const std::exception &e) {
    result = "Error executing command: " + std::string(e.what());
    return 1;
  }
}
}  // namespace aima::monitor

#endif    // __x86_64__ || defined(_M_X64) || defined(__i386__) || defined(_M_IX86)
