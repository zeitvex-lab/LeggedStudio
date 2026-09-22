// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <filesystem>
#include "src/core/core.h"
#include "src/macro/macro.h"
#include "src/interface/aimrt_module_cpp_interface/logger/logger.h"

// 在初始化阶段、运行阶段、退出阶段均可调用的接口
namespace aimrte::ctx
{
/**
 * @return 当前上下文中的日志输出接口，需要用于进一步输出日志
 */
[[nodiscard]] core::Context::OpLog log(AIMRTE(src(call_loc)));

/**
 * @brief 检查给定的条件是否成立，若不成立，则执行后续的操作
 * @param con 被检查的条件
 * @return 后置动作接口
 */
[[nodiscard]] core::Context::OpCheck check(bool con, AIMRTE(src(call_loc)));

/**
 * @brief 将给定的对象显式转换为 bool 后，判断其是否为 true，若不是，则执行后续操作。
 */
template <class T>
[[nodiscard]] core::Context::OpCheck check(const T& obj, AIMRTE(src(call_loc)))
{
  return check(static_cast<bool>(obj), call_loc);
}

/**
 * @return 异常日志记录与抛出接口
 */
[[nodiscard]] core::Context::OpRaise raise(AIMRTE(src(call_loc)));

/**
 * @brief 获取当前的模块的数据路径
 */
const std::filesystem::path& GetDataPath(AIMRTE(src(call_loc)));

/**
 * @brief 获取当前的模块的参数路径
 */
const std::filesystem::path& GetParamPath(AIMRTE(src(call_loc)));

/**
 * @brief 获取当前模块的临时目录的路径
 */
const std::filesystem::path& GetTempPath(AIMRTE(src(call_loc)));

/**
 * @return 当前模块是否被要求退出
 */
bool Ok(AIMRTE(src(call_loc)));

/**
 * @brief 没有上下文的情况下，日志接口的实现
 */
inline aimrt::logger::LoggerRef global_logger;
template <class... TArgs>
void DefaultLogImpl(const std::uint32_t level, const std::source_location& src_loc, const ::fmt::format_string<aimrte::core::details::LogExType<TArgs>...>& fmt, TArgs&&... args)
{
  const aimrt::logger::LoggerRef& logger = global_logger ? global_logger : aimrt::logger::GetSimpleLoggerRef();
  if (level < logger.GetLogLevel())
    return;
  aimrt::common::util::LogImpl(
    logger,
    level,
    src_loc.line(),
    src_loc.file_name(),
    src_loc.function_name(),
    fmt, aimrte::core::details::LogEx(std::forward<TArgs>(args))...);
}
}  // namespace aimrte::ctx

// 一些 log 宏，使用宏可以避免在等级不够时，节省日志内容的计算
#define AIMRTE_DETAILS_LOG_IMPL(_level_, _src_loc_, ...)                                                            \
  do {                                                                                                              \
    if (!aimrte::core::details::g_thread_ctx.ctx_ptr.expired()) {                                                   \
      if (auto op = ::aimrte::ctx::log(_src_loc_); op.GetLevel() <= ::aimrte::core::Context::OpLog::_level_##Level) \
        op._level_(__VA_ARGS__);                                                                                    \
    } else {                                                                                                        \
      ::aimrte::ctx::DefaultLogImpl(::aimrte::core::Context::OpLog::_level_##Level, _src_loc_, __VA_ARGS__);        \
    }                                                                                                               \
  } while (false)

#define AIMRTE_DETAILS_LOG_IMPL_HERE(_level_, _fmt_, ...) AIMRTE_DETAILS_LOG_IMPL(_level_, std::source_location::current(), _fmt_, ##__VA_ARGS__)
#define AIMRTE_DETAILS_LOG_IMPL_HERE_EVERY_N(_num_, _level_, _fmt_, ...) \
  do {                                                                                                              \
    static std::atomic<std::uint32_t> __counter__(0);                                                               \
    if ((__counter__.fetch_add(1, std::memory_order_relaxed) % (_num_)) == 0) {                                     \
      AIMRTE_DETAILS_LOG_IMPL_HERE(_level_, _fmt_, ##__VA_ARGS__);                                                   \
    }                                                                                                               \
  } while (false)

#define AIMRTE_TRACE(_fmt_, ...) AIMRTE_DETAILS_LOG_IMPL_HERE(Trace, _fmt_, ##__VA_ARGS__)
#define AIMRTE_DEBUG(_fmt_, ...) AIMRTE_DETAILS_LOG_IMPL_HERE(Debug, _fmt_, ##__VA_ARGS__)
#define AIMRTE_INFO(_fmt_, ...) AIMRTE_DETAILS_LOG_IMPL_HERE(Info, _fmt_, ##__VA_ARGS__)
#define AIMRTE_WARN(_fmt_, ...) AIMRTE_DETAILS_LOG_IMPL_HERE(Warn, _fmt_, ##__VA_ARGS__)
#define AIMRTE_ERROR(_fmt_, ...) AIMRTE_DETAILS_LOG_IMPL_HERE(Error, _fmt_, ##__VA_ARGS__)
#define AIMRTE_FATAL(_fmt_, ...) AIMRTE_DETAILS_LOG_IMPL_HERE(Fatal, _fmt_, ##__VA_ARGS__)

#define AIMRTE_TRACE_EVERY(_num_, _fmt_, ...) AIMRTE_DETAILS_LOG_IMPL_HERE_EVERY_N(_num_, Trace, _fmt_, ##__VA_ARGS__)
#define AIMRTE_DEBUG_EVERY(_num_, _fmt_, ...) AIMRTE_DETAILS_LOG_IMPL_HERE_EVERY_N(_num_, Debug, _fmt_, ##__VA_ARGS__)
#define AIMRTE_INFO_EVERY(_num_, _fmt_, ...) AIMRTE_DETAILS_LOG_IMPL_HERE_EVERY_N(_num_, Info, _fmt_, ##__VA_ARGS__)
#define AIMRTE_WARN_EVERY(_num_, _fmt_, ...) AIMRTE_DETAILS_LOG_IMPL_HERE_EVERY_N(_num_, Warn, _fmt_, ##__VA_ARGS__)
#define AIMRTE_ERROR_EVERY(_num_, _fmt_, ...) AIMRTE_DETAILS_LOG_IMPL_HERE_EVERY_N(_num_, Error, _fmt_, ##__VA_ARGS__)
#define AIMRTE_FATAL_EVERY(_num_, _fmt_, ...) AIMRTE_DETAILS_LOG_IMPL_HERE_EVERY_N(_num_, Fatal, _fmt_, ##__VA_ARGS__)

#define AIMRTE_TRACE_AT(_src_loc_, _fmt_, ...) AIMRTE_DETAILS_LOG_IMPL(Trace, _src_loc_, _fmt_, ##__VA_ARGS__)
#define AIMRTE_DEBUG_AT(_src_loc_, _fmt_, ...) AIMRTE_DETAILS_LOG_IMPL(Debug, _src_loc_, _fmt_, ##__VA_ARGS__)
#define AIMRTE_INFO_AT(_src_loc_, _fmt_, ...) AIMRTE_DETAILS_LOG_IMPL(Info, _src_loc_, _fmt_, ##__VA_ARGS__)
#define AIMRTE_WARN_AT(_src_loc_, _fmt_, ...) AIMRTE_DETAILS_LOG_IMPL(Warn, _src_loc_, _fmt_, ##__VA_ARGS__)
#define AIMRTE_ERROR_AT(_src_loc_, _fmt_, ...) AIMRTE_DETAILS_LOG_IMPL(Error, _src_loc_, _fmt_, ##__VA_ARGS__)
#define AIMRTE_FATAL_AT(_src_loc_, _fmt_, ...) AIMRTE_DETAILS_LOG_IMPL(Fatal, _src_loc_, _fmt_, ##__VA_ARGS__)

#define AIMRTE_DETAILS_LOG_STREAM_IMPL(_level_, _src_loc_, ...)    \
  do {                                                             \
    std::stringstream __ss;                                        \
    __ss << __VA_ARGS__;                                           \
    AIMRTE_DETAILS_LOG_IMPL(_level_, _src_loc_, "{}", __ss.str()); \
  } while (0)

#define AIMRTE_DETAILS_LOG_STREAM_IMPL_HERE(_level_, ...) AIMRTE_DETAILS_LOG_STREAM_IMPL(_level_, std::source_location::current(), __VA_ARGS__)

#define AIMRTE_TRACE_STREAM(...) AIMRTE_DETAILS_LOG_STREAM_IMPL_HERE(Trace, __VA_ARGS__)
#define AIMRTE_DEBUG_STREAM(...) AIMRTE_DETAILS_LOG_STREAM_IMPL_HERE(Debug, __VA_ARGS__)
#define AIMRTE_INFO_STREAM(...) AIMRTE_DETAILS_LOG_STREAM_IMPL_HERE(Info, __VA_ARGS__)
#define AIMRTE_WARN_STREAM(...) AIMRTE_DETAILS_LOG_STREAM_IMPL_HERE(Warn, __VA_ARGS__)
#define AIMRTE_ERROR_STREAM(...) AIMRTE_DETAILS_LOG_STREAM_IMPL_HERE(Error, __VA_ARGS__)
#define AIMRTE_FATAL_STREAM(...) AIMRTE_DETAILS_LOG_STREAM_IMPL_HERE(Fatal, __VA_ARGS__)

#define AIMRTE_TRACE_STREAM_AT(_src_loc_, ...) AIMRTE_DETAILS_LOG_STREAM_IMPL(Trace, _src_loc_, __VA_ARGS__)
#define AIMRTE_DEBUG_STREAM_AT(_src_loc_, ...) AIMRTE_DETAILS_LOG_STREAM_IMPL(Debug, _src_loc_, __VA_ARGS__)
#define AIMRTE_INFO_STREAM_AT(_src_loc_, ...) AIMRTE_DETAILS_LOG_STREAM_IMPL(Info, _src_loc_, __VA_ARGS__)
#define AIMRTE_WARN_STREAM_AT(_src_loc_, ...) AIMRTE_DETAILS_LOG_STREAM_IMPL(Warn, _src_loc_, __VA_ARGS__)
#define AIMRTE_ERROR_STREAM_AT(_src_loc_, ...) AIMRTE_DETAILS_LOG_STREAM_IMPL(Error, _src_loc_, __VA_ARGS__)
#define AIMRTE_FATAL_STREAM_AT(_src_loc_, ...) AIMRTE_DETAILS_LOG_STREAM_IMPL(Fatal, _src_loc_, __VA_ARGS__)

#define AIMRTE_CHECK_THROW(__expr__, ...) \
  do {                                    \
    if (!(__expr__)) [[unlikely]] {       \
      aimrte::panic().wtf(__VA_ARGS__);   \
    }                                     \
  } while (0)
