// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "battery.h"

#include <sys/syslog.h>

#include <cstdint>
#include <fstream>
#include "aimdk/protocol/hal/bms/bms.pb.h"
#include "src/hds/interface.h"
namespace aima::monitor {

bool battery::Initialize(const YAML::Node& config) {
  if (config["battery_low_percent"]) {
    battery_low_percent_ = config["battery_low_percent"].as<float>();
    AIMRTE_INFO("set battery battery_low_percent:{}", battery_low_percent_);
  }

  if (config["battery_low_limit_percent"]) {
    battery_low_limit_percent_ = config["battery_low_limit_percent"].as<float>();
    AIMRTE_INFO("set battery battery_low_limit_percent:{}", battery_low_limit_percent_);
  }

  if (config["battery_low_2_percent"]) {
    battery_low_2_percent_ = config["battery_low_2_percent"].as<float>();
    AIMRTE_INFO("set battery battery_low_2_percent:{}", battery_low_2_percent_);
  }

  res_.regular.bms_state_sub.WhenInit().SubscribeOn(res_.regular.work_thread_pool, [this](std::shared_ptr<const aimdk::protocol::BmsStateChannel> msg) -> aimrte::co::Task<void> {
    AIMRTE_DEBUG("battery percent:{}", msg.get()->data().charge());
    std::unique_lock<std::shared_mutex> w_lock(r_w_mutex_);
    last_battery_info_ = msg;
    static double last_battery = msg.get()->data().charge();
    if (msg.get()->data().charge() != last_battery) {
      AIMRTE_INFO("battery percent changed:{}", msg.get()->data().charge());
    }
    last_battery = msg.get()->data().charge();
    co_return;
  });
  return true;
}

bool battery::Start() {
  return true;
}

void battery::Shutdown() {}

void battery::DiagnoseOnce() {
  std::shared_lock<std::shared_mutex> read_lock(r_w_mutex_);

  // 打点上报电池电量
  if (last_battery_info_) {
    float percent = last_battery_info_.get()->data().charge();
    float voltage = last_battery_info_.get()->data().voltage();
    float current = last_battery_info_.get()->data().current();
    float temperature = last_battery_info_.get()->data().temperature();

    if (last_battery_info_.get()->data().power_supply_status() != aimdk::protocol::PowerSupplyStatus::PowerSupplyStatus_CHARGING) {
      if (percent >= battery_low_2_percent_ && percent < battery_low_percent_) {
        // aimrte::ctx::log().Debug("battery low");
      } else if (percent >= battery_low_limit_percent_ && percent < battery_low_2_percent_) {
        aimrte::ctx::log().Debug("battery low 2");
      } else if (percent < battery_low_limit_percent_) {
        aimrte::ctx::log().Debug("battery low limit");
      }
    }
  }
}

void battery::PubBatteryData(const std::shared_ptr<const aimdk::protocol::BmsStateChannel>& msg) {
  aimdk::protocol::SystemStatusChannel status_channel;
  status_channel.set_gist_msg_type(aimdk::protocol::SystemMsgType_BATTERY_USAGE);

  auto pBattery = status_channel.mutable_battery_usage();
  pBattery->set_percent(last_battery_info_.get()->data().charge());
  pBattery->set_voltage(last_battery_info_.get()->data().voltage());
  pBattery->set_current(last_battery_info_.get()->data().current());
  pBattery->set_temp(last_battery_info_.get()->data().temperature());
  pBattery->set_is_plugin(last_battery_info_.get()->data().power_supply_status() == aimdk::protocol::PowerSupplyStatus::PowerSupplyStatus_CHARGING);
  if (res_.local.local_pub.IsValid()) {
    auto ctx = aimrte::ctx::init::GetCorePtr();
    ctx->Publish(res_.local.local_pub, status_channel);
  } else {
    AIMRTE_ERROR("res_.local.local_pub is null, cannot publish battery data");
  }
}

}  // namespace aima::monitor