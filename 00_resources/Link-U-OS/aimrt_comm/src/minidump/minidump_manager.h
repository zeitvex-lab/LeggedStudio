// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <client/linux/handler/exception_handler.h>
#include <memory>
#include <string>

namespace aimrte::minidump
{
class MinidumpManager
{
 public:
  static MinidumpManager& GetInstance();
  bool Initialize();
  bool Initialize(int max_dump_count, int max_dump_size_kb, bool enable_rotation);
  int GetMaxDumpCount() const;

 private:
  MinidumpManager()                                  = default;
  MinidumpManager(const MinidumpManager&)            = delete;
  MinidumpManager& operator=(const MinidumpManager&) = delete;

  std::string GetDumpFileName();
  bool GetEnvAsBool(const char* env, bool default_val);
  int GetEnvAsInt(const char* env, int default_val);
  int GetCurrentDumpCount();
  bool RemoveOldestDumps(size_t keep_count);
  bool DumpCallback(const google_breakpad::MinidumpDescriptor& descriptor, bool succeeded);

  bool is_initialized_{false};
  int max_dump_count_{0};
  bool enable_rotation_{true};
  std::unique_ptr<google_breakpad::ExceptionHandler> exp_handler_{nullptr};
};
}  // namespace aimrte::minidump
