// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/core/core.h"
#include "./details/service_proxy_builder.h"

namespace aimrte::ctx::init
{
/**
 * @brief 注册指定的信道资源的消息回调，该回调发生在原生通信系统的回调中。
 * @param ch       信道资源标识符
 * @param callback 回调函数或协程，参数为 std::shared_ptr<T> 或 const T&，
 *                 将在原生通信的回调中执行，请勿编写过重的内容。
 */
template <class T, core::concepts::SupportedSubscriber<T> TCallback>
void SubscribeInline(const res::Channel<T>& ch, TCallback callback, AIMRTE(src(loc)))
{
  core::details::ExpectContext(loc)->sub(loc).SubscribeInline(ch, std::move(callback));
}

/**
 * @brief 注册指定服务资源的服务处理回调，该回调发生在原生通信系统的回调中。
 * @tparam Q 请求数据类型
 * @tparam P 响应数据类型
 * @param srv     服务资源标识符
 * @param server  服务处理回调函数或协程，参数为 (rpc::ContextRef, const Q &, P &) 或
 *                (const Q &, P &)，返回 rpc::Status.
 *                该处理器将在原生通信的回调中执行，请勿编写过重的内容。
 */
template <class Q, class P, core::concepts::SupportedServer<Q, P> TServer>
void ServeInline(
  const res::Service<Q, P>& srv, TServer server, AIMRTE(src(loc)))
{
  core::details::ExpectContext(loc)->srv(loc).ServeInline(srv, std::move(server));
}

/**
 * @brief 取出指定执行器上下文，以完成在该执行器上的操作（监听、调度协程）。
 * @param res 执行器资源标识符
 */
[[nodiscard]] core::Context::OpExe exe(const res::Executor& res, AIMRTE(src(loc)));

[[nodiscard]] core::Context::OpExe exe(res::Executor&& res, AIMRTE(src(loc)));

/**
 * @brief 辅助构建一个 rpc proxy
 * @tparam T 由 AimRT 生成的 rpc proxy 类型
 * @return rpc proxy 构建器，可以查看 @ref core::details::ServiceProxyBuilder 以获知所有信息补充接口。
 *
 * @code
 *  std::shared_ptr<T> my_proxy_ptr =
 *    ctx::BuildClient<MyProxy>()
 *    .RegisterTimeCostFilter()
 *    .Make();
 * @endcode
 */
template <std::derived_from<aimrt::rpc::ProxyBase> T>
[[nodiscard]] auto BuildClient(AIMRTE(src(loc)))
{
  return details::ServiceProxyBuilder<T>(core::details::ExpectContext(loc));
}

/**
 * @brief 取出上下文指针
 */
[[nodiscard]] std::shared_ptr<core::Context> GetCorePtr(AIMRTE(src(loc)));
}  // namespace aimrte::ctx::init
