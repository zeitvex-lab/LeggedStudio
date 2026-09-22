// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "record.h"
#include <cstdint>
#include "gflags/gflags.h"
#include <filesystem>
namespace fs = std::filesystem;

namespace recordplayback{

  void record_module::OnConfigure(aimrte::ctx::ModuleCfg &cfg) {
    using  namespace aimrte;
    option_.soc_index_ = aimrte::sys::GetSOCIndex() == 1 ? record_module::SocIndex::ORIN : record_module::SocIndex::X86;

    cfg
      [cfg::Module::Executor]
        .Declare(option_.exe);

    if (option_.soc_index_ == record_module::SocIndex::ORIN) {
      cfg
        [cfg::Ch::udp | cfg::Ch::ros2 ]
        .Def(option_.exception_channel_sub);
    }
    option_.max_file_size = 1LL * soc_cfg_.all_bag_size * 1024 * 1024 * 1024;
  }

  bool record_module::OnInitialize() {
    AIMRTE_INFO("Initialize module {}, soc_index {} .", GetInfo().name, option_.soc_index_);
    record_proxy_ = std::make_unique<aimrt::protocols::record_playback_plugin::RecordPlaybackServiceSyncProxy>(GetCoreRef().GetRpcHandle());
    record_proxy_->RegisterClientFunc(GetCoreRef().GetRpcHandle());


    return true;
  }

  bool record_module::OnStart() {
    AIMRTE_INFO("Start module {}.", GetInfo().name);
    option_.exe.Post([this]() {
      MainLoop();
    });
    return true;
  }

  void record_module::OnShutdown() {
    AIMRTE_INFO("Shutdown module {}.", GetInfo().name);
  }

  bool record_module::UpdateMetadata(const std::string& action_name, const std::string& mode)
  {
    if (record_proxy_ == nullptr) {
      return false;
    }

    ::aimrt::protocols::record_playback_plugin::UpdateMetadataReq req;
    ::aimrt::protocols::record_playback_plugin::CommonRsp rsp;
    req.set_action_name(action_name);
    req.mutable_kv_pairs()->emplace("robot_model", aimrte::sys::GetModel());
    req.mutable_kv_pairs()->emplace("robot_sn", aimrte::sys::GetSN());
    req.mutable_kv_pairs()->emplace("soc_index", std::to_string(aimrte::sys::GetSOCIndex()));
    req.mutable_kv_pairs()->emplace("bag_id", aimrte::utils::GenerateUuid());
    req.mutable_kv_pairs()->emplace("release_version", aimrte::sys::GetReleaseVersion());
    req.mutable_kv_pairs()->emplace("proto_version", aimrte::sys::GetProtocolVersion());
    req.mutable_kv_pairs()->emplace("record_mode", mode);
    req.mutable_kv_pairs()->emplace("record_action", action_name);
    auto status = record_proxy_->UpdateMetadata(req, rsp);
    if (!status.OK()) {
      AIMRTE_WARN("Update metadata failed: code={}, msg={}", status.Code(), aimrt::rpc::Status::GetCodeMsg(status.Code()));
      return false;
    }
    AIMRTE_INFO("Update metadata success");
    return true;
  }

  bool record_module::StartRecordSignalAction(const std::string& action_name, const uint32_t& preparation_duration_s, const uint32_t& record_duration_s, const bool need_upload)
  {
    if (record_proxy_ == nullptr) {
      return false;
    }

    ::aimrt::protocols::record_playback_plugin::StartRecordReq start_req;
    ::aimrt::protocols::record_playback_plugin::StartRecordRsp start_rsp;
    start_req.set_action_name(action_name);
    start_req.set_preparation_duration_s(preparation_duration_s);
    start_req.set_record_duration_s(record_duration_s);
    auto start_status = record_proxy_->StartRecord(start_req, start_rsp);
    if (!start_status.OK()) {
      AIMRTE_WARN("StartRecord action={} pre={} dur={} failed: code={}, msg={}", action_name, preparation_duration_s, record_duration_s, start_status.Code(), aimrt::rpc::Status::GetCodeMsg(start_status.Code()));
      return false;
    }
    auto filefolder = start_rsp.filefolder();
    if (!filefolder.empty() && need_upload) {
      std::unique_lock<std::shared_mutex> lock(record_action_files_mutex_);
      record_action_files[action_name].insert(filefolder);
    }
    AIMRTE_INFO("StartRecord action={} pre={} dur={} success: code={}, msg={}", action_name, preparation_duration_s, record_duration_s, start_status.Code(), aimrt::rpc::Status::GetCodeMsg(start_status.Code()));
    AIMRTE_INFO("action file folder is: {} ", start_rsp.filefolder());
    UpdateMetadata(action_name, "signal");
    return true;
  }

  bool record_module::StopRecordSignalAction(const std::string& action_name)
  {
    if (record_proxy_ == nullptr) {
      return false;
    }

    ::aimrt::protocols::record_playback_plugin::StopRecordReq stop_req;
    ::aimrt::protocols::record_playback_plugin::CommonRsp stop_rsp;
    stop_req.set_action_name(action_name);
    auto stop_status = record_proxy_->StopRecord(stop_req, stop_rsp);
    if (!stop_status.OK()) {
      AIMRTE_WARN("StopRecord action={} failed: code={}, msg={}", action_name, stop_status.Code(), aimrt::rpc::Status::GetCodeMsg(stop_status.Code()));
      return false;
    }
    AIMRTE_INFO("StopRecord action={} success: code={}, msg={}", action_name, stop_status.Code(), aimrt::rpc::Status::GetCodeMsg(stop_status.Code()));
    return true;
  }

  bool record_module::UpdateActionEnable(const std::string& action_name, const bool record_enabled)
  {
    if (record_proxy_ == nullptr) {
      return false;
    }

    ::aimrt::protocols::record_playback_plugin::UpdateRecordActionReq enable_req;
    ::aimrt::protocols::record_playback_plugin::UpdateRecordActionRsp enable_rsp;
    enable_req.set_action_name(action_name);
    enable_req.set_record_enabled(record_enabled);
    auto enable_status = record_proxy_->UpdateRecordAction(enable_req, enable_rsp);
    if (!enable_status.OK()) {
      AIMRTE_WARN("UpdateActionEnable action={} record_enabled={} failed: code={}, msg={}",
        action_name, record_enabled, enable_status.Code(), aimrt::rpc::Status::GetCodeMsg(enable_status.Code()));
      return false;
    }
    if (enable_rsp.common_rsp().code() != 0) {
      AIMRTE_WARN("UpdateActionEnable action={} record_enabled={} failed: errorcode={}",
        action_name, record_enabled, enable_rsp.common_rsp().code());
      return false;
    }
    AIMRTE_INFO("UpdateActionEnable action={} record_enabled={} success: code={}, msg={}",
      action_name, record_enabled, enable_status.Code(), aimrt::rpc::Status::GetCodeMsg(enable_status.Code()));

    auto action = std::find_if(soc_cfg_.actions.begin(), soc_cfg_.actions.end(), [&action_name](const Action& a) {
                      return a.action_name == action_name;
                  });
    if (action == soc_cfg_.actions.end()) {
      AIMRTE_ERROR("action_name {} not found.", action_name);
      return false;
    }
    action->record_enabled_now = record_enabled;
    return true;
  }

  bool record_module::UpdateRecordAction(const record_playback_msgs::srv::UpdateRecordAction::Request& req)
  {
    if (record_proxy_ == nullptr) {
      return false;
    }

    std::string action_name = req.action_name;
    ::aimrt::protocols::record_playback_plugin::UpdateRecordActionReq upt_req;
    ::aimrt::protocols::record_playback_plugin::UpdateRecordActionRsp upt_rsp;
    upt_req.set_action_name(action_name);
    upt_req.set_record_enabled(req.record_enabled);
    for (const auto& meta : req.topic_metas) {
      ::aimrt::protocols::record_playback_plugin::TopicMeta* pb_meta = upt_req.add_topic_metas();
      pb_meta->set_topic_name(meta.topic_name);
      pb_meta->set_msg_type(meta.msg_type);
      pb_meta->set_record_enabled(meta.record_enabled);
    }
    auto upt_status = record_proxy_->UpdateRecordAction(upt_req, upt_rsp);
    if (!upt_status.OK()) {
      AIMRTE_WARN("UpdateRecordAction action={} failed: code={}, msg={}",
        action_name, upt_status.Code(), aimrt::rpc::Status::GetCodeMsg(upt_status.Code()));
      return false;
    }
    if (upt_rsp.common_rsp().code() != 0) {
      AIMRTE_WARN("UpdateRecordAction action={} failed: errorcode={}",
        action_name, upt_rsp.common_rsp().code());
      return false;
    }
    AIMRTE_INFO("UpdateRecordAction action={} success: code={}, msg={}",
      action_name, upt_status.Code(), aimrt::rpc::Status::GetCodeMsg(upt_status.Code()));

    auto action = std::find_if(soc_cfg_.actions.begin(), soc_cfg_.actions.end(), [&action_name](const Action& a) {
                      return a.action_name == action_name;
                  });
    if (action == soc_cfg_.actions.end()) {
      AIMRTE_ERROR("action_name {} not found.", action_name);
      return false;
    }
    action->record_enabled_now = req.record_enabled;
    return true;
  }

  void record_module::MainLoop() {
    if (!soc_cfg_.is_fctl) {
      AIMRTE_INFO("Main Loop Not in fctl mode.");
      return;
    }

    aimrte::ctx::exe(option_.exe).Post([this]() -> aimrt::co::Task<void> {
      int64_t count = 0;
      while (aimrte::ctx::Ok()) {
        co_await aimrte::ctx::Sleep(std::chrono::seconds(3));
        if(!fs::exists(soc_cfg_.record_bag_path)){
          AIMRTE_INFO("bag_file_path not exists: {}", soc_cfg_.record_bag_path);
          continue;
        }
        auto files = getDbFiles(soc_cfg_.record_bag_path);
        deleteOldestFiles(files, option_.max_file_size);

        for (auto& action : soc_cfg_.actions) {
          if (action.is_enable && !action.has_update_metadata && action.mode == "imd") {
            action.has_update_metadata = UpdateMetadata(action.action_name, action.mode);
          }
        }

        if (++count % 600 == 0) {
          malloc_trim(1024 * 1024);
        }
      }
    });

  }

  std::vector<record_module::FileInfo> record_module::getDbFiles(const fs::path& directory) {
    std::vector<FileInfo> db3Files;
    for (const auto& entry : fs::recursive_directory_iterator(directory)) {
      if (entry.is_directory()) {
        continue;
      }
    if (entry.is_regular_file() && (entry.path().extension() == ".db3" || entry.path().extension() == ".mcap")) {
        db3Files.push_back(FileInfo{entry.path(), entry.file_size(), fs::last_write_time(entry).time_since_epoch().count()});
      }
    }
    return db3Files;
  }

  std::uint64_t record_module::calculateTotalSize(const std::vector<FileInfo>& files) {
      return std::accumulate(files.begin(), files.end(),
          static_cast<std::uint64_t>(0),
          [](std::uint64_t sum, const FileInfo& file) {
              return sum + file.size;
      });
  }

  void record_module::deleteOldestFiles(std::vector<FileInfo>& files, std::uint64_t maxCapacity) {
    std::sort(files.begin(), files.end(), [](const FileInfo& filea, const FileInfo& fileb) {
      return filea.last_write_time < fileb.last_write_time; // 按文件的最后修改时间升序排序
  });

    auto currentSize = calculateTotalSize(files);
    for (auto& file : files) {
      if (currentSize <= maxCapacity) {
        break;
      }
      if (fs::exists(file.path)) {
        AIMRTE_INFO("currentSize: {} , maxCapacity: {}, delete file: {}, fileSize: {}", currentSize , maxCapacity, file.path.string(), file.size);
        currentSize -= file.size;
        modifyYamls(file);
        fs::remove(file.path);
      }
      fs::path parentDir = file.path.parent_path();
      bool hasDBFile = std::any_of(fs::directory_iterator(parentDir), fs::directory_iterator(), [](const fs::directory_entry& entry) {
        return entry.is_regular_file() && (entry.path().extension() == ".db3" || entry.path().extension() == ".mcap");
      });

      if (!hasDBFile && fs::exists(parentDir)) {
        AIMRTE_INFO("Delete directory: {}", parentDir);
        fs::remove_all(parentDir);
      }
    }
  }

  void record_module::modifyYamls(FileInfo &fileInfo) {
    try {
      std::string yaml_file_path = fileInfo.path.parent_path().string() + "/metadata.yaml";
      if(!fs::exists(yaml_file_path)){
        AIMRTE_INFO("No metadata.yaml found in {}", fileInfo.path.parent_path().string());
        return;
      }

      YAML::Node config = YAML::LoadFile(yaml_file_path);
      if (!config["aimrt_bagfile_information"] || !config["aimrt_bagfile_information"]["files"]) {
        AIMRTE_ERROR("metadata.yaml without aimrt_bagfile_information or files");
        return;
      }
      std::string delete_file = fileInfo.path.filename().string();
      YAML::Node files = config["aimrt_bagfile_information"]["files"];
      YAML::Node new_files;
      for (const auto& file : files) {
        if (!file["path"]) {
          AIMRTE_WARN("metadata.yaml without path");
          continue;
        }
        if (file["path"].as<std::string>() != delete_file) {
          new_files.push_back(file);
        }
      }
      config["aimrt_bagfile_information"]["files"] = new_files;

      std::ofstream fout(yaml_file_path);
      if (!fout) {
        AIMRTE_ERROR("failed to open output file: {}", yaml_file_path);
        return;
      }
      fout << config;
      fout.close();
      if (fout.fail()) {
        AIMRTE_ERROR("failed to write YAML file");
        return;
      }
    } catch (const YAML::Exception& e) {
        AIMRTE_ERROR("YAML error: {}", e.what());
    } catch (const std::exception& e) {
        AIMRTE_ERROR("system error: {}", e.what());
    } catch (...) {
        AIMRTE_ERROR("catch unknown exception");
    }
  }
} // namespace recordplayback
