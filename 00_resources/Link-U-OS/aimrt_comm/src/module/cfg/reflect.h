// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/ctx/ctx.h"
#include <chrono>
#include <rfl.hpp>

namespace aimrte::cfg::details
{
template <class TRes>
struct ResourceRfl {
  std::string name;

  static ResourceRfl from_class(const TRes& res) noexcept
  {
    return {res.GetName()};
  }

  TRes to_class() const
  {
    TRes res;
    res::details::Base::SetName(res, name);
    return res;
  }
};

struct ExecutorRfl {
  std::string name;

  static ExecutorRfl from_class(const ctx::Executor& obj) noexcept;
  ctx::Executor to_class() const;
};

struct DurationRfl {
  enum class Unit {
    sec,
    ms,
    us,
    ns,
    min
  };

  std::int64_t value = 0;
  Unit unit          = Unit::sec;

  static DurationRfl from_class(const std::chrono::steady_clock::duration& t) noexcept;

  [[nodiscard]] std::chrono::steady_clock::duration to_class() const;
};
}  // namespace aimrte::cfg::details

namespace rfl::parsing
{
template <class ReaderType, class WriterType, class T, class ProcessorsType>
struct Parser<ReaderType, WriterType, aimrte::ctx::Publisher<T>, ProcessorsType>
    : CustomParser<ReaderType, WriterType, ProcessorsType, aimrte::ctx::Publisher<T>, aimrte::cfg::details::ResourceRfl<aimrte::ctx::Publisher<T>>> {
};

template <class ReaderType, class WriterType, class T, class ProcessorsType>
struct Parser<ReaderType, WriterType, aimrte::ctx::Subscriber<T>, ProcessorsType>
    : CustomParser<ReaderType, WriterType, ProcessorsType, aimrte::ctx::Subscriber<T>, aimrte::cfg::details::ResourceRfl<aimrte::ctx::Subscriber<T>>> {
};

template <class ReaderType, class WriterType, class ProcessorsType>
struct Parser<ReaderType, WriterType, aimrte::ctx::Executor, ProcessorsType>
    : CustomParser<ReaderType, WriterType, ProcessorsType, aimrte::ctx::Executor, aimrte::cfg::details::ExecutorRfl> {
};

template <class ReaderType, class WriterType, class ProcessorsType>
struct Parser<ReaderType, WriterType, std::chrono::steady_clock::duration, ProcessorsType>
    : CustomParser<ReaderType, WriterType, ProcessorsType, std::chrono::steady_clock::duration, aimrte::cfg::details::DurationRfl> {
};
}  // namespace rfl::parsing
