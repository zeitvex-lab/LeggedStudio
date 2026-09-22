// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "gflags/gflags.h"
#include <vector>
#include "parse_cmd.h"
#include "record.h"
#include "util.h"

using namespace recordplayback;

DEFINE_string(type_support_pkg, "", "--type_support_pkg=[libexample_event_type_support_pkg.so]");

int main(int argc, char *argv[])
{
  aimrte::Cfg cfg(argc, argv, "recordbag");
  cfg
    .WithDefaultLogger();

  if (!METATOPICPATH.empty()) {
    ParseTopicYaml(METATOPICPATH, topic_map_);
  }

  if (!YAMLPATH.empty()) {
    soc_cfg_ = LoadConfig(YAMLPATH);
  }

  std::vector<record_playback::Path> type_support_pkgs_name_list;
  if(!FLAGS_type_support_pkg.empty()) {
    ParseTypeSupport(FLAGS_type_support_pkg, type_support_pkgs_name_list);
  } else {
    aimrte::utils::GetTypeSupportPkgs<record_playback::Path>(aimrte::utils::Env("LD_LIBRARY_PATH"), type_support_pkgs_name_list);
  }

  RecordPlaybackSetting(cfg, soc_cfg_, type_support_pkgs_name_list);
  MqttPluginSetting(cfg);
  NetPluginSetting(cfg);
  cfg[aimrte::cfg::Exe::asio_thread] += {
    .name = "record_file_control_thread",
    .options = {{.thread_num = 4}},
  };

  return  aimrte::Run(cfg, {{"recordbag", std::make_shared<recordplayback::record_module>()}});
}
