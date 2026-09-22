// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./info.h"
#include <fstream>
#include "./details/utils.h"
#include "./internal/fs.h"
#include "yaml-cpp/yaml.h"

namespace aimrte::sys
{
std::string GetSN()
{
  return details::ReadOneLine(internal::GetSNPath());
}

std::string GetName()
{
  return details::ReadOneLine(internal::GetNamePath());
}

std::string GetModel()
{
  return details::ReadOneLine(internal::GetModelPath());
}

std::size_t GetSOCIndex()
{
  const std::string content = details::ReadOneLine(internal::GetSOCIndexPath());

  try {
    return std::stoull(content);
  } catch (...) {
    return -1;
  }
}

const Parameter& GetParameter()
{
  const static Parameter parameter{
    .f_urdf = internal::GetInfoRoot() + "/urdf",
  };

  return parameter;
}

std::string GetReleaseVersion()
{
  try {
    YAML::Node cfg = YAML::LoadFile(internal::GetSoftwareMetadataPath());
    return cfg["version"].as<std::string>();
  } catch (const std::exception& e) {
    return "";
  }
}

std::string GetProtocolVersion()
{
  return "";
}
}  // namespace aimrte::sys
