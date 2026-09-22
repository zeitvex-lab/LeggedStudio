// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <future>

#include "process_error_code.h"
#include "global.h"


namespace process_manager
{

class FutureMultiThreadMgr {
 public:
  FutureMultiThreadMgr() = default;
  ~FutureMultiThreadMgr() = default;

  void PushTask(std::function<ProcessErrorCode()> task, std::function<void(ProcessErrorCode)> ret_callback) {
    FutureInfo info;
    info.future = std::async(std::launch::async, task);
    info.ret_callback = ret_callback;
    future_list_.emplace_back(std::move(info));
  }

  void WaitTaskFinish() {
    for (auto& ele : future_list_) {
      ProcessErrorCode code;
      try {
        code = ele.future.get();
      } catch(const std::exception& e) {
        AIMRT_ERROR("catch exception, {}, return ProcessErrorCode::INTERNAL_ERROR", e.what());
        ele.ret_callback(ProcessErrorCode::INTERNAL_ERROR);
        continue;
      }
      ele.ret_callback(code);
    }

    future_list_.clear();
  }

 private:
  struct FutureInfo {
    std::future<ProcessErrorCode> future;
    std::function<void(ProcessErrorCode)> ret_callback;
  };

  std::vector<FutureInfo> future_list_;
};

}
