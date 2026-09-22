// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <set>
#include <string>
#include <vector>

namespace aimrte::sys::config
{
/**
 * @return 是否允许启用 hds 功能
 */
bool EnableHDS();

/**
 * @return 是否允许启用日志控制功能
 */
bool EnableLogControl();

/**
 * @return 是否允许启用状态管理功能
 */
bool EnableStateManagement();

/**
 * @return 是否允许启用 trace 功能
 */
bool EnableTrace();

/**
 * @return 是否允许启用 monitor 功能
 */
bool EnableMonitor();

/**
 * @return 是否允许启用 viz 功能
 */
bool EnableViz();

/**
 * @return 是否是上线模式，也即在机上运行的模式
 */
bool EnableOnlineMode();

/**
 * @return 是否使用原本是 .dump 文件作为配置文件，并忽略框架的注入。
 *         可用于线上迅速调整配置并进行测试。
 */
bool EnableIgnorePredefinedCfgAndUseDumpFile();

/**
 * @return 是否忽略框架注入的配置。
 */
bool EnableIgnorePredefinedCfg();

/**
 * @return 是否启用 topic logger 功能
 */
bool EnableTopicLogger();

/**
 * @return 是否启用文件日志功能
 */
bool EnableFileLogger();

/**
 * @return 环境变量 EM_APP_NAME 的值
 */
std::string EMAppName();

/**
 * @return 框架默认为用户选择的 channel 通信后端。
 */
std::set<std::string> DefaultChannelBackends();

/**
 * @return 框架默认为用户选择的 rpc 通信后端
 */
std::set<std::string> DefaultRpcBackends();

/**
 * @return 框架默认为用户选择的日志后端
 */
std::set<std::string> DefaultLoggerBackends();

/**
 * @return 框架默认为用户选择的执行器类型
 */
std::string DefaultExecutorType();

/**
 * @return 需要在用户补丁之前执行的补丁文件列表
 */
std::vector<std::string> PatchBeforeConfigFiles();

/**
 * @return 需要在用户补丁之后执行的补丁文件列表
 */
std::vector<std::string> PatchAfterConfigFiles();
}  // namespace aimrte::sys::config

/// 支持新旧特性在线切换的后门选项
namespace aimrte::sys::config
{
/**
 * @return 为框架心跳选择新的通信后端。目前支持 ros2, zenoh. 默认使用 mqtt.
 */
std::string FeatureHeartbeatNewBackend();

/**
 * @return 为框架 HDS 告警链路选择新的通信后端。目前支持 ros2, zenoh. 默认使用 udp.
 */
std::string FeatureHDSNewBackend();

/**
 * @return 为所有 ros2 channel 配置统一的 qos (yaml 格式)。默认为空、不配置。
 */
std::string FeatureRos2ChannelQos();

/**
 * @return 设置日志强制落盘间隔。默认为 0，也即不设置强制落盘。
 */
int FeatureLogSyncInterval();
}  // namespace aimrte::sys::config
