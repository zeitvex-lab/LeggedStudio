// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./topic_hz_calculator.h"
#include "src/ctx/ctx.h"
namespace aimrte::common
{
void TopicHzCalculator::Initialize(const std::set<TopicInfo>& topic_list, size_t windowSize)
{
  AIMRTE_CHECK_THROW(std::atomic_exchange(&step_, Step::Running) == Step::Init, "the topic hz calculate can only be initialized once!");

  windowSize_ = windowSize;
  std::stringstream ss;
  for (auto& topic : topic_list) {
    topicsData_[topic] = std::make_shared<TopicData>();
    ss << "[" << topic.topic_name << "-" << topic.msg_type << "]";
  }
  std::cout << "the topic hz calculate is initialized, topics: " << ss.str() << std::endl;
}

void TopicHzCalculator::FeedTopic(const TopicInfo& topic)
{
  if (std::atomic_load(&step_) != Step::Running) [[unlikely]] {
    return;
  }

  auto data = GetTopicData(topic);
  if (data == nullptr) [[unlikely]] {
    return;
  }

  std::lock_guard<std::mutex> guard(data->mutex);
  auto currentTime = std::chrono::steady_clock::now();

  if (not data->is_active) [[unlikely]] {
    data->is_active = true;
  }

  if (currentTime == TimePoint::min()) {
    if (!data->times.empty()) {
      // std::cout << "time has reset, resetting counters" << std::endl;
      data->times.clear();
    }
    return;
  }

  auto curr  = currentTime;
  auto msgT0 = data->msgT0;

  if (msgT0 == TimePoint::min() || msgT0 > curr) {
    data->msgT0 = curr;
    data->msgTn = curr;
    data->times.clear();
  } else {
    data->times.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(curr - data->msgTn).count());
    data->msgTn = curr;
  }

  if (data->times.size() > windowSize_) {
    data->times.erase(data->times.begin());
  }
}

TopicHzCalculator::TopicFrequencyStats TopicHzCalculator::Calculate(const TopicInfo& topic)
{
  TopicFrequencyStats stats{};
  if (std::atomic_load(&step_) != Step::Running) [[unlikely]] {
    return stats;
  }

  stats.maxWindow = windowSize_;
  auto data       = GetTopicData(topic);

  if (data == nullptr) [[unlikely]] {
    return stats;
  }

  // 如果当前topic没有做初始化 则直接返回
  if (not data) [[unlikely]] {
    return stats;
  }

  std::lock_guard<std::mutex> guard(data->mutex);

  stats.is_active = data->is_active;
  if (data->times.empty()) {
    return stats;
  }

  size_t n    = data->times.size();
  double mean = std::accumulate(data->times.begin(), data->times.end(), 0.0) / n;
  stats.rate  = mean > 0 ? 1.0 / mean : 0;

  stats.stdDev = std::sqrt(std::accumulate(data->times.begin(), data->times.end(), 0.0, [mean](double sum, double val) {
                             return sum + std::pow(val - mean, 2);
                           }) /
                           n);

  stats.maxDelta   = *std::max_element(data->times.begin(), data->times.end());
  stats.minDelta   = *std::min_element(data->times.begin(), data->times.end());
  stats.windowSize = n;

  // 计算自上次消息以来的时间 判断消息是否超时没有收到
  auto currentTime      = std::chrono::steady_clock::now();
  auto timeSinceLastMsg = std::chrono::duration_cast<std::chrono::nanoseconds>(currentTime - data->msgTn).count();

  // 超时未收到消息处理 频率在 2s 以内的 topic 的超时时间设置为2s
  double timeoutThreshold = std::max(mean + 5 * stats.stdDev, 2e9);  // 2s = 2 * 10^9 nanoseconds
  stats.timeout_threshold = timeoutThreshold;
  if (timeSinceLastMsg > timeoutThreshold) {
    stats.rate = 0;
    data->times.clear();
    data->msgT0 = TimePoint::min();
    data->msgTn = TimePoint::min();
    return stats;
  }

  // 单位转换 秒
  stats.rate *= 1e9;
  stats.stdDev *= 1e-9;
  stats.minDelta *= 1e-9;
  stats.maxDelta *= 1e-9;
  stats.timeout_threshold *= 1e-9;

  return stats;
}

TopicHzCalculator::HzInfoMap TopicHzCalculator::CalculateAll()
{
  HzInfoMap allStats;

  if (std::atomic_load(&step_) != Step::Running) [[unlikely]] {
    return allStats;
  }

  for (const auto& topicPair : topicsData_) {
    const auto& topic = topicPair.first;
    allStats[topic]   = Calculate(topic);
  }
  return allStats;
}

std::shared_ptr<TopicHzCalculator::TopicData> TopicHzCalculator::GetTopicData(const TopicInfo& topic)
{
  if (topicsData_.find(topic) == topicsData_.end()) [[unlikely]] {
    return nullptr;
  }
  return topicsData_[topic];
}
}  // namespace aimrte::common
