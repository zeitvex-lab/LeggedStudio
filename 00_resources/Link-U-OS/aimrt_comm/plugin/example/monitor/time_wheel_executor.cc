// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./time_wheel_executor.h"

#include "src/interface/aimrt_module_cpp_interface/co/aimrt_context.h"
#include "src/interface/aimrt_module_cpp_interface/co/schedule.h"
#include "src/interface/aimrt_module_cpp_interface/co/sync_wait.h"

namespace aimrt::module::executor
{

TimeWheelExecutor::TimeWheelExecutor() {}

void TimeWheelExecutor::Init(aimrt::executor::ExecutorRef executor)
{
  executor_ = executor;
}

void TimeWheelExecutor::Start()
{
  try {
    is_running_ = true;

    if (queue_.empty()) {
      return;
    }

    // 启动
    scope_.spawn(Loop());
  } catch (const std::exception& e) {
    is_running_ = false;
  }
}

void TimeWheelExecutor::Shutdown()
{
  is_running_ = false;

  aimrt::co::SyncWait(scope_.complete());

  while (!queue_.empty()) {
    auto worker = queue_.top();
    queue_.pop();
    delete worker;
  }
}

void TimeWheelExecutor::ResetWorkerTime()
{
  // 重置时间
  std::vector<BaseWorkerPtr> workers;
  while (!queue_.empty()) {
    auto worker = queue_.top();
    worker->ResetWakeTime();
    timespec now{};
    clock_gettime(CLOCK_MONOTONIC, &now);
    worker->UpdateWorkerTime(now);
    workers.push_back(worker);
    queue_.pop();
  }
  for (auto worker : workers) {
    queue_.push(worker);
  }
}

aimrt::co::Task<void> TimeWheelExecutor::Loop()
{
  if (queue_.empty()) {
    co_return;
  }

  aimrt::co::AimRTScheduler scheduler(executor_);
  co_await aimrt::co::Schedule(scheduler);

  ResetWorkerTime();
  timespec now{};
  clock_gettime(CLOCK_MONOTONIC, &now);
  while (is_running_) {
    // 获取优先级队列中最快要到期的worker
    auto worker = queue_.top();
    if (worker->IsExpired(now)) {
      // 更新
      worker->UpdateWorkerTime(now);
      // Work
      worker->Run();
      // 重新入队
      queue_.pop();
      queue_.push(worker);
    } else {
      // 等待下一个周期
      clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &worker->GetWakeTime(), nullptr);
      clock_gettime(CLOCK_MONOTONIC, &now);  // 更新当前时间
    }
  }

  co_return;
}

}  // namespace aimrt::module::executor
