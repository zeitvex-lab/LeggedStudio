// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "self_resource_info.h"

// 获取系统总内存（KB）
unsigned long get_system_total_memory()
{
  struct sysinfo info;
  sysinfo(&info);
  return info.totalram * info.mem_unit / 1024;
}

// 获取当前进程的内存使用（常驻内存，KB）
unsigned long get_process_memory_usage()
{
  std::ifstream statm_file("/proc/self/statm");
  unsigned long size, resident;
  statm_file >> size >> resident;

  long page_size = sysconf(_SC_PAGESIZE);  // 获取页面大小（字节）
  return resident * page_size / 1024;      // 转换为 KB
}

// 获取 CPU 核心数
int get_cpu_cores()
{
  return sysconf(_SC_NPROCESSORS_ONLN);
}

// 获取所有线程的 CPU 使用时间
unsigned long long get_all_threads_cpu_time(pid_t pid)
{
  unsigned long long total_time = 0;
  std::string stat_file = "/proc/" + std::to_string(pid) + "/stat";
  std::ifstream file(stat_file);
  if (file.is_open()) {
    std::string ignore;
    unsigned long long utime, stime;
    for (int i = 0; i < 13; ++i) {
      file >> ignore;  // Skip first 13 fields
       }
    file >> utime >> stime;
    total_time += utime + stime;
  }

  return total_time;
}

// 获取系统总的 CPU 使用时间
unsigned long long get_total_cpu_time()
{
  std::ifstream cpu_file("/proc/stat");
  std::string line;
  std::getline(cpu_file, line);
  std::istringstream iss(line);
  std::string cpu;
  unsigned long long total_cpu_time = 0;
  iss >> cpu;
  unsigned long long value;
  while (iss >> value) {
    total_cpu_time += value;
  }
  return total_cpu_time;
}

// 计算进程的 CPU 使用率（考虑多线程和多核）
double get_process_cpu_usage(pid_t pid)
{
  static unsigned long long prev_process_time   = 0;
  static unsigned long long prev_total_cpu_time = 0;

  unsigned long long process_time   = get_all_threads_cpu_time(pid);
  unsigned long long total_cpu_time = get_total_cpu_time();

  if (process_time < prev_process_time || total_cpu_time <= prev_total_cpu_time) {
    // 异常情况 返回0
    return 0;
  }

  double cpu_usage = 100.0 * (double)(process_time - prev_process_time) / (total_cpu_time - prev_total_cpu_time);

  prev_process_time   = process_time;
  prev_total_cpu_time = total_cpu_time;

  int cpu_cores = get_cpu_cores();
  return cpu_usage * cpu_cores;  // 考虑多核
}

// 获取当前进程的线程数
int get_process_thread_count()
{
  std::ifstream status_file("/proc/self/status");
  std::string line;
  while (std::getline(status_file, line)) {
    if (line.find("Threads:") == 0) {
      return std::stoi(line.substr(line.find_last_of("\t") + 1));
    }
  }
  return 0;
}

// 获取调度策略的名称
std::string get_sched_policy_name(int policy)
{
  switch (policy) {
    case SCHED_OTHER:
      return "SCHED_OTHER";
    case SCHED_FIFO:
      return "SCHED_FIFO";
    case SCHED_RR:
      return "SCHED_RR";
    case SCHED_BATCH:
      return "SCHED_BATCH";
    case SCHED_IDLE:
      return "SCHED_IDLE";
    case SCHED_DEADLINE:
      return "SCHED_DEADLINE";
    default:
      return "UNKNOWN";
  }
}

// 获取进程的调度策略和优先级
std::pair<std::string, int> get_process_sched_info(pid_t pid)
{
  int policy = sched_getscheduler(pid);
  if (policy == -1) {
    return {"", 0};
  }

  struct sched_param param;
  if (sched_getparam(pid, &param) == -1) {
    return {"", 0};
  }

  return {get_sched_policy_name(policy), param.sched_priority};
}

std::vector<int> get_bound_cpus()
{
  cpu_set_t mask;
  CPU_ZERO(&mask);

  // 获取当前进程的 CPU 绑定信息
  if (sched_getaffinity(0, sizeof(mask), &mask) == -1) {
    perror("sched_getaffinity error");
    return {};  // 如果发生错误，返回空的 vector
  }

  std::vector<int> bound_cpus;
  for (int i = 0; i < CPU_SETSIZE; ++i) {
    if (CPU_ISSET(i, &mask)) {
      bound_cpus.push_back(i);
    }
  }

  return bound_cpus;
}
