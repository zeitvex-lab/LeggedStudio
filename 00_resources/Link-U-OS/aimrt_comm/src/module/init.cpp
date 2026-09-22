// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./init.h"

#include "aimdk/protocol/hds/exception_channel.pb.h"
#include "aimdk/protocol/trace/event_channel.pb.h"
#include "src/ctx/details/fs.h"
#include "src/hds/hds.h"
#include "src/trace/internal/context.h"

namespace aimrte::impl
{
template <>
void Convert(const hds::ModuleExceptionChannel& src, aimdk::protocol::ModuleExceptionChannel& dst)
{
  dst.mutable_timestamp()->set_ms_since_epoch(src.timestamp);
  for (auto one_exc : src.exception_list) {
    auto exception = dst.mutable_exception_list()->Add();
    exception->set_code(one_exc.module_exception);
    exception->set_module_id(one_exc.module_id);
    exception->set_info(one_exc.info);
    exception->mutable_timestamp()->set_ms_since_epoch(one_exc.timestamp);
    switch (one_exc.type) {
      case hds::ModuleException::Type::kNormal:
        exception->set_type(aimdk::protocol::ExceptionType_Normal);
        break;
      case hds::ModuleException::Type::kTriggerAppear:
        exception->set_type(aimdk::protocol::ExceptionType_Trigger_Appear);
        break;
      case hds::ModuleException::Type::kTriggerDisappear:
        exception->set_type(aimdk::protocol::ExceptionType_Trigger_Disappear);
        break;
    }
  }
}

template <>
void Convert(const aimdk::protocol::ModuleExceptionChannel& src, aimrte::hds::ModuleExceptionChannel& dst)
{
}

template <>
void Convert(const trace::internal::EventChannel& src, aimdk::protocol::EventChannel& dst)
{
  dst.mutable_header()->mutable_timestamp()->set_ms_since_epoch(src.timestamp);
  for (const auto& event : src.events) {
    auto event_ptr = dst.mutable_events()->Add();
    event_ptr->mutable_timestamp()->set_ms_since_epoch(event.timestamp);
    event_ptr->set_local_id(event.local_id);
    event_ptr->set_status(static_cast<aimdk::protocol::Event::Status>(event.status));
    event_ptr->set_name(event.name);
    event_ptr->set_code(event.code);
    event_ptr->set_module_id(event.module_id);
    for (const auto& attribute : event.attributes) {
      event_ptr->mutable_attributes()->insert({attribute.first, attribute.second});
    }
    event_ptr->set_event_content(event.event_content);
  }
}

template <>
void Convert(const aimdk::protocol::EventChannel& src, aimrte::trace::internal::EventChannel& dst)
{
}

}  // namespace aimrte::impl

namespace aimrte::ctx
{
static std::string_view GetModuleName(const core::Context& core_ctx)
{
  return core::Context::GetRawRef(core_ctx).Info().name;
}

static void InitFs(core::Context& core_ctx)
{
  core_ctx.InitSubContext<details::Fs>(
    core::Context::SubContext::Fs, std::string(GetModuleName(core_ctx)));
}

static void InitHDS(core::Context& core_ctx)
{
  auto& ctx = core_ctx.InitSubContext<hds::Context>(core::Context::SubContext::Hds);
  ctx.ch_ec = core_ctx.pub().Init<hds::ModuleExceptionChannel, convert::By<aimdk::protocol::ModuleExceptionChannel>>("/aima/hds/exception");
}

static void InitTrace(core::Context& core_ctx)
{
  auto& ctx    = core_ctx.InitSubContext<trace::internal::Context>(core::Context::SubContext::Trace);
  ctx.ch_event = core_ctx.pub().Init<trace::internal::EventChannel, convert::By<aimdk::protocol::EventChannel>>("/aimrte/trace/events");
}

std::shared_ptr<core::Context> Init(const aimrt::CoreRef core_ref)
{
  auto ctx_ptr = internal::InitWithoutSubsystems(core_ref);

  // 初始化各个子系统的上下文
  InitFs(*ctx_ptr);
  InitHDS(*ctx_ptr);
  InitTrace(*ctx_ptr);
  // 返回上下文信息给用户持有
  return ctx_ptr;
}

std::shared_ptr<core::Context> internal::InitWithoutSubsystems(aimrt::CoreRef core_ref)
{
  auto ctx_ptr = std::make_shared<core::Context>(core_ref);

  // 使能 ctx 全局函数
  core::details::g_thread_ctx = {ctx_ptr->weak_from_this()};

  // 返回上下文信息给用户持有
  return ctx_ptr;
}
}  // namespace aimrte::ctx
