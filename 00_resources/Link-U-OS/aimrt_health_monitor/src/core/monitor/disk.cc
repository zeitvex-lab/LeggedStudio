// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "disk.h"
#include <sys/statvfs.h>
#include <fstream>
#include "src/hds/interface.h"

#define BUFFSIZE 1024

namespace aima::monitor {
// 获取系统磁盘使用情况
float disk::get_disk_usage() {
  struct statvfs disk_info;
  const char* path = "/";  // 监控根目录所在的文件系统

  if (statvfs(path, &disk_info) != 0) {
    std::cerr << "Failed to get disk information for " << path << std::endl;
    return 1;
  }

  unsigned long long total_space = disk_info.f_blocks * disk_info.f_frsize;
  unsigned long long free_space = disk_info.f_bfree * disk_info.f_frsize;
  unsigned long long used_space = total_space - free_space;

  float disk_usage = (static_cast<float>(used_space) / static_cast<float>(total_space)) * 100;
  return disk_usage;
}

void disk::get_io_counter(std::map<std::string, DISK_IO_COUNTER>& io_counters) {
  char buff[BUFFSIZE];
  FILE* fd;
  DISK_IO_COUNTER io_counter;
  io_counters.clear();

  fd = fopen("/proc/diskstats", "r");
  if (fd == NULL) {
    perror("Failed to open /proc/diskstats");
    exit(EXIT_FAILURE);
  }

  while (fgets(buff, sizeof(buff), fd) != NULL) {
    unsigned int unused;
    sscanf(buff, "   %u\t%u %s %u %u %u %u %u %u %u %u %u %u %u", &unused, &unused, io_counter.name,
           &io_counter.reads, &io_counter.read_merged, &io_counter.read_sectors, &io_counter.read_time,
           &io_counter.writes, &io_counter.write_merged, &io_counter.write_sectors, &io_counter.write_time,
           &io_counter.io_in_progress, &io_counter.io_time, &io_counter.io_time_weighted);
    io_counter.read_bytes = io_counter.read_sectors * 512;    // 假定扇区大小为 512 bytes
    io_counter.write_bytes = io_counter.write_sectors * 512;  // 假定扇区大小为 512 bytes
    // 忽略掉 loop 设备
    if (strncmp(io_counter.name, "loop", 4) != 0) {
      io_counter.steady_time = std::chrono::steady_clock::now();
      io_counters.emplace(std::string(io_counter.name), io_counter);
    }
  }
  fclose(fd);
}

std::tuple<disk::RWTIMES, disk::RWMEGABYTES, disk::RWTIMECOST> disk::cal_rw_speed(const DISK_IO_COUNTER& c1, const DISK_IO_COUNTER& c2) {
  auto read_bytes = c2.read_bytes - c1.read_bytes;
  auto write_bytes = c2.write_bytes - c1.write_bytes;
  auto delta_time = std::chrono::duration_cast<std::chrono::milliseconds>(c2.steady_time - c1.steady_time);
  auto read_speed_mbs = static_cast<double>(read_bytes) / (delta_time.count() / 1000.0) / 1024 / 1024;
  auto write_speed_mbs = static_cast<double>(write_bytes) / (delta_time.count() / 1000.0) / 1024 / 1024;
  AIMRTE_DEBUG("read_time {} {} write_time {} {}", c2.read_time, c1.read_time, c2.write_time, c1.write_time);
  auto read_time_cost = static_cast<double>(c2.read_time - c1.read_time);     // 单位毫秒
  auto write_time_cost = static_cast<double>(c2.write_time - c1.write_time);  // 单位毫秒

  auto read_times = static_cast<double>(c2.reads - c1.reads);
  auto write_times = static_cast<double>(c2.writes - c1.writes);
  return std::make_tuple(std::make_pair(read_times, write_times),
                         std::make_pair(read_speed_mbs, write_speed_mbs),
                         std::make_pair(read_time_cost, write_time_cost));
}

bool disk::Initialize(const YAML::Node& config) {
  if (config["max_usage"]) {
    max_usage_ = config["max_usage"].as<float>();
    AIMRTE_INFO("set disk max useage:{}", max_usage_);
  }
  return true;
}

bool disk::Start() {
  // 获取初始的磁盘IO统计信息
  get_io_counter(disk_last_);
  return true;
}

void disk::Shutdown() {}

void disk::DiagnoseOnce() {
  float current_usage = get_disk_usage();
  get_io_counter(disk_current_);

#if defined(__x86_64__) || defined(_M_X64) || defined(__i386__) || defined(_M_IX86)
  if (current_usage >= max_usage_) {
    AIMRTE_ERROR("disk usage:{} over limit:{}", current_usage, max_usage_);
  }
#else
  if (current_usage >= max_usage_) {
    AIMRTE_ERROR("disk usage:{} over limit:{}", current_usage, max_usage_);
  }
#endif

  aimdk::protocol::DiskUsage disk_usage_msg;
  for (auto& [name, io_counter] : disk_current_) {
    double read_times = 0, write_times = 0;
    double read_speed_mbs = 0, write_speed_mbs = 0;
    int read_await_us = 0, write_await_us = 0;
    auto find_iter = disk_last_.find(name);
    if (find_iter != disk_last_.end()) {
      // 计算读写速度
      auto rw_tuple = cal_rw_speed(find_iter->second, io_counter);
      read_times = std::get<0>(rw_tuple).first;
      write_times = std::get<0>(rw_tuple).second;
      read_speed_mbs = std::get<1>(rw_tuple).first;
      write_speed_mbs = std::get<1>(rw_tuple).second;
      auto read_await = std::get<2>(rw_tuple).first / read_times,
           write_await = std::get<2>(rw_tuple).second / write_times;
      read_await_us = (read_await < 0) ? 0 : static_cast<int>(read_await * 1000);
      write_await_us = (write_await < 0) ? 0 : static_cast<int>(write_await * 1000);
    } else {
      AIMRTE_ERROR("disk name:{} not found in last disk stats", name);
    }
    // 每1s记录一次磁盘IO统计信息
    auto& disk_info = *disk_usage_msg.add_partition_infos();
    disk_info.set_partition_name(std::string(find_iter->second.name));
    disk_info.set_read_mbs(read_speed_mbs);
    disk_info.set_write_mbs(write_speed_mbs);
    disk_info.set_usage(current_usage);
    disk_info.set_read_times(static_cast<int>(read_times));
    disk_info.set_write_times(static_cast<int>(write_times));
    disk_info.set_read_await_us_total(read_await_us);                                                // 转换为微秒
    disk_info.set_write_await_us_total(write_await_us);                                              // 转换为微秒
    disk_info.set_read_await_us_max(static_cast<int>(io_counter.read_time / read_times * 1000));     // 转换为微秒
    disk_info.set_write_await_us_max(static_cast<int>(io_counter.write_time / write_times * 1000));  // 转换为微秒
  }
  disk_last_ = std::move(disk_current_);

  PubDiskData(disk_usage_msg);
}

void disk::PubDiskData(const aimdk::protocol::DiskUsage& msg) {
  aimdk::protocol::SystemStatusChannel status_channel;
  status_channel.set_gist_msg_type(aimdk::protocol::SystemMsgType_DISK_USAGE);
  status_channel.mutable_disk_usage()->CopyFrom(msg);

  if (res_.local.local_pub.IsValid()) {
    auto ctx = aimrte::ctx::init::GetCorePtr();
    ctx->Publish(res_.local.local_pub, status_channel);
  } else {
    AIMRTE_ERROR("res_.local.local_pub is not set, cannot publish disk data");
  }
}

}  // namespace aima::monitor