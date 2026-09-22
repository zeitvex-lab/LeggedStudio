// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

namespace aimrte::core
{
class Context::OpSub : public OpBase
{
 public:
  using OpBase::OpBase;

  /**
   * @brief 初始化指定通信类型与话题名称的订阅信道，并返回它的资源标识符。
   * @tparam T AimRT 支持的通信类型
   * @param topic_name 话题名称
   * @return 信道资源标识符，将用于后续注册回调。
   */
  template <concepts::DirectlySupportedType T>
  [[nodiscard]] res::Channel<T> Init(const std::string_view& topic_name);

  /**
   * @brief 在给定通信类型适配器的情况下，初始化指定用户类型与话题名称的订阅信道，
   *        并返回它的资源标识符。
   * @tparam T          用户自定义类型
   * @tparam TConverter 用于转换用户类型到通信类型的转化器，其中定义了通信类型
   * @param topic_name  话题名称
   * @return 信道资源标识符，将用于后续注册回调。
   */
  template <class T, concepts::ByConverter TConverter>
  [[nodiscard]] res::Channel<T> Init(const std::string_view& topic_name);

  /**
   * @brief 初始化一个被测的订阅通道资源
   */
  template <class T>
  res::Channel<T> InitMock(const std::string_view& topic_name, IMockSubscriber<T>& mocker);

  /**
   * @brief 注册指定的信道资源的消息回调，该回调发生在原生通信系统的回调中。
   * @param ch       信道资源标识符
   * @param callback 回调函数或协程，参数为 std::shared_ptr<T> 或 const T&，
   *                 将在原生通信的回调中执行，请勿编写过重的内容。
   */
  template <class T, concepts::SupportedSubscriber<T> TCallback>
  void SubscribeInline(const res::Channel<T>& ch, TCallback callback);

 private:
  /**
   * @brief 基础的 channel sub 初始化过程，原生的 sub ref 将被初始化，发布类型 TRaw 将被注册。
   * 其余上下文需要由调用者进一步完善。
   * @tparam T 使用时的类型
   * @tparam TRaw 用于通信的类型。
   * @param topic_name 信道话题名称
   * @return 新的 channel 资源描述符，以及初始化了部分内容的信道上下文。
   */
  template <class T, concepts::DirectlySupportedType TRaw = T>
  std::pair<res::Channel<T>, ChannelContext&> DoInit(const std::string_view& topic_name);

  /**
   * @brief 向原生订阅器，注册回调函数，将区分是否在 exectuor 上，设置不同的过程。
   * @tparam T AimRT 支持的通信类型
   * @tparam F 回调函数或协程
   * @param subscriber   原生注册器接口
   * @param ctx_weak_ptr 本模块的上下文，将用于回调函数执行前的环境准备
   * @param callback     用户的回调协程
   * @param exe          可能的执行器资源，若资源不可用，将设置 inline 模式回调。
   * @return 是否注册成功
   */
  template <concepts::DirectlySupportedType T, concepts::SubscriberCoroutine<T> F>
  static bool RawSubscribe(aimrt::channel::SubscriberRef subscriber, std::weak_ptr<Context> ctx_weak_ptr, res::Executor exe, F callback);

  /**
   * @return 注册回调的函数
   */
  template <concepts::DirectlySupportedType T>
  static SubscribeFunction<T> CreateSubscribeFunction();

  /**
   * @return 注册先转换类型、然后进行回调的函数
   */
  template <class T, concepts::ByConverter TConverter>
  static SubscribeFunction<T> CreateSubscribeFunction();

  /**
   * @brief 统一的 channel 注册订阅过程。
   */
  template <class T, concepts::SupportedSubscriber<T> TCallback>
  void DoSubscribe(const res::Channel<T>& ch, TCallback callback, res::Executor exe);

  /**
   * @brief 标准化订阅函数为 co::Task<void>(std::shared_ptr<const T>)
   */
  template <class T, concepts::SupportedSubscriber<T> F>
  constexpr auto StandardizeSubscriber(F cb);

  friend class OpExe;
};
}  // namespace aimrte::core
