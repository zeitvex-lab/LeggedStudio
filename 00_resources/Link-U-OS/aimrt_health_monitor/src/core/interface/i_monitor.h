// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#ifndef I_MONITOR_H
#define I_MONITOR_H
#include <cstdint>
#include <filesystem>
#include <string>
#include <utility>
#include "src/core/context.h"
#include "src/core/res.h"
#include "src/ctx/ctx.h"

#include "yaml-cpp/yaml.h"

namespace aima::monitor {

class IMonitor {
 public:
  virtual ~IMonitor() = default;
  bool Initialize(const YAML::Node& config, Res& res);
  virtual bool Initialize(const YAML::Node& params) = 0;
  virtual bool Start() = 0;
  virtual void Shutdown() = 0;
  virtual void DiagnoseOnce() = 0;
  float GetRate() const;
  std::string GetName() const;

 protected:
  Res res_;

 private:
  float rate_;
  bool is_initialized_;
  std::string name_;
};

class MonitorRegister {
 public:
  MonitorRegister() = default;
  ~MonitorRegister() = default;
  static MonitorRegister* Instance();

  using RegisterFuncType = std::function<std::unique_ptr<IMonitor>()>;
  void Registe(const std::string& name, RegisterFuncType create_func) {
    registed_monitor_map_.emplace(name, create_func);
  }
  std::map<std::string, RegisterFuncType>& GetRegistedMonitorMap() {
    return registed_monitor_map_;
  }
  RegisterFuncType GetRegisterFunc(const std::string& name) {
    auto itr = registed_monitor_map_.find(name);
    if (itr == registed_monitor_map_.end()) {
      return nullptr;
    }
    return itr->second;
  }

 private:
  std::map<std::string, RegisterFuncType> registed_monitor_map_;
};

#define REGISTER_MONITOR_IMPL(class_name)                                                 \
  static inline auto class_name##_register = []() {                                       \
    MonitorRegister::Instance()->Registe(#class_name, []() { return std::make_unique<class_name>(); }); \
    return 0;                                                                             \
  }();

}  // namespace aima::monitor
#endif  // MONITOR_PLUGIN_H
