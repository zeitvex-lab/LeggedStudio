// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

namespace aimrte::core
{
namespace details
{
template <class T>
concept StreamOutputSupport =
  requires(std::ostream& os, T&& data) {
    os << data;
  };

template <class T>
decltype(auto) LogEx(T&& data)
{
  using TRaw = std::remove_cvref_t<T>;

  if constexpr (::fmt::is_formattable<TRaw>())
    return std::forward<T>(data);
  else if constexpr (std::is_base_of_v<google::protobuf::Message, TRaw>) {
    return aimrt::Pb2CompactJson(data);
  } else if constexpr (StreamOutputSupport<T>) {
    std::stringstream stream;
    stream << data;
    return stream.str();
  } else {
    return rfl::yaml::write(std::forward<T>(data));
  }
}

template <class T>
struct LogExTrait {
  using Type = T;
};

template <class T>
struct LogExTrait<T&> {
  using Type = T&;
};

template <class T>
struct LogExTrait<T&&> {
  using Type = T;
};

template <class T>
using LogExType = typename LogExTrait<decltype(LogEx(std::declval<T>()))>::Type;
}  // namespace details

/**
 * @brief 日志输出接口，仅临时使用
 */
class Context::OpLog : public OpBase
{
 public:
  constexpr static std::uint32_t TraceLevel = AIMRT_LOG_LEVEL_TRACE;
  constexpr static std::uint32_t DebugLevel = AIMRT_LOG_LEVEL_DEBUG;
  constexpr static std::uint32_t InfoLevel  = AIMRT_LOG_LEVEL_INFO;
  constexpr static std::uint32_t WarnLevel  = AIMRT_LOG_LEVEL_WARN;
  constexpr static std::uint32_t ErrorLevel = AIMRT_LOG_LEVEL_ERROR;
  constexpr static std::uint32_t FatalLevel = AIMRT_LOG_LEVEL_FATAL;

 public:
  using OpBase::OpBase;

  template <class... TArgs>
  void Trace(const ::fmt::format_string<details::LogExType<TArgs>...>& fmt, TArgs&&... args)
  {
    Impl(TraceLevel, fmt, std::forward<TArgs>(args)...);
  }

  template <class... TArgs>
  void Debug(const ::fmt::format_string<details::LogExType<TArgs>...>& fmt, TArgs&&... args)
  {
    Impl(DebugLevel, fmt, std::forward<TArgs>(args)...);
  }

  template <class... TArgs>
  void Info(const ::fmt::format_string<details::LogExType<TArgs>...>& fmt, TArgs&&... args)
  {
    Impl(InfoLevel, fmt, std::forward<TArgs>(args)...);
  }

  template <class... TArgs>
  void Warn(const ::fmt::format_string<details::LogExType<TArgs>...>& fmt, TArgs&&... args)
  {
    Impl(WarnLevel, fmt, std::forward<TArgs>(args)...);
  }

  template <class... TArgs>
  void Error(const ::fmt::format_string<details::LogExType<TArgs>...>& fmt, TArgs&&... args)
  {
    Impl(ErrorLevel, fmt, std::forward<TArgs>(args)...);
  }

  template <class... TArgs>
  void Fatal(const ::fmt::format_string<details::LogExType<TArgs>...>& fmt, TArgs&&... args)
  {
    Impl(FatalLevel, fmt, std::forward<TArgs>(args)...);
  }

  std::uint32_t GetLevel() const
  {
    return ctx_.core_.GetLogger().GetLogLevel();
  }

  template <class... TArgs>
  void TestEx(const ::fmt::format_string<details::LogExType<TArgs>...>& fmt, TArgs&&... args)
  {
    ctx_.Log(InfoLevel, loc_, fmt, details::LogEx(std::forward<TArgs>(args))...);
  }

 private:
  template <class... TArgs>
  void Impl(const std::uint32_t level, const ::fmt::format_string<details::LogExType<TArgs>...>& fmt, TArgs&&... args)
  {
    ctx_.Log(level, loc_, fmt, details::LogEx(std::forward<TArgs>(args))...);
  }
};
}  // namespace aimrte::core
