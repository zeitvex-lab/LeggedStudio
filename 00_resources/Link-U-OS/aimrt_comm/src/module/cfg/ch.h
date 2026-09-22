// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <optional>
#include <string>
#include <vector>

#include "./basic.h"

/**
 * @brief channel 的各种后端配置
 */
namespace aimrte::cfg::backend::ch
{
/**
 * @brief ch backend 的基础内容，仅包含关键字
 */
struct meta {
  std::string type;
};

/**
 * @brief ros2 channel backend options
 */
struct ros2 {
  using QosOptions = details::QosOptions;

  struct PubOption {
    std::string topic_name;
    std::optional<QosOptions> qos;
  };

  using SubOption = PubOption;

  struct Option {
    std::optional<std::vector<PubOption>> pub_topics_options;
    std::optional<std::vector<SubOption>> sub_topics_options;
  };

  std::string type{"ros2"};
  std::optional<Option> options;
};

/**
 * @brief mqtt channel backend options
 */
struct mqtt {
  struct PubOption {
    std::string topic_name;
    std::optional<int> qos;
  };

  using SubOption = PubOption;

  struct Option {
    std::optional<std::vector<PubOption>> pub_topics_options;
    std::optional<std::vector<SubOption>> sub_topics_options;
  };

  std::string type{"mqtt"};
  std::optional<Option> options;
};

/**
 * @brief http channel backend options
 */
struct http {
  struct PubOption {
    std::string topic_name;
    std::vector<std::string> server_url_list;
  };

  struct Option {
    std::optional<std::vector<PubOption>> pub_topics_options;
  };

  std::string type{"http"};
  std::optional<Option> options;
};

/**
 * @brief tcp channel backend options
 */
struct tcp {
  using Option = http::Option;

  std::string type{"tcp"};
  std::optional<Option> options;
};

/**
 * @brief udp channel backend options
 */
struct udp {
  using Option    = http::Option;
  using PubOption = http::PubOption;

  std::string type{"udp"};
  std::optional<Option> options;
};

/**
 * @brief lcm channel backend options
 */
struct lcm {
  struct PubOption {
    std::string topic_name;
    std::optional<std::string> lcm_url;
    std::optional<int> priority;
  };

  struct SubOption {
    std::string topic_name;
    std::optional<std::string> lcm_url;
    std::optional<int> priority;
    std::optional<std::string> executor;
    std::optional<std::string> lcm_dispatcher_executor;
  };

  struct Option {
    std::optional<std::string> sub_default_executor;
    std::optional<std::vector<PubOption>> pub_topic_options;
    std::optional<std::vector<SubOption>> sub_topic_options;
  };

  std::string type{"lcm"};
  std::optional<Option> options;
};

/**
 * @brief local channel backend options
 */
struct local {
  struct Option {
    std::optional<bool> subscriber_use_inline_executor;
    std::optional<std::string> subscriber_executor;
  };

  std::string type{"local"};
  std::optional<Option> options;
};

/**
 * @brief monitor channel backend options
 */
struct monitor {
  struct Option {
    std::optional<std::string> executor;
  };

  std::string type{"monitor"};
  std::optional<Option> options;
};

/**
 * @brief zenoh channel backend options
 */
struct zenoh {
  std::string type{"zenoh"};
};

/**
 * @brief iceoryx channel backend options
 */
struct iceoryx {
  struct Option {
    std::optional<std::string> listener_thread_name;
    std::optional<std::string> listener_thread_sched_policy;
    std::optional<std::vector<std::uint32_t>> listener_thread_bind_cpu;
  };

  std::string type{"iceoryx"};
  std::optional<Option> options;
};
}  // namespace aimrte::cfg::backend::ch
