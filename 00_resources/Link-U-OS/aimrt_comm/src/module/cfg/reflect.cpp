// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./reflect.h"

namespace aimrte::cfg::details
{
ExecutorRfl ExecutorRfl::from_class(const ctx::Executor& obj) noexcept
{
  return {obj.GetName()};
}

ctx::Executor ExecutorRfl::to_class() const
{
  return ctx::Executor::CreateDeclaration(name);
}

DurationRfl DurationRfl::from_class(const std::chrono::steady_clock::duration& t) noexcept
{
  std::int64_t value = t.count();

  if (value % 1000 != 0)
    return {value, Unit::ns};

  value /= 1000;

  if (value % 1000 != 0)
    return {value, Unit::us};

  value /= 1000;

  if (value % 1000 != 0)
    return {value, Unit::ms};

  value /= 1000;

  if (value % 1000 != 0)
    return {value, Unit::sec};

  value /= 1000;
  return {value, Unit::min};
}

std::chrono::steady_clock::duration DurationRfl::to_class() const
{
  switch (unit) {
    case Unit::sec:
      return std::chrono::seconds(value);
    case Unit::ms:
      return std::chrono::milliseconds(value);
    case Unit::us:
      return std::chrono::microseconds(value);
    case Unit::ns:
      return std::chrono::nanoseconds(value);
    case Unit::min:
      return std::chrono::seconds(value * 1000);
    default:
      panic().wtf("unknown time unit, {}", static_cast<int>(unit));
  }
}
}  // namespace aimrte::cfg::details
