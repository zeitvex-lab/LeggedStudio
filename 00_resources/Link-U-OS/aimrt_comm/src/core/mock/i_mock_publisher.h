// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/res/res.h"
#include <memory>

namespace aimrte::core
{
template <class T>
class IMockPublisher
{
 public:
  /**
   * @return 本发布器通道的名称
   */
  [[nodiscard]] const std::string& GetResourceName() const
  {
    return res_.GetName();
  }

  virtual ~IMockPublisher() = default;

 protected:
  /**
   * @brief 分析被测的发布器发布的消息是否合理。
   */
  virtual void Analyze(const T& msg) = 0;

  virtual void Analyze(std::shared_ptr<const T> msg_ptr)
  {
    Analyze(*msg_ptr);
  }

 private:
  friend class Context;

  // 由 Context 设置
  res::Channel<T> res_;
};
}  // namespace aimrte::core
