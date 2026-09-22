// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/trait/trait.h"
#include <yaml-cpp/yaml.h>
#include <variant>
#include <vector>

namespace aimrte::cfg::details
{
/**
 * @brief 遍历 ext yaml 的各个字段，直接写入到 res yaml 对应字段中。
 *        若字段是结构体类型，将进一步递归处理。
 */
void MergeMapNode(YAML::Node res, YAML::Node ext);

/**
 * @brief 检查给定 yaml 节点是否未定义，空节点也认为是未定义
 */
bool IsUndefined(const YAML::Node& node);

/**
 * @brief 在数组容器中，找到指定类型的变体对象，并使用给定函数对其进行处理
 */
template <class T, class F, class... Ts>
bool Visit(std::vector<std::variant<Ts...>>& data, F&& func)
{
  for (std::variant<Ts...>& i : data) {
    if (trait::get_index<T, decltype(i)>::value == i.index()) {
      func(std::get<T>(i));
      return true;
    }
  }

  return false;
}
}  // namespace aimrte::cfg::details
