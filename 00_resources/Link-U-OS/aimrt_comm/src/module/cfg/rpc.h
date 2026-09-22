// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <optional>
#include <string>
#include <vector>

#include "./basic.h"

/**
 * @brief rpc 的各种后端配置
 */
namespace aimrte::cfg::backend::rpc
{
/**
 * @brief rpc backend 的基础内容，仅包含关键字
 */
struct meta {
  std::string type;
};

/**
 * @brief ros2 rpc backend options
 */
struct ros2 {
  using QosOptions = details::QosOptions;

  struct CliOption {
    std::string func_name;
    std::optional<QosOptions> qos;
  };

  using SrvOption = CliOption;

  struct Option {
    std::optional<std::string> timeout_executor;
    std::optional<std::vector<CliOption>> clients_options;
    std::optional<std::vector<SrvOption>> servers_options;
  };

  std::string type{"ros2"};
  std::optional<Option> options;
};

/**
 * @brief mqtt rpc backend options
 */
struct mqtt {
  struct CliOption {
    std::string func_name;
    std::optional<std::string> server_mqtt_id;
  };

  struct SrvOption {
    std::string func_name;
    std::optional<bool> allow_share;
  };

  struct Option {
    std::optional<std::string> timeout_executor;
    std::optional<std::vector<CliOption>> clients_options;
    std::optional<std::vector<SrvOption>> servers_options;
  };

  std::string type{"mqtt"};
  std::optional<Option> options;
};

/**
 * @brief omp rpc backend options
 */
struct omp {
  struct Option {
    std::optional<std::string> timeout_executor;
  };

  std::string type{"omp"};
  std::optional<Option> options;
};

/**
 * @brief http rpc backend options
 */
struct http {
  struct CliOption {
    std::string func_name;
    std::string server_url;
  };

  struct Option {
    std::optional<std::vector<CliOption>> clients_options;
  };

  std::string type{"http"};
  std::optional<Option> options;
};

/**
 * @brief local rpc backend options
 */
struct local {
  std::string type{"local"};
};

/**
 * @brief monitor rpc backend options
 */
struct monitor {
  struct Option {
    std::optional<std::string> executor;
  };

  std::string type{"monitor"};
  std::optional<Option> options;
};

/**
 * @brief zenoh rpc backend options
 */
struct zenoh {
  struct Option {
    std::optional<std::string> timeout_executor;
  };

  std::string type{"zenoh"};
  std::optional<Option> options;
};
}  // namespace aimrte::cfg::backend::rpc
