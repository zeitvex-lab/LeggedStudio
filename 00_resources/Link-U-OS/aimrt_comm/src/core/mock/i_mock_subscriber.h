// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/res/res.h"
#include <functional>

namespace aimrte::core
{
template <class T>
class IMockSubscriber
{
 public:
  /**
   * @return 本订阅通道的名称
   */
  [[nodiscard]] const std::string& GetResourceName() const
  {
    return res_.GetName();
  }

  /**
   * @brief 饲喂数据给被测的订阅者
   */
  void Feed(T msg)
  {
    if (cb_ == nullptr) {
      OnNullSubscriberError();
      return;
    }

    cb_(std::move(msg));
  }

  void FeedAsync(T msg)
  {
    if (async_cb_ == nullptr) {
      OnNullSubscriberError();
      return;
    }

    async_cb_(std::move(msg), std::bind(&IMockSubscriber::AnalyzeAsync, this));
  }

  virtual ~IMockSubscriber() = default;

 protected:
  /**
   * @brief 处理订阅者未设置的错误
   */
  virtual void OnNullSubscriberError() = 0;

  /**
   * @brief 并发测试时，用户回调结束后调用的函数，由子类实现一些收敛与统计工作
   */
  virtual void AnalyzeAsync() = 0;

 private:
  friend class Context;

  // 由 Context 设置的被测回调函数，
  // 以及可并发的被测回调函数，最终收敛逻辑，由子类实现
  std::function<void(T)> cb_;

  using AnalyzeCaller = std::function<void()>;

  std::function<void(T, AnalyzeCaller)> async_cb_;

  // 由 Context 设置
  res::Channel<T> res_;
};
}  // namespace aimrte::core
