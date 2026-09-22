// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <iostream>
#include "src/core/interface/i_monitor.h"
namespace aima::monitor {

struct DISK_IO_COUNTER {
  char name[32];                                      // 磁盘名称
  unsigned int reads;                                 // 读取IO次数
  unsigned int read_merged;                           // 读取合并次数
  unsigned int read_sectors;                          // 读取扇区数
  unsigned int read_time;                             // 读取时间
  unsigned int writes;                                // 写入IO次数
  unsigned int write_merged;                          // 写入合并次数
  unsigned int write_sectors;                         // 写入扇区数
  unsigned int write_time;                            // 写入时间
  unsigned int io_in_progress;                        // IO进行中的次数
  unsigned int io_time;                               // IO时间
  unsigned int io_time_weighted;                      // IO时间加权
  unsigned int read_bytes;                            // 读取字节数
  unsigned int write_bytes;                           // 写入字节数
  std::chrono::steady_clock::time_point steady_time;  // 记录的时间戳
};

class disk : public IMonitor {
 public:
  using RWTIMECOST = std::pair<double, double>;
  using RWMEGABYTES = std::pair<double, double>;
  using RWTIMES = std::pair<double, double>;

 private:
  float max_usage_{95};

 private:
  float get_disk_usage();
  void get_io_counter(std::map<std::string, DISK_IO_COUNTER>& io_counters);
  std::tuple<RWTIMES, RWMEGABYTES, RWTIMECOST> cal_rw_speed(const DISK_IO_COUNTER& c1, const DISK_IO_COUNTER& c2);

  std::map<std::string, DISK_IO_COUNTER> disk_last_;
  std::map<std::string, DISK_IO_COUNTER> disk_current_;

 public:
  disk() = default;
  ~disk() = default;
  bool Initialize(const YAML::Node& config) override;
  bool Start() override;
  void Shutdown() override;
  void DiagnoseOnce() override;
  void PubDiskData(const aimdk::protocol::DiskUsage& msg);
};

REGISTER_MONITOR_IMPL(disk);

}  // namespace aima::monitor
