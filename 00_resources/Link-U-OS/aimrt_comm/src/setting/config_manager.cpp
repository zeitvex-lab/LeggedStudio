// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./config_manager.h"
#include "src/ctx/ctx.h"
#include <nlohmann/json.hpp>
#include <map>
#include <filesystem>
#include <fstream>

namespace aimrte::setting
{

namespace fs = std::filesystem;

std::string GetDnsConfigPath()
{
  return GetConfigPath() + "/dns-config";
}

std::string GetGlobalConfigPath()
{
  return GetConfigPath() + "/global-config/global-site-setting.json";
}

std::string GetSettingConfigPath()
{
  std::ifstream version_file("/etc/bsp_version");
  if (version_file.good()) {
    return GetConfigPath() + "/tz-config";
  } else {
    return GetConfigPath() + "/apq-config";
  }
}

std::string GetConfigPath()
{
  return "/agibot/data/param/setting/config";
}

bool GetConfig(std::vector<RobotConfig>& configs)
{
  std::vector<std::pair<std::string, std::string>> config_map = ScanConfigMap();
  if (config_map.empty()) {
    return false;
  }

  for (auto &cfg : configs) {
    const std::string &key = cfg.key;
    auto it = std::find_if(config_map.begin(), config_map.end(), [&](const auto &kv) {
      return kv.first == key;
    });

    if (it != config_map.end()) {
      AIMRTE_INFO("get key:{} value:{}", key, it->second);
      cfg.value = it->second;
    } else {
      AIMRTE_WARN("get config key not exist: {}", key);
    }
  }
  return true;
}

std::vector<std::pair<std::string, std::string>> ScanConfigMap()
{
  std::vector<std::pair<std::string, std::string>> config_map;

  std::string config_path = GetSettingConfigPath();
  std::string site_id, site_file;

  if (!fs::exists(config_path) || !fs::is_directory(config_path)) {
    AIMRTE_ERROR("config path invalid : {}", config_path);
    return config_map;
  }

  for (const auto &entry : fs::directory_iterator(config_path)) {
    if (!entry.is_regular_file() || entry.path().extension() != ".json") {
      AIMRTE_INFO("invalid file {}", entry.path().string());
      continue;
    }

    try {
      std::ifstream file(entry.path());
      auto cfgfile = std::make_shared<nlohmann::json>(nlohmann::json::parse(file));
      for (const auto &[key, value] : cfgfile->items()) {
        std::string value_tmp = value.is_string() ? value.get<std::string>() : value.dump();
        config_map.emplace_back(key, value_tmp);
        if (key == "master.globalconfig.site_id") site_id = value_tmp;
        if (key == "master.globalconfig.site_file") site_file = value_tmp;
      }
    } catch (const std::exception &ex) {
      AIMRTE_ERROR("bad json file {}: {}", entry.path().string(), ex.what());
    }
  }

  if (site_id.empty() || site_file.empty()) {
    AIMRTE_ERROR("dns config not found: {}, {}.", site_id, site_file);
    return config_map;
  }

  std::string global_config_path = GetGlobalConfigPath();
  if (!fs::exists(global_config_path) || !fs::is_regular_file(global_config_path)) {
    AIMRTE_ERROR("region_site_config path invalid : {}", global_config_path);
    return config_map;
  }

  nlohmann::json global_config;
  try {
    std::ifstream ifs(global_config_path);
    if (!ifs.is_open()) {
      AIMRTE_ERROR("region config file open failed: {}", global_config_path);
      return config_map;
    }
    ifs >> global_config;
  } catch (const nlohmann::json::parse_error& e) {
    AIMRTE_ERROR("region config json parse failed : {}", e.what());
    return config_map;
  }

  for (const auto& site : global_config.at("site-configs")) {
    if (site.value("site_id", "") == site_id) {
      std::string expected_site_file = site.value("site_file", "");
      if (site_file != expected_site_file) {
        AIMRTE_ERROR("dns config: site_file mismatch for site_id {} (expected: {}, got: {})", site_id, expected_site_file, site_file);
      }
      break;
    }
  }

  fs::path dns_config_path = fs::path(GetDnsConfigPath()) / (site_file + ".json");
  if (!fs::exists(dns_config_path) || !fs::is_regular_file(dns_config_path)) {
    AIMRTE_ERROR("dns config file not found: {}", dns_config_path.string());
    return config_map;
  }
  try {
    std::ifstream dns_file(dns_config_path);
    auto dns_cfg = std::make_shared<nlohmann::json>(nlohmann::json::parse(dns_file));
    for (const auto &[key, value] : dns_cfg->items()) {
      config_map.emplace_back(key, value.is_string() ? value.get<std::string>() : value.dump());
    }
  } catch (const std::exception &ex) {
    AIMRTE_ERROR("dns config file {} parse failed : {}", dns_config_path.string(), ex.what());
  }

  return config_map;
}

}  // namespace aimrte::setting
