// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "aimdk/protocol/hal/bms/hal_bms_channel.pb.h"
#include "aimdk/protocol/hal/state/hal_state_channel.pb.h"
#include "aimdk/protocol/hds/process/process_heartbeat_channel.pb.h"
#include "aimdk/protocol/hds/system_status.pb.h"
#include "src/prelude/prelude.h"

namespace aima::monitor {
struct Res {
  // 使用默认配置的资源
  struct {
    // Pub
    aimrte::Pub<aimdk::protocol::SystemStatusChannel> system_status_pub;

    // Sub
    aimrte::Sub<aimdk::protocol::BmsStateChannel> bms_state_sub{"/aima/bms/data"};
    aimrte::Sub<aimdk::protocol::ProcessHeartbeatChannel> process_heartbeat_sub{"/aima/heartbeat"};

    // Exe
    aimrte::Exe work_thread_pool{"work_thread_pool", 10};
  } regular;

  // 使用mqtt后端配置的资源
  struct {
    aimrte::Sub<aimdk::protocol::EmergencyStateChannel> emergency_state_sub{"/hal_state/emergency"};
  } mqtt;

  // 使用local后端配置的资源
  struct {
    aimrte::Pub<aimdk::protocol::SystemStatusChannel> local_pub{"/local/system_status"};
    aimrte::Sub<aimdk::protocol::SystemStatusChannel> local_sub{"/local/system_status"};
  } local;
};
}
