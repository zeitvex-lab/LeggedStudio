// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./impl.h"

namespace aimrte::panic_details
{

static thread_local bool panic_by_throw = false;

void SetPanicByThrow(const bool enable)
{
  panic_by_throw = enable;
}

Panic::Panic(std::source_location call_loc)
    : call_loc_(call_loc)
{
}

void Panic::PrintAndAbort(const std::string_view& tag, const std::string& msg) const
{
  std::string str =
    ::fmt::format(R"([{}]! {}
  in: {}
  at: line {}, column {}
  of: {})",
                  tag, msg, call_loc_.function_name(), call_loc_.line(), call_loc_.column(), call_loc_.file_name());

  if (not panic_by_throw) {
    std::cerr << str << std::endl;
    std::abort();
  }

  throw PanicExeception(std::move(str));
}
}  // namespace aimrte::panic_details
