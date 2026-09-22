// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <atomic>
#include "./worker.h"

#include "src/all_in_one/include/aimrte.h"
#include "src/interface/aimrt_module_cpp_interface/co/async_scope.h"
#include "src/interface/aimrt_module_cpp_interface/co/task.h"

namespace aimrt::module::executor
{

class TimeWheelExecutor
{
 public:
  TimeWheelExecutor();
  ~TimeWheelExecutor() = default;

  void Init(aimrt::executor::ExecutorRef executor);
  void Start();
  void Shutdown();

  template <typename T, typename... ConstructorArgs>
  void AddWorker(ConstructorArgs&&... args)
  {
    static_assert(std::is_base_of<BaseWorker, T>::value, "T must be derived from BaseWorker");
    auto worker = new T(std::forward<ConstructorArgs>(args)...);
    queue_.push(worker);
  }

 private:
  void ResetWorkerTime();
  co::Task<void> Loop();

 private:
  aimrt::co::AsyncScope scope_;
  std::atomic<bool> is_running_{false};
  aimrt::executor::ExecutorRef executor_;
  std::priority_queue<BaseWorkerPtr, std::vector<BaseWorkerPtr>, BaseWorkerCompare> queue_;
};

}  // namespace aimrt::module::executor
