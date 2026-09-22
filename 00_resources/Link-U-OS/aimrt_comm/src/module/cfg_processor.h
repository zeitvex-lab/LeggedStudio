// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "./cfg.h"
#include "./module_cfg.h"

namespace aimrte
{
class Cfg::Processor
{
 public:
  explicit Processor(Cfg& cfg);

  void SetUserPatchConfigFilePaths(std::vector<std::string> paths);

 private:
  void AddHDSCfg();

  void AddTraceEventCfg();

  void AddMonitorCfg();

  void AddVizCfg();

  void AddLogControlCfg();

  void AddDefaultNet();

  void AddDefaultBackends();

  void AddCommunicationOption(cfg::backend::ch::udp::PubOption option);

  void SetRos2ChannelQos();

  void SetLogSync();

  void AddDefaultLocal();

  /**
   * @brief 注入框架的默认配置
   */
  void InjectDefaultCfg();

  /**
   * @brief 注入 AimRTe 提供的默认配置到 aimrt yaml node 中
   */
  void InjectDefaultCfgToAimRTNode(YAML::Node res);

 public:
  /**
   * @brief 追加给定的模块信息
   */
  void AddModuleConfig(const ctx::ModuleCfg& cfg);

  /**
   * @return 框架的启动配置
   */
  [[nodiscard]] cfg::details::CoreConfig GetCoreConfig() const;

  /**
   * @brief 将配置对象中的内容，与用户给定的外部配置合并，生成一份临时配置，供本次加载使用
   * @return 临时配置文件的路径，调用者要负责删除它
   */
  std::string DumpFile();

 private:
  /**
   * @brief 将配置对象转换为 yaml
   */
  [[nodiscard]] YAML::Node MakeYamlFromCfg();

  /**
   * @brief 合并 yaml 中的 aimrt 节点
   */
  static void MergeAimRTNode(YAML::Node res, YAML::Node ext);

  /**
   * @brief 合并 yaml 中的 aimrt.log 节点
   */
  static void MergeAimRTLogNode(YAML::Node res, YAML::Node ext);

  /**
   * @brief 合并 yaml 中的 aimrt.plugin 节点
   */
  static void MergeAimRTPluginNode(YAML::Node res, YAML::Node ext);

  /**
   * @brief 合并 yaml 中的 aimrt.channel 节点
   */
  static void MergeAimRTChannelNode(YAML::Node res, YAML::Node ext);

  /**
   * @brief 合并 yaml 中的 aimrt.rpc 节点
   */
  static void MergeAimRTRpcNode(YAML::Node res, YAML::Node ext);

  /**
   * @brief 合并 yaml 中的 aimrt.executor 节点
   */
  static void MergeAimRTExecutorNode(YAML::Node res, YAML::Node ext);

  /**
   * @brief 合并 yaml 中的 aimrt.module 节点
   */
  static void MergeAimRTModuleNode(YAML::Node res, YAML::Node ext);

  /**
   * @brief 给定内部配置的根 yaml 以及用户从外部给定的根 yaml，将外部给定的配置中的自定义模块配置，
   *        合并入最终配置中。
   */
  static void MergeCustomNodes(YAML::Node& yaml, const YAML::Node& ext_yaml);

  /**
   * @brief 合并 ext 列表型 yaml 中的内容到 res 列表型 yaml 的对应元素上。
   *        若 res 列表中存在 ext 不存在的元素，将被删除。
   * @param id_key 用于表示是否是同一个 yaml 元素的字段名称
   */
  static void MergeListNode(YAML::Node res, YAML::Node ext, const std::string& id_key);

  /**
   * @brief 合并 ext 与 res 的列表型 yaml 内容，但使用给定的处理器，去合并对应的字段
   */
  static void MergeListNode(
    YAML::Node res, YAML::Node ext, const std::string& id_key, const std::function<void(YAML::Node sub_res, YAML::Node sub_ext)>& handler);

  /**
   * @brief 遍历 ext yaml 的各个字段，合并到 res yaml 对应字段中，若字段名称隶属于给定的列表里，
   *        则按列表合并规则处理它们的合并
   * @param res 要求是 map 类型的 yaml
   * @param ext 要求是 map 类型的 yaml
   * @param possible_list 字段名称与其内部内容的 key id 字段的名称，将用它的 key id 进行列表规则的合并
   */
  static void MergeMapNodeWithSubList(
    YAML::Node res, YAML::Node ext, const std::map<std::string, std::string>& possible_list);

  /**
   * @brief 遍历 ext yaml 的各个字段，直接写入到 res yaml 对应字段中。
   *        若字段是结构体类型，将进一步递归处理。
   */
  static void MergeMapNode(YAML::Node res, YAML::Node ext);

 private:
  enum class PatchMode : std::uint32_t {
    Undefined     = 0,
    Override      = 1,
    OverrideFront = 1 << 1,
    OverrideBack  = 1 << 2,
    Skip          = 1 << 3,
    NewFront      = 1 << 4,
    NewBack       = 1 << 5,
    NewNever      = 1 << 6,
    Delete        = 1 << 7,
    Explicit      = 1 << 8,
    Merge         = 1 << 9,
  };

  friend bool operator&(PatchMode lhs, PatchMode rhs)
  {
    return (static_cast<std::uint32_t>(lhs) & static_cast<std::uint32_t>(rhs)) != 0;
  }

  friend PatchMode operator|(PatchMode lhs, PatchMode rhs)
  {
    return static_cast<PatchMode>(static_cast<std::uint32_t>(lhs) | static_cast<std::uint32_t>(rhs));
  }

  friend PatchMode operator|=(PatchMode& lhs, PatchMode rhs)
  {
    return lhs = lhs | rhs;
  }

  /**
   * @brief 分析给定 yaml 配置节点的补丁模式，多个模式将合并到一个值中返回，
   *        用 | 分析各个 bit，确定是否有启用对应的模式。
   */
  [[nodiscard]] PatchMode AnalyzePatchMode(const YAML::Node& node) const;

  /**
   * @brief 分析指定 yaml 节点是否附带 !!override 标签，用于各个相对顶层的配置节点，实现整体替换
   */
  [[nodiscard]] bool HasExplicitOverridePatchMode(const YAML::Node& node) const;

  /**
   * @brief 增量地补丁配置中的 airmt 节点。
   *
   *  通过在补丁配置的各个地方，使用不同的 yaml tag 来告知系统合并规则，支持以下几种：
   *  1. override，将合并存在的同名字段；若没有设置任何 tag，默认使用 override 规则；
   *  2. skip，将跳过存在的同名字段；
   *  3. new，若不存在同名字段时，进行新增。如果指明该模式，在这种情况下将报“未使用配置”的错误；
   *  4. delete，将删除存在的同名字段。
   *
   *  以上模式通过 + 相连，代表一起生效，可以用以下几种使用场景：
   *  1. delete，删除同名字段；
   *  2. new，新增配置字段；若已存在同名字段，将报错；
   *  3. new+override，若存在同名字段，则进行覆盖；若不存在，则新增配置；
   *  4. new+skip，若存在同名字段，则跳过不处理；若不存在，则新增配置；
   *  5. new+delete，若存在同名字段，则删除它；若不存在，则新增配置；
   *  6. 不指定任何 tag 时，等价于 override，若存在同名字段，则覆盖；若不存在，则报错；
   *  7. skip，跳过该配置；
   *  8. merge，比较，如果不存在，则直接添加，如果存在，则比较相同节点，已配置中的为准，替换已有的
   *
   *  新增配置、覆盖配置时，可以指定将插入的位置，有如下几种：
   *  1. new.front，等价于 new，也即是新增的默认操作，总是将新增配置在数组的最前插入；
   *  2. new.back，总是将新增配置在数组的最后插入；
   *  3. override，在配置当前所在位置覆写，不调整位置；
   *  4. override.front，覆写同名配置后，将配置调整到数组的最前；
   *  5. override.back，复现同名配置后，将配置调整到数组的最后。
   *
   *  以上所述的补丁模式，可是使用在 AimRT 所有的列表型配置的各个元素中，包括：
   *  - log.backends
   *  - plugin.plugins
   *  - channel.backends
   *  - channel.backends 元素的 options.pub_topics_options 与 options.sub_topics_options
   *  - channel.pub_topics_options
   *  - channel.pub_topics_options 元素的 enable_backends 与 enable_filters
   *  - channel.sub_topics_options
   *  - channel.sub_topics_options 元素的 enable_backends 与 enable_filters
   *  - rpc.backends
   *  - rpc.backends 元素的 options.servers_options 与 options.clients_options
   *  - rpc.servers_options
   *  - rpc.servers_options 元素的 enable_backends 与 enable_filters
   *  - rpc.clients_options
   *  - rpc.clients_options 元素的 enable_backends 与 enable_filters
   *  - executor.executors
   *  - module.pkgs
   *  - module.modules
   *  特别的，支持给以上数组元素添加 !!override 标签，表示整体覆盖替换。
   *  AimRT 其他普通 map 类型配置，均使用逐项覆盖的方式进行配置补丁。
   *
   * @param res 用户预定义、且合并了 aimrt 外部配置后的 aimrt yaml 节点
   * @param ext 任意配置文件中的 aimrte yaml 节点
   */
  void PatchAimRTNode(YAML::Node res, YAML::Node ext) const;

  /**
   * @brief 补丁 yaml 中的 aimrte.log 节点
   */
  void PatchAimRTLogNode(YAML::Node res, YAML::Node ext) const;

  /**
   * @brief 补丁 yaml 中的 aimrte.plugin 节点
   */
  void PatchAimRTPluginNode(YAML::Node res, YAML::Node ext) const;

  /**
   * @brief 补丁 yaml 中的 aimrte.channel 节点
   */
  void PatchAimRTChannelNode(YAML::Node res, YAML::Node ext) const;

  /**
   * @brief 补丁 yaml 中的 aimrte.rpc 节点
   */
  void PatchAimRTRpcNode(YAML::Node res, YAML::Node ext) const;

  /**
   * @brief 补丁 yaml 中的 aimrte.executor 节点
   */
  void PatchAimRTExecutorNode(YAML::Node res, YAML::Node ext) const;

  /**
   * @brief 补丁 yaml 中的 aimrte.module 节点
   */
  void PatchAimRTModuleNode(YAML::Node res, YAML::Node ext) const;

  /**
   * @brief 将 ext 列表型 yaml 中的内容逐项补丁到 res 列表型 yaml 的对应元素上。
   *        若 ext 拥有 !!override 标签，则整体覆盖替换。
   * @param id_key 用于表示是否是同一个 yaml 元素的字段名称。若 id_key 为空，则将把元素整体作为键值比对。
   */
  void PatchListNode(YAML::Node res, YAML::Node ext, const std::string& id_key) const;

  /**
   * @brief 补丁 ext 内容到 res 中，但使用给定的处理器，去进一步处理对应的字段
   */
  void PatchListNode(
    YAML::Node res, YAML::Node ext, const std::string& id_key, const std::function<void(YAML::Node sub_res, YAML::Node sub_ext)>& handler) const;

  /**
   * @brief 遍历 ext yaml 的各个字段，覆盖到 res yaml 对应字段中，若字段名称隶属于给定的列表里，
   *        则按列表补丁规则处理它们的补丁
   * @param res 要求是 map 类型的 yaml
   * @param ext 要求是 map 类型的 yaml
   * @param possible_list 字段名称与其内部内容的 key id 字段的名称，将用它的 key id 进行列表规则的补丁
   */
  void PatchMapNodeWithSubList(YAML::Node res, YAML::Node ext, const std::map<std::string, std::string>& possible_list) const;

  /**
   * @brief 补丁最简单的、不包含任何可以进一步分析的子结构的配置
   */
  void PatchMapNode(YAML::Node res, YAML::Node ext) const;

  /**
   * @brief 产生未知模式的报错
   */
  void PanicUnsupportedMode(const YAML::Node& node, const std::string& mode_str) const;

 private:
  /**
   * @return 提取的自定义 yaml tag 内容
   */
  static std::string_view ExtractCustomTag(const YAML::Node& node);

  /**
   * @brief 读取指定路径的 yaml 文件，将自动将其中的环境变量进行求值。
   *        将设置本类的 current_processing_yaml_file_path_ 成员，用于错误提示。
   */
  YAML::Node ReadYaml(const std::string& path);

  /**
   * @brief 追加指定元素到 yaml 列表的最前方
   */
  static void PushFront(YAML::Node& list, YAML::Node element);

  /**
   * @brief 比较两个 yaml 节点，如果存在，则比较相同节点，已配置中的为准，替换已有的
   */
  static void CompareAndReplaceNode(YAML::Node res, YAML::Node ext);

 private:
  Cfg& cfg_;

  // 模块资源的统计收集
  std::map<std::string, std::set<cfg::Ch>> pubs_, subs_;
  std::map<std::string, std::set<cfg::Rpc>> clis_, srvs_;
  std::map<std::string, cfg::details::ExeConfig> exes_;

  // 用户的补丁配置
  std::vector<std::string> user_patch_config_file_paths_;

  // 当前正在处理的 yaml 文件路径
  std::string current_processing_yaml_file_path_;
};
}  // namespace aimrte
