// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <mutex>
#include "ros2/demo/GetLatestBall.h"
#include "src/all_in_one/include/aimrte.h"

#include "./ball.h"

namespace example::pong
{
class Module final : public aimrte::Mod
{
 public:
  struct Option {
    // 用于接收的通道，默认构造中的话题名称，将在 OnConfigure() 阶段使用。
    // 由于使用的是自定义类型，而不是直接支持的通信数据类型（protobuf 或 ros2 protocol 类型），
    // 因此，需要在某个地方（本例子在 module.cpp 中）定义转换过程。
    aimrte::Sub<Ball> sub{"/example/ping_pong_ball"};

    // 支持使用 ros 数据类型进行通信
    aimrte::Sub<demo_msgs::msg::Ball> sub_ros{"/example/ping_pong_ball/ros"};

    // rpc 服务端。该对象需要维持和模块等长的生命周期。
    aimdk::protocol::res::DemoService srv;

    // 支持 ros 数据格式的 srv，但通信后端不一定需要是 ros 的
    demo_msgs::srv::res::GetLatestBall srv_ros;

    // 自定义 service name 的 rpc 服务端
    aimdk::protocol::res::DemoService srv_renamed;

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
   * @brief 初始化接收球信息的订阅信道。该订阅处理在原生通信后端内运行。
   */
  void InitSubscriber();

  /**
   * @brief 初始化对外提供的球信息获取服务。该服务在指定执行器上运行。
   */
  void InitServer();

 private:
  // 本模块的配置
  Option option_;

  // 确保球的访问安全
  std::mutex ball_mutex_;

  // 最新收到的球信息
  std::shared_ptr<const Ball> latest_ball_;
};
}  // namespace example::pong
