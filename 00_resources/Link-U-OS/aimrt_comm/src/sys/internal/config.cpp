// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./config.h"
#include "src/utils/utils.h"
#include "boost/algorithm/string.hpp"

namespace aimrte::sys::config
{
bool EnableHDS()
{
  return utils::Env("AGIBOT_ENABLE_HDS", "false") == "true";
}

bool EnableLogControl()
{
  return utils::Env("AGIBOT_ENABLE_LOG_CONTROL", "false") == "true";
}

bool EnableStateManagement()
{
  return utils::Env("AGIBOT_ENABLE_STATE_MANAGEMENT", "false") == "true";
}

bool EnableTrace()
{
  return utils::Env("AGIBOT_ENABLE_TRACE", "false") == "true";
}

bool EnableMonitor()
{
  return utils::Env("AGIBOT_ENABLE_MONITOR", "false") == "true";
}

bool EnableViz()
{
  return utils::Env("AGIBOT_ENABLE_VIZ", "false") == "true";
}

bool EnableTopicLogger()
{
  return utils::Env("AGIBOT_ENABLE_TOPIC_LOGGER", "false") == "true";
}

bool EnableFileLogger()
{
  return utils::Env("AGIBOT_ENABLE_FILE_LOGGER", "true") == "true";
}

bool EnableOnlineMode()
{
  return utils::Env("AGIBOT_ENABLE_ONLINE_MODE", "false") == "true";
}

bool EnableIgnorePredefinedCfgAndUseDumpFile()
{
  return utils::Env("AGIBOT_ENABLE_IGNORE_PREDEFINED_CFG_AND_USE_DUMP_FILE", "false") == "true";
}

bool EnableIgnorePredefinedCfg()
{
  return utils::Env("AGIBOT_ENABLE_IGNORE_PREDEFINED_CFG", "false") == "true";
}

std::string EMAppName()
{
  return utils::Env("EM_APP_NAME", "");
}

static std::set<std::string> SplitBackendSettingEnv(const std::string_view& env_var, const std::string_view& default_value)
{
  std::vector<std::string> result = utils::SplitTrim(utils::Env(env_var, default_value), '|');
  return {std::move_iterator(result.begin()), std::move_iterator(result.end())};
}

std::set<std::string> DefaultChannelBackends()
{
  return SplitBackendSettingEnv("AGIBOT_DEFAULT_CHANNEL_BACKENDS", "ros2");
}

std::set<std::string> DefaultRpcBackends()
{
  return SplitBackendSettingEnv("AGIBOT_DEFAULT_RPC_BACKENDS", "ros2");
}

std::set<std::string> DefaultLoggerBackends()
{
  return SplitBackendSettingEnv("AGIBOT_DEFAULT_LOGGER_BACKENDS", "console | rotate_file | topic_logger");
}

std::string DefaultExecutorType()
{
  return utils::Env("AGIBOT_DEFAULT_EXECUTOR_TYPE", "asio_thread");
}

std::vector<std::string> PatchBeforeConfigFiles()
{
  return utils::SplitTrim(utils::Env("AGIBOT_CFG_PATCH_BEFORE", ""), ';');
}

std::vector<std::string> PatchAfterConfigFiles()
{
  return utils::SplitTrim(utils::Env("AGIBOT_CFG_PATCH_AFTER", ""), ';');
}
}  // namespace aimrte::sys::config

namespace aimrte::sys::config
{
std::string FeatureHeartbeatNewBackend()
{
  return utils::Env("AGIBOT_FEATURE_HEARTBEAT_NEW_BACKEND", "ros2");
}

std::string FeatureHDSNewBackend()
{
  return utils::Env("AGIBOT_FEATURE_HDS_NEW_BACKEND", "udp");
}

std::string FeatureRos2ChannelQos()
{
  return utils::Env("AGIBOT_FEATURE_ROS2_CHANNEL_QOS", "");
}

int FeatureLogSyncInterval()
{
  return std::stoi(utils::Env("AGIBOT_FEATURE_LOG_SYNC_INTERVAL", "0"));
}
}  // namespace aimrte::sys::config
