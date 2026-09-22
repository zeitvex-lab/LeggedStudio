// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/core/core.h"
// #include "aimrte/hds/module_info/module.h"
#include <cstdint>
#include <memory>
#include <source_location>
#include <string>
#include "./context.h"

namespace aimrte::debug
{

/**
 * @brief aim-master客户端抛出debug信息
 * @tparam TException
 * @param info 模块消息

 * @param call_loc
 */
template <typename TException>
void Toast(const std::string& info = "", std::source_location call_loc = std::source_location::current())
{
  // // 获取 AimRTe 上下文
  // std::shared_ptr core_ctx = core::details::ExpectContext(call_loc);
  // using TModule            = typename aimrte::module::details::ModuleTypeTrait<TException>::ModuleType;
  // // 获取本系统的上下文
  // hds::Context& ctx = core::details::ExpectContext(call_loc)->GetSubContext<hds::Context>(core::Context::SubContext::Hds);

  // hds::ModuleException exc;
  // exc.timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::system_clock::now().time_since_epoch())
  //                   .count();
  // exc.module_id        = TModule::GetId();
  // exc.module_exception = 0;  // 0 为 debug 信息
  // exc.type             = hds::ModuleException::Type::kNormal;
  // exc.info             = info;

  // hds::ModuleExceptionChannel msg;
  // msg.timestamp = exc.timestamp;
  // msg.exception_list.push_back(exc);
  // // 发布异常码
  // core_ctx->pub().Publish(ctx.ch_ec, msg);
}

}  // namespace aimrte::debug

namespace aimrte::hds
{
/**
 * @brief 根据规则生成uint64异常码
 * @param module_id 模块ID
 * @param module_exception 模块异常
 * @return 生成的异常码
 */
inline uint64_t MakeExceptionCode(const uint8_t module_id, const uint32_t module_exception)
{
  return ((0xFFFFFFFFFFFFFFFF & module_id) << 32) | (0xFFFFFFFFFFFFFFFF & module_exception);
}

/**
 * @brief 将uint64异常码进行拆分 获取具体的异常
 * @param module_id 模块ID
 * @param module_exception 模块异常
 */
inline void SplitExceptionCode(uint64_t exception_code, uint8_t& module_id, uint32_t& module_exception)
{
  module_id        = (exception_code >> 32) & 0xFF;
  module_exception = (exception_code)&0xFFFFFFFF;
}

/**
 * @brief 抛出一次vector中所有的异常给健康诊断系统
 * @tparam TException
 * @param module_exc_list
 * @param call_loc
 */
template <typename TException>
void Throw(const std::vector<TException>& module_exc_list, const std::string& info = "", std::source_location call_loc = std::source_location::current())
{
  // using TModule = typename aimrte::module::details::ModuleTypeTrait<TException>::ModuleType;
  // // 获取 AimRTe 上下文
  // std::shared_ptr core_ctx = core::details::ExpectContext(call_loc);

  // // 获取本系统的上下文
  // Context& ctx = core::details::ExpectContext(call_loc)->GetSubContext<Context>(core::Context::SubContext::Hds);

  // ModuleExceptionChannel msg;
  // msg.timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::system_clock::now().time_since_epoch())
  //                   .count();
  // for (auto& one_exc : module_exc_list) {
  //   ModuleException exc;
  //   exc.timestamp        = msg.timestamp;
  //   exc.module_id        = TModule::GetId();
  //   exc.module_exception = static_cast<uint32_t>(one_exc);
  //   exc.type             = ModuleException::Type::kNormal;
  //   exc.info             = info;
  //   msg.exception_list.push_back(exc);
  // }

  // // 发布异常码
  // core_ctx->pub().Publish(ctx.ch_ec, msg);
}

/**
 * @brief 抛出一次该异常给告警系统(有异常时需要持续抛出,告警系统不做保持)
 * @tparam TException 模块名
 * @param module_exc 模块异常
 * @param call_loc
 */
template <typename TException>
void Throw(TException module_exc, const std::string& info = "", std::source_location call_loc = std::source_location::current())
{
  // using TModule = typename aimrte::module::details::ModuleTypeTrait<TException>::ModuleType;

  // // 获取 AimRTe 上下文
  // std::shared_ptr core_ctx = core::details::ExpectContext(call_loc);

  // // 获取本系统的上下文
  // Context& ctx = core::details::ExpectContext(call_loc)->GetSubContext<Context>(core::Context::SubContext::Hds);

  // ModuleException exc;
  // exc.timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::system_clock::now().time_since_epoch())
  //                   .count();
  // exc.module_id        = TModule::GetId();
  // exc.module_exception = static_cast<uint32_t>(module_exc);
  // exc.type             = ModuleException::Type::kNormal;
  // exc.info             = info;

  // ModuleExceptionChannel msg;
  // msg.timestamp = exc.timestamp;
  // msg.exception_list.push_back(exc);
  // // 发布异常码
  // core_ctx->pub().Publish(ctx.ch_ec, msg);
}

/**
 * @brief 直接抛出一次异常码与故障id给告警系统
 * @param module_id 模块ID
 * @param module_exception 模块异常
 * @param call_loc
 */
inline void ThrowCode(uint8_t module_id, uint32_t module_exception, std::source_location call_loc = std::source_location::current())
{
  // // 获取 AimRTe 上下文
  // std::shared_ptr core_ctx = core::details::ExpectContext(call_loc);

  // // 获取本系统的上下文
  // Context& ctx = core::details::ExpectContext(call_loc)->GetSubContext<Context>(core::Context::SubContext::Hds);

  // ModuleException exc;
  // exc.timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::system_clock::now().time_since_epoch())
  //                   .count();
  // exc.module_id        = module_id;
  // exc.module_exception = module_exception;
  // exc.type             = ModuleException::Type::kNormal;

  // ModuleExceptionChannel msg;
  // msg.timestamp = exc.timestamp;
  // msg.exception_list.push_back(exc);
  // // 发布异常码
  // core_ctx->pub().Publish(ctx.ch_ec, msg);
}

/**
 * @brief 设置列表中所有异常状态为产生(异常产生时只需抛出一次,告警系统自动做保持)
 * @tparam TException 模块名
 * @param module_exc_list 模块异常列表
 * @param call_loc
 */
template <typename TException>
void TriggerOn(const std::vector<TException>& module_exc_list, const std::string& info = "", std::source_location call_loc = std::source_location::current())
{
  // using TModule = typename aimrte::module::details::ModuleTypeTrait<TException>::ModuleType;

  // // 获取 AimRTe 上下文
  // std::shared_ptr core_ctx = core::details::ExpectContext(call_loc);

  // // 获取本系统的上下文
  // Context& ctx = core::details::ExpectContext(call_loc)->GetSubContext<Context>(core::Context::SubContext::Hds);

  // ModuleExceptionChannel msg;
  // msg.timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::system_clock::now().time_since_epoch())
  //                   .count();
  // for (auto& one_exc : module_exc_list) {
  //   ModuleException exc;
  //   exc.timestamp        = msg.timestamp;
  //   exc.module_id        = TModule::GetId();
  //   exc.module_exception = static_cast<uint32_t>(one_exc);
  //   exc.type             = ModuleException::Type::kTriggerAppear;
  //   exc.info             = info;

  //   msg.exception_list.push_back(exc);
  // }

  // // 发布异常码
  // core_ctx->pub().Publish(ctx.ch_ec, msg);
}

/**
 * @brief 设置该异常状态为产生(异常产生时只需抛出一次,告警系统自动做保持)
 * @tparam TException 模块名
 * @param module_exc 模块异常
 * @param call_loc
 */
template <typename TException>
void TriggerOn(TException module_exc, const std::string& info = "", std::source_location call_loc = std::source_location::current())
{
  // using TModule = typename aimrte::module::details::ModuleTypeTrait<TException>::ModuleType;

  // // 获取 AimRTe 上下文
  // std::shared_ptr core_ctx = core::details::ExpectContext(call_loc);

  // // 获取本系统的上下文
  // Context& ctx = core::details::ExpectContext(call_loc)->GetSubContext<Context>(core::Context::SubContext::Hds);

  // ModuleException exc;
  // exc.timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::system_clock::now().time_since_epoch())
  //                   .count();
  // exc.module_id        = TModule::GetId();
  // exc.module_exception = static_cast<uint32_t>(module_exc);
  // exc.type             = ModuleException::Type::kTriggerAppear;
  // exc.info             = info;

  // ModuleExceptionChannel msg;
  // msg.timestamp = exc.timestamp;
  // msg.exception_list.push_back(exc);

  // // 发布异常码
  // core_ctx->pub().Publish(ctx.ch_ec, msg);
}

/**
 * @brief 设置列表中所有异常状态为消失(异常消失时只需抛出一次,告警系统自动做保持)
 * @tparam TException 模块名
 * @param module_exc_list 模块异常列表
 * @param call_loc
 */
template <typename TException>
void TriggerOff(const std::vector<TException>& module_exc_list, std::source_location call_loc = std::source_location::current())
{
  // using TModule = typename aimrte::module::details::ModuleTypeTrait<TException>::ModuleType;

  // // 获取 AimRTe 上下文
  // std::shared_ptr core_ctx = core::details::ExpectContext(call_loc);

  // // 获取本系统的上下文
  // Context& ctx = core::details::ExpectContext(call_loc)->GetSubContext<Context>(core::Context::SubContext::Hds);

  // ModuleExceptionChannel msg;
  // msg.timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::system_clock::now().time_since_epoch())
  //                   .count();
  // for (auto& one_exc : module_exc_list) {
  //   ModuleException exc;
  //   exc.timestamp        = msg.timestamp;
  //   exc.module_id        = TModule::GetId();
  //   exc.module_exception = static_cast<uint32_t>(one_exc);
  //   exc.type             = ModuleException::Type::kTriggerDisappear;

  //   msg.exception_list.push_back(exc);
  // }

  // // 发布异常码
  // core_ctx->pub().Publish(ctx.ch_ec, msg);
}

/**
 * @brief 设置该异常状态为消失(异常消失时只需抛出一次,告警系统自动做保持)
 * @tparam TException 模块名
 * @param module_exc 模块异常
 * @param call_loc
 */
template <typename TException>
void TriggerOff(TException module_exc, std::source_location call_loc = std::source_location::current())
{
  // using TModule = typename aimrte::module::details::ModuleTypeTrait<TException>::ModuleType;

  // // 获取 AimRTe 上下文
  // std::shared_ptr core_ctx = core::details::ExpectContext(call_loc);

  // // 获取本系统的上下文
  // Context& ctx = core::details::ExpectContext(call_loc)->GetSubContext<Context>(core::Context::SubContext::Hds);

  // ModuleException exc;
  // exc.timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::system_clock::now().time_since_epoch())
  //                   .count();
  // exc.module_id        = TModule::GetId();
  // exc.module_exception = static_cast<uint32_t>(module_exc);
  // exc.type             = ModuleException::Type::kTriggerDisappear;

  // ModuleExceptionChannel msg;
  // msg.timestamp = exc.timestamp;
  // msg.exception_list.push_back(exc);
  // // 发布异常码
  // core_ctx->pub().Publish(ctx.ch_ec, msg);
}

}  // namespace aimrte::hds
