// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/sys/internal/fs.h"
#include "src/utils/utils.h"
#include <optional>
#include "./env.h"

namespace aimrte::cfg::backend::log
{
/**
 * @brief 日志配置的基础内容，仅包含关键字
 */
struct meta {
  std::string type;
};

/**
 * @brief 控制台打印日志的配置
 */
struct console {
  std::string type{"console"};

  struct Option {
    std::optional<bool> color;
    std::optional<std::string> module_filter;
    std::optional<std::string> log_executor_name;
  };

  std::optional<Option> options;
};

/**
 * @brief 落盘日志的配置
 */
struct rotate_file {
  std::string type{"rotate_file"};

  struct {
    std::string path{DefaultLogPath()};
    std::string filename{cfg::details::ProcName() + ".log"};
    std::optional<std::uint32_t> max_file_size_m;
    std::optional<std::uint32_t> max_file_num;
    std::optional<std::string> module_filter;
    std::optional<std::string> log_executor_name;
    std::optional<std::string> pattern;
    std::optional<bool> enable_sync;
    std::optional<std::uint32_t> sync_interval_ms;
    std::optional<std::string> sync_executor_name;
  } options;

 private:
  static std::string DefaultLogPath();
};

/**
 * @brief Topic 日志后端的配置(用于将日志输出到指定的 Topic 中，数据回环)
 */
struct topic_logger {
  std::string type{"topic_logger"};

  struct {
    std::string topic_name;
    std::string timer_executor_name;
    uint32_t interval_ms;
    size_t max_msg_size;
  } options;
};

}  // namespace aimrte::cfg::backend::log
