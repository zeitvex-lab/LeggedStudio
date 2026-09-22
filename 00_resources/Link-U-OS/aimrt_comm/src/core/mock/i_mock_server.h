// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/res/res.h"
#include "src/trait/trait.h"
#include <functional>

namespace aimrte::core
{
template <class Q, class P>
class IMockServer
{
 public:
  /**
   * @return 本订阅通道的名称
   */
  [[nodiscard]] const std::string &GetResourceName() const
  {
    return res_.GetName();
  }

  /**
   * @brief 饲喂被测服务端的服务过程，并分析它的响应数据与响应状态
   */
  void Feed(const Q &q)
  {
    static const aimrt::rpc::ContextRef rpc_ctx{};
    Feed(rpc_ctx, q);
  }

  /**
   * @brief 饲喂被测服务端的服务过程，并分析它的响应数据与响应状态。
   * @param rpc_ctx 指定的 rpc 参数
   */
  void Feed(const aimrt::rpc::ContextRef &rpc_ctx, const Q &q)
  {
    if (func_ == nullptr) {
      OnNullServerError();
      return;
    }

    P p;
    const aimrt::rpc::Status ret = func_(rpc_ctx, q, p);
    Analyze(rpc_ctx, q, p, ret);
  }

  void FeedAsync(Q q)
  {
    static const aimrt::rpc::ContextRef rpc_ctx{};
    FeedAsync(rpc_ctx, std::move(q));
  }

  void FeedAsync(aimrt::rpc::ContextRef rpc_ctx, Q q)
  {
    if (async_func_ == nullptr) {
      OnNullServerError();
      return;
    }

    async_func_(std::move(rpc_ctx), std::move(q), trait::bind_<4>(&IMockServer::AnalyzeAsync, this));
  }

  virtual ~IMockServer() = default;

 protected:
  /**
   * @brief 处理服务函数未设置的错误
   */
  virtual void OnNullServerError() = 0;

  /**
   * @brief 分析服务端的响应数据与状态是否合理。
   * @param rpc_ctx 测试端设置的 rpc 参数
   * @param q       测试端饲喂的假请求数据
   * @param p       被测服务端回传的响应数据
   * @param ret     被测服务端回传的 rpc 状态
   */
  virtual void Analyze(
    const aimrt::rpc::ContextRef &rpc_ctx, const Q &q, const P &p, const aimrt::rpc::Status &ret) = 0;

  /**
   * @brief 分析服务端的响应数据与状态是否合理，该函数用于 FeedAsync() 触发的并发回传数据分析
   * @param rpc_ctx 测试端设置的 rpc 参数
   * @param q       测试端饲喂的假请求数据
   * @param p       被测服务端回传的响应数据
   * @param ret     被测服务端回传的 rpc 状态
   */
  virtual void AnalyzeAsync(
    const aimrt::rpc::ContextRef &rpc_ctx, const Q &q, const P &p, const aimrt::rpc::Status &ret) = 0;

 private:
  friend class Context;

  // 由 Context 设置的被测服务函数，
  // 以及以及可并发的被测服务函数，最终收敛逻辑，由子类实现
  std::function<aimrt::rpc::Status(const aimrt::rpc::ContextRef &rpc_ctx, const Q &q, P &p)> func_;

  using AnalyzeCaller =
    std::function<void(const aimrt::rpc::ContextRef &, const Q &, const P &, const aimrt::rpc::Status &)>;

  std::function<void(aimrt::rpc::ContextRef, Q, AnalyzeCaller)> async_func_;

  // 由 Context 设置
  res::Service<Q, P> res_;
};
}  // namespace aimrte::core
