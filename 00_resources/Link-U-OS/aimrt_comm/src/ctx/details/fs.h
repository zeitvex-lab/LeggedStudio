// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <filesystem>
#include <mutex>
#include <source_location>
#include <string>

namespace aimrte::ctx::details
{
class Fs
{
 public:
  explicit Fs(std::string module_name);
  ~Fs();

  const std::filesystem::path& GetData();
  const std::filesystem::path& GetParam();
  const std::filesystem::path& GetTemp();

 private:
  std::string module_name_;

  std::filesystem::path data_;
  std::once_flag data_flag_;

  std::filesystem::path param_;
  std::once_flag param_flag_;

  std::filesystem::path temp_;
  std::once_flag temp_flag_;
};
}  // namespace aimrte::ctx::details
