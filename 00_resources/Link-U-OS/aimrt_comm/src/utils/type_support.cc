// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./type_support.h"
#include <yaml-cpp/yaml.h>

namespace aimrte::utils
{
bool GetTopicMetaList(const std::string& yaml_path, std::unordered_map<std::string, std::string>& topic_map)
{
  try {
    YAML::Node config = YAML::LoadFile(yaml_path);
    const YAML::Node& meta_list = config["topic_meta_list"];
    if (!meta_list || !meta_list.IsSequence()) {
      // AIMRTE_ERROR("'topic_meta_list' not found or not a sequence in {}", yaml_path);
      return false;
    }

    for (const auto& node : meta_list) {
      if (!node["topic_name"] || !node["msg_type"]) {
        // AIMRTE_WARN("Skip invalid topic_meta entry: {}", YAML::Dump(node));
        continue;
      }
      std::string topic = node["topic_name"].as<std::string>();
      std::string type  = node["msg_type"].as<std::string>();
      auto [_, inserted] = topic_map.emplace(topic, type);
      if (!inserted) {
        // AIMRTE_WARN("Duplicate topic_name '{}' in {}", topic, yaml_path);
      }
    }
    return true;
  } catch (const YAML::Exception& e) {
    // AIMRTE_ERROR("YAML error: {}", e.what());
    return false;
  }
}
}  // namespace aimrte::utils
