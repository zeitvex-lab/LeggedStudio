// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <thread>

#include <shared_mutex>
#include "./utils.h"
#include "src/interface/aimrt_module_cpp_interface/co/task.h"
#include "src/interface/aimrt_module_cpp_interface/rpc/rpc_status.h"
#include "src/common/topic_hz_calculator.h"
#include "boost/asio.hpp"
#include "boost/asio/spawn.hpp"
#include "boost/asio/strand.hpp"
#include "src/runtime/core/aimrt_core.h"
#include "src/runtime/core/util/module_detail_info.h"
#include "yaml-cpp/yaml.h"

namespace aimrte::plugin::monitor
{
class DataManager
{
 public:
  DataManager() = default;

  void ShutDown();

  /**
   * @brief 收集数据
   */
  aimrt::co::Task<void> CollectData();

  void OnPublishFilter(std::string_view topic_name, std::string_view msg_type);

  void OnSubscribeFilter(std::string_view topic_name, std::string_view msg_type);

  YAML::Node& GetDumpRootConfig();

  YAML::Node& GetOriginConfig();

  common::TopicHzCalculator::HzInfoMap GetPubTopicHzMap()
  {
    std::unique_lock<std::mutex> lock(mutext_);
    return pub_topic_hz_map_;
  }

  common::TopicHzCalculator::HzInfoMap GetSubTopicHzMap()
  {
    std::unique_lock<std::mutex> lock(mutext_);
    return sub_topic_hz_map_;
  }

 public:
  const std::set<TopicInfo>& GetSubTopicInfoList()
  {
    return sub_topic_set_;
  }

  void SetSubTopicInfoList(const std::set<TopicInfo>& sub_topic_set);

  const std::set<TopicInfo>& GetPubTopicInfoList()
  {
    return pub_topic_set_;
  }

  void SetPubTopicInfoList(const std::set<TopicInfo>& sub_topic_set);

  const std::set<RpcFuncInfo>& GetRpcServiceInfoList()
  {
    return rpc_service_info_set_;
  }

  void SetRpcServiceInfoList(const std::set<RpcFuncInfo>& rpc_service_info_set)
  {
    rpc_service_info_set_ = rpc_service_info_set;
  }

  const std::set<RpcFuncInfo>& GetRpcClientInfoList()
  {
    return rpc_client_info_set_;
  }

  void SetRpcClientInfoList(const std::set<RpcFuncInfo>& rpc_service_info_set)
  {
    rpc_client_info_set_ = rpc_service_info_set;
  }

  void SetOriOptionRootConf(const YAML::Node& node)
  {
    origin_option_root_ = node;
  }

  void SetOptionRootConf(const YAML::Node& node) { option_root_ = node; }

 private:
  aimrt::runtime::core::AimRTCore* core_ptr_;
  std::vector<const aimrt::runtime::core::util::ModuleDetailInfo*> module_detail_list_;

  std::set<TopicInfo> sub_topic_set_;
  std::set<TopicInfo> pub_topic_set_;

  std::set<RpcFuncInfo> rpc_service_info_set_;
  std::set<RpcFuncInfo> rpc_client_info_set_;

  std::mutex mutext_;

  std::atomic_bool init_flag_{false};

  YAML::Node origin_option_root_;
  YAML::Node option_root_;

  common::TopicHzCalculator sub_topic_hz_calculate_;
  common::TopicHzCalculator::HzInfoMap sub_topic_hz_map_;
  common::TopicHzCalculator pub_topic_hz_calculate_;
  common::TopicHzCalculator::HzInfoMap pub_topic_hz_map_;
};

}  // namespace aimrte::plugin::monitor
