// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <mutex>
#include <shared_mutex>

namespace aimrte::sync
{
template <class T>
class AtomData
{
 public:
  /**
   * @brief 构造函数
   * @param timeout 默认为0，不设置超时时间，数据超时时间(毫秒)，如果超过这个时间还未set数据，则Get时返回false(无数据)
   */
  AtomData(uint64_t timeout = 0) : timeout_(timeout)
  {
  }

  /**
   * @brief 使用写锁写入数据
   * @param a 要设置的值
   */
  void Set(const T& a)
  {
    std::unique_lock lock(mutex_);

    if (timeout_ != 0) {
      auto now        = std::chrono::system_clock::now();
      last_recv_time_ = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()).count();
    }

    obj_ = a;
    has_ = true;
  }

  /**
   * @brief 使用读锁读取数据
   */
  T Get()
  {
    std::shared_lock lock(mutex_);
    T res;
    if (has_) {
      res = obj_;
    }
    return res;
  }

  /**
   * @brief 使用读与写锁，判断是否有数据，如果有则读取数据并清空数据
   * @param a 获取到的值
   * @return 是否获取成功(无值，或超时时返回false)
   */
  bool GetAndClear(T& a)
  {
    bool res = Has();
    if (not res) return res;

    std::unique_lock lock(mutex_);
    a    = obj_;
    has_ = false;
    return res;
  }

  /**
   * @brief 使用读锁判断是否有数据
   * @return 是否有值（无值或超时时返回false）
   */
  bool Has()
  {
    std::shared_lock lock(mutex_);

    if (timeout_ != 0) {
      auto now           = std::chrono::system_clock::now();
      auto now_timestemp = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()).count();
      if (now_timestemp - last_recv_time_ > timeout_) {
        return false;
      }
    }

    return has_;
  }

  /**
   * @brief 使用写锁清空数据
   */
  void Clear()
  {
    std::unique_lock lock(mutex_);
    has_ = false;
  }

 private:
  T obj_;
  bool has_{false};
  uint64_t timeout_{0};
  uint64_t last_recv_time_{0};
  std::shared_mutex mutex_;
};
}  // namespace aimrte::sync
