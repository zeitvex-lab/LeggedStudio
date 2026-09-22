// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <variant>
#include <vector>
#include "viz_module/common.h"
#ifdef GOOGLE_PROTOBUF_USING_BAZEL
  #include "src/protocols/viz_plugin/viz_plugin.aimrt_rpc.pb.h"
  #include "src/protocols/viz_web/viz_web.aimrt_rpc.pb.h"
  #include "version.h"  // 版本号头文件，bazel 编译时会自动生成
#else
  #include "viz_plugin.aimrt_rpc.pb.h"
  #include "viz_web.aimrt_rpc.pb.h"
#endif

namespace aimrt_viz::viz_module {
struct NodeInfoWrapper {
  StaticInfo static_info;
  DynamicInfo dynamic_info;
  std::vector<uint32_t> resource_ids;
};

struct RpcInfoWrapper {
  std::string req_type;
  std::string rsp_type;
  uint32_t req_schema_id;
  uint32_t rsp_schema_id;
  std::unordered_map<std::string, int32_t> used_backends;
  std::unordered_map<std::string, int32_t> used_filters;

  std::unordered_map<NodeModeKey, RpcDynamicInfoMeta, NodeModeKey::Hash> server_dynamic_info_map;
  std::unordered_map<NodeModeKey, RpcDynamicInfoMeta, NodeModeKey::Hash> client_dynamic_info_map;
};

struct ChannelInfoWrapper {
  uint32_t schema_id;
  std::unordered_map<std::string, int32_t> used_backends;
  std::unordered_map<std::string, int32_t> used_filters;

  std::unordered_map<NodeModeKey, ChannelDynamicMeta, NodeModeKey::Hash> sub_dynamic_info;
  std::unordered_map<NodeModeKey, ChannelDynamicMeta, NodeModeKey::Hash> pub_dynamic_info;
};

enum class ResourceType {
  NONE,
  STRING,
  BYTE_VECTOR,
};

struct ResourceInfoWrapper {
  ResourceInfoWrapper(ResourceType type, std::variant<std::string, std::vector<std::byte>> data) : data(data), type(type) {}
  std::variant<std::string, std::vector<std::byte>> data;
  ResourceType type;
};

struct InfoRegistry {
  InfoRegistry() = default;

  InfoRegistry(const InfoRegistry& other) : version(other.version) {
    for (const auto& pair : other.node_info_registry_) {
      if (pair.second) {
        node_info_registry_[pair.first] = std::make_shared<NodeInfoWrapper>(*(pair.second));
      } else {
        node_info_registry_[pair.first] = nullptr;
      }
    }

    for (const auto& pair : other.rpc_info_registry_) {
      if (pair.second) {
        rpc_info_registry_[pair.first] = std::make_shared<RpcInfoWrapper>(*(pair.second));
      } else {
        rpc_info_registry_[pair.first] = nullptr;
      }
    }

    for (const auto& pair : other.channel_info_registry_) {
      if (pair.second) {
        channel_info_registry_[pair.first] = std::make_shared<ChannelInfoWrapper>(*(pair.second));
      } else {
        channel_info_registry_[pair.first] = nullptr;
      }
    }

    for (const auto& pair : other.resource_info_registry_) {
      if (pair.second) {
        resource_info_registry_[pair.first] = std::make_shared<ResourceInfoWrapper>(*(pair.second));
      } else {
        resource_info_registry_[pair.first] = nullptr;
      }
    }
  }

  uint64_t version = 0;

  std::unordered_map<std::string, std::shared_ptr<NodeInfoWrapper>> node_info_registry_;
  std::unordered_map<RpcMetaKey, std::shared_ptr<RpcInfoWrapper>, RpcMetaKey::Hash> rpc_info_registry_;
  std::unordered_map<ChannelMetaKey, std::shared_ptr<ChannelInfoWrapper>, ChannelMetaKey::Hash> channel_info_registry_;
  std::unordered_map<uint32_t, std::shared_ptr<ResourceInfoWrapper>> resource_info_registry_;
};

class DataManager {
 public:
  void SetNodeRequire(aimrt::protocols::viz_plugin::NodeInfoRequest& req, const std::string& node_name);

  void SetSystemInfo(SystemInfo& system_info);
  void SetWebSystemInfoResponse(::aimrt::protocols::viz_web::SystemInfoResponse& rsp);

  void SetWebNodeBaseInfoResponse(::aimrt::protocols::viz_web::NodeBaseInfoResponse& rsp);
  void SetWebNodeDetailInfoResponse(const std::string& node_name, ::aimrt::protocols::viz_web::NodeDetailInfoResponse& rsp);
  void SetWebModuleDetailInfoResponse(const std::string& node_name, const std::string& module_name, ::aimrt::protocols::viz_web::ModuleDetailInfoResponse& rsp);

  void SetWebRpcIndexInfoResponse(::aimrt::protocols::viz_web::RpcIndexInfoResponse& rsp);
  void SetWebRpcDetailInfoResponse(const std::string& func_name, ::aimrt::protocols::viz_web::RpcDetailInfoResponse& rsp);

  void SetWebChannelIndexInfoResponse(::aimrt::protocols::viz_web::ChannelIndexInfoResponse& rsp);
  void SetWebChannelDetailInfoResponse(const std::string& topic_name, const std::string& msg_type, ::aimrt::protocols::viz_web::ChannelDetailInfoResponse& rsp);

  void SetWebResourceResponse(const uint32_t& resource_id, ::aimrt::protocols::viz_web::GetResourceResponse& rsp);

  void DeleteOfflineNodeInfo(std::shared_ptr<InfoRegistry> data_ptr, const std::string& node_name);

  void UpdateData(const std::unordered_map<std::string, std::optional<aimrt::protocols::viz_plugin::NodeInfoResponse>>& response_map);

  void UpdateNodeStaticData(StaticInfo& data_ptr,
                            std::vector<uint32_t>& resource_ids,
                            std::unordered_map<uint32_t, std::shared_ptr<ResourceInfoWrapper>>& resource_info_registry,
                            const ::aimrt::protocols::viz_plugin::StaticInfo& static_info);

  void UpdateNodeDynamicData(DynamicInfo& data_ptr, uint64_t start_time_stamp_ns,
                             const ::aimrt::protocols::viz_plugin::DynamicInfo& dynamic_info);

  void UpdateChannelDynamicKey(std::shared_ptr<InfoRegistry> data_ptr,
                               const ::aimrt::protocols::viz_plugin::StaticInfo& static_info);

  void UpdateChannelDynamicData(const std::string& node_name_svice,
                                std::shared_ptr<InfoRegistry> data_ptr,
                                const ::aimrt::protocols::viz_plugin::DynamicInfo& dynamic_info);

  void UpdateRpcDynamicKey(std::shared_ptr<InfoRegistry> data_ptr,
                           const ::aimrt::protocols::viz_plugin::StaticInfo& static_info);

  void UpdateRpcDynamicData(const std::string& node_name_svice,
                            std::shared_ptr<InfoRegistry> data_ptr,
                            const ::aimrt::protocols::viz_plugin::DynamicInfo& dynamic_info);

 private:
  mutable std::mutex m_mutex;
  int32_t resource_id_ = 1;
  std::shared_ptr<const InfoRegistry> m_active_data_ = std::make_shared<InfoRegistry>();
  SystemInfo system_info_;
};
}  // namespace aimrt_viz::viz_module