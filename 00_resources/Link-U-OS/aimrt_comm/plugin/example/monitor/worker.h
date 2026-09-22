// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <time.h>
#include <cstdint>
#include <string>

namespace aimrt::module::executor
{

class BaseWorker
{
 private:
  std::string name;
  uint64_t period_ns;
  timespec wake_abs_time;

 public:
  BaseWorker(uint64_t period_ns, const std::string& name = "");
  virtual ~BaseWorker() = default;

  void ResetWakeTime();
  void UpdateWorkerTime(const timespec& now);

  uint64_t GetPeriod() const;
  const std::string& GetName() const;
  const timespec& GetWakeTime() const;
  [[nodiscard]] bool IsExpired(const timespec& now) const;
  bool operator<(BaseWorker& x) const;

  virtual void Run() = 0;
};

using BaseWorkerPtr = BaseWorker*;
struct BaseWorkerCompare {
  bool operator()(BaseWorkerPtr x, BaseWorkerPtr y) const;
};

}  // namespace aimrt::module::executor
