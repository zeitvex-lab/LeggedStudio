// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/interface/aimrt_module_cpp_interface/rpc/rpc_status.h"
#include "src/res/res.h"
#include <memory>

namespace aimrte::core
{
template <class Q, class P>
class IMockClient
{
 public:
  /**
   * @return 本发布器通道的名称
   */
  [[nodiscard]] const std::string& GetResourceName() const
  {
    return res_.GetName();
  }

  virtual ~IMockClient() = default;

 protected:
  /**
   * @brief 分析被测的客户端发起的 rpc 请求数据是否合理，并设置响应数据与 rpc 状态。
   * @param rpc_ctx 此次 rpc 的参数
   * @param q       被测客户端发起的请求数据
   * @param p       需要由子类回传的假响应数据
   * @param ret     需要由子类回传的假 rpc 状态
   */
  virtual void AnalyzeAndFeedback(
    const aimrt::rpc::ContextRef& rpc_ctx, const Q& q, P& p, aimrt::rpc::Status& ret) = 0;

 private:
  friend class Context;

  // 由 Context 设置
  res::Service<Q, P> res_;
};
}  // namespace aimrte::core
