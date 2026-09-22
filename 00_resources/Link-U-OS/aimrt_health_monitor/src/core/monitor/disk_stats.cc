// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "disk_stats.h"
#include "src/utils/execute.h"

namespace aima::monitor {

bool disk_stats::Initialize(const YAML::Node& config) {
  if (config["disk_name"]) {
    disk_name_ = config["disk_name"].as<std::string>();
    AIMRTE_INFO("disk_stats: set disk name:{}", disk_name_);
  }
  return true;
}

bool disk_stats::Start() {
  std::string cmd = "smartctl -a " + disk_name_ + " | grep \"Warning  Comp. Temp. Threshold\" | awk '{print $5}'";
  std::string result;
  if (aimrte::utils::Execute(cmd, result) != 0) {
    AIMRTE_ERROR("disk_stats: Failed to execute command: {}", cmd);
    return false;
  }

  AIMRTE_INFO("disk_stats: SSD Warning Temperature Threshold: {}", result);

  try {
    warning_temp_threshold_ = std::stoull(result);
  } catch (const std::exception& e) {
    AIMRTE_ERROR("disk_stats: Failed to parse warning temperature threshold: {}", e.what());
    return false;
  }

  return true;
}

void disk_stats::Shutdown() {}

void disk_stats::DiagnoseOnce() {
  std::string cmd = "smartctl -a -j " + disk_name_;
  std::string result;
  if (aimrte::utils::Execute(cmd, result) != 0) {
    AIMRTE_ERROR("disk_stats: Failed to execute command: {}", cmd);
  }

  try {
    auto json_data = nlohmann::json::parse(result, nullptr, true);
    auto is_pass = json_data.at("smart_status").at("passed").get<bool>();
    auto controller_busy_time = json_data.at("nvme_smart_health_information_log").at("controller_busy_time").get<uint64_t>();
    auto temperature = json_data.at("nvme_smart_health_information_log").at("temperature").get<uint64_t>();
    auto warning_temp_time = json_data.at("nvme_smart_health_information_log").at("warning_temp_time").get<uint64_t>();

    std::vector<uint64_t> temps;
    if (json_data.at("nvme_smart_health_information_log").contains("temperature_sensors")) {
      auto& temperature_sensors = json_data.at("nvme_smart_health_information_log").at("temperature_sensors");
      for (auto& ts : temperature_sensors) {
        if (ts.is_number()) {
          temps.push_back(ts.get<uint64_t>());
        } else {
          temps.push_back(0);
        }
      }
    }

    if (temperature >= warning_temp_threshold_) {
      uint64_t current_time = aimrte::utils::GetCurrentTimestamp();
      if (last_overtemp_time_ == 0) {
        last_overtemp_time_ = current_time;
      } else {
        auto overtemp_time = current_time - last_overtemp_time_;
        if (overtemp_time >= overtemp_duration_threshold_) {
          AIMRTE_ERROR("disk_stats: SSD temperature:{} over warning threshold:{} for {} miliseconds", temperature, warning_temp_threshold_, overtemp_time);
        }
      }
    } else {
      last_overtemp_time_ = 0;
    }
  } catch (const std::exception& e) {
    AIMRTE_ERROR("disk_stats: Failed to parse JSON data: msg={}, err={}", result, e.what());
  }
}

}  // namespace aima::monitor
