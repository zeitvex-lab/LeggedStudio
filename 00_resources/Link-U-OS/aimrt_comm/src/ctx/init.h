// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/core/core.h"
#include "./res.h"

/**
 * @brief 仅用于初始化阶段的上下文操作接口
 */
namespace aimrte::ctx::init
{
/**
 * @brief 根据指定名称，初始化执行器，并返回它的资源标识符。
 *        若指定名称的执行器不存在时，将报错。
 * @param name 执行器名称
 * @return 执行器资源标识符，将在使用执行器时使用。
 */
[[nodiscard]] ctx::Executor Executor(const std::string_view& name, AIMRTE(src(loc)));

inline ctx::Executor& Executor(ctx::Executor& res, const std::string_view& name, AIMRTE(src(loc)))
{
  return res = Executor(name, loc);
}

/**
 * @brief 根据指定名称，初始化一个线程安全的执行器，并返回它的资源标识符。
 *        若指定名称的执行器不存在、或者它不是线程安全时，将报错。
 * @param name 执行器名称
 * @return 执行器资源标识符，将在使用执行器时使用。
 */
[[nodiscard]] ctx::Executor ThreadSafeExecutor(const std::string_view& name, AIMRTE(src(loc)));

inline ctx::Executor& ThreadSafeExecutor(ctx::Executor& res, const std::string_view& name, AIMRTE(src(loc)))
{
  return res = ThreadSafeExecutor(name, loc);
}

/**
 * @brief 初始化指定通信类型与话题名称的发布信道，并返回它的资源标识符。
 * @tparam T AimRT 支持的通信类型
 * @param topic_name 话题名称
 * @return 信道资源标识符，将用于后续发布数据
 */
template <core::concepts::DirectlySupportedType T>
[[nodiscard]] ctx::Publisher<T> Publisher(const std::string_view& topic_name, AIMRTE(src(loc)))
{
  return {core::details::ExpectContext(loc)->pub(loc).Init<T>(topic_name)};
}

template <core::concepts::DirectlySupportedType T>
ctx::Publisher<T>& Publisher(ctx::Publisher<T>& res, const std::string_view& topic_name, AIMRTE(src(loc)))
{
  return res = Publisher<T>(topic_name, loc);
}

/**
 * @brief 在给定通信类型适配器的情况下，初始化指定用户类型与话题名称的发布信道，
 *        并返回它的资源标识符。
 * @tparam T          用户自定义类型
 * @tparam TConverter 用于转换用户类型到通信类型的转化器，其中定义了通信类型
 * @param topic_name  话题名称
 * @return 信道资源标识符，将用于后续发布数据。
 */
template <class T, core::concepts::ByConverter TConverter>
[[nodiscard]] ctx::Publisher<T> Publisher(const std::string_view& topic_name, AIMRTE(src(loc)))
{
  return {core::details::ExpectContext(loc)->pub(loc).Init<T, TConverter>(topic_name)};
}

template <class T, core::concepts::ByConverter TConverter>
ctx::Publisher<T>& Publisher(ctx::Publisher<T>& res, const std::string_view& topic_name, AIMRTE(src(loc)))
{
  return res = Publisher<T, TConverter>(topic_name, loc);
}

/**
 * @brief 初始化指定通信类型与话题名称的订阅信道，并返回它的资源标识符。
 * @tparam T AimRT 支持的通信类型
 * @param topic_name 话题名称
 * @return 信道资源标识符，将用于后续注册回调。
 */
template <core::concepts::DirectlySupportedType T>
[[nodiscard]] ctx::Subscriber<T> Subscriber(const std::string_view& topic_name, AIMRTE(src(loc)))
{
  return {core::details::ExpectContext(loc)->sub(loc).Init<T>(topic_name)};
}

template <core::concepts::DirectlySupportedType T>
ctx::Subscriber<T>& Subscriber(ctx::Subscriber<T>& res, const std::string_view& topic_name, AIMRTE(src(loc)))
{
  return res = Subscriber<T>(topic_name, loc);
}

/**
 * @brief 在给定通信类型适配器的情况下，初始化指定用户类型与话题名称的订阅信道，
 *        并返回它的资源标识符。
 * @tparam T          用户自定义类型
 * @tparam TConverter 用于转换用户类型到通信类型的转化器，其中定义了通信类型
 * @param topic_name  话题名称
 * @return 信道资源标识符，将用于后续注册回调。
 */
template <class T, core::concepts::ByConverter TConverter>
[[nodiscard]] ctx::Subscriber<T> Subscriber(const std::string_view& topic_name, AIMRTE(src(loc)))
{
  return {core::details::ExpectContext(loc)->sub(loc).Init<T, TConverter>(topic_name)};
}

template <class T, core::concepts::ByConverter TConverter>
ctx::Subscriber<T>& Subscriber(ctx::Subscriber<T>& res, const std::string_view& topic_name, AIMRTE(src(loc)))
{
  return res = Subscriber<T, TConverter>(topic_name, loc);
}

/**
 * @brief 初始化指定类型的服务调用资源
 * @tparam Q AimRT 支持的请求数据类型
 * @tparam P AimRT 支持的响应数据类型
 * @tparam TSrv 通信需要的额外类型信息
 * @param func_name 方法名称
 * @return 该调用资源的标识符，将用于服务调用
 */
template <core::concepts::DirectlySupportedType Q, core::concepts::DirectlySupportedType P, class TSrv = void>
[[nodiscard]] ctx::Client<Q, P> ClientFunc(const std::string_view& func_name, AIMRTE(src(loc)))
{
  return {core::details::ExpectContext(loc)->cli(loc).InitFunc<Q, P, TSrv>(func_name)};
}

template <core::concepts::DirectlySupportedType Q, core::concepts::DirectlySupportedType P, class TSrv = void>
ctx::Client<Q, P>& ClientFunc(
  ctx::Client<Q, P>& res, const std::string_view& func_name, AIMRTE(src(loc)))
{
  return res = ClientFunc<Q, P, TSrv>(func_name, loc);
}

/**
 * @brief 初始化指定类型的服务调用资源
 * @tparam Q 用于自定义的请求数据类型
 * @tparam P 用于自定义的响应数据类型
 * @tparam QCvt 用于转换用户请求数据类型的类型转换器
 * @tparam PCvt 用于转换用户请求数据类型的类型转换器
 * @tparam TSrv 通信需要的额外类型信息
 * @param func_name 方法名称
 * @return 该调用资源的标识符，将用于服务调用
 */
template <class Q, class P, core::concepts::ByConverter QCvt, core::concepts::ByConverter PCvt, class TSrv = void>
[[nodiscard]] ctx::Client<Q, P> ClientFunc(const std::string_view& func_name, AIMRTE(src(loc)))
{
  return {core::details::ExpectContext(loc)->cli(loc).InitFunc<Q, P, QCvt, PCvt, TSrv>(func_name)};
}

template <class Q, class P, core::concepts::ByConverter QCvt, core::concepts::ByConverter PCvt, class TSrv = void>
ctx::Client<Q, P>& ClientFunc(
  ctx::Client<Q, P>& res, const std::string_view& func_name, AIMRTE(src(loc)))
{
  return res = ClientFunc<Q, P, QCvt, PCvt, TSrv>(func_name, loc);
}

/**
 * @brief 初始化指定类型的服务资源
 * @tparam Q AimRT 支持的请求数据类型
 * @tparam P AimRT 支持的响应数据类型
 * @tparam TSrv 通信需要的额外类型信息
 * @param func_name 方法名称
 * @return 该调用资源的标识符，将用于注册服务回调函数
 */
template <core::concepts::DirectlySupportedType Q, core::concepts::DirectlySupportedType P, class TSrv = void>
[[nodiscard]] ctx::Server<Q, P> ServerFunc(const std::string_view& func_name, AIMRTE(src(loc)))
{
  return {core::details::ExpectContext(loc)->srv(loc).InitFunc<Q, P, TSrv>(func_name)};
}

template <core::concepts::DirectlySupportedType Q, core::concepts::DirectlySupportedType P, class TSrv = void>
ctx::Server<Q, P>& ServerFunc(ctx::Server<Q, P>& res, const std::string_view& func_name, AIMRTE(src(loc)))
{
  return res = ServerFunc<Q, P, TSrv>(func_name, loc);
}

/**
 * @brief 初始化指定类型的服务资源
 * @tparam Q 用于自定义的请求数据类型
 * @tparam P 用于自定义的响应数据类型
 * @tparam QCvt 用于转换用户请求数据类型的类型转换器
 * @tparam PCvt 用于转换用户请求数据类型的类型转换器
 * @tparam TSrv 通信需要的额外类型信息
 * @param func_name 方法名称
 * @return 该调用资源的标识符
 */
template <class Q, class P, core::concepts::ByConverter QCvt, core::concepts::ByConverter PCvt, class TSrv = void>
[[nodiscard]] ctx::Server<Q, P> ServerFunc(const std::string_view& func_name, AIMRTE(src(loc)))
{
  return {core::details::ExpectContext(loc)->srv(loc).InitFunc<Q, P, QCvt, PCvt, TSrv>(func_name)};
}

template <class Q, class P, core::concepts::ByConverter QCvt, core::concepts::ByConverter PCvt, class TSrv = void>
ctx::Server<Q, P>& ServerFunc(ctx::Server<Q, P>& res, const std::string_view& func_name, AIMRTE(src(loc)))
{
  return res = ServerFunc<Q, P, QCvt, PCvt, TSrv>(func_name, loc);
}

/**
 * @brief 使用指定的请求响应数据类型，初始化新的客户端资源，用于 Call() 函数发起远程调用。
 * 需要指定 AimRT 原生 service proxy 接口，来赋能该操作。
 * @note 该函数一般只在 AimRT service proxy 对象上使用。
 * @tparam Q 请求数据类型
 * @tparam P 响应数据类型
 * @param service_name 一个服务过程/方法的名称，目前仅用于日志记录。
 * @param client AimRT service proxy 的某一个方法接口，形如
 *               aimrt::co::Task<aimrt::rpc::Status>(aimrt::rpc::ContextRef, const Q &, P &)
 * @return 客户端资源标识符，将用于用户发起调用。
 */
template <core::concepts::DirectlySupportedType Q, core::concepts::DirectlySupportedType P, core::concepts::RawClient<Q, P> TClient>
[[nodiscard]] ctx::Client<Q, P> Client(const std::string_view& service_name, TClient client, AIMRTE(src(loc)))
{
  return {core::details::ExpectContext(loc)->cli(loc).Init<Q, P>(service_name, std::move(client))};
}

template <core::concepts::DirectlySupportedType Q, core::concepts::DirectlySupportedType P, core::concepts::RawClient<Q, P> TClient>
ctx::Client<Q, P>& Client(
  ctx::Client<Q, P>& res, const std::string_view& service_name, TClient client, AIMRTE(src(loc)))
{
  return res = Client<Q, P, TClient>(service_name, std::move(client), loc);
}

/**
 * @brief 使用指定的请求响应数据类型，初始化新的服务端资源，用于 Serve() 函数绑定用户服务处理回调，
 * 或在原生通信模型中，通过 Serving() 函数执行用户的处理回调。
 * @note 该函数一般只在 AimRT service impl 子类中使用。
 * @tparam Q 请求数据类型
 * @tparam P 响应数据类型
 * @param service_name 一个服务过程/方法的名称，目前仅用于日志记录。
 * @return 服务端资源标识符，将用于后续绑定用户的处理函数、或由原生通信模型，驱动处理回调的调用。
 */
template <core::concepts::DirectlySupportedType Q, core::concepts::DirectlySupportedType P>
[[nodiscard]] ctx::Server<Q, P> Server(const std::string_view& service_name, AIMRTE(src(loc)))
{
  return {core::details::ExpectContext(loc)->srv(loc).Init<Q, P>(service_name)};
}

template <core::concepts::DirectlySupportedType Q, core::concepts::DirectlySupportedType P>
ctx::Server<Q, P>& Server(ctx::Server<Q, P>& res, const std::string_view& service_name, AIMRTE(src(loc)))
{
  return res = Server<Q, P>(service_name, loc);
}

/**
 * @brief 将已有的服务资源处理的类型，转换为另外一套类型。
 * @tparam Q 新的请求数据类型
 * @tparam P 新的响应数据类型
 * @tparam QRaw 原始请求数据类型
 * @tparam PRaw 原始响应数据类型
 * @param srv 有效的服务资源，转换之后将失效
 * @return 新的服务资源
 */
template <class Q, class P, core::concepts::DirectlySupportedType QRaw, core::concepts::DirectlySupportedType PRaw>
[[nodiscard]] ctx::Client<Q, P> Service(ctx::Client<QRaw, PRaw>&& srv, AIMRTE(src(loc)))
{
  return {core::details::ExpectContext(loc)->cli(loc).InitService<Q, P, QRaw, PRaw>(std::move(srv))};
}

template <class Q, class P, core::concepts::DirectlySupportedType QRaw, core::concepts::DirectlySupportedType PRaw>
ctx::Client<Q, P>& Service(ctx::Client<Q, P>& res, res::Service<QRaw, PRaw>&& srv, AIMRTE(src(loc)))
{
  return res = Service<Q, P, QRaw, PRaw>(std::move(srv), loc);
}

template <class Q, class P, core::concepts::DirectlySupportedType QRaw, core::concepts::DirectlySupportedType PRaw>
[[nodiscard]] ctx::Server<Q, P> Service(ctx::Server<QRaw, PRaw>&& srv, AIMRTE(src(loc)))
{
  return {core::details::ExpectContext(loc)->srv(loc).InitService<Q, P, QRaw, PRaw>(std::move(srv))};
}

template <class Q, class P, core::concepts::DirectlySupportedType QRaw, core::concepts::DirectlySupportedType PRaw>
ctx::Server<Q, P>& Service(ctx::Server<Q, P>& res, res::Service<QRaw, PRaw>&& srv, AIMRTE(src(loc)))
{
  return res = Service<Q, P, QRaw, PRaw>(std::move(srv), loc);
}
}  // namespace aimrte::ctx::init
