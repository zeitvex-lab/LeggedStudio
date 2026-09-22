// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <dirent.h>
#include <pthread.h>
#include <sys/sysinfo.h>
#include <unistd.h>
#include <csignal>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

// 获取系统总内存（KB）
unsigned long get_system_total_memory();

// 获取当前进程的内存使用（常驻内存，KB）
unsigned long get_process_memory_usage();

// 获取 CPU 核心数
int get_cpu_cores();

// 获取所有线程的 CPU 使用时间
unsigned long long get_all_threads_cpu_time(pid_t pid);
// 获取系统总的 CPU 使用时间
unsigned long long get_total_cpu_time();

// 计算进程的 CPU 使用率（考虑多线程和多核）
double get_process_cpu_usage(pid_t pid);

// 获取当前进程的线程数
int get_process_thread_count();

// 获取调度策略的名称
std::string get_sched_policy_name(int policy);

// 获取进程的调度策略和优先级
std::pair<std::string, int> get_process_sched_info(pid_t pid);

std::vector<int> get_bound_cpus();
