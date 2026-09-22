// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <cstdint>
#include <optional>
#include <string>

namespace aimrte::cfg::backend::details
{
struct QosOptions {
  /**
   * @brief 历史记录选项
   *  - keep_last: 保留最近的记录(缓存最多N条记录，可通过队列长度选项来配置)
   *  - keep_all: 保留所有记录(缓存所有记录，但受限于底层中间件可配置的最大资源)
   *  - default: 系统默认
   */
  std::optional<std::string> history;

  /**
   * @brief 队列深度选项 (只能与 Keep_last 配合使用)
   */
  std::optional<std::int32_t> depth;

  /**
   * @brief 可靠性选项
   *  - reliable: 可靠的(消息丢失时，会重新发送,反复重传以保证数据传输成功)
   *  - best_effort: 尽力而为的(尝试传输数据但不保证成功传输,当网络不稳定时可能丢失数据)
   *  - default: 系统默认
   */
  std::optional<std::string> reliability;

  /**
   * @brief 持续性选项
   *  - transient_local: 局部瞬态 (发布器为晚连接 (late-joining) 的订阅器保留数据 )
   *  - volatile: 易变态(不保留任何数据)
   *  - default: 系统默认
   */
  std::optional<std::string> durability;

  /**
   * @brief 后续消息发布到主题之间的预期最大时间量
   *  ms 级时间戳 -1为不设置
   */
  std::optional<std::int64_t> deadline;

  /**
   * @brief 消息发布和接收之间的最大时间量，而不将消息视为陈旧或过期（过期的消息被静默地丢弃，并且实际上从未被接收）。
   *   ms 级时间戳 -1为不设置
   */
  std::optional<std::int64_t> lifespan;

  /**
   * @brief 如何确定发布者是否活跃
   *  - automatic: 自动 (ROS2 会根据消息发布和接收的时间间隔来判断)
   *  - manual_by_topic: 需要发布者定期声明
   *  - default: 系统默认
   */
  std::optional<std::string> liveliness;

  /**
   * @brief 活跃性租期的时长，如果超过这个时间发布者没有声明活跃，则被认为是不活跃的。
   *   ms 级时间戳 -1 为不设置
   */
  std::optional<std::int64_t> liveliness_lease_duration;
};
}  // namespace aimrte::cfg::backend::details
