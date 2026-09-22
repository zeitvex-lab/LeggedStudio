// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/ctx/ctx.h"
#include "src/module/module.h"

namespace aimrte
{
/**
 * @brief 发送器
 */
template <class T>
using Pub = ctx::Publisher<T>;

/**
 * @brief 订阅器
 */
template <class T>
using Sub = ctx::Subscriber<T>;

/**
 * @brief 服务调用器，某个 service method 的客户端
 */
template <class Q, class P>
using Cli = ctx::Client<Q, P>;

/**
 * @brief 服务处理器，某个 service method 的服务端
 */
template <class Q, class P>
using Srv = ctx::Server<Q, P>;

/**
 * @brief 执行器
 */
using Exe = ctx::Executor;

/**
 * @brief AimRTe 的模块基类
 */
using Mod = ctx::ModuleBase;

/**
 * @brief AimRTe 的模块配置对象
 */
using ModCfg = ctx::ModuleCfg;

/**
 * @brief AimRTe 协程类型
 */
template <class T>
using Co = co::Task<T>;

/**
 * @brief 用于 rpc 的配置
 */
using RpcCfg = aimrt::rpc::Context;
}  // namespace aimrte
