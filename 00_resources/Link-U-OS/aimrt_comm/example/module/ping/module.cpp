// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./module.h"

namespace example::ping
{
void Module::OnConfigure(aimrte::ModCfg& cfg)
{
  // 方便本函数内执行各种配置过程
  using namespace aimrte;

  // 使用类似于 ini 配置的风格，对不同维度的选项进行配置
  cfg
    // 基础的模块配置，可以读取模块参数、设置模块是否使能等
    [cfg::Module::Basic]
      .Config(option_)

        // 配置本模块的日志参数
        [cfg::Module::Logger]
      .Level(cfg::LogLevel::Trace)

        // 配置 channel 通信后端，通过 Def 资源对象来完成。
        // 这些资源对象的默认值，为资源的默认名称，可以被外部参数所覆盖（详见 example/cfg）
        // 可以定义多个 [session] 进行配置，
        // 可以在一个 [session] 下定义多个 channel（pub 和 sub），
        // 还可以支持对一个嵌套类型（结构体，包含多个 channel 资源对象）同时定义，
        // 这些资源对象将在 OnInitialize() 阶段自动初始化。
        [cfg::Ch::zenoh | cfg::Ch::mqtt]
      .Def(option_.pub)

        [cfg::Ch::ros2]
      .Def(option_.pub_ros)

        // 同样的，可以定义 rpc 通信
        [cfg::Rpc::zenoh]
      .Def(option_.cli)
      .Def(option_.cli_renamed, "custom.service.name")

        [cfg::Rpc::zenoh]
      .Def(option_.cli_ros)

        // 声明本模块所需的执行器。执行器是一个进程内的概念，只能在 main() 处定义，
        // 模块可以声明拥有指定名称的执行器，并会在 OnInitialize() 阶段自动初始化它
        [cfg::Module::Executor]
      .Declare(option_.exe);
}

bool Module::OnInitialize()
{
  // 在 OnConfigure() 阶段，我们为本模块配置了很多资源，它们将在本函数执行前自动初始化。

  AIMRTE_INFO("Initialize module {}.", GetInfo().name);
  return true;
}

bool Module::OnStart()
{
  // 在本模块的执行器上，开启异步
  option_.exe.Post(
    [this]() -> aimrte::Co<void> {
      co_await MainLoop();
    });

  AIMRTE_WARN("Module {} is started !", GetInfo().name);
  return true;
}

void Module::OnShutdown()
{
  AIMRTE_ERROR("Module {} shutdowns !", GetInfo().name);
}

aimrte::Co<void> Module::MainLoop() const
{
  aimdk::protocol::BallChannel ball_msg;
  ball_msg.mutable_ball()->set_msg("hello world");

  while (aimrte::ctx::Ok()) {
    ball_msg.mutable_header()->set_seq(ball_msg.header().seq() + 1);

    // 发送当前的球信息
    DoPublish(ball_msg);

    // 进行一次 rpc，获得对端收到的最新球信息
    co_await DoCall();

    // 睡眠一段时间
    co_await aimrte::ctx::Sleep(std::chrono::seconds(1));
  }
}

void Module::DoPublish(const aimdk::protocol::BallChannel& msg) const
{
  // 发送该球信息给对端
  AIMRTE_INFO("Send Ball {}.", msg.header().seq());
  option_.pub(msg);
  option_.pub_ros(demo_msgs::msg::Ball{});
}

aimrte::Co<void> Module::DoCall() const
{
  // 发起 rpc，获取响应
  aimdk::protocol::GetLatestBallRequest req;
  AIMRTE_TRACE("Call GetLatestBall ...");

  {
    // 设置超时参数（可选，但建议配置）
    aimrt::rpc::Context rpc_ctx;
    rpc_ctx.SetTimeout(std::chrono::seconds(1));

    const std::optional<aimdk::protocol::GetLatestBallResponse> rep = co_await option_.cli.GetLatestBall(rpc_ctx, req);
    if (rep.has_value())
      AIMRTE_INFO("Get Latest ball {} !", rep->ball().msg());
    else
      AIMRTE_ERROR("Fail to get ball !");
  }

  {
    // 设置超时参数（可选，但建议配置），不能复用 rpc context
    aimrt::rpc::Context rpc_ctx;
    rpc_ctx.SetTimeout(std::chrono::seconds(1));

    // 使用 ros 消息进行调用
    demo_msgs::srv::GetLatestBall_Request ros_req;
    demo_msgs::srv::GetLatestBall_Response ros_rep;
    if ((co_await option_.cli_ros.Func(rpc_ctx, ros_req, ros_rep)).OK())
      AIMRTE_INFO("demo_msgs::srv::GetLatestBall success !");
    else
      AIMRTE_ERROR("demo_msgs::srv::GetLatestBall failed !");
  }

  {
    aimrt::rpc::Context rpc_ctx;
    rpc_ctx.SetTimeout(std::chrono::seconds(1));

    const std::optional rep = co_await option_.cli_renamed.GetLatestBall(rpc_ctx, {});
    if (rep.has_value())
      AIMRTE_INFO("Get Latest ball {} with custom service name !", rep->ball().msg());
    else
      AIMRTE_ERROR("Fail to get ball with custom service name !");
  }
}
}  // namespace example::ping
