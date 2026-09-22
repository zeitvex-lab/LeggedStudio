// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./fs.h"
#include "src/macro/macro.h"
#include "src/panic/panic.h"
#include "src/sys/internal/config.h"
#include "src/sys/internal/fs.h"

namespace aimrte::ctx::details
{
Fs::Fs(std::string module_name)
    : module_name_(std::move(module_name))
{
}

Fs::~Fs()
{
  std::error_code ec;
  remove_all(temp_, ec);
}

const std::filesystem::path& Fs::GetData()
{
  std::call_once(
    data_flag_,
    [this]() {
      if (not std::filesystem::is_directory(sys::internal::GetDataRoot()) and sys::config::EnableOnlineMode())
        panic().wtf("Agibot modules' data directory is NOT existed !");

      const std::string path = sys::internal::GetDataRoot() + "/" + module_name_;

      if (not std::filesystem::exists(path))
        std::filesystem::create_directories(path);

      data_ = path;
    });

  return data_;
}

const std::filesystem::path& Fs::GetParam()
{
  std::call_once(
    param_flag_,
    [this]() {
      if (not std::filesystem::is_directory(sys::internal::GetParamRoot()) and sys::config::EnableOnlineMode())
        panic().wtf("Agibot modules' param directory is NOT existed !");

      const std::string path = sys::internal::GetParamRoot() + "/" + module_name_;

      if (not std::filesystem::exists(path))
        std::filesystem::create_directories(path);

      param_ = path;
    });

  return param_;
}

const std::filesystem::path& Fs::GetTemp()
{
  std::call_once(
    temp_flag_,
    [this]() {
      const std::string path = sys::internal::GetTempModuleRoot(module_name_);

      if (not std::filesystem::exists(path))
        std::filesystem::create_directories(path);

      temp_ = path;
    });

  return temp_;
}
}  // namespace aimrte::ctx::details
