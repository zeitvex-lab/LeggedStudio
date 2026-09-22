// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once
#include "src/protocols/plugins/record_playback_plugin/record_playback_plugin_new.aimrt_rpc.pb.h"
#include "aimdk/protocol/hds/exception_channel.pb.h"
#include "record_playback_msgs/msg/record_upload.hpp"
#include "ros2/record_playback/GetActionList/GetActionList.h"
#include "ros2/record_playback/GetBagList/GetBagList.h"
#include "ros2/record_playback/StartRecord/StartRecord.h"
#include "ros2/record_playback/StopRecord/StopRecord.h"
#include "ros2/record_playback/GetUploadAllowed/GetUploadAllowed.h"
#include "ros2/record_playback/UpdateRecordAction/UpdateRecordAction.h"
#include "src/all_in_one/include/aimrte.h"
#include <cstdint>
#include <filesystem>
#include <malloc.h>
#include <atomic>
#include "parse_cmd.h"
namespace fs = std::filesystem;

namespace recordplayback
{

class record_module final : public aimrte::Mod
{
 public:

  enum class SocIndex {
    X86  = 0,
    ORIN = 1
  };
  struct Option {
    aimrte::Exe exe{"record_file_control_thread"};
    long long  max_file_size;
    aimrte::ctx::Subscriber<aimdk::protocol::ModuleExceptionChannel> exception_channel_sub{"/aima/hds/exception"};
    SocIndex soc_index_{SocIndex::ORIN};
  };


 public:
   void OnConfigure(aimrte::ctx::ModuleCfg &cfg) override;
   bool OnInitialize() override;
   bool OnStart() override;
   void OnShutdown() override;

 private:
 struct FileInfo {
    fs::path path;
    std::uint64_t size;
    std::time_t last_write_time;
  };

  Option option_;
  std::unique_ptr<aimrt::protocols::record_playback_plugin::RecordPlaybackServiceSyncProxy> record_proxy_{nullptr};

  std::atomic<bool> is_wifi_{false};
  std::atomic<bool> need_upload_{true};
  std::atomic<bool> is_start_inter_{false};

  std::shared_mutex start_inter_timestamp_mutex_;
  uint64_t start_inter_timestamp_;

  std::shared_mutex record_action_files_mutex_;
  std::unordered_map<std::string, std::set<std::string>> record_action_files;

  bool UpdateMetadata(const std::string& action_name, const std::string& mode);
  bool StartRecordSignalAction(const std::string& action_name, const uint32_t& preparation_duration_s, const uint32_t& record_duration_s, const bool need_upload);
  bool StopRecordSignalAction(const std::string& action_name);
  void SetUploadState(const bool disable);
  bool UpdateActionEnable(const std::string& action_name, const bool record_enabled);
  bool UpdateRecordAction(const record_playback_msgs::srv::UpdateRecordAction::Request& req);

private:
  void MainLoop();

  std::vector<FileInfo> getDbFiles(const fs::path&);
  std::uint64_t calculateTotalSize(const std::vector<FileInfo>&);
  void deleteOldestFiles(std::vector<FileInfo>& , std::uint64_t);
  void modifyYamls(struct FileInfo& fileInfo);
};

} // namespace recordplayback
