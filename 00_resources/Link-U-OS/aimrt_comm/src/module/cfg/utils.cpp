// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "./utils.h"
#include <stack>

namespace aimrte::cfg::details
{
void MergeMapNode(YAML::Node res, YAML::Node ext)
{
  // YAML::Node 是使用指针共享了同一份数据，因此我们可以认为这里记录的每一份子 node 对象，
  // 对它们的修改，最终都可以反应到根 node 上
  struct Data {
    YAML::Node res;
    YAML::Node ext;
  };

  // 使用栈代替递归实现
  std::stack<Data> stack;
  stack.push({res, ext});

  while (not stack.empty()) {
    Data curr = std::move(stack.top());
    stack.pop();

    // 若外部配置为空，则忽略这一层的判断
    if (IsUndefined(curr.ext))
      continue;

    // 若外部配置不是 map 类型，或内部配置不是 map 类型，则直接采纳外部配置的值
    if (not curr.res.IsMap() or not curr.ext.IsMap()) {
      curr.res = curr.ext;
      continue;
    }

    // 遍历外部配置的每一个键值对，替换掉内部配置中同名的字段内容
    for (const auto ext_it : curr.ext) {
      const auto field_name      = ext_it.first.as<std::string>();
      const YAML::Node ext_field = ext_it.second;

      stack.push({curr.res[field_name], ext_field});
    }
  }
}

bool IsUndefined(const YAML::Node& node)
{
  return not node.IsDefined() or node.IsNull();
}
}  // namespace aimrte::cfg::details
