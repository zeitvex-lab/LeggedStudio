// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "util_func.h"

#include <sstream>
#include <iomanip>
#include <fstream>
#include <chrono>
#include <filesystem>

#include "global.h"
#include "localtime.h"

namespace process_manager {

uint64_t GetCurrentMilliSecondTimestamp()
{
  auto now      = std::chrono::system_clock::now();
  auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch());
  return duration.count();
}

uint64_t GetCurrentNanoSecondTimestamp()
{
  auto now      = std::chrono::system_clock::now();
  auto duration = std::chrono::duration_cast<std::chrono::nanoseconds>(now.time_since_epoch());
  return duration.count();
}

std::string GetNanoSecondTimestampStr(uint64_t timestamp)
{
  std::time_t sec = timestamp / 1000000000l;
  int ms = static_cast<int>(timestamp % 1000000000);

  std::tm tm;
  gmtime_r(&sec, &tm);   // 0 时区

  // 3. 拼字符串
  std::ostringstream oss;
  oss << std::put_time(&tm, "%Y-%m-%dT%H:%M:%S");
  oss << '.' << std::setfill('0') << std::setw(9) << ms << 'Z';
  return oss.str();
}

std::string GetLocalSecondTimestampStr(uint64_t timestamp) {
  std::time_t sec = timestamp / 1000000000l;
  int ms = static_cast<int>(timestamp % 1000000000);

  tm   tm{};
  nolocks_localtime(&tm, sec, g_timezone, 0);  // 随系统的时区

  // 3. 拼字符串
  std::ostringstream oss;
  oss << std::put_time(&tm, "%Y-%m-%dT%H:%M:%S");
  oss << '.' << std::setfill('0') << std::setw(9) << ms << 'Z';
  return oss.str();
}

bool CreateFileDir(const std::string& dir) {
  try
  {
    if (!std::filesystem::exists(dir)) {
      std::filesystem::create_directories(dir);
    }
  }
  catch(const std::exception& e)
  {
    AIMRT_ERROR("create dir [{}] failed, {}", dir, e.what());
    return false;
  }

  return true;
}

std::string GetLocalFileData(const std::string& file_path) {
  std::string file_data_str;
  try
  {
    std::filesystem::path sf_file_path(file_path);
    if (std::filesystem::exists(sf_file_path)) {
      std::ifstream ifs(file_path);
      std::getline(ifs, file_data_str);
    }
  }
  catch(const std::exception& e) {
    AIMRT_ERROR("Catch exception: {}, file_path: {}", e.what(), file_path);
    file_data_str = "";
  }
  return file_data_str;
}

}
