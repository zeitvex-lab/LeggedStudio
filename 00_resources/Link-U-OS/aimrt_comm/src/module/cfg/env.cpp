// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./env.h"
#include "src/utils/utils.h"

namespace aimrte::cfg::details
{
std::string ProcName()
{
  return utils::Env(ENV_PROCESS_NAME, "_");
}
}  // namespace aimrte::cfg::details
