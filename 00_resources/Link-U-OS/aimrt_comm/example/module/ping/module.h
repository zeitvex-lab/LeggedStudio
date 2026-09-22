// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "aimdk/protocol/demo/demo_service.h"
#include "aimdk/protocol/demo/demo_channel.pb.h"
#include "ros2/demo/GetLatestBall.h"
#include "src/all_in_one/include/aimrte.h"

namespace example::ping
{
class Module final : public aimrte::Mod
{
 public:
  struct Option {
    // 用于发送的通道，默认构造中的话题名称，将在 OnConfigure() 阶段使用。
    aimrte::Pub<aimdk::protocol::BallChannel> pub{"/example/ping_pong_ball"};

    // 支持使用 ros 数据类型进行通信
    aimrte::Pub<demo_msgs::msg::Ball> pub_ros{"/example/ping_pong_ball/ros"};

    // 调用对方的服务的操作接口
    aimdk::protocol::res::DemoServiceProxy cli;

    // 支持使用 ros 调用对方的服务的操作接口（要求对方也有相应的 ros 服务注册），
    // 但也可以只使用 ros 的序列化、选用其他方式进行通信。
    demo_msgs::srv::res::GetLatestBallProxy cli_ros;

    // 指定了自定义 service name 的客户端
    aimdk::protocol::res::DemoServiceProxy cli_renamed;

    // 本模块的执行器资源，也即，用于执行异步任务的“线程池”。
    aimrte::Exe exe{"work_thread_pool"};
  };

 protected:
  /**
   * @brief 在框架启动前的配置流程，通过 C++ SDK 来设置 AimRT 的默认启动参数，
   *        若启动程序时给定  --cfg_file_path 参数，则将用外部参数文件，逐字段地覆盖默认参数。
   *
   * @param cfg 本模块的配置接口，可用于配置本模块所需的通信资源、执行器资源、以及本模块自己的参数。
   *
   * @note 通过 cfg 配置的通信资源、执行器资源，其相关对象生命周期必须要能延续到 OnInitialize() 阶段。
   */
  void OnConfigure(aimrte::ModCfg& cfg) override;

  /**
   * @brief 执行 AimRT 初始化阶段的工作，如，读取配置、初始化通信资源、以及获取执行器资源等。
   *        该阶段不应该启动、存在异步过程，框架的所有组件也是静默的，因此可以认为该过程是线程安全的。
   *
   * @note 在 OnConfigure() 阶段配置的通信资源、执行器资源，将被自动初始化。
   *
   * @return 是否初始化成功
   */
  bool OnInitialize() override;

  /**
   * @brief 执行 AimRT 启动阶段的工作，如，开启异步线程、协程等。
   *        该阶段所有框架组件也已经启动，也可能存在用户定义的异步过程，因此需要万分小心。
   *
   * @note 该函数在 main 线程中调用，不允许阻塞本函数，否则会导致其他模块被阻塞。
   *
   * @return 是否启动成功
   */
  bool OnStart() override;

  /**
   * @brief 执行 AimRT 关闭阶段的工作，如，回收用户资源、执行退出逻辑等。
   *        该阶段可能存在异步流程，因此需要万分小心。
   */
  void OnShutdown() override;

 private:
  /**
   * @brief 自定义的主循环
   */
  aimrte::Co<void> MainLoop() const;

  /**
   * @brief 进行一次消息发送
   */
  void DoPublish(const aimdk::protocol::BallChannel& msg) const;

  /**
   * @brief 进行一次 rpc
   */
  aimrte::Co<void> DoCall() const;

 private:
  // 本模块的配置，将在 OnConfigure() 阶段进行初始化。
  Option option_;
};
}  // namespace example::ping
