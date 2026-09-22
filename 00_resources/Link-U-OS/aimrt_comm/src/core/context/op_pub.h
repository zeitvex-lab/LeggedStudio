// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

namespace aimrte::core
{
class Context::OpPub : public OpBase
{
 public:
  using OpBase::OpBase;

  /**
   * @brief 初始化指定通信类型与话题名称的发布信道，并返回它的资源标识符。
   * @tparam T AimRT 支持的通信类型
   * @param topic_name 话题名称
   * @return 信道资源标识符，将用于后续发布数据
   */
  template <concepts::DirectlySupportedType T>
  [[nodiscard]] res::Channel<T> Init(const std::string_view& topic_name);

  /**
   * @brief 在给定通信类型适配器的情况下，初始化指定用户类型与话题名称的发布信道，
   *        并返回它的资源标识符。
   * @tparam T          用户自定义类型
   * @tparam TConverter 用于转换用户类型到通信类型的转化器，其中定义了通信类型
   * @param topic_name  话题名称
   * @return 信道资源标识符，将用于后续发布数据。
   */
  template <class T, concepts::ByConverter TConverter>
  [[nodiscard]] res::Channel<T> Init(const std::string_view& topic_name);

  /**
   * @brief 初始化一个被测发布通道资源
   */
  template <class T>
  res::Channel<T> InitMock(const std::string_view& topic_name, IMockPublisher<T>& mocker);

  /**
   * @brief 使用指定信道资源，发布数据
   * @param ch  信道资源描述符，约定了类型以及对应的发布器，若资源没有正确初始化或使用，将报错
   * @param msg 需要被发送的数据
   */
  template <class T>
  void Publish(const res::Channel<T>& ch, const T& msg);

  /**
   * @brief 使用指定信道资源，发布数据，同时给定应用 channel 上下文
   */
  template <class T>
  void Publish(const res::Channel<T>& ch, aimrt::channel::ContextRef ch_ctx, const T& msg);

 private:
  /**
   * @brief 基础的 channel pub 初始化过程，原生的 pub ref 将被初始化，发布类型 TRaw 将被注册。
   * 其余上下文需要由调用者进一步完善。
   * @tparam T 使用时的类型
   * @tparam TRaw 用于通信的类型。
   * @param topic_name 信道话题名称
   * @return 新的 channel 资源描述符，以及初始化了部分内容的信道上下文。
   */
  template <class T, concepts::DirectlySupportedType TRaw = T>
  std::pair<res::Channel<T>, ChannelContext&> DoInit(const std::string_view& topic_name);

  /**
   * @return 发布数据的函数
   */
  template <concepts::DirectlySupportedType T>
  static PublishFunction<T> CreatePublishFunction();

  /**
   * @return 转换类型后，发布数据的函数
   */
  template <class T, concepts::ByConverter TConverter>
  static PublishFunction<T> CreatePublishFunction();
};
}  // namespace aimrte::core
