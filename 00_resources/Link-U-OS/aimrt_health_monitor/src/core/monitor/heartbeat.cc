// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "heartbeat.h"

namespace aima::monitor {

bool heartbeat::Initialize(const YAML::Node& config) 
{
  res_.regular.process_heartbeat_sub.WhenInit().SubscribeOn(res_.regular.work_thread_pool, [this](std::shared_ptr<const aimdk::protocol::ProcessHeartbeatChannel> msg) -> aimrte::co::Task<void> {
    std::lock_guard<std::mutex> lock(mutex_);
    heartbeats_[msg->data().name()] = std::const_pointer_cast<aimdk::protocol::ProcessHeartbeatChannel>(msg);
    co_return;
  });
  return true;
}

bool heartbeat::Start() { return true; }

void heartbeat::Shutdown() {}

void heartbeat::DiagnoseOnce()
{
  std::lock_guard<std::mutex> lock(mutex_);
  aimdk::protocol::AppHeartBeatList msg;
  for (const auto& hb : heartbeats_) {
    auto& app_heartbeat = *msg.add_app_hearbeats();
    app_heartbeat.set_app_name(hb.second->data().name());
    app_heartbeat.set_cpu_usage(hb.second->data().resource_info().cpu_usage_ratio());
    app_heartbeat.set_mem_usage(hb.second->data().resource_info().mem_usage_ratio());
    app_heartbeat.set_mem_usage_kb(hb.second->data().resource_info().mem_usage());
    app_heartbeat.set_pid(hb.second->data().resource_info().pid());
    app_heartbeat.set_thread_count(hb.second->data().resource_info().thread_count());
    app_heartbeat.set_cpu_sched_policy(static_cast<aimdk::protocol::SCHED_POLICY>(ShcedPolicy(hb.second->data().resource_info().cpu_sched_policy())));
    app_heartbeat.set_cpu_sched_priority(hb.second->data().resource_info().cpu_sched_priority());
  }
  PubAppHeartbeat(msg);
}

void heartbeat::PubAppHeartbeat(const aimdk::protocol::AppHeartBeatList& msg) {
  aimdk::protocol::SystemStatusChannel status_channel;
  status_channel.set_gist_msg_type(aimdk::protocol::SystemMsgType_HEARTBEAT_LIST);
  status_channel.mutable_heartbeat_list()->CopyFrom(msg);

  if (res_.local.local_pub.IsValid()) {
    auto ctx = aimrte::ctx::init::GetCorePtr();
    ctx->Publish(res_.local.local_pub, status_channel);
  } else {
    AIMRTE_DEBUG("res_.local.local_pub is not set, cannot publish disk data");
  }
}

uint8_t heartbeat::ShcedPolicy(const std::string &policy)
{
  if (policy == "SCHED_OTHER") {
    return SCHED_OTHER;
  } else if (policy == "SCHED_FIFO") {
    return SCHED_FIFO;
  } else if (policy == "SCHED_RR") {
    return SCHED_RR;
  } else if (policy == "SCHED_BATCH") {
    return SCHED_BATCH;
  } else if (policy == "SCHED_IDLE") {
    return SCHED_IDLE;
  } else if (policy == "SCHED_DEADLINE") {
    return SCHED_DEADLINE;
  }
  return SCHED_OTHER;  // 默认返回
}
}   // namespace aima::monitor
