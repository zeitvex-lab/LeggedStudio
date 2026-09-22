// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "channel.h"

#include "src/ctx/ctx.h"
#include <memory>

namespace YAML
{
template <>
struct convert<aimrte::plugin::monitor::MonitorChannelBackend::Options> {
  static Node encode(
    const aimrte::plugin::monitor::MonitorChannelBackend::Options& rhs)
  {
    Node node;

    // node["executor"] = rhs.executor;

    return node;
  }

  static bool decode(const Node& node, aimrte::plugin::monitor::MonitorChannelBackend::Options& rhs)
  {
    if (!node.IsMap()) return false;

    // rhs.executor = node["executor"].as<std::string>();

    return true;
  }
};
}  // namespace YAML

namespace aimrte::plugin::monitor
{

MonitorChannelBackend::MonitorChannelBackend() {}

void MonitorChannelBackend::Initialize(
  YAML::Node options_node)
{
  if (options_node && !options_node.IsNull())
    options_ = options_node.as<Options>();
}

void MonitorChannelBackend::SetChannelRegistry(const aimrt::runtime::core::channel::ChannelRegistry* channel_registry_ptr) noexcept
{
  channel_registry_ptr_ = channel_registry_ptr;
}

std::vector<std::string> MonitorChannelBackend::GetBackendsByRules(
  std::string_view topic_name,
  const std::vector<std::pair<std::string, std::vector<std::string>>>& rules)
{
  for (const auto& item : rules) {
    const auto& topic_regex     = item.first;
    const auto& enable_backends = item.second;
    try {
      if (std::regex_match(topic_name.begin(), topic_name.end(), std::regex(topic_regex, std::regex::ECMAScript))) {
        return enable_backends;
      }
    } catch (const std::exception& e) {
      AIMRTE_WARN("Regex get exception, expr: {}, string: {}, exception info: {}", topic_regex, topic_name, e.what());
    }
  }

  return {};
}

void MonitorChannelBackend::Start()
{
  const auto& publish_type_wrapper_map =
    channel_registry_ptr_->GetPublishTypeWrapperMap();
  const auto& subscribe_wrapper_map =
    channel_registry_ptr_->GetSubscribeWrapperMap();

  // 获取框架配置 读取不同topic所走的后端的配置
  auto aimrt_config = data_manager_->GetDumpRootConfig()["aimrt"];

  // 统计配置中的topic订阅与发布的backend信息
  if (aimrt_config["channel"] && aimrt_config["channel"]["sub_topics_options"] && aimrt_config["channel"]["sub_topics_options"].IsSequence()) {
    for (auto pub_topic_options_node : aimrt_config["channel"]["sub_topics_options"]) {
      auto topic_name      = pub_topic_options_node["topic_name"].as<std::string>();
      auto enable_backends = pub_topic_options_node["enable_backends"].as<std::vector<std::string>>();
      sub_topics_backends_rules.emplace_back(topic_name, enable_backends);
    }
  }
  if (aimrt_config["channel"] && aimrt_config["channel"]["pub_topics_options"] && aimrt_config["channel"]["pub_topics_options"].IsSequence()) {
    for (auto pub_topic_options_node : aimrt_config["channel"]["pub_topics_options"]) {
      auto topic_name      = pub_topic_options_node["topic_name"].as<std::string>();
      auto enable_backends = pub_topic_options_node["enable_backends"].as<std::vector<std::string>>();
      pub_topics_backends_rules.emplace_back(topic_name, enable_backends);
    }
  }

  std::set<TopicInfo> sub_topic_list;
  std::set<TopicInfo> pub_topic_list;

  /////////收集发布与订阅的消息 回传给前端
  // publish info
  for (const auto& [key, wrapper] : publish_type_wrapper_map) {
    TopicInfo topic_info;
    topic_info.topic_name = key.topic_name;
    topic_info.msg_type   = key.msg_type;
    // 获取topic所走的后端
    topic_info.backends = GetBackendsByRules(key.topic_name, pub_topics_backends_rules);

    // topic信息统计
    pub_topic_list.insert(topic_info);
  }

  // sub info
  for (const auto& [key, wrapper] : subscribe_wrapper_map) {
    TopicInfo topic_info;
    topic_info.topic_name = key.topic_name;
    topic_info.msg_type   = key.msg_type;
    // 获取topic所走的后端
    topic_info.backends = GetBackendsByRules(key.topic_name, sub_topics_backends_rules);

    // topic信息统计
    sub_topic_list.insert(topic_info);
  }

  data_manager_->SetSubTopicInfoList(sub_topic_list);
  data_manager_->SetPubTopicInfoList(pub_topic_list);
}

void MonitorChannelBackend::Shutdown()
{
  if (std::atomic_exchange(&status_, Status::Shutdown) == Status::Shutdown)
    ;
}

}  // namespace aimrte::plugin::monitor
