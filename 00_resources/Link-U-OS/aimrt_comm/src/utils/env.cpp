// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./env.h"

namespace aimrte::utils
{
std::string Env(const std::string_view& name, const std::string_view& fallback)
{
  if (const char* str = std::getenv(name.data()); str != nullptr)
    return str;

  return fallback.data();
}
}  // namespace aimrte::utils
