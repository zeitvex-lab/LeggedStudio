// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/sys/sys.h"
#include <optional>
#include <string>
#include <vector>

#include "./env.h"

namespace aimrte::cfg::backend::plugin
{
/**
 * @brief 插件的基础内容，仅包含关键字
 */
struct meta {
  std::string name;
};

/**
 * @brief ros2 插件的配置
 */
struct ros2 {
  enum class ExecutorType {
    SingleThreaded,
    StaticSingleThreaded,
    MultiThreaded
  };

  std::string name{"ros2_plugin"};
  std::string path{"libaimrt_ros2_plugin.so"};
  struct {
    std::string node_name{cfg::details::ProcName()};
    std::optional<ExecutorType> executor_type;
    std::optional<int> executor_thread_num;
    std::optional<bool> auto_initialize_logging{false};
  } options;
};

/**
 * @brief mqtt 插件的配置
 */
struct mqtt {
  std::string name{"mqtt_plugin"};
  std::string path{"libaimrt_mqtt_plugin.so"};
  struct {
    std::string broker_addr{"tcp://127.0.0.1:1883"};
    std::string client_id{cfg::details::ProcName()};
    std::optional<int> max_pkg_size_k;
  } options;
};

/**
 * @brief net 插件的配置
 */
struct net {
  struct HttpOption {
    std::string listen_ip{"0.0.0.0"};
    int listen_port{0};
  };

  struct TcpOption {
    std::string listen_ip{"0.0.0.0"};
    int listen_port{0};
  };

  struct UdpOption {
    std::string listen_ip{"0.0.0.0"};
    int listen_port{0};
    std::optional<int> max_pkg_size;
  };

  std::string name{"net_plugin"};
  std::string path{"libaimrt_net_plugin.so"};

   struct Options {
      int thread_num{2};
      std::optional<HttpOption> http_options;
      std::optional<TcpOption> tcp_options;
      std::optional<UdpOption> udp_options;
    };

    Options options;
};

/**
 * @brief lcm 插件的配置
 */
struct lcm {
  std::string name{"lcm_plugin"};
  std::string path{"libaimrt_lcm_plugin.so"};
};

/**
 * @brief parameter 插件的配置
 */
struct parameter {
  std::string name{"parameter_plugin"};
  std::string path{"libaimrt_parameter_plugin.so"};
};

/**
 * @brief log_control 插件的配置。本配置已经默认加载。
 */
struct log_control {
  std::string name{"log_control_plugin"};
  std::string path{"libaimrt_log_control_plugin.so"};
};

/**
 * @brief opentelemetry 插件的配置
 */
struct opentelemetry {
  std::string name{"opentelemetry_plugin"};
  std::string path{"libaimrt_opentelemetry_plugin.so"};

  struct Attr {
    std::string key;
    std::string val;
  };

  struct
  {
    std::string node_name{cfg::details::ProcName()};
    std::string trace_otlp_http_exporter_url;
    std::vector<Attr> attributes{
      {"sn", sys::GetSN()}};
  } options;
};

/**
 *    @brief record_playback 插件的配置
 */
struct record_playback {
  enum class ExecutorType {
    record_thread,
    storage_executor,
    playback_thread_pool,
  };
  enum class ActionType {
    record_action,
    playback_action
  };

  std::string name{"record_playback_plugin"};
  std::string path{"libaimrt_record_playback_plugin.so"};

  struct TopicMetaList {
    std::string topic_name;
    std::string msg_type;
    std::string serialization_type;
    bool record_enabled;
    bool cache_last_msg;
  };

  struct StoragePolicy {
    std::string storage_format;
    int max_bag_size_m;
    int max_bag_num;
    int msg_write_interval;
    int msg_write_interval_time;
    std::string compression_mode;
    std::string compression_level;
  };

  struct RecordActions {
    std::string name;
    struct {
      std::string bag_path;
      std::string mode;
      uint64_t max_preparation_duration_s = 0;
      ExecutorType executor;
      StoragePolicy storage_policy;
      std::vector<TopicMetaList> topic_meta_list;
      bool record_enabled = true;
      std::vector<std::string> extra_file_path;
    } options;
  };

  struct PlaybackActions {
    std::string name;
    struct {
      std::string bag_path;
      std::string mode;
      ExecutorType executor = ExecutorType::playback_thread_pool;
      uint32_t skip_duration_s   = 0;
      uint32_t play_duration_s   = 0;
      std::vector<TopicMetaList> topic_meta_list;
    } options;
  };

  struct Path {
    std::string path;
  };

  struct {
    std::vector<Path> type_support_pkgs;
    ExecutorType timer_executor = ExecutorType::storage_executor;
    std::vector<RecordActions> record_actions;
    std::vector<PlaybackActions> playback_actions;
  } options;
};

/**
 * @brief monitor 插件的配置。本配置已经默认加载。
 */
struct monitor {
  std::string name{"monitor_plugin"};
  std::string path{"libaimrt_monitor_plugin.so"};

  struct
  {
    std::string executor{"default_monitor_executor"};
    std::string node_name{cfg::details::ProcName()};
  } options;
};

/**
 * @brief viz 插件的配置。本配置已经默认加载。
 */
struct viz {
  std::string name{"viz_plugin"};
  std::string path{"libaimrt_viz_plugin.so"};

  struct
  {
    std::string executor{"default_viz_executor"};
    std::string update_interval{"1000"};
    std::string node_name{cfg::details::ProcName()};
    std::string soc{"x86_64"};
    std::string service_name{node_name};
  } options;
};

/**
 * @brief zenoh 插件的配置。本配置已经默认加载。
 */
struct zenoh {
  std::string name{"zenoh_plugin"};
  std::string path{"libaimrt_zenoh_plugin.so"};

  struct Option {
    std::optional<std::string> native_cfg_path;
    std::optional<std::string> limit_domain{{LimitDomain()}};
  };

  static std::string LimitDomain()
  {
    if (const std::string sn = sys::GetSN(); sn.empty())
      return "agibot";
    else
      return "agibot/" + sn;
  }

  std::optional<Option> options;
};

/**
 * @brief iceoryx 插件的配置
 */
struct iceoryx {
  std::string name{"iceoryx_plugin"};
  std::string path{"libaimrt_iceoryx_plugin.so"};

  struct Option {
    std::optional<int> shm_init_size;
  };

  std::optional<Option> options;
};

/**
 * @brief aim omp 插件
 */
struct omp {
  std::string name{"omp_plugin"};
  std::string path{"libaimrt_omp_plugin.so"};
  struct {
    std::string broker_addr;
    std::string client_id{utils::Env("PRODUCT_KEY", "A1") + utils::Env("DEVICE_NAME", "test")};
    std::optional<int> max_pkg_size_k;
    struct
    {
      std::string product_key{utils::Env("PRODUCT_KEY", "A1")};
      std::string device_name{utils::Env("DEVICE_NAME", "test")};
      std::string secret_key{utils::Env("SECRET_KEY", "test")};
      int publish_resource{1};
    } common;
  } options;
};

/**
 * @brief echo 插件的配置
 */
struct echo {
  std::string name{"echo_plugin"};
  std::string path{"libaimrt_echo_plugin.so"};

  struct Path {
    std::string path;
  };

  struct TopicMetaList {
    std::string topic_name;
    std::string msg_type;
    std::string echo_type;
  };

  struct {
    std::vector<Path> type_support_pkgs;
    std::vector<TopicMetaList> topic_meta_list;
  } options;
};

/**
 * @brief proxy 插件的配置
 */
struct proxy {
  std::string name{"proxy_plugin"};
  std::string path{"libaimrt_proxy_plugin.so"};

  struct Path {
    std::string path;
  };

  struct TopicMeta {
    std::string sub_topic_name;
    std::vector<std::string> pub_topic_name;
    std::string msg_type;
  };

  struct ProxyActions {
    std::string name;
    struct {
      std::string executor;
      std::vector<TopicMeta> topic_meta_list;
    } options;
  };

  struct {
    std::vector<Path> type_support_pkgs;
    std::vector<ProxyActions> proxy_actions;
  } options;
};

struct topic_logger {
  std::string name{"topic_logger_plugin"};
  std::string path{"libaimrt_topic_logger_plugin.so"};
};

}  // namespace aimrte::cfg::backend::plugin
