// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/all_in_one/include/aimrte.h"
#include <cstdio>
#include <random>
#include "src/module/cfg.h"
#include "src/module/cfg/exe.h"
#include "gflags/gflags.h"
#include "src/utils/utils.h"
#include "src/module/cfg/plugin.h"
#include <filesystem>
#include <fmt/format.h>
#include "./parse_cmd.h"

using aimrte::cfg::backend::plugin::record_playback;
using namespace aimrte;

namespace recordplayback {

inline void NetPluginSetting(aimrte::Cfg &cfg)
{
  cfg
    [cfg::backend::Plugin::net] = {
    .options = {
      .thread_num = 4,
      .http_options = {{ .listen_port = 50593 }},
      .tcp_options = {{ .listen_port = 51593 }},
      .udp_options = {{ .listen_port = 52593 }}
    }
  };
  cfg
    [cfg::backend::Ch::http] = {};
  cfg
    [cfg::backend::Rpc::http] = {};
}

inline void MqttPluginSetting(aimrte::Cfg &cfg, const std::string& broker_ip = utils::Env("MQTT_BROKER_IP", "127.0.0.1")) {
  std::srand(static_cast<unsigned>(std::time(0)));
  cfg
    [cfg::backend::Plugin::mqtt] = {
      .options = {
        .broker_addr = fmt::format("tcp://{}:1883", broker_ip),
        .client_id = "recordplayback_bag_client_" + cfg::details::ProcName() + "_" + std::to_string(getpid()),
        .max_pkg_size_k = 10240,
      },
    };
  cfg
    [cfg::backend::Ch::mqtt] = {};
  cfg
    [cfg::backend::Rpc::mqtt] = {
      .options = {{
        .timeout_executor = "default_timeout_executor",
        .servers_options  = {},
      }},
    };
  cfg
    .WithDefaultTimeoutExecutor();
}

inline void ZenohPluginSetting(aimrte::Cfg &cfg) {
  cfg
    .WithDefaultZenoh();
}

inline void IceoryxPluginSetting(aimrte::Cfg &cfg) {
  cfg
    .WithDefaultIceoryx();
}

inline void PluginSetting(aimrte::Cfg &cfg, const std::string &channel_backend)
{
  if(channel_backend == "mqtt" || channel_backend == "ros2" || channel_backend == "http" || channel_backend == "tcp" || channel_backend == "udp") {
    // mqtt and ros2 has been setting
  } else if (channel_backend == "zenoh") {
    ZenohPluginSetting(cfg);
  } else if (channel_backend == "iceoryx") {
    IceoryxPluginSetting(cfg);
  }
}

inline void ChannelSetting(aimrte::Cfg &cfg, const std::string &method,
  const std::unordered_map<std::string, std::set<std::string>> &backend_and_topics)
{
  auto Transfer = [](const std::string& channel) -> aimrte::cfg::Ch {
    if(channel == "mqtt") return cfg::Ch::mqtt;
    if(channel == "ros2") return cfg::Ch::ros2;
    if(channel == "http") return cfg::Ch::http;
    if(channel == "tcp") return cfg::Ch::tcp;
    if(channel == "udp") return cfg::Ch::udp;
    if(channel == "zenoh") return cfg::Ch::zenoh;
    if(channel == "iceoryx") return cfg::Ch::iceoryx;
    return cfg::Ch::local;
  };

  std::unordered_map<std::string, std::vector<aimrte::cfg::Ch>> channels_map;
  for(const auto& [topic, backends] : backend_and_topics) {
    for(const auto &backend : backends) {
      channels_map[topic].push_back(Transfer(backend));
    }
  }
  for(const auto &[topic, channels] : channels_map) {
    cfg
      .SetBackendTopic(method, topic, channels);
  }
}

inline void RecordPlaybackSetting(aimrte::Cfg &cfg,
  SocCfg soccfg,
  std::vector<record_playback::Path> type_support_pkgs_name_list)
{
  std::vector<record_playback::RecordActions> record_actionses;
  std::vector<record_playback::PlaybackActions> playback_actionses;

  for (const auto& action : soccfg.actions) {
    if (!action.is_enable) {
      AIMRTE_INFO_STREAM("action: " << action.action_name << " is not enable");
      continue;
    }

    if (action.method == "record") {
      std::vector<record_playback::TopicMetaList> topic_list_pb;
      for(auto &topic : action.topic_list) {
        topic_list_pb.push_back(record_playback::TopicMetaList{
          .topic_name = topic.topic_name,
          .msg_type = topic.msg_type,
          .record_enabled = topic.record_enabled,
          .cache_last_msg = topic.cache_last_msg,
        });
      }
      record_actionses.emplace_back(record_playback::RecordActions{
        .name = action.action_name,
        .options = {
          .bag_path = soccfg.record_bag_path + action.mode + (action.mode == "signal" ? "/" + action.action_name : ""),
          .mode = action.mode,
          .max_preparation_duration_s = (action.mode == "signal" ? action.preparation_duration_s : 0),
          .executor = record_playback::ExecutorType::record_thread,
          .storage_policy = {
            .storage_format = "mcap",
            .max_bag_size_m = soccfg.max_single_bag_size,
            .msg_write_interval = soccfg.msg_write_interval,
            .msg_write_interval_time = soccfg.msg_write_interval_time,
            .compression_mode = soccfg.compression_mode,
            .compression_level = soccfg.compression_level,
          },
          .topic_meta_list = std::move(topic_list_pb),
          .record_enabled = action.record_enabled,
          .extra_file_path = action.extra_file_path,
        }
      });
    } else if (action.method == "playback") {
      std::vector<std::string> playback_list;
      ParsePlayback(action.playback_bag_path, playback_list);

      for (auto &bag_path : playback_list) {
        AIMRTE_INFO_STREAM("playback bag path: " << bag_path);
        if (!std::filesystem::exists(bag_path) || !std::filesystem::is_directory(bag_path)) {
          AIMRTE_WARN_STREAM("skip invalid bag dir: " << bag_path);
          continue;
        }

        std::vector<record_playback::TopicMetaList> TopicList;
        ParsePlaybackYaml(bag_path + "metadata.yaml",  TopicList);
        playback_actionses.emplace_back(record_playback::PlaybackActions{
          .name = action.action_name,
          .options = {
            .bag_path = bag_path,
            .mode = action.mode,
            .executor = record_playback::ExecutorType::playback_thread_pool,
            .skip_duration_s = action.skip_duration_s,
            .play_duration_s = action.play_duration_s,
            .topic_meta_list = std::move(TopicList),
          },
        });
      }
    } else {
      AIMRTE_ERROR_STREAM("invalid method: " << action.method);
      continue;
    }

    std::unordered_map<std::string, bool> backend_map;
    for(const auto& [topic, backends] : action.backend_and_topics) {
      for(const auto& backend : backends) {
        if(backend_map.find(backend) == backend_map.end()) {
          PluginSetting(cfg, backend);
          backend_map[backend] = true;
        }
      }
    }

    ChannelSetting(cfg, action.method, action.backend_and_topics);
  }

  cfg
    [cfg::backend::Plugin::record_playback] = {
    .path = "libaimrt_record_playback_plugin.so",
      .options = {
        .type_support_pkgs = std::move(type_support_pkgs_name_list),
        .timer_executor = record_playback::ExecutorType::storage_executor,
        .record_actions =  std::move(record_actionses),
        .playback_actions = std::move(playback_actionses),
      },
    };
  cfg
    [cfg::Exe::simple_thread] += {
      .name = "record_thread",
      .options = {{
        .queue_threshold = 100000,
      }},
    };
  cfg
    [cfg::Exe::asio_thread] += {
      .name = "storage_executor",
      .options = {{.thread_num = 2}},
    };
  cfg
    [cfg::Exe::asio_thread] += {
      .name = "playback_thread_pool",
      .options = {{.thread_num = 2}},
    };
}

} // namespace recordplayback
