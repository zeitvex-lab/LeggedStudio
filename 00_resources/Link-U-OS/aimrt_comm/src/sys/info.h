// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <filesystem>
#include <string>

namespace aimrte::sys
{
/**
 * @return 本机器人的 SN 码
 */
std::string GetSN();

/**
 * @return 本机器人的名字
 */
std::string GetName();

/**
 * @return 本机器人的型号
 */
std::string GetModel();

/**
 * @return 当前进程运行所在的机器人 SOC 编号
 */
std::size_t GetSOCIndex();
}  // namespace aimrte::sys

namespace aimrte::sys
{
struct Parameter {
  // 机器人的 URDF 文件路径
  std::filesystem::path f_urdf;
};

/**
 * @return 机器人系统的公共参数
 */
const Parameter& GetParameter();
}  // namespace aimrte::sys

namespace aimrte::sys
{
/**
 * @return 软件版本号
 */
std::string GetReleaseVersion();

/**
 * @return Protocol版本号
 */
std::string GetProtocolVersion();
}  // namespace aimrte::sys
