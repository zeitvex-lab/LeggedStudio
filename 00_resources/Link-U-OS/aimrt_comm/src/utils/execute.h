// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#ifndef SYSTEM_EXEC_H
#define SYSTEM_EXEC_H
#include <cstdio>
#include <string>
#include <string_view>
namespace aimrte::utils
{

/**
 * @brief  : 执行一段系统指令,并将结果返回
 * @param  : cmd 指令
 * @param  : result 返回系统输出或错误信息
 * @return : 0 成功, 非0 失败
 */
int Execute(std::string_view cmd, std::string &result);

}  // namespace aimrte::utils

#endif  // SYSTEM_EXEC_H
