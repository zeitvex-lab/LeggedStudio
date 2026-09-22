// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <string>

namespace aimrte::sys::details
{
/**
 * @brief 读取给定文件的第一行并返回。若读取失败，则返回空。
 */
std::string ReadOneLine(const std::string& path);

/**
 * @brief 将指定的一行内容，写入到指定路径的文件中。若写入失败、或内容中包含换行符时，将抛出异常。
 */
void WriteOneLine(const std::string& path, const std::string& content);

/**
 * @brief 将指定的一行内容，写入到指定路径的文件中，返回是否操作成功。
 */
bool WriteOneLine(const std::string& path, const std::string& content, std::nothrow_t);
}  // namespace aimrte::sys::details
