// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./module.h"

// 使用特化，为自定义类型，指定全局唯一的通信数据类型。编译器将会去自动寻找它们的转换函数。
namespace aimrte::convert
{
template <>
struct For<example::pong::Ball> : By<aimdk::protocol::BallChannel> {
};
}  // namespace aimrte::convert

namespace example::pong
{
void Module::OnConfigure(aimrte::ModCfg &cfg)
{
  // example/module/ping 中已经对 OnConfigure() 阶段有详细介绍，这里不再赘述。
  using namespace aimrte;

  cfg
    [cfg::Module::Basic]
      .Config(option_)

        [cfg::Ch::zenoh | cfg::Ch::mqtt]
      .Def(option_.sub)  // 此处 channel 用的类型是自定义类型，需要指定通信数据类型来和它转换（见上文）

        [cfg::Ch::ros2]
      .Def(option_.sub_ros)

        [cfg::Rpc::zenoh]
      .Def(option_.srv)
      .Def(option_.srv_renamed, "custom.service.name")

        [cfg::Rpc::zenoh]
      .Def(option_.srv_ros)

        [cfg::Module::Executor]
      .Declare(option_.exe);
}

bool Module::OnInitialize()
{
  // 初始化本模块的订阅器
  InitSubscriber();

  // 初始化本模块对外的服务处理过程
  InitServer();

  // 返回初始化成功
  return true;
}

bool Module::OnStart()
{
  AIMRTE_TRACE("Module {} is started !", GetInfo().name);
  return true;
}

void Module::OnShutdown()
{
  AIMRTE_TRACE("Module {} shutdowns !", GetInfo().name);
}

void Module::InitSubscriber()
{
  // 在原生通信后端中，注册回调
  option_.sub.WhenInit().SubscribeInline(
    [this](std::shared_ptr<const Ball> msg) {
      AIMRTE_INFO("Receive ball {} {}.", msg->msg, msg->seq);

      std::unique_lock lock(ball_mutex_);
      latest_ball_ = std::move(msg);
    });

  // 也可以在给定执行器上，注册我们的回调函数
  option_.sub_ros.WhenInit().SubscribeOn(
    option_.exe,
    [](const auto &) {
      AIMRTE_INFO("Receive demo_msgs::msg::Ball on thread {}.", std::this_thread::get_id());
    });
}

void Module::InitServer()
{
  // 我们要能够处理的服务，其实是 srv 中的一个方法。
  // 我们也可以将其中操作的类型转换为自定义类型，方法如下：
  const auto srv = aimrte::ctx::init::Service<std::nullptr_t, Ball>(std::move(option_.srv.GetLatestBall));

  // 如果您不想转换类型，请删除上述调用。

  // 由于请求数据我们不关心，可以使用 std::nullptr_t 代替，或者换成您喜欢别的类型，
  // 只要提供对应的转换函数即可（见 ball.h）

  // 在给定执行器上，注册我们的服务函数
  srv.WhenInit().ServeOn(
    option_.exe,
    [this](const std::nullptr_t &, Ball &rep) -> aimrt::rpc::Status {
      std::unique_lock lock(ball_mutex_);

      if (latest_ball_ != nullptr)
        rep = *latest_ball_;

      return {};
    });

  option_.srv_renamed.GetLatestBall.WhenInit().ServeOn(
    option_.exe,
    [this](const auto &, auto &) {
    });

  // 也可以在原生的通信后端上注册回调
  option_.srv_ros.Func.WhenInit().ServeInline(
    [](const auto &, auto &) {
      AIMRTE_INFO("Serve demo_msgs::srv::GetLatestBall.");
    });
}
}  // namespace example::pong
