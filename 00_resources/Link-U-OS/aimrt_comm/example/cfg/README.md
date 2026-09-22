# AimRTe 配置示例 (cfg)

本目录包含一系列 AimRTe 框架配置使用的示例程序，展示了不同的模块配置和通信方式。

## 目录结构

```
cfg/
├── demo1/          # 基础配置：使用 ModuleBase 的经典模式
├── demo2/          # 高级配置：手动管理模块实例与后端配置
├── demo3/          # 嵌套配置：复杂结构体中的 Channel/RPC/Executor 定义
├── demo4/          # 类型转换：自定义类型与协议类型的映射
├── demo5/          # 全自动配置：ConfigAndDefineByDefault 简化模式
└── BUILD           # 打包配置
```

---

## Demo1 - 基础模块配置

**演示内容**: 使用 `ModuleBase` 基类创建模块，展示基本的配置流程。

### 核心特性

- 继承 `aimrte::ctx::ModuleBase`
- 使用 `OnConfigure` 配置 Channel 和 Executor
- 支持 ROS2 和 MQTT 双后端发布

### 关键代码

```cpp
void OnConfigure(aimrte::ctx::ModuleCfg& cfg) override
{
  using namespace aimrte::cfg;

  cfg
    [Module::Basic]
      .Config(option)

        [Module::Logger]
      .Level(LogLevel::Info)

        [Ch::ros2 | Ch::mqtt]    // 同时使用 ROS2 和 MQTT 后端
      .Def(publisher_, option.topic_name)

        [Module::Executor]
      .Declare(exe_, option.executor_name);
}
```

### 启动配置

```cpp
cfg
  .WithDefaultLogger()
  .WithDefaultTimeoutExecutor()
  .WithDefaultMqtt()
  .WithDefaultRos()
  .SetModuleConfig("my_module", MyModule::MyOption{...});
```

---

## Demo2 - 手动管理模块与后端配置

**演示内容**: 模块实例的手动管理，以及手动配置通信后端。

### 核心特性

- 模块在外部实例化，自己管理生命周期
- 手动配置 ROS2 Channel/RPC 后端
- 支持外部配置文件合并（缺失字段使用默认值）

### 关键代码

```cpp
// 可实例化 AimRTe 模块，自己管理
MyModule my_module;
my_module.option = {
  .pub_topic_name = "my_pub_topic",
  .sub_topic_name = "my_sub_topic",
};

// 若没有给定外部的配置、或者外部配置字段缺失的，将采用给定对象对应字段的默认值
cfg.GetModuleConfig("my_module", my_module.option);

// 手动配置 ros2 后端
cfg[aimrte::cfg::backend::Plugin::ros2] = {};

cfg[aimrte::cfg::backend::Ch::ros2] = {
  .options = {{
    .pub_topics_options = {{
      {
        .topic_name = default_pub_topic_name,
        .qos        = {{.reliability{"best_effort"}}},
      },
    }},
  }},
};

// 将自己的局部对象创建为 std::shared_ptr 传入，但生命周期仍然归自己管
return aimrte::Run(cfg, {{"my_module", aimrte::trait::AddressOf(my_module)}});
```

---

## Demo3 - 嵌套结构体配置

**演示内容**: 在复杂嵌套结构体中定义 Channel、RPC 和 Executor。

### 核心特性

- 支持嵌套结构体中定义 Pub/Sub
- 支持嵌套结构体中定义 Executor
- 支持 `ignore_invalid` 忽略无效配置
- 私有执行器命名 (`~/my_private_executor`)

### 关键代码

```cpp
struct Option {
  aimrte::Pub<aimdk::protocol::BallChannel> pub{"/my/pub/topic"};
  aimrte::Sub<aimdk::protocol::BallChannel> sub{"/my/sub/topic"};

  aimrte::Exe exe{"my_executor"};
  aimrte::Exe mod_exe{"~/my_private_executor"};
  aimrte::Exe mode_exe2{"global_executor_maybe_multiple_defined", 3};

  // 嵌套的 Channel 定义
  struct {
    aimrte::Pub<aimdk::protocol::BallChannel> pub{"/my/nested/pub/topic"};
    aimrte::Sub<aimdk::protocol::BallChannel> sub{"/my/nested/sub/topic"};
  } nested_ch;

  // 嵌套的 RPC 定义
  struct {
    aimrte::Pub<aimdk::protocol::BallChannel> pub{"/my/nested/unused/pub/topic"};
    aimrte::Sub<aimdk::protocol::BallChannel> sub{"/my/nested/unused/sub/topic"};
    aimdk::protocol::res::DemoServiceProxy cli;
  } nested_rpc;

  // 嵌套的 Executor 定义
  struct {
    aimrte::Exe exe1{"/my/global/exe"};
    aimrte::Exe exe2{"~/my/private/exe"};
  } nested_exe;
};
```

### 配置定义

```cpp
cfg
  [Ch::ros2]
  .Def(option.pub)
  .Def(option.sub)  // 注意，sub 要求其至少生存至初始化阶段

    [Ch::mqtt]
  .Def(option.nested_ch)  // 绑定嵌套类型

    [Rpc::ros2]
  .Def(option.srv)  // 注意，srv 需要一直生存至模块执行结束

    [Module::Executor]
  .Declare(option.exe)      // 声明执行器，但不定义配置
  .Def(option.mod_exe, 2)   // 定义执行器，如果出现同名，将报错
  .Def(option.nested_exe);  // 支持嵌套定义执行器
```

---

## Demo4 - 自定义类型转换

**演示内容**: 自定义类型与协议类型之间的转换映射。

### 核心特性

- 定义类型转换函数
- 注册全局唯一的转换类型
- 使用原生类型进行 Pub/Sub

### 关键代码

```cpp
// 定义类型转换函数
namespace aimrte::impl
{
template <>
void Convert(const int& src, aimdk::protocol::BallChannel& dst)
{
  dst.mutable_ball()->set_msg("int value " + std::to_string(src));
}

template <>
void Convert(const aimdk::protocol::BallChannel& src, int& dst)
{
  // 反向转换
}
}

// 注册全局唯一的转换类型（仅可以定义一次）
namespace aimrte::convert
{
template <>
struct For<int> : By<aimdk::protocol::BallChannel> {
};
}
```

### 使用方式

```cpp
struct Option {
  aimrte::Pub<int> pub{"/my/pub/topic"};  // 直接使用 int 类型
  aimrte::Sub<int> sub{"/my/sub/topic"};
};

cfg
  [Ch::ros2 | Ch::mqtt]
  .Def(option_);  // 自动应用类型转换
```

---

## Demo5 - 全自动配置模式

**演示内容**: 使用 `ConfigAndDefineByDefault` 实现一键配置。

### 核心特性

- 最简化的配置方式
- 自动扫描并配置结构体中的所有资源
- 支持子配置节点

### 关键代码

```cpp
struct Option {
  aimrte::Pub<aimdk::protocol::BallChannel> pub{"/my/pub/topic"};
  aimrte::Sub<aimdk::protocol::BallChannel> sub{"/my/sub/topic"};

  aimrte::Exe exe1{"~/my_private_executor", 2};
  aimrte::Exe exe2{"global_executor_maybe_multiple_defined", 3};

  aimdk::protocol::res::DemoService srv;
  aimdk::protocol::res::DemoServiceProxy cli;

  std::chrono::steady_clock::duration t{std::chrono::seconds(1)};
  std::string param{"hello world"};
};

void OnConfigure(aimrte::ModCfg& cfg) override
{
  // 一键配置主选项
  cfg.ConfigAndDefineByDefault(option_);

  // 从子节点配置其他选项
  cfg.ConfigAndDefineByDefault(cfg.Yaml()["sub_option"], other_option_);
}
```

### 启动配置

```cpp
aimrte::Cfg cfg(argc, argv, "example_cfg_demo5");
return aimrte::Run(cfg, {{"my_module", std::make_shared<MyModule>()}});
```

---

## 配置补丁模式

AimRTe 支持增量地补丁配置，通过 YAML tag 指定合并规则：

| 模式 | 说明 |
|------|------|
| `override` | 覆盖存在的同名字段（默认） |
| `skip` | 跳过存在的同名字段 |
| `new` | 新增字段，存在则报错 |
| `delete` | 删除存在的同名字段 |
| `merge` | 不存在则添加，存在则以已配置为准 |

### 组合模式

- `new+override`: 存在则覆盖，不存在则新增
- `new+skip`: 存在则跳过，不存在则新增
- `new+delete`: 存在则删除，不存在则新增

### 插入位置

- `new.front`: 在数组最前插入（默认）
- `new.back`: 在数组最后插入
- `override.front`: 覆写后移至最前
- `override.back`: 覆写后移至最后

### 支持补丁的配置项

- `log.backends`
- `plugin.plugins`
- `channel.backends` 及其 `options.pub_topics_options` / `options.sub_topics_options`
- `channel.pub_topics_options` 及其 `enable_backends` / `enable_filters`
- `channel.sub_topics_options` 及其 `enable_backends` / `enable_filters`
- `rpc.backends` 及其 `options.servers_options` / `options.clients_options`
- `rpc.servers_options` 及其 `enable_backends` / `enable_filters`
- `rpc.clients_options` 及其 `enable_backends` / `enable_filters`
- `executor.executors`
- `module.pkgs`
- `module.modules`

---

## 依赖关系

所有示例都依赖以下库：

- `//:aimrte` - AimRTe 核心库
- `//aimdk/protocol/demo:demo_service_rpc` - 示例 RPC 服务定义
- `//aimdk/protocol/demo:demo_channel_cc_proto` - 示例 Channel 协议定义



---

[返回上一级](../README.md)
