// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./minidump_manager.h"
#include "src/ctx/anytime.h"

#include <filesystem>
#include <functional>
#include <regex>
#include <sstream>

extern char* __progname;

namespace
{
constexpr char DUMP_PATH[]          = "/agibot/data/minidump";
constexpr char DUMP_ENABLED_ENV[]   = "AIMRTE_MINIDUMP_ENABLED";
constexpr char DUMP_COUNT_ENV[]     = "AIMRTE_MINIDUMP_COUNT";
constexpr char DUMP_SIZE_ENV[]      = "AIMRTE_MINIDUMP_MAX_DUMP_SIZE_KB";
constexpr char DUMP_ROTATE_ENV[]    = "AIMRTE_MINIDUMP_ENABLE_ROTATION";
constexpr bool DEFAULT_DUMP_ENABLED = true;
constexpr int DEFAULT_DUMP_COUNT    = 3;
constexpr int MIN_DUMP_SIZE_KB      = 500;
constexpr bool DEFAULT_DUMP_ROTATE  = true;
}  // namespace

namespace aimrte::minidump
{
MinidumpManager& MinidumpManager::GetInstance()
{
  static MinidumpManager instance;
  return instance;
}
bool MinidumpManager::Initialize()
{
  bool enable_minidump = GetEnvAsBool(DUMP_ENABLED_ENV, DEFAULT_DUMP_ENABLED);
  if (!enable_minidump) {
    AIMRTE_INFO_STREAM("Minidump is disabled: enable_minidump: " << enable_minidump);
    return false;
  }

  int max_dump_count   = GetEnvAsInt(DUMP_COUNT_ENV, DEFAULT_DUMP_COUNT);
  bool enable_rotation = GetEnvAsBool(DUMP_ROTATE_ENV, DEFAULT_DUMP_ROTATE);
  int max_dump_size_kb = GetEnvAsInt(DUMP_SIZE_ENV, MIN_DUMP_SIZE_KB);
  if (max_dump_size_kb < MIN_DUMP_SIZE_KB) {
    max_dump_size_kb = MIN_DUMP_SIZE_KB;
  }
  return Initialize(max_dump_count, max_dump_size_kb * 1024, enable_rotation);
}
bool MinidumpManager::Initialize(int max_dump_count, int max_dump_size_kb, bool enable_rotation)
{
  if (is_initialized_) {
    AIMRTE_INFO("Minidump has already been initialized.");
    return true;
  }
  if (!std::filesystem::exists(DUMP_PATH)) {
    AIMRTE_INFO("Minidump is disabled: path not exists");
    return false;
  }
  int current_count = GetCurrentDumpCount();
  if (!enable_rotation && current_count >= max_dump_count) {
    AIMRTE_INFO_STREAM("Minidump is disabled: enable_rotation: " << enable_rotation << ", current_count: " << current_count << ", max_count: " << max_dump_count);
    return false;
  }
  AIMRTE_INFO_STREAM("Minidump is enabled, max count: " << max_dump_count << ", size limit: " << max_dump_size_kb << ", enable rotation: " << enable_rotation);
  is_initialized_  = true;
  max_dump_count_  = max_dump_count;
  enable_rotation_ = enable_rotation;
  google_breakpad::MinidumpDescriptor descriptor(DUMP_PATH);
  descriptor.set_size_limit(max_dump_size_kb);
  const auto callback_func = [](const google_breakpad::MinidumpDescriptor& descriptor, void* context, bool succeeded) -> bool {
    MinidumpManager* manager = static_cast<MinidumpManager*>(context);
    if (manager == nullptr) {
      return false;
    }
    return manager->DumpCallback(descriptor, succeeded);
  };
  exp_handler_ = std::make_unique<google_breakpad::ExceptionHandler>(descriptor, nullptr, callback_func, this, true, -1);
  return true;
}
int MinidumpManager::GetMaxDumpCount() const
{
  return max_dump_count_;
}
std::string MinidumpManager::GetDumpFileName()
{
  struct timeval tv;
  gettimeofday(&tv, nullptr);

  std::ostringstream oss;
  oss << DUMP_PATH
      << "/"
      << __progname
      << "_"
      << tv.tv_sec << "_"
      << getpid() << ".dmp";
  return oss.str();
}
bool MinidumpManager::GetEnvAsBool(const char* env, bool default_val)
{
  const char* val = std::getenv(env);
  if (val == nullptr) {
    return default_val;
  }
  return (std::strcmp(val, "true") == 0);
}
int MinidumpManager::GetEnvAsInt(const char* env, int default_val)
{
  const char* val = std::getenv(env);
  if (val == nullptr) {
    return default_val;
  }
  return std::atoi(val);
}
int MinidumpManager::GetCurrentDumpCount()
{
  std::string app_name{__progname};
  AIMRTE_INFO_STREAM("Get current dump count: app_name: " << app_name);
  std::filesystem::path dump_dir{DUMP_PATH};
  std::regex pattern(std::string("^" + app_name + "_\\d{10}_\\d+.dmp$"));
  int count = 0;
  for (const auto& item : std::filesystem::directory_iterator(dump_dir)) {
    if (std::regex_match(item.path().filename().string(), pattern)) {
      ++count;
    }
  }
  return count;
}
bool MinidumpManager::RemoveOldestDumps(size_t keep_count)
{
  std::string app_name{__progname};
  AIMRTE_INFO_STREAM("Remove oldest dumps: app_name: " << app_name << ", keep_count: " << keep_count);
  std::filesystem::path dump_dir{DUMP_PATH};
  std::regex pattern(std::string("^" + app_name + "_\\d{10}_\\d+.dmp$"));
  std::vector<std::string> dump_files;
  for (const auto& item : std::filesystem::directory_iterator(dump_dir)) {
    if (std::regex_match(item.path().filename().string(), pattern)) {
      dump_files.push_back(item.path().string());
    }
  }
  std::sort(dump_files.begin(), dump_files.end());
  if (dump_files.size() > keep_count) {
    for (size_t i = 0; i < dump_files.size() - keep_count; ++i) {
      std::error_code ec;
      std::filesystem::remove(dump_files[i], ec);
      AIMRTE_INFO_STREAM("Removed dump file: " << dump_files[i]);
    }
  }
  return true;
}
bool MinidumpManager::DumpCallback(const google_breakpad::MinidumpDescriptor& descriptor, bool succeeded)
{
  // 删除多余dump
  AIMRTE_INFO_STREAM("Dump callback: max_dump_count: " << max_dump_count_);
  if (max_dump_count_ == 0) {
    return false;
  }
  RemoveOldestDumps(max_dump_count_ - 1);
  // 重命名minidump文件
  std::string new_name{GetDumpFileName()};
  rename(descriptor.path(), new_name.c_str());
  AIMRTE_INFO_STREAM("Dump callback: DUMP_PATH: " << new_name);
  return succeeded;
}
}  // namespace aimrte::minidump
