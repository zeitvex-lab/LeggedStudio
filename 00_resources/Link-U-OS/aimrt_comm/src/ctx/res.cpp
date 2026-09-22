// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/ctx/res.h"

namespace aimrte::ctx
{
Executor::Executor(std::string name)
    : res::Executor(std::move(name))
{
}

Executor::Executor(std::string name, std::uint32_t thread_num, std::vector<std::uint32_t> thread_bind_cpu, std::string thread_sched_policy)
    : res::Executor(std::move(name)), option_({{thread_num, std::move(thread_bind_cpu), std::move(thread_sched_policy)}})
{
}

Executor::Executor(res::Executor&& res)
    : res::Executor(std::move(res))
{
}

Executor::Executor(const res::Executor& res)
    : res::Executor(res)
{
}

Executor& Executor::operator=(const Executor& other)
{
  static_cast<res::Executor&>(*this) = static_cast<const res::Executor&>(other);

  if (not other.no_copy_option_)
    option_ = other.option_;

  return *this;
}

std::optional<Executor::Option> Executor::GetOption(const Executor& exe)
{
  return exe.option_;
}

Executor Executor::CreateDeclaration(std::string name)
{
  Executor result;
  SetName(result, std::move(name));
  result.no_copy_option_ = true;
  return result;
}

bool Executor::ThreadSafe(const std::source_location call_loc) const
{
  return core::Context::OpExe::GetRawRef(
           core::details::ExpectContext(call_loc)->exe(*this, call_loc))
    .ThreadSafe();
}
}  // namespace aimrte::ctx
