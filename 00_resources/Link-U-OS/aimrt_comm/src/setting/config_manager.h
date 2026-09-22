// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <string>
#include <vector>
#include <nlohmann/json.hpp>

namespace aimrte::setting
{
struct RobotConfig {
  std::string key;
  std::string value;
  std::string extra;
};

std::string GetDnsConfigPath();
std::string GetGlobalConfigPath();
std::string GetSettingConfigPath();
std::string GetConfigPath();

// 获取配置
bool GetConfig(std::vector<RobotConfig>& configs);

std::vector<std::pair<std::string, std::string>> ScanConfigMap();

}  // namespace aimrte::setting
