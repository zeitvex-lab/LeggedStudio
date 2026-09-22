// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <optional>
#include <string>
#include <vector>

namespace aimrte::cfg::exe
{
/**
 * @brief 执行器的基础内容，仅包含关键字
 */
struct meta {
  std::string type;
  std::string name;
};

/**
 * @brief main_thread 配置
 */
struct main_thread {
  std::optional<std::string> name;
  std::optional<std::string> thread_sched_policy;
  std::optional<std::vector<std::uint32_t>> thread_bind_cpu;
};

/**
 * @brief guard_thread 配置
 */
struct guard_thread {
  std::optional<std::string> name;
  std::optional<std::string> thread_sched_policy;
  std::optional<std::vector<std::uint32_t>> thread_bind_cpu;
};

/**
 * @brief simple_thread 执行器配置
 */
struct simple_thread {
  struct Option {
    std::optional<std::string> thread_sched_policy;
    std::optional<std::vector<std::uint32_t>> thread_bind_cpu;
    std::optional<std::uint32_t> queue_threshold;
  };

  std::string type{"simple_thread"};
  std::string name;
  std::optional<Option> options;
};

/**
 * @brief asio_thread 执行器配置
 */
struct asio_thread {
  struct Option {
    std::optional<std::uint32_t> thread_num;
    std::optional<std::string> thread_sched_policy;
    std::optional<std::vector<std::uint32_t>> thread_bind_cpu;
    std::optional<std::uint32_t> timeout_alarm_threshold_us;
  };

  std::string type{"asio_thread"};
  std::string name;
  std::optional<Option> options;
};

/**
 * @brief asio_strand 执行器配置
 */
struct asio_strand {
  std::string type{"asio_strand"};
  std::string name;
  struct {
    std::string bind_asio_thread_executor_name;
    std::optional<std::uint32_t> timeout_alarm_threshold_us;
  } options;
};

/**
 * @brief tbb_thread 执行器配置
 */
struct tbb_thread {
  using Option = asio_thread::Option;

  std::string type{"tbb_thread"};
  std::string name;
  std::optional<Option> options;
};

/**
 * @brief time_wheel 执行器配置
 */
struct time_wheel {
  struct Option {
    std::optional<std::string> bind_executor;
    std::optional<std::uint32_t> dt_us{50000};
    std::optional<std::uint32_t> wheel_size;
    std::optional<std::string> threads_ched_policy;
    std::optional<std::vector<std::uint32_t>> thread_bind_cpu;
  };

  std::string type{"time_wheel"};
  std::string name;
  std::optional<Option> options;
};
}  // namespace aimrte::cfg::exe
