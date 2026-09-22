// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/interface/aimrt_module_protobuf_interface/channel/protobuf_channel.h"
#include "src/interface/aimrt_module_ros2_interface/channel/ros2_channel.h"
#include "src/concepts/concepts.h"
#include "src/convert/convert.h"
#include <concepts>

#include "../coroutine.h"

namespace aimrte::core::concepts
{
/**
 * @brief 判断一个函数签名是否符合预期。仅为一个别名。
 */
template <class F, class TSignature>
concept Function = ::aimrte::concepts::Function<F, TSignature>;

/**
 * @brief 判断一个类型，是否是指定类型的消息回调函数
 */
template <class F, class T>
concept SubscriberFunction = Function<F, void(std::shared_ptr<const T>)>;

/**
 * @brief 判断一个类型，是否是指定类型的消息回调协程。
 * 这是我们内部使用的统一形态。
 */
template <class F, class T>
concept SubscriberCoroutine =
  Function<F, co::Task<void>(std::shared_ptr<const T>)>;

/**
 * @brief 判断一个类型，是否是指定类型的 AimRT 原生回调协程
 * @deprecated 后续不再支持 AimRT 原生协程
 */
template <class F, class T>
concept SubscriberRawCoroutine =
  Function<F, aimrt::co::Task<void>(std::shared_ptr<const T>)>;

/**
 * @brief 判断一个类型，是否是指定类型的消息回调函数，但其参数是解引用后的类型
 */
template <class F, class T>
concept SubscriberFunctionDeref = Function<F, void(const T &)>;

/**
 * @brief 判断一个类型，是否是指定类型的消息回调协程，但其参数是解引用后的类型
 */
template <class F, class T>
concept SubscriberCoroutineDeref =
  Function<F, co::Task<void>(const T &)>;
/**
 * @brief 判断一个类型，是否是指定类型的 AimRT 原生回调协程，但其参数是解引用后的类型
 * @deprecated 后续不再支持 AimRT 原生协程
 */
template <class F, class T>
concept SubscriberRawCoroutineDeref =
  Function<F, aimrt::co::Task<void>(const T &)>;

/**
 * @brief 判断一个类型，是否是我们支持的回调函数类型
 */
template <class F, class T>
concept SupportedSubscriber =
  SubscriberFunction<F, T> or
  SubscriberCoroutine<F, T> or
  SubscriberRawCoroutine<F, T> or
  SubscriberFunctionDeref<F, T> or
  SubscriberCoroutineDeref<F, T> or
  SubscriberRawCoroutineDeref<F, T>;

/**
 * @brief 判断一个类型，是否是指定类型的服务处理函数
 */
template <class F, class Q, class P>
concept ServerFunction =
  Function<F, aimrt::rpc::Status(const Q &, P &)>;

/**
 * @brief 判断一个类型，是否是指定类型的服务处理协程
 */
template <class F, class Q, class P>
concept ServerCoroutine =
  Function<F, co::Task<aimrt::rpc::Status>(const Q &, P &)>;

/**
 * @brief 判断一个类型，是否是指定类型的 AimRT 服务处理协程
 * @deprecated 后续不再支持 AimRT 原生协程
 */
template <class F, class Q, class P>
concept ServerRawCoroutine =
  Function<F, aimrt::co::Task<aimrt::rpc::Status>(const Q &, P &)>;

/**
 * @brief 判断一个类型，是否是指定类型的、且携带 rpc 上下文参数的服务处理函数
 */
template <class F, class Q, class P>
concept ServerFunctionWithCtx =
  Function<F, aimrt::rpc::Status(aimrt::rpc::ContextRef, const Q &, P &)>;

/**
 * @brief 判断一个类型，是否是指定类型的、且携带 rpc 上下文的服务处理协程。
 * 这是我们内部使用的统一形态。
 */
template <class F, class Q, class P>
concept ServerCoroutineWithCtx =
  Function<F, co::Task<aimrt::rpc::Status>(aimrt::rpc::ContextRef, const Q &, P &)>;

/**
 * @brief 判断一个类型，是否是指定类型的、且携带 rpc 上下文的 AimRT 服务处理协程
 * @deprecated 后续不再支持 AimRT 原生协程
 */
template <class F, class Q, class P>
concept ServerRawCoroutineWithCtx =
  Function<F, aimrt::co::Task<aimrt::rpc::Status>(aimrt::rpc::ContextRef, const Q &, P &)>;

/**
 * @brief 默认返回 Ok 的普通服务函数
 */
template <class F, class Q, class P>
concept ServerFunctionReturnVoid = Function<F, void(const Q &, P &)>;

/**
 * @brief 默认返回 OK 的服务协程
 */
template <class F, class Q, class P>
concept ServerCoroutineReturnVoid = Function<F, co::Task<void>(const Q &, P &)>;

/**
 * @brief 默认返回 Ok 的普通服务函数，但携带 ctx 参数
 */
template <class F, class Q, class P>
concept ServerFunctionReturnVoidWithCtx = Function<F, void(aimrt::rpc::ContextRef, const Q &, P &)>;

/**
 * @brief 默认返回 OK 的服务协程，但携带 ctx 参数
 */
template <class F, class Q, class P>
concept ServerCoroutineReturnVoidWithCtx = Function<F, co::Task<void>(aimrt::rpc::ContextRef, const Q &, P &)>;

/**
 * @brief 判断一个类型，是否为我们支持的可调用的服务处理类型。
 */
template <class F, class Q, class P>
concept SupportedServer =
  ServerFunction<F, Q, P> or
  ServerCoroutine<F, Q, P> or
  ServerRawCoroutine<F, Q, P> or
  ServerFunctionWithCtx<F, Q, P> or
  ServerCoroutineWithCtx<F, Q, P> or
  ServerRawCoroutineWithCtx<F, Q, P> or
  ServerFunctionReturnVoid<F, Q, P> or
  ServerCoroutineReturnVoid<F, Q, P> or
  ServerFunctionReturnVoidWithCtx<F, Q, P> or
  ServerCoroutineReturnVoidWithCtx<F, Q, P>;

template <class T>
concept RosMessage = rosidl_generator_traits::is_message<T>::value;

template <class T>
concept RosService =
  requires {
    typename T::Request;
    typename T::Response;
    requires RosMessage<typename T::Request>;
    requires RosMessage<typename T::Response>;
  };

template <class T>
concept Protobuf = std::derived_from<T, google::protobuf::Message>;

/**
 * @brief 判断一个类型，是否是 AimRT 直接支持的消息类型
 */
template <class T>
concept DirectlySupportedType = RosMessage<T> or Protobuf<T>;

/**
 * @brief 判断两个类型，是否是同一种 AimRT 直接支持的消息类型
 */
template <class T, class E>
concept SameDirectlySupportedType =
  (RosMessage<T> and RosMessage<E>) or (Protobuf<T> and Protobuf<E>);

/**
 * @brief 判断一个类型，是否是 AimRT 生成的 service proxy 函数
 */
template <class F, class Q, class P>
concept RawClient =
  Function<F, aimrt::co::Task<aimrt::rpc::Status>(aimrt::rpc::ContextRef, const Q &, P &)> and DirectlySupportedType<Q> and DirectlySupportedType<P>;

/**
 * @brief 判断一个函数，是否是能够将指定类型转换为 AimRT 直接支持的消息类型
 */
template <class F, class TCustom>
concept CustomTypeEncoder =
  requires(F f) {
    {
      f(TCustom())
      } -> DirectlySupportedType;
  };

/**
 * @brief 判断一个函数，是否是能够将指定 AimRT 直接支持的消息类型，转换为用户期望的类型
 */
template <class F, class TCustom, class TRaw>
concept CustomTypeDecoder =
  requires(F f) {
    {
      f(TRaw())
      } -> std::same_as<TCustom>;
  } and DirectlySupportedType<TRaw>;

/**
 * @brief 判断给定类型是否是 convert::By<E> 类型
 */
template <class T>
concept ByConverter =
  requires {
    typename T::AnotherType;
    requires std::same_as<T, convert::By<typename T::AnotherType>>;
    requires concepts::DirectlySupportedType<typename T::AnotherType>;
  };
}  // namespace aimrte::core::concepts

namespace aimrte::concepts
{
/**
 * @brief 判断给定的函数是 AimRTe 的协程，且该协程返回 void
 */
template <class F, class... TArgs>
concept ReturnVoidCoroutine =
  requires(F f, TArgs &&...args) {
    {
      f(std::forward<TArgs>(args)...)
      } -> std::same_as<co::Task<void>>;
  };

}  // namespace aimrte::concepts

namespace aimrte::core::concepts
{
/**
 * @brief 判断一个类型，是否是 executor 可执行的函数类型
 */
template <class F>
concept InvokerFunction = ::aimrte::concepts::ReturnVoidFunction<F>;

/**
 * @brief 判断一个类型，是否是 executor 可执行的协程类型
 */
template <class F>
concept InvokerCoroutine = ::aimrte::concepts::ReturnVoidCoroutine<F>;

/**
 * @brief 判断一个类型，是否是 executor 可执行的 AimRT 协程类型
 */
template <class F>
concept InvokerRawCoroutine = Function<F, aimrt::co::Task<void>()>;

/**
 * @brief 判断一个类型，是否是 executor 支持的可执行类型
 */
template <class F>
concept SupportedInvoker =
  InvokerFunction<F> or
  InvokerCoroutine<F> or
  InvokerRawCoroutine<F>;
}  // namespace aimrte::core::concepts
