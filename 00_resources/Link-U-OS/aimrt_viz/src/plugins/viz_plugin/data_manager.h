// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#pragma once

#include <yaml-cpp/yaml.h>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

#include "core/aimrt_core.h"
#include "core/channel/channel_backend_manager.h"
#include "core/channel/channel_manager.h"
#include "core/channel/channel_msg_wrapper.h"
#include "global.h"
#include "google/protobuf/descriptor.pb.h"
#include "process_info.h"

// #include "viz_plugin.pb.h"
#ifdef GOOGLE_PROTOBUF_USING_BAZEL
  #include "src/protocols/viz_plugin/viz_plugin.aimrt_rpc.pb.h"
#else
  #include "viz_plugin.aimrt_rpc.pb.h"
#endif

#include "schema_info.h"
#include "util.h"

namespace aimrt::plugins::viz_plugin {

class DataManager {
 public:
  bool Initialize(aimrt::runtime::core::AimRTCore* core_ptr);
  void SetConfig();
  void SetLog();
  void SetBaseInfo(const std::string& node_name, const std::string& soc);
  void SetPluginList();
  void SetExecutorList();

  void SetBackends();

  void SetPubChannel();
  void SetSubChannel();
  void SetRpcClient();
  void SetRpcServer();
  void SetModuleInfo();

  void OnSubscribe(runtime::core::channel::MsgWrapper& msg_wrapper);
  void OnPublish(runtime::core::channel::MsgWrapper& msg_wrapper);
  void OnRpcClient(const std::shared_ptr<aimrt::runtime::core::rpc::InvokeWrapper>& wrapper_ptr, aimrt::rpc::Status& status, uint64_t begin_time_stamp_us);
  void OnRpcServer(const std::shared_ptr<aimrt::runtime::core::rpc::InvokeWrapper>& wrapper_ptr, aimrt::rpc::Status& status, uint64_t begin_time_stamp_us);

  void ReportNodeInfo(const aimrt::protocols::viz_plugin::NodeInfoRequest& req, aimrt::protocols::viz_plugin::NodeInfoResponse& rsp);
  void SetStaticReply(aimrt::protocols::viz_plugin::NodeInfoResponse& rsp);
  void SetDynamicReply(aimrt::protocols::viz_plugin::NodeInfoResponse& rsp);

  void DoUpdateDynamicInfo();

 private:
  aimrt::runtime::core::AimRTCore* core_ptr_ = nullptr;

  std::shared_ptr<ProcessInfoManager> process_info_manager_ptr_;

  std::mutex dynamic_mtx_;
  std::shared_ptr<DynamicInfoWrapper> dynamic_info_wrapper_ptr_;
  uint64_t prev_time_stamp_ns_ = 0;

  DynamicInfoWrapper dynamic_info_wrapper_;
  StaticInfoWrapper static_info_wrapper_;

  std::unordered_map<TopicMetaKey, ChannelDynamicRecord, TopicMetaKey::Hash> channel_pub_stats_map_;
  std::unordered_map<TopicMetaKey, ChannelDynamicRecord, TopicMetaKey::Hash> channel_sub_stats_map_;
  std::unordered_map<RpcMetaKey, RpcDynamicRecord, RpcMetaKey::Hash> rpc_client_stats_map_;
  std::unordered_map<RpcMetaKey, RpcDynamicRecord, RpcMetaKey::Hash> rpc_server_stats_map_;
};

}  // namespace aimrt::plugins::viz_plugin
