// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

namespace aimrte::core
{
/**
 * @brief 检测给定条件是否成立，并执行对应行为的操作接口
 */
class Context::OpCheck : public OpBase
{
 public:
  template <class... TArgs>
  void Trace(const ::fmt::format_string<TArgs...>& fmt, TArgs&&... args)
  {
    LogImpl(AIMRT_LOG_LEVEL_TRACE, fmt, std::forward<TArgs>(args)...);
  }

  template <class... TArgs>
  void Debug(const ::fmt::format_string<TArgs...>& fmt, TArgs&&... args)
  {
    LogImpl(AIMRT_LOG_LEVEL_DEBUG, fmt, std::forward<TArgs>(args)...);
  }

  template <class... TArgs>
  void Info(const ::fmt::format_string<TArgs...>& fmt, TArgs&&... args)
  {
    LogImpl(AIMRT_LOG_LEVEL_INFO, fmt, std::forward<TArgs>(args)...);
  }

  template <class... TArgs>
  void Warn(const ::fmt::format_string<TArgs...>& fmt, TArgs&&... args)
  {
    LogImpl(AIMRT_LOG_LEVEL_WARN, fmt, std::forward<TArgs>(args)...);
  }

  template <class... TArgs>
  void Error(const ::fmt::format_string<TArgs...>& fmt, TArgs&&... args)
  {
    LogImpl(AIMRT_LOG_LEVEL_ERROR, fmt, std::forward<TArgs>(args)...);
  }

  template <class... TArgs>
  void Fatal(const ::fmt::format_string<TArgs...>& fmt, TArgs&&... args)
  {
    LogImpl(AIMRT_LOG_LEVEL_FATAL, fmt, std::forward<TArgs>(args)...);
  }

  template <class... TArgs>
  void ErrorThrow(const ::fmt::format_string<TArgs...>& fmt, TArgs&&... args)
  {
    LogThrowImpl(AIMRT_LOG_LEVEL_ERROR, fmt, std::forward<TArgs>(args)...);
  }

  template <class... TArgs>
  void FatalThrow(const ::fmt::format_string<TArgs...>& fmt, TArgs&&... args)
  {
    LogThrowImpl(AIMRT_LOG_LEVEL_FATAL, fmt, std::forward<TArgs>(args)...);
  }

 private:
  template <class... TArgs>
  void LogImpl(const std::uint32_t level, const ::fmt::format_string<TArgs...>& fmt, TArgs&&... args)
  {
    // 条件不成立时，根据日志等级输出日志
    if (not con_) [[unlikely]]
      ctx_.Log(level, loc_, fmt, std::forward<TArgs>(args)...);
  }

  template <class... TArgs>
  void LogThrowImpl(const std::uint32_t level, const ::fmt::format_string<TArgs...>& fmt, TArgs&&... args)
  {
    // 条件不成立时，处理日志打印并抛出异常
    if (not con_) [[unlikely]]
      ctx_.LogAndThrow(level, loc_, fmt, std::forward<TArgs>(args)...);
  }

 private:
  friend class Context;

  OpCheck(Context& ctx, bool con, std::source_location loc);

 private:
  // 条件是否成立
  const bool con_;
};
}  // namespace aimrte::core
