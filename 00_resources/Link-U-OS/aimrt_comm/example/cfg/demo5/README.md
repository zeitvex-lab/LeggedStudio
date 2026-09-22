# 增量地补丁配置中的 airmt 节点

通过在补丁配置的各个地方，使用不同的 yaml tag 来告知系统合并规则，支持以下几种：

1. **override**：将合并存在的同名字段；若没有设置任何 tag，默认使用 override 规则；
2. **skip**：将跳过存在的同名字段；
3. **new**：若不存在同名字段时，进行新增。如果指明该模式，在这种情况下将报“未使用配置”的错误；
4. **delete**：将删除存在的同名字段。

以上模式通过 `+` 相连，代表一起生效，可以用以下几种使用场景：

1. **delete**：删除同名字段；
2. **new**：新增配置字段；若已存在同名字段，将报错；
3. **new+override**：若存在同名字段，则进行覆盖；若不存在，则新增配置；
4. **new+skip**：若存在同名字段，则跳过不处理；若不存在，则新增配置；
5. **new+delete**：若存在同名字段，则删除它；若不存在，则新增配置；
6. 不指定任何 tag 时，等价于 override，若存在同名字段，则覆盖；若不存在，则报错；
7. **skip**：跳过该配置；
8. **merge**：比较，如果不存在，则直接添加，如果存在，则比较相同节点，已配置中的为准，替换已有的

新增配置、覆盖配置时，可以指定将插入的位置，有如下几种：

1. **new.front**：等价于 new，也即是新增的默认操作，总是将新增配置在数组的最前插入；
2. **new.back**：总是将新增配置在数组的最后插入；
3. **override**：在配置当前所在位置覆写，不调整位置；
4. **override.front**：覆写同名配置后，将配置调整到数组的最前；
5. **override.back**：复现同名配置后，将配置调整到数组的最后。

以上所述的补丁模式，可是使用在 AimRT 所有的列表型配置的各个元素中，包括：

- `log.backends`
- `plugin.plugins`
- `channel.backends`
- `channel.backends` 元素的 `options.pub_topics_options` 与 `options.sub_topics_options`
- `channel.pub_topics_options`
- `channel.pub_topics_options` 元素的 `enable_backends` 与 `enable_filters`
- `channel.sub_topics_options`
- `channel.sub_topics_options` 元素的 `enable_backends` 与 `enable_filters`
- `rpc.backends`
- `rpc.backends` 元素的 `options.servers_options` 与 `options.clients_options`
- `rpc.servers_options`
- `rpc.servers_options` 元素的 `enable_backends` 与 `enable_filters`
- `rpc.clients_options`
- `rpc.clients_options` 元素的 `enable_backends` 与 `enable_filters`
- `executor.executors`
- `module.pkgs`
- `module.modules`

特别的，支持给以上数组元素添加 `!!override` 标签，表示整体覆盖替换。AimRT 其他普通 map 类型配置，均使用逐项覆盖的方式进行配置补丁。

**参数说明**:

- `res`：用户预定义、且合并了 aimrt 外部配置后的 aimrt yaml 节点
- `ext`：任意配置文件中的 aimrte yaml 节点