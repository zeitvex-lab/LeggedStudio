// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./worker.h"
#include <cstdint>
#include <iostream>
namespace aimrt::module::executor
{

BaseWorker::BaseWorker(uint64_t p, const std::string& n) : name(n), period_ns(p) { ResetWakeTime(); }

void BaseWorker::ResetWakeTime() { clock_gettime(CLOCK_MONOTONIC, &wake_abs_time); }

void BaseWorker::UpdateWorkerTime(const timespec& now)
{
  if (period_ns <= 0) {
    return;
  }
  wake_abs_time.tv_nsec += period_ns;
  if (wake_abs_time.tv_nsec > 999999999) {
    wake_abs_time.tv_sec += wake_abs_time.tv_nsec / 1000000000;
    wake_abs_time.tv_nsec = wake_abs_time.tv_nsec % 1000000000;
  }

  // 更新唤醒时间后，发现还小于当前时间，则重置时间
  if (wake_abs_time.tv_sec < now.tv_sec || (wake_abs_time.tv_sec == now.tv_sec && wake_abs_time.tv_nsec < now.tv_nsec)) {
    auto diff = ((now.tv_sec - wake_abs_time.tv_sec) * 1000000) + ((now.tv_nsec - wake_abs_time.tv_nsec) / 1000);
    // std::cout << GetName() << " worker missed wakeup time! diff " << diff << " us, period: " << (period_ns / 1000) << " us, miss :" << (period_ns / 1000.0) << std::endl;
    ResetWakeTime();
    UpdateWorkerTime(now);
  }
}

[[nodiscard]] bool BaseWorker::IsExpired(const timespec& now) const
{
  return (now.tv_sec > wake_abs_time.tv_sec) || (now.tv_sec == wake_abs_time.tv_sec && now.tv_nsec >= wake_abs_time.tv_nsec);
}

bool BaseWorker::operator<(BaseWorker& x) const
{
  return ((wake_abs_time.tv_sec > x.wake_abs_time.tv_sec) || (wake_abs_time.tv_sec == x.wake_abs_time.tv_sec && wake_abs_time.tv_nsec > x.wake_abs_time.tv_nsec));
}

uint64_t BaseWorker::GetPeriod() const { return period_ns; }
const std::string& BaseWorker::GetName() const { return name; }
const timespec& BaseWorker::GetWakeTime() const { return wake_abs_time; }

bool BaseWorkerCompare::operator()(BaseWorkerPtr x, BaseWorkerPtr y) const { return *x < *y; }

}  // namespace aimrt::module::executor
