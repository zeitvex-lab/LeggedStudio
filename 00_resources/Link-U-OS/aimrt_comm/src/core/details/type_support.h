// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/trait/trait.h"
#include "./concepts.h"

namespace aimrte::core::details
{
/**
 * @return 给定类型的 support 信息
 */
template <concepts::DirectlySupportedType T>
const aimrt_type_support_base_t* GetMessageTypeSupport()
{
  if constexpr (concepts::RosMessage<T>)
    return aimrt::GetRos2MessageTypeSupport<T>();
  else if constexpr (concepts::Protobuf<T>)
    return aimrt::GetProtobufMessageTypeSupport<T>();
  else
    static_assert(trait::always_false_v<T>);
}

/**
 * @return 给定类型的第三方通信的 support 信息
 */
template <class T>
const void* GetCustomTypeSupport()
{
  if constexpr (concepts::RosService<T>)
    return rosidl_typesupport_cpp::get_service_type_support_handle<T>();
  else if constexpr (std::is_void_v<T>)
    return nullptr;
  else
    static_assert(trait::always_false_v<T>, "UNKNOWN communication type");
}

/**
 * @return 给定类型的序列化方法名称
 */
template <concepts::DirectlySupportedType T>
constexpr std::string_view GetSerializationType()
{
  if constexpr (concepts::RosMessage<T>)
    return "ros2";
  else if constexpr (concepts::Protobuf<T>)
    return "pb";
  else
    static_assert(trait::always_false_v<T>);
}

/**
 * @return 根据 AimRT 规则，封装 rpc 方法名
 */
template <concepts::DirectlySupportedType T>
std::string WrapRpcFuncName(const std::string_view& name)
{
  if (name.empty() or name.front() != '/')
    return std::string(GetSerializationType<T>()) + ":/" + std::string(name);
  else
    return std::string(GetSerializationType<T>()) + ":" + std::string(name);
}

/**
 * @brief 从 AimRT 的消息回调中，构造明确了类型的数据指针
 */
template <class T>
std::shared_ptr<const T> MakeSharedMessage(const void* msg_raw_ptr, aimrt_function_base_t* release_callback_base)
{
  // 负责释放数据内存的过程
  aimrt::util::Function<aimrt_function_subscriber_release_callback_ops_t> release_callback(
    release_callback_base);

  // 构建数据指针，其析构时，负责将内存回收
  std::shared_ptr<const T> msg_ptr(
    static_cast<const T*>(msg_raw_ptr),
    [release_callback = std::move(release_callback)](const T*) {
      release_callback();
    });

  // 返回该数据指针
  return msg_ptr;
}
}  // namespace aimrte::core::details
