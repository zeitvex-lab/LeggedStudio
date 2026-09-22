// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./fs.h"
#include <fmt/format.h>
#include <pwd.h>
#include <unistd.h>
#include <cstdlib>

namespace aimrte::sys::internal
{
const std::string& GetRoot()
{
  const static std::string path = []() {
    char* home_env_str = std::getenv("AGIBOT_HOME");
    return std::string(home_env_str ? home_env_str : "") + "/agibot";
  }();

  return path;
}

const std::string& GetInfoRoot()
{
  const static std::string path = GetRoot() + "/data/info";
  return path;
}

const std::string& GetSysRoot()
{
  const static std::string path = GetRoot() + "/sys";
  return path;
}

const std::string& GetOTARoot()
{
  const static std::string path = GetRoot() + "/data/ota";
  return path;
}

const std::string& GetSoftwareRoot()
{
  const static std::string path = GetRoot() + "/software";
  return path;
}

const std::string& GetSoftwareMetadataPath()
{
  const static std::string path = GetSoftwareRoot() + "/v0/metadata.yaml";
  return path;
}

const std::string& GetLogRoot()
{
  const static std::string path = GetRoot() + "/data/log";
  return path;
}

const std::string& GetDataRoot()
{
  const static std::string path = GetRoot() + "/data/var";
  return path;
}

const std::string& GetParamRoot()
{
  const static std::string path = GetRoot() + "/data/param";
  return path;
}

static std::string GetTempRoot()
{
  // 按用户分临时目录，避免权限问题
  const passwd* pwd = getpwuid(getuid());
  return ::fmt::format("{}/data/tmp/agibot-{}", GetRoot(), (pwd and pwd->pw_name ? pwd->pw_name : "_"));
}

std::string GetTempModuleRoot(const std::string_view& module_name)
{
  return ::fmt::format("{}/mod/{}/{}", GetTempRoot(), module_name, std::to_string(getpid()));
}

std::string GetTempProcessRoot(const std::string_view& process_name)
{
  return ::fmt::format("{}/proc/{}", GetTempRoot(), process_name);
}
}  // namespace aimrte::sys::internal

namespace aimrte::sys::internal
{
const std::string& GetSNPath()
{
  const static std::string path = GetInfoRoot() + "/sn";
  return path;
}

const std::string& GetNamePath()
{
  const static std::string path = GetInfoRoot() + "/name";
  return path;
}

const std::string& GetModelPath()
{
  const static std::string path = GetInfoRoot() + "/model";
  return path;
}

const std::string& GetSOCIndexPath()
{
  const static std::string path = GetInfoRoot() + "/soc_index";
  return path;
}
}  // namespace aimrte::sys::internal
