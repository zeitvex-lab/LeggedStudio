// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

namespace aimrte::core
{
/**
 * @brief 记录日志、并抛出异常的执行接口
 */
class Context::OpRaise : OpBase
{
 public:
  using OpBase::OpBase;

  template <class... TArgs>
  void Error(const ::fmt::format_string<TArgs...>& fmt, TArgs&&... args)
  {
    ctx_.LogAndThrow(
      AIMRT_LOG_LEVEL_ERROR, loc_, fmt, std::forward<TArgs>(args)...);
  }

  template <class... TArgs>
  void Fatal(const ::fmt::format_string<TArgs...>& fmt, TArgs&&... args)
  {
    ctx_.LogAndThrow(
      AIMRT_LOG_LEVEL_FATAL, loc_, fmt, std::forward<TArgs>(args)...);
  }
};
}  // namespace aimrte::core
