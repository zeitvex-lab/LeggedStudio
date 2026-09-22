// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <atomic>
#include <chrono>
#include <cmath>
#include <iostream>
#include <map>
#include <memory>
#include <mutex>
#include <numeric>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>

namespace aimrte::common
{

class TopicHzCalculator
{
 public:
  using TimePoint = std::chrono::steady_clock::time_point;

  struct TopicFrequencyStats {
    double rate{0};               // 平均频率
    double minDelta{0};           // 最小时间间隔（纳秒）
    double maxDelta{0};           // 最大时间间隔（纳秒）
    double stdDev{0};             // 标准差
    size_t maxWindow{0};          // 使用的最大窗口大小
    size_t windowSize{0};         // 当前窗口大小
    double timeout_threshold{0};  // 未收到消息的超时阈值（纳秒）
    bool is_active{false};        // 是否活跃
  };

  struct TopicInfo {
    std::string process_name;
    std::string topic_name;
    std::string msg_type;

    bool operator<(const TopicInfo& other) const
    {
      return std::tie(process_name, topic_name, msg_type) < std::tie(other.process_name, other.topic_name, other.msg_type);
    }

    bool operator==(const TopicInfo& other) const
    {
      return process_name == other.process_name && topic_name == other.topic_name && msg_type == other.msg_type;
    }
  };

  struct TopicInfoHash {
    std::size_t operator()(const TopicInfo& info) const
    {
      return std::hash<std::string>()(info.process_name) ^ (std::hash<std::string>()(info.topic_name) << 1) ^ (std::hash<std::string>()(info.msg_type) << 2);
    }
  };

  using HzInfoMap = std::unordered_map<TopicInfo, TopicFrequencyStats, TopicInfoHash>;

  TopicHzCalculator() = default;

  /**
   * @brief 初始化topic，传入要监听的topic列表
   * @param topic_list topic列表
   * @param windowSize 计算时的滑动窗口大小
   */
  void Initialize(const std::set<TopicInfo>& topic_list, size_t windowSize = 5000);

  /**
   * @brief 更新topic
   * @param topic
   */
  void FeedTopic(const TopicInfo& topic);

  /**
   * @brief 计算topic的频率
   * @param topic 要计算的topic
   * @return
   */
  TopicFrequencyStats Calculate(const TopicInfo& topic);

  /**
   * @brief 计算所有的tpoic频率
   * @return
   */
  HzInfoMap CalculateAll();

 private:
  struct TopicData {
    std::mutex mutex;  // 独立锁
    TimePoint msgT0 = TimePoint::min();
    TimePoint msgTn = TimePoint::min();
    std::vector<int64_t> times;
    bool is_active = false;
  };

  enum Step {
    Init    = 1,
    Running = 2,
  };

  size_t windowSize_{400};

  std::unordered_map<TopicInfo, std::shared_ptr<TopicData>, TopicInfoHash> topicsData_;  // 该map为线程安全的(初始化后不会改变)

  std::shared_ptr<TopicHzCalculator::TopicData> GetTopicData(const TopicInfo& topic);

  std::atomic<Step> step_{Step::Init};
};
}  // namespace aimrte::common
