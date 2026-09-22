// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "network.h"
#include <sys/statvfs.h>
#include <fstream>
#include "src/hds/interface.h"
#include "src/utils/execute.h"

#define BUFFSIZE 1024

namespace aima::monitor {

// 获取网络使用情况
void network::get_net_counter(std::map<std::string, NET_IO_COUNTER>& net_interfaces) {
  char buff[BUFFSIZE];
  FILE* fd;
  NET_IO_COUNTER io_counter;
  net_interfaces.clear();

  fd = fopen("/proc/net/dev", "r");
  if (fd == NULL) {
    perror("Failed to open /proc/net/dev");
    exit(EXIT_FAILURE);
  }
  // 跳过前两行数据
  fgets(buff, sizeof(buff), fd);
  fgets(buff, sizeof(buff), fd);

  while (fgets(buff, sizeof(buff), fd) != NULL) {
    unsigned int unused;
    sscanf(buff, "%s\t%lu\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t%lu ", io_counter.name, &io_counter.download_bytes, &unused, &unused,
           &unused, &unused, &unused, &unused, &unused, &io_counter.upload_bytes);
    if (auto ch = strchr(io_counter.name, ':')) {
      *ch = '\0';  // 去掉冒号
    }

    // 判断是否是可读字符的网卡名
    if (io_counter.name[0] == '\0' || !std::all_of(io_counter.name, io_counter.name + strlen(io_counter.name), ::isprint)) {
      AIMRTE_ERROR("Invalid network interface name: {}", io_counter.name);
      continue;
    }

    // 忽略掉 本地回环loop
    if (strncmp(io_counter.name, "lo", 2) != 0) {
      io_counter.steady_time = std::chrono::steady_clock::now();
      net_interfaces.emplace(std::string(io_counter.name), io_counter);
    }
  }
  fclose(fd);
}

std::pair<double, double> network::cal_up_down_speed(const NET_IO_COUNTER& c1, const NET_IO_COUNTER& c2) {
  auto download_bytes = c2.download_bytes - c1.download_bytes;
  auto upload_bytes = c2.upload_bytes - c1.upload_bytes;
  auto delta_time = std::chrono::duration_cast<std::chrono::milliseconds>(c2.steady_time - c1.steady_time);
  auto upload_speed_mbs = static_cast<double>(upload_bytes) / (delta_time.count() / 1000.0) / 1024 / 1024;
  auto download_speed_mbs = static_cast<double>(download_bytes) / (delta_time.count() / 1000.0) / 1024 / 1024;
  return {upload_speed_mbs, download_speed_mbs};
}

bool network::GetNetworkStatus() const {
  std::string result;
  if (aimrte::utils::Execute("ping 192.168.100.100 -c1 -W0.1", result) != 0 || result.find("1 received") == std::string::npos) {
    return false;
  }
  return true;
}

bool network::Initialize(const YAML::Node& config) {
  return true;
}

bool network::Start() {
  // 获取初始的磁盘IO统计信息
  get_net_counter(network_last_);
  return true;
}

void network::Shutdown() {}

void network::DiagnoseOnce() {
  get_net_counter(network_current_);

#if defined(__x86_64__) || defined(_M_X64) || defined(__i386__) || defined(_M_IX86)
  // Do nothing for x86
#else
  bool cur_status = GetNetworkStatus();
  if (last_network_status_.has_value() && !last_network_status_.value() && !cur_status) {
    AIMRTE_INFO("throw network exc: ping x86 failed");
  }
  last_network_status_ = cur_status;
#endif

  aimdk::protocol::NetworkUsage network_usage_msg;
  for (auto& [nic, io_counter] : network_current_) {
    double upload_speed_mbs = 0, download_speed_mbs = 0;
    auto find_iter = network_last_.find(nic);
    if (find_iter != network_last_.end()) {
      // 计算读写速度
      auto ud_speed = cal_up_down_speed(find_iter->second, io_counter);
      upload_speed_mbs = ud_speed.first;
      download_speed_mbs = ud_speed.second;
    } else {
      AIMRTE_ERROR("network name:{} not found in last network stats", nic);
    }
    // 每1s记录一次网卡IO统计信息
    network_usage_msg.add_nic_infos()->set_nic_name(find_iter->second.name);
    network_usage_msg.mutable_nic_infos()->rbegin()->set_upload_speed_mbs(upload_speed_mbs);
    network_usage_msg.mutable_nic_infos()->rbegin()->set_download_speed_mbs(download_speed_mbs);
  }
  network_last_ = std::move(network_current_);

  PubNetworkData(network_usage_msg);
}

void network::PubNetworkData(const aimdk::protocol::NetworkUsage& msg) {
  aimdk::protocol::SystemStatusChannel status_channel;
  status_channel.set_gist_msg_type(aimdk::protocol::SystemMsgType_NETWORK_USAGE);
  status_channel.mutable_network_usage()->CopyFrom(msg);

  if (res_.local.local_pub.IsValid()) {
    auto ctx = aimrte::ctx::init::GetCorePtr();
    ctx->Publish(res_.local.local_pub, status_channel);
  } else {
    AIMRTE_ERROR("Local publisher is not set for network");
  }
}
}  // namespace aima::monitor