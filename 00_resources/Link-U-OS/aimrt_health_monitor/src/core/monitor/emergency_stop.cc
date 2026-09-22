// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "emergency_stop.h"
#include "src/hds/interface.h"

namespace aima::monitor {
bool EmergencyStop::Initialize(const YAML::Node& config) {
  res_.mqtt.emergency_state_sub.WhenInit().SubscribeOn(res_.regular.work_thread_pool, [this](std::shared_ptr<const aimdk::protocol::EmergencyStateChannel> msg) -> aimrte::co::Task<void> {
    is_estop_ = msg->data().active();
    estop_reason_ = aimdk::protocol::EmergencyState_Reason_Name(msg->data().reason());

    static bool last_estop = false;
    if (is_estop_ != last_estop) {
      AIMRTE_INFO("estop state changed to {},reason:{}", is_estop_, estop_reason_);
    }
    last_estop = is_estop_;

    // 防撞条触发状态
    if (msg->data().left_back_sensor_alarm() || msg->data().left_front_sensor_alarm() || msg->data().right_back_sensor_alarm() || msg->data().right_front_sensor_alarm() || msg->data().left_sensor_alarm() || msg->data().right_sensor_alarm()) {
      crash_bar_trigger_ = true;
    }

    co_return;
  });
  return true;
}

bool EmergencyStop::Start() {
  return true;
}

void EmergencyStop::Shutdown() {}

void EmergencyStop::DiagnoseOnce() {}

}  // namespace aima::monitor