// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <memory>
#include <string>
#include <map>

#include "aimdk/protocol/em/api.pb.h"

namespace process_manager
{

enum EmAppInfo_State : int {
  EmAppInfo_State_State_UNDEFINED = 0,
  EmAppInfo_State_State_IDLE = 1,
  EmAppInfo_State_State_STARTING = 2,
  EmAppInfo_State_State_RUNNING = 3,
  EmAppInfo_State_State_STOPPING = 4,
  EmAppInfo_State_State_EXITED = 5,
  EmAppInfo_State_State_RUNNING_IN_PASS = 6,   // 表示之前正常启动, 但中途异常, 用于内部状态管理, 对外返回 RUNNING,
};

class StateTrans {
 public:
  static aimdk::protocol::EmAppInfo_State TranLocalStateToProtoState(EmAppInfo_State state) {
    aimdk::protocol::EmAppInfo_State proto_state = aimdk::protocol::EmAppInfo_State::EmAppInfo_State_State_UNDEFINED;
    switch(state) {
      case EmAppInfo_State::EmAppInfo_State_State_IDLE:
      {
        proto_state = aimdk::protocol::EmAppInfo_State::EmAppInfo_State_State_IDLE;
      } break;
      case EmAppInfo_State::EmAppInfo_State_State_STARTING:
      {
        proto_state = aimdk::protocol::EmAppInfo_State::EmAppInfo_State_State_STARTING;
      } break;
      case EmAppInfo_State::EmAppInfo_State_State_RUNNING:
      case EmAppInfo_State::EmAppInfo_State_State_RUNNING_IN_PASS:
      {
        proto_state = aimdk::protocol::EmAppInfo_State::EmAppInfo_State_State_RUNNING;
      } break;
      case EmAppInfo_State::EmAppInfo_State_State_STOPPING:
      {
        proto_state = aimdk::protocol::EmAppInfo_State::EmAppInfo_State_State_STOPPING;
      } break;
      case EmAppInfo_State::EmAppInfo_State_State_EXITED:
      {
        proto_state = aimdk::protocol::EmAppInfo_State::EmAppInfo_State_State_EXITED;
      } break;
      case EmAppInfo_State::EmAppInfo_State_State_UNDEFINED:
      default:
        break;
    }
    return proto_state;
  }

};

}
