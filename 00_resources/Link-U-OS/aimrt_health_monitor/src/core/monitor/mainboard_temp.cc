// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "mainboard_temp.h"

#include <sys/syslog.h>

#include <fstream>
#include "src/hds/interface.h"
namespace aima::monitor {

bool mainboard_temp::Initialize(const YAML::Node& config) {
  if (config["mainboard_temp_low_percent"]) {
    mainboard_temp_low_percent_ = config["mainboard_temp_low_percent"].as<float>();
    AIMRTE_INFO("set mainboard_temp mainboard_temp_low_percent:{}", mainboard_temp_low_percent_);
  }
  return true;
}

float mainboard_temp::GetMainboardTemp() {
  try {
    const std::string temp_file = "/sys/class/thermal/thermal_zone0/temp";
    std::ifstream file(temp_file);

    if (!file.is_open()) {
      AIMRTE_ERROR("Failed to open temperature file: {}", temp_file);
      return 0.0;
    }

    int temp_millicelsius = 0;
    file >> temp_millicelsius;

    if (file.fail()) {
      AIMRTE_ERROR("Failed to read temperature from file: {}", temp_file);
      return 0.0;
    }

    file.close();

    // Convert from milli-Celsius to Celsius
    return temp_millicelsius / 1000.0;
  } catch (const std::exception& e) {
    AIMRTE_ERROR("Failed to get mainboard temperature: {}", e.what());
    return 0.0;
  }
}

bool mainboard_temp::Start() {
  return true;
}

void mainboard_temp::Shutdown() {}

void mainboard_temp::DiagnoseOnce() {}
}  // namespace aima::monitor