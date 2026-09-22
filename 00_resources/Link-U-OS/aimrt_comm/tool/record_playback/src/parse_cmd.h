// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "gflags/gflags.h"
#include <sstream>
#include <iostream>
#include "src/all_in_one/include/aimrte.h"
#include "src/utils/utils.h"
#include <yaml-cpp/yaml.h>
#include <filesystem>

#include "record.h"

using aimrte::cfg::backend::plugin::record_playback;

namespace recordplayback {

constexpr std::string_view METATOPICPATH = "/agibot/data/ota/firmware/v0/config/record_playback/topic_meta_list.yaml";
constexpr std::string_view YAMLPATH = "/agibot/data/ota/firmware/v0/config/record_playback/record_playback_action.yaml";

struct TopicMeta {
  std::string topic_name;
  std::string msg_type;
  std::vector<std::string> backend;
  bool record_enabled{true};
  bool cache_last_msg{false};
};

struct Action {
  std::string action_name;
  std::string mode;
  std::string method;
  bool is_enable;
  bool record_enabled; // 配置文件中的开关状态
  bool record_enabled_now{false}; // 实际开关状态
  bool is_auto_upload;
  bool has_update_metadata{false};
  uint32_t preparation_duration_s;
  uint32_t record_duration_s;
  uint32_t max_record_duration_s;
  uint32_t skip_duration_s;
  uint32_t play_duration_s;
  std::string playback_bag_path;
  std::unordered_map<std::string, std::set<std::string>> backend_and_topics;
  std::unordered_set<std::string> cache_last_msg_topics;
  std::vector<TopicMeta> topic_list;
  std::vector<std::string> extra_file_path;
};

struct SocCfg {
  int32_t max_single_bag_size;   // MB
  int32_t all_bag_size;          // GB
  bool is_fctl;
  int32_t msg_write_interval;
  int32_t msg_write_interval_time;
  std::string record_bag_path;
  std::vector<Action> actions;
  std::string compression_mode;
  std::string compression_level;
};

inline std::unordered_map<std::string, std::string> topic_map_;
inline SocCfg soc_cfg_;

inline void ParsePlayback(const std::string &playbag_path, std::vector<std::string> &playbag_path_list) {
    std::stringstream ss(playbag_path);
    std::string playbag_path_str;
    while (std::getline(ss, playbag_path_str, ',')) {
        if (!playbag_path_str.empty()) {
            if (playbag_path_str.back() != '/') {
                playbag_path_str += '/';
            }
            playbag_path_list.push_back(playbag_path_str);
        }
    }
}

inline void ParseTypeSupport(const std::string& input, std::vector<record_playback::Path>& type_support)
{
    std::stringstream ss(input);
    std::string type;
    while (std::getline(ss, type, ':')) {
        if (!type.empty()) {
            type_support.push_back({type});
        }
    }
}

inline void ParseTopicYaml(const std::string_view& yaml_path, std::unordered_map<std::string, std::string>& topic_map)
{
    try {
        YAML::Node config = YAML::LoadFile(std::string(yaml_path));
        const YAML::Node& meta_list = config["topic_meta_list"];
        if (!meta_list || !meta_list.IsSequence()) {
            AIMRTE_ERROR("'topic_meta_list' not found or not a sequence in {}", yaml_path);
            return;
        }

        for (const auto& node : meta_list) {
            if (!node["topic_name"] || !node["msg_type"]) {
                AIMRTE_WARN("Skip invalid topic_meta entry: {}", YAML::Dump(node));
                continue;
            }
            std::string topic = node["topic_name"].as<std::string>();
            std::string type  = node["msg_type"].as<std::string>();
            auto [_, inserted] = topic_map.emplace(topic, type);
            if (!inserted) {
                AIMRTE_WARN("Duplicate topic_name '{}' in {}", topic, yaml_path);
            }
        }
        return;
    } catch (const YAML::Exception& e) {
        AIMRTE_ERROR("YAML error: {}", e.what());
        return;
    }
}

inline void ParsePlaybackYaml(const std::string& yaml_path, std::vector<record_playback::TopicMetaList> &topic_meta_list) {
    try {
        auto LoadTopicMeta = [](const YAML::Node& node) {
            record_playback::TopicMetaList  topic_meta;
            topic_meta.topic_name = node["topic_name"].as<std::string>();
            topic_meta.msg_type = node["msg_type"].as<std::string>();
            if(node["serialization_type"].IsDefined()) {
                topic_meta.serialization_type = node["serialization_type"].as<std::string>();
            }
            return topic_meta;
        };
        YAML::Node config = YAML::LoadFile(yaml_path);
        if (config["aimrt_bagfile_information"].IsDefined() &&  config["aimrt_bagfile_information"]["topics"].IsDefined()) {
            std::transform(config["aimrt_bagfile_information"]["topics"].begin(), config["aimrt_bagfile_information"]["topics"].end(), std::back_inserter(topic_meta_list), LoadTopicMeta);
        }
    } catch (const YAML::Exception& e) {
        AIMRTE_ERROR("YAML error: {}", e.what());
    }
}

inline std::vector<TopicMeta> ParseTopicLists(const std::unordered_map<std::string, std::set<std::string>>& backend_and_topics,
                                              const std::unordered_set<std::string> cache_last_msg_topics) {
    std::vector<TopicMeta> topic_list;
    for(const auto &[topic, backends] : backend_and_topics) {
        if (topic_map_.find(topic) == topic_map_.end()) {
            AIMRTE_ERROR_STREAM("topic: " << topic << " not found in topic_map_");
            continue;
        }
        TopicMeta meta;
        meta.topic_name     = topic;
        meta.msg_type       = topic_map_[topic];
        meta.backend.assign(backends.begin(), backends.end());
        meta.record_enabled = true;
        meta.cache_last_msg = cache_last_msg_topics.count(topic);
        topic_list.emplace_back(std::move(meta));
    }
    return topic_list;
}

inline std::string GetEnv(const std::string& backend) {
    if (backend.starts_with("${") && backend.ends_with('}')) {
        return aimrte::utils::Env(backend.substr(2, backend.size() - 3));
    } else if (backend.starts_with("$")) {
        return aimrte::utils::Env(backend.substr(1, backend.size() - 1));
    } else {
        return backend;
    }
}

inline std::unordered_map<std::string, std::set<std::string>> ParseBackendAndTopics(const YAML::Node& node) {
    std::unordered_map<std::string, std::set<std::string>> backend_and_topics;
    for (const auto& no : node) {
        const std::string topicnode = no.as<std::string>();
        AIMRTE_INFO_STREAM("get topic: " << topicnode);

        size_t colon_pos = topicnode.find(':');
        if (colon_pos == std::string::npos) {
            AIMRTE_ERROR_STREAM("Invalid input format for part: " << topicnode);
            continue;
        }
        std::string backend = topicnode.substr(0, colon_pos);
        backend = GetEnv(backend);
        std::transform(backend.begin(), backend.end(), backend.begin(), ::tolower);

        std::string topic = topicnode.substr(colon_pos + 1);
        if (!backend.empty() && !topic.empty()) {
            backend_and_topics[topic].insert(backend);
        }
    }
    return backend_and_topics;
}

inline std::unordered_set<std::string> ParseCacheTopics(const YAML::Node& node) {
    std::unordered_set<std::string> cache_last_msg_topics;
    for (const auto& n : node) {
        cache_last_msg_topics.insert(n.as<std::string>());
    }
    return cache_last_msg_topics;
}

inline Action ParseAction(const YAML::Node& action) {
    Action act;
    try {
        act.action_name            = action["action_name"].as<std::string>("");
        act.mode                   = action["mode"].as<std::string>("");
        act.method                 = action["method"].as<std::string>("");
        act.preparation_duration_s = action["preparation_duration_s"].as<uint32_t>(0);
        act.record_duration_s      = action["record_duration_s"].as<uint32_t>(0);
        act.max_record_duration_s  = action["max_record_duration_s"].as<uint32_t>(0);
        act.skip_duration_s        = action["skip_duration_s"].as<uint32_t>(0);
        act.play_duration_s        = action["play_duration_s"].as<uint32_t>(0);
        act.playback_bag_path      = action["playback_bag_path"].as<std::string>("");
        act.is_enable              = action["is_enable"].as<bool>(false);
        act.record_enabled         = action["record_enabled"].as<bool>(true);
        act.record_enabled_now     = action["record_enabled"].as<bool>(false);
        act.is_auto_upload         = action["is_auto_upload"].as<bool>(false);
        act.has_update_metadata    = false;
        if (!action["topics"] || !action["topics"].IsSequence()) {
            AIMRTE_ERROR("Missing or invalid 'topics' for action {}", act.action_name);
            return act;
        }
        act.backend_and_topics    = ParseBackendAndTopics(action["topics"]);
        act.cache_last_msg_topics = ParseCacheTopics(action["cache_last_msg_topics"]);
        act.topic_list            = ParseTopicLists(act.backend_and_topics, act.cache_last_msg_topics);
        act.extra_file_path       = action["extra_file_path"].as<std::vector<std::string>>();
    } catch (const YAML::Exception& e) {
        AIMRTE_ERROR("YAML parse error in action {}: {}", action["action_name"].as<std::string>(""), e.what());
    }
    return act;
}

inline SocCfg LoadConfig(const std::string_view& yaml_file) {
    SocCfg cfg;
    try {
        YAML::Node node = YAML::LoadFile(std::string(yaml_file));
        cfg.max_single_bag_size     = node["max_single_bag_size"].as<int32_t>(1000);
        cfg.all_bag_size            = node["all_bag_size"].as<int32_t>(100);
        cfg.is_fctl                 = node["is_fctl"].as<bool>(true);
        cfg.msg_write_interval      = node["msg_write_interval"].as<int32_t>(1000);
        cfg.msg_write_interval_time = node["msg_write_interval_time"].as<int32_t>(1000);
        cfg.record_bag_path         = node["record_bag_path"].as<std::string>("/agibot/data/bag/");
        cfg.compression_mode        = node["compression_mode"].as<std::string>("zstd");
        cfg.compression_level       = node["compression_level"].as<std::string>("default");
        const YAML::Node& actions_node = node["actions"];
        if (!actions_node || !actions_node.IsSequence()) {
            AIMRTE_WARN("soc config node has no valid 'actions' sequence");
            return cfg;
        }
        for (const auto& action : actions_node) {
            try {
                cfg.actions.emplace_back(ParseAction(action));
            } catch (const YAML::Exception& e) {
                AIMRTE_ERROR("Skip invalid action in soc config: {}", e.what());
                continue;
            }
        }
        AIMRTE_INFO("ParseSocConfig finished: {} actions loaded", cfg.actions.size());
    } catch (const YAML::Exception& e) {
        AIMRTE_ERROR("YAML error: {}", e.what());
    }
    return cfg;
}

} // namespace recordplayback
