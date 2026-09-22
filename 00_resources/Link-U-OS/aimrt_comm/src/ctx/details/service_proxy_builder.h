// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/interface/aimrt_module_cpp_interface/rpc/rpc_handle.h"
#include "src/core/core.h"
#include <list>

namespace aimrte::ctx::details
{
/**
 * @brief 将给定的消息转换为人类可读的字符串，用于日志记录。
 * @param cfg 通信上下文，用于识别序列化方式。
 * @param msg_ptr 消息指针
 * @return 可读的字符串，若序列化方式未知，将为空。
 */
std::string ToHumanReadable(const aimrt::rpc::ContextRef& cfg, const void* msg_ptr);

/**
 * @brief 辅助用户创建并初始化指定的 AimRT service proxy 对象。
 */
template <std::derived_from<aimrt::rpc::ProxyBase> T>
class ServiceProxyBuilder
{
 public:
  explicit ServiceProxyBuilder(std::shared_ptr<core::Context> ctx_ptr)
      : ctx_ptr_(std::move(ctx_ptr))
  {
  }

  AIMRTE_DECLARE_FORBIDDEN_COPY_MOVE(ServiceProxyBuilder);

 public:
  /**
   * @brief 注册一个 rpc filter，用于服务调用前后做一些分析处理。
   */
  template <std::constructible_from<aimrt::rpc::CoRpcFilter> F>
  ServiceProxyBuilder& RegisterFilter(F&& f)
  {
    filters_.emplace_back(std::forward<F>(f));
    return *this;
  }

  /**
   * @brief 注册统计调用时间的 rpc filter
   */
  ServiceProxyBuilder& RegisterTimeCostFilter()
  {
    return RegisterFilter(
      [weak_ctx_ptr = ctx_ptr_->weak_from_this()](const aimrt::rpc::ContextRef ctx, const void* req_ptr, void* rsp_ptr, const aimrt::rpc::CoRpcHandle& next)
        -> aimrt::co::Task<aimrt::rpc::Status> {
        const auto begin_time           = std::chrono::steady_clock::now();
        const aimrt::rpc::Status status = co_await next(ctx, req_ptr, rsp_ptr);
        const auto end_time             = std::chrono::steady_clock::now();

        if (const std::shared_ptr ctx_ptr = weak_ctx_ptr.lock(); ctx_ptr != nullptr)
          ctx_ptr->log().Debug(
            "Svr rpc time cost {} us",
            std::chrono::duration_cast<std::chrono::microseconds>(end_time - begin_time).count());

        co_return status;
      });
  }

  /**
   * @brief 注册在调用前后，通过日志记录输入、输出数据的 rpc filter
   */
  ServiceProxyBuilder& RegisterIOLogFilter()
  {
    return RegisterFilter(
      [weak_ctx_ptr = ctx_ptr_->weak_from_this()](const aimrt::rpc::ContextRef ctx, const void* req_ptr, void* rsp_ptr, const aimrt::rpc::CoRpcHandle& next)
        -> aimrt::co::Task<aimrt::rpc::Status> {
        if (const std::shared_ptr ctx_ptr = weak_ctx_ptr.lock(); ctx_ptr != nullptr)
          ctx_ptr->log().Debug("Svr get new rpc call. req: {}", ToHumanReadable(ctx, req_ptr));

        const aimrt::rpc::Status status = co_await next(ctx, req_ptr, rsp_ptr);

        if (const std::shared_ptr ctx_ptr = weak_ctx_ptr.lock(); ctx_ptr != nullptr)
          ctx_ptr->log().Debug("Svr handle rpc completed, status: {}, rsp: {}", status.ToString(), ToHumanReadable(ctx, rsp_ptr));

        co_return status;
      });
  }

  /**
   * @brief 根据 builder 所有级联调用设置的构建参数，最终构建 rpc proxy 对象
   * @return 指定类型的
   */
  std::shared_ptr<T> Make(const std::source_location call_loc = std::source_location::current())
  {
    if (ctx_ptr_ == nullptr)
      panic(call_loc).wtf("You CANNOT call ServiceProxyBuilder::Make() twice on the same object !");

    const aimrt::rpc::RpcHandleRef rpc_handle = core::Context::GetRawRef(*ctx_ptr_).GetRpcHandle();
    ctx_ptr_->check(rpc_handle, call_loc).ErrorThrow("Get rpc handle failed.");

    const bool register_status = aimrt::rpc::RegisterClientFunc<T>(rpc_handle);
    ctx_ptr_->check(register_status, call_loc).ErrorThrow("Register client failed.");

    auto proxy_ptr = std::make_shared<T>(rpc_handle);

    for (aimrt::rpc::CoRpcFilter& f : filters_)
      proxy_ptr->RegisterFilter(std::move(f));

    // 让本对象不再可用
    ctx_ptr_ = nullptr;
    filters_ = {};

    // 返回结果
    return proxy_ptr;
  }

 private:
  // 用于创建该 service proxy 对象的上下文信息
  std::shared_ptr<core::Context> ctx_ptr_;

  // 在构建过程中暂存的 rpc filter
  std::list<aimrt::rpc::CoRpcFilter> filters_;
};
}  // namespace aimrte::ctx::details
