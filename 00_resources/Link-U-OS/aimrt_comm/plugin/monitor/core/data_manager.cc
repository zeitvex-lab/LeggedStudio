// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./data_manager.h"
#include "src/ctx/ctx.h"
#include <bitset>
#include <iostream>

namespace aimrte::plugin::monitor
{

void DataManager::SetSubTopicInfoList(const std::set<TopicInfo> &topic_list)
{
  sub_topic_set_ = topic_list;

  std::set<common::TopicHzCalculator::TopicInfo> all_topic;
  for (const auto &one_topic : topic_list) {
    all_topic.insert(common::TopicHzCalculator::TopicInfo{.topic_name = std::string(one_topic.topic_name), .msg_type = std::string(one_topic.msg_type)});
  }
  sub_topic_hz_calculate_.Initialize(all_topic);
  init_flag_ = true;
}

void DataManager::SetPubTopicInfoList(const std::set<TopicInfo> &topic_list)
{
  pub_topic_set_ = topic_list;

  std::set<common::TopicHzCalculator::TopicInfo> all_topic;
  for (const auto &one_topic : topic_list) {
    all_topic.insert(common::TopicHzCalculator::TopicInfo{.topic_name = std::string(one_topic.topic_name), .msg_type = std::string(one_topic.msg_type)});
  }
  pub_topic_hz_calculate_.Initialize(all_topic);
  init_flag_ = true;
}

void DataManager::ShutDown()
{
  init_flag_ = false;
}

aimrt::co::Task<void> DataManager::CollectData()
{
  if (not init_flag_) co_return;

  std::unique_lock<std::mutex> lock(mutext_);
  // 计算topic频率

  sub_topic_hz_map_ = sub_topic_hz_calculate_.CalculateAll();
  pub_topic_hz_map_ = pub_topic_hz_calculate_.CalculateAll();

  co_return;
}

void DataManager::OnPublishFilter(std::string_view topic_name, std::string_view msg_type)
{
  pub_topic_hz_calculate_.FeedTopic(common::TopicHzCalculator::TopicInfo{.topic_name = std::string(topic_name), .msg_type = std::string(msg_type)});
}

void DataManager::OnSubscribeFilter(std::string_view topic_name, std::string_view msg_type)
{
  sub_topic_hz_calculate_.FeedTopic(common::TopicHzCalculator::TopicInfo{.topic_name = std::string(topic_name), .msg_type = std::string(msg_type)});
}

YAML::Node &DataManager::GetDumpRootConfig()
{
  return option_root_;
}

YAML::Node &DataManager::GetOriginConfig()
{
  return origin_option_root_;
}

}  // namespace aimrte::plugin::monitor
