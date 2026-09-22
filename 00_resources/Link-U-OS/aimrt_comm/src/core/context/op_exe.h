// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

namespace aimrte::core
{
/**
 * @brief 基于指定执行器上下文的操作接口，仅临时使用
 */
class Context::OpExe : public OpBase
{
 public:
  using OpBase::OpBase;

  /**
   * @brief 在当前执行器上，注册指定的信道资源的消息回调。
   * @param ch       信道资源标识符
   * @param callback 回调函数或协程，参数为 std::shared_ptr<T> 或 const T&
   */
  template <class T, concepts::SupportedSubscriber<T> TCallback>
  OpExe& Subscribe(const res::Channel<T>& ch, TCallback callback);

  /**
   * @brief 在当前执行器上，注册指定服务资源的服务处理回调。
   * @tparam Q 请求数据类型
   * @tparam P 响应数据类型
   * @param srv    服务资源标识符
   * @param server 服务处理回调函数或协程，参数为 (rpc::ContextRef, const Q &, P &) 或
   *               (const Q &, P &)，返回 rpc::Status.
   */
  template <class Q, class P, concepts::SupportedServer<Q, P> TServer>
  OpExe& Serve(const res::Service<Q, P>& srv, TServer server);

 public:
  /**
   * @brief 在本执行器中，执行给定函数或协程
   */
  template <class F>
    requires concepts::SupportedInvoker<F>
  OpExe& Post(F f);

  /**
   * @brief 在本执行器中，执行给定函数或协程，
   *        但使用用户提供的异步管理器对该任务进行生命周期管理。
   */
  template <class F>
    requires concepts::SupportedInvoker<F>
  OpExe& Post(aimrt::co::AsyncScope& scope, F f);

  /**
   * @brief 在本执行器中，原地执行完给定函数或协程
   */
  template <class F>
    requires concepts::SupportedInvoker<F>
  OpExe& Inline(F&& f);

 private:
  friend class Context;

  OpExe(Context& ctx, const res::Executor& res, std::source_location loc);
  OpExe(Context& ctx, res::Executor&& res, std::source_location loc);

  /**
   * @brief 检查给定的资源描述是否匹配当前的上下文，并从中取出执行器
   */
  void CheckAndInit();

  /**
   * @brief 标准化供执行器执行的任务为 co::Task<void>()
   */
  template <concepts::SupportedInvoker F>
  constexpr auto StandardizeInvoker(F&& cb);

 public:
  /**
   * @return 执行器原生句柄
   */
  static aimrt::executor::ExecutorRef GetRawRef(const OpExe& ref);

 private:
  // 执行器的资源临时对象，若用户导出执行器接口，使用了临时资源对象时，我们需要暂存它。
  // 我们不会直接使用它。
  res::Executor temp_res_;

  // 执行器的资源描述
  const res::Executor& res_;

  // 执行器
  aimrt::executor::ExecutorRef executor_;
};
}  // namespace aimrte::core
