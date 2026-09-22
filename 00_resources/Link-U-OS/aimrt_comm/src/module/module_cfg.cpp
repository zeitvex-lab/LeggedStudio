// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./module_cfg.h"

namespace aimrte::ctx::cfg_details
{
Session::Session(ModuleCfg* cfg)
    : cfg_(cfg)
{
}

BasicPart Session::operator[](decltype(cfg::Module::Basic))
{
  return BasicPart(cfg_);
}

LoggerPart Session::operator[](decltype(cfg::Module::Logger))
{
  return LoggerPart(cfg_);
}

ExecutorPart Session::operator[](decltype(cfg::Module::Executor))
{
  return ExecutorPart(cfg_);
}

ChPart Session::operator[](const cfg::Ch methods)
{
  return ChPart(cfg_, methods);
}

RpcPart Session::operator[](const cfg::Rpc methods)
{
  return RpcPart(cfg_, methods);
}

BasicPart::BasicPart(ModuleCfg* cfg)
    : Session(cfg)
{
}

BasicPart& BasicPart::Enable(const bool value)
{
  cfg_->config_.enable = value;
  return *this;
}

BasicPart& BasicPart::Disable(const bool value)
{
  return Enable(not value);
}

LoggerPart::LoggerPart(ModuleCfg* cfg)
    : Session(cfg)
{
}

LoggerPart& LoggerPart::Level(const cfg::LogLevel value)
{
  cfg_->config_.log_lvl = value;
  return *this;
}

LoggerPart& LoggerPart::UseDefaultLevel()
{
  cfg_->config_.log_lvl.reset();
  return *this;
}

ExecutorPart::ExecutorPart(ModuleCfg* cfg)
    : Session(cfg)
{
}

ExecutorPart& ExecutorPart::Declare(Executor& res, std::string name)
{
  DoDeclare(res, std::move(name), false);
  return *this;
}

ExecutorPart& ExecutorPart::DeclareThreadSafe(Executor& res, std::string name)
{
  DoDeclare(res, std::move(name), true);
  return *this;
}

ExecutorPart& ExecutorPart::Def(Executor& res, std::string name, const std::uint32_t thread_num, std::vector<std::uint32_t> thread_bind_cpu, std::string thread_sched_policy)
{
  DoDef(res, std::move(name), false, thread_num, std::move(thread_bind_cpu), std::move(thread_sched_policy));
  return *this;
}

ExecutorPart& ExecutorPart::Def(Executor& res, std::string name)
{
  if (std::optional opt = Executor::GetOption(res); opt.has_value()) {
    DoDef(res, std::move(name), false, opt->thread_num, std::move(opt->thread_bind_cpu), std::move(opt->thread_sched_policy));
    return *this;
  }

  return Def(res, std::move(name), 1);
}

ExecutorPart& ExecutorPart::DefThreadSafe(Executor& res, std::string name)
{
  if (std::optional opt = Executor::GetOption(res); opt.has_value()) {
    DoDef(res, std::move(name), true, opt->thread_num, std::move(opt->thread_bind_cpu), std::move(opt->thread_sched_policy));
    return *this;
  }

  return DefThreadSafe(res, std::move(name), {});
}

ExecutorPart& ExecutorPart::DefThreadSafe(Executor& res, std::string name, std::vector<std::uint32_t> thread_bind_cpu, std::string thread_sched_policy)
{
  DoDef(res, std::move(name), true, 1, std::move(thread_bind_cpu), std::move(thread_sched_policy));
  return *this;
}

void ExecutorPart::DoDeclare(Executor& res, std::string name, const bool check_thread_safe)
{
  name = ReplaceWithFullName(std::move(name));
  cfg_->exes_.push_back({name});
  AddInitializer(res, std::move(name), check_thread_safe);
}

void ExecutorPart::DoDef(
  Executor& res, std::string name, const bool check_thread_safe, const std::uint32_t thread_num, std::vector<std::uint32_t> thread_bind_cpu, std::string thread_sched_policy)
{
  name = ReplaceWithFullName(std::move(name));
  cfg_->exes_.push_back({name, {{thread_num, std::move(thread_bind_cpu), std::move(thread_sched_policy)}}});
  AddInitializer(res, std::move(name), check_thread_safe);
}

std::string ExecutorPart::ReplaceWithFullName(std::string name) const
{
  if (name.starts_with("~/"))
    return cfg_->config_.name + name.substr(1);

  return name;
}

void ExecutorPart::AddInitializer(Executor& res, std::string name, bool check_thread_safe)
{
  res::details::Base::SetName(res, std::move(name));

  cfg_->resource_manager_->AddInitializer(
    [&res, name{res.GetName()}, check_thread_safe]() {
      if (check_thread_safe)
        res = init::ThreadSafeExecutor(name);
      else
        res = init::Executor(name);
    });
}

ChPart::ChPart(ModuleCfg* cfg, const cfg::Ch methods)
    : Session(cfg), methods_(methods)
{
  if (methods_ == cfg::Ch::Default) {
    for (const std::string& i : sys::config::DefaultChannelBackends()) {
      methods_ = methods_ | rfl::string_to_enum<cfg::Ch>(i).value();
    }
  }
}

ChPart& ChPart::DefPub(std::string name)
{
  cfg_->pubs_.push_back({methods_, std::move(name)});
  return *this;
}

ChPart& ChPart::DefSub(std::string name)
{
  cfg_->subs_.push_back({methods_, std::move(name)});
  return *this;
}

RpcPart::RpcPart(ModuleCfg* cfg, const cfg::Rpc methods)
    : Session(cfg), methods_(methods)
{
  if (methods_ == cfg::Rpc::Default) {
    for (const std::string& i : sys::config::DefaultRpcBackends()) {
      methods_ = methods_ | rfl::string_to_enum<cfg::Rpc>(i).value();
    }
  }
}

RpcPart& RpcPart::DefCli(std::string name)
{
  cfg_->clis_.push_back({methods_, std::move(name)});
  return *this;
}

RpcPart& RpcPart::DefSrv(std::string name)
{
  cfg_->srvs_.push_back({methods_, std::move(name)});
  return *this;
}
}  // namespace aimrte::ctx::cfg_details

namespace aimrte::ctx
{
ModuleCfg::ModuleCfg(Cfg* process_cfg, ContextResourceManager* resource_manager, std::string module_name)
    : Session(this), process_cfg_(process_cfg), resource_manager_(resource_manager)
{
  config_.name = std::move(module_name);
}

YAML::Node ModuleCfg::Yaml()
{
  return cfg_->process_cfg_->GetMutableModuleConfigYaml(cfg_->config_.name);
}
}  // namespace aimrte::ctx
