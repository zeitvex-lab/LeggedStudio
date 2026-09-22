// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once
#include <map>
#include <set>
#include <string>
#include <vector>
#include "src/interface/aimrt_module_cpp_interface/util/buffer.h"
#include "src/interface/aimrt_module_cpp_interface/util/type_support.h"

namespace aimrte::plugin::monitor
{

struct TopicInfo {
  std::string_view topic_name;
  std::string_view msg_type;
  std::vector<std::string> backends;

  bool operator<(const TopicInfo& other) const
  {
    return std::tie(topic_name, msg_type) < std::tie(other.topic_name, other.msg_type);
  }

  bool operator==(const TopicInfo& other) const
  {
    return topic_name == other.topic_name && msg_type == other.msg_type;
  }
};

struct TopicInfoHash {
  std::size_t operator()(const TopicInfo& info) const
  {
    return std::hash<std::string>()(std::string(info.topic_name)) ^ (std::hash<std::string>()(std::string(info.msg_type)) << 1);
  }
};

struct RpcFuncInfo {
  std::string_view func_name;
  std::string_view req_type;
  std::string_view rsp_type;
  std::vector<std::string> backends;
  bool operator<(const RpcFuncInfo& other) const
  {
    return (func_name < other.func_name) and (req_type < other.req_type) and (rsp_type < other.rsp_type);
  }
};

struct ModuleInfo {
  std::string_view name;
  std::string_view pkg_path;
  uint32_t major_version = 0;
  uint32_t minor_version = 0;
  uint32_t patch_version = 0;
  uint32_t build_version = 0;

  std::string_view author;
  std::string_view description;
  std::string_view cfg_file_path;
  std::set<TopicInfo> pub_topic;
  std::set<TopicInfo> sub_topic;
  std::set<RpcFuncInfo> rpc_service;  // 提供的rpc服务
  std::set<RpcFuncInfo> rpc_invoke;   // 调用的rpc服务
};

}  // namespace aimrte::plugin::monitor
