// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/concepts/concepts.h"
#include "src/core/core.h"
#include <gtest/gtest.h>
#include <chrono>
#include <sstream>

namespace aimrte::test
{
class TestBase : public ::testing::Test
{
 protected:
  void SetUp() final;

  void TearDown() final;

 protected:
  /**
   * @brief 用于测试启动时，让子类注入过程
   */
  virtual void OnSetup()
  {
  }

  /**
   * @brief 用于测试关闭时，让子类注入过程
   */
  virtual void OnTearDown()
  {
  }

  /**
   * @brief 判断当前的输出中，是否有指定的内容，分析内容截止上次本函数被调用为止。
   * @return 是否有期望的内容
   */
  bool ExpectOutputContent(const std::string& str);

  /**
   * @brief 判断当前的输出中，是否有指定的内容，分析内容截止上次本函数被调用为止。
   * @return 是否有期望的内容
   */
  bool ExpectOutputContent(const std::initializer_list<std::string>& strs);

  /**
   * @brief 测试给定过程是否“精确”地经历了指定的时间
   * @param dur 预期的时间间隔
   * @param err 计时误差
   * @param f   用户定义的过程
   * @return 用户定义的过程耗时是否在允许的误差范围内
   */
  template <class TDur, class TErr, concepts::ReturnVoidFunction<> F>
  bool TimePass(TDur dur, TErr err, F f)
  {
    const auto t_begin = std::chrono::steady_clock::now();
    f();
    const auto t_end  = std::chrono::steady_clock::now();
    const auto t_used = t_end - t_begin;

    return t_used <= dur + err and t_used >= dur - err;
  }

  template <class TDur, class TErr, concepts::ReturnVoidCoroutine<> F>
  co::Task<bool> TimePass(TDur dur, TErr err, F f)
  {
    const auto t_begin = std::chrono::steady_clock::now();
    co_await f();
    const auto t_end  = std::chrono::steady_clock::now();
    const auto t_used = t_end - t_begin;

    co_return t_used <= dur + err and t_used >= dur - err;
  }

  template <class TDur, concepts::ReturnVoidFunction<> F>
  bool TimePass(TDur dur, F f)
  {
    return TimePass(dur, std::chrono::milliseconds(1), std::move(f));
  }

  template <class TDur, concepts::ReturnVoidCoroutine<> F>
  co::Task<bool> TimePass(TDur dur, F f)
  {
    co_return co_await TimePass(dur, std::chrono::milliseconds(1), std::move(f));
  }

 private:
  // 重定向标准输出到这里来，用于日志内容断言分析
  std::stringstream output_buffer_;

  // 记录原来 std::cout 的输出缓存区
  std::streambuf* old_cout_buffer_ptr = nullptr;
};
}  // namespace aimrte::test
