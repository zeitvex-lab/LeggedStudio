// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <string>

namespace aimrte::sys::internal
{
/**
 * @return SOC 软件系统的根目录
 */
const std::string& GetRoot();

/**
 * @return SOC 软件系统的信息目录
 */
const std::string& GetInfoRoot();

/**
 * @return SOC 软件系统的运行时目录，存放一些系统状态
 */
const std::string& GetSysRoot();

/**
 * @return SOC 上的 OTA 工作目录
 */
const std::string& GetOTARoot();

/**
 * @return SOC 上软件包的根目录，包含多个版本的文件夹
 */
const std::string& GetSoftwareRoot();

/**
 * @return 软件包元数据文件路径
 */
const std::string& GetSoftwareMetadataPath();

/**
 * @return SOC 上的日志根目录，包含各个模块的日志文件夹
 */
const std::string& GetLogRoot();

/**
 * @return SOC 上的数据根目录，包含多个模块的数据文件夹
 */
const std::string& GetDataRoot();

/**
 * @return SOC 上的参数根目录，包含多个模块的数据文件夹
 */
const std::string& GetParamRoot();

/**
 * @return 指定模块的临时目录
 */
std::string GetTempModuleRoot(const std::string_view& module_name);

/**
 * @return 指定进程的临时目录
 */
std::string GetTempProcessRoot(const std::string_view& process_name);
}  // namespace aimrte::sys::internal

namespace aimrte::sys::internal
{
/**
 * @return 机器人的 SN 文件路径
 */
const std::string& GetSNPath();

/**
 * @return 机器人的名称文件路径
 */
const std::string& GetNamePath();

/**
 * @return 机器人的型号文件路径
 */
const std::string& GetModelPath();

/**
 * @return 机器人的 SOC 编号文件路径
 */
const std::string& GetSOCIndexPath();
}  // namespace aimrte::sys::internal
