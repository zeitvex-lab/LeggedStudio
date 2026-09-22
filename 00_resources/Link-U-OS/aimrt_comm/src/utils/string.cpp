// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./string.h"
#include <cctype>
#include <sstream>
#include <string>
#include <vector>

namespace aimrte::utils
{
std::vector<std::string> SplitTrim(const std::string_view& str, const char separator)
{
  std::vector<std::string> result;
  std::string s{str};
  std::string item;
  std::istringstream ss(s);

  // 使用 std::getline 按分隔符分割字符串
  while (std::getline(ss, item, separator)) {
    // 修剪字符串前后的空白
    auto start = item.find_first_not_of(" \t\n\v\f\r");
    if (start == std::string::npos) {
      // 字符串只包含空白字符
      continue;
    }

    auto end = item.find_last_not_of(" \t\n\v\f\r");
    item     = item.substr(start, end - start + 1);

    // 如果修剪后的字符串非空，添加到结果中
    if (!item.empty()) {
      result.push_back(item);
    }
  }

  return result;
}
}  // namespace aimrte::utils
