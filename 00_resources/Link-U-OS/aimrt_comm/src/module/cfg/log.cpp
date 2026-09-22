// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./log.h"

namespace aimrte::cfg::backend::log
{
std::string rotate_file::DefaultLogPath()
{
  const std::string proc_name = details::ProcName();

  if (utils::Env("AGIBOT_LOG_PATH_ENABLE", "false") == "true")
    return sys::internal::GetLogRoot() + "/" + proc_name;

  return utils::Env("LOG_PATH", "./log");
}
}  // namespace aimrte::cfg::backend::log
