# 第二章 组件

## 插件：viz_plugin

### 概述
运行在业务节点侧，采集节点/模块与 RPC/Channel 的运行信息；通过 RPC 对外提供，供 `VizModule` 拉取。自身不含通信能力，复用已有通信后端（如 HTTP、ROS2）。

开启动态性能指标（频率）需在对应 RPC/Channel 启用 `viz` 过滤器。

### 配置项

| 配置项 | 类型 | 是否必选 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| executor | string | 必选 | "" | 用于更新信息的执行器名称 |
| update_interval | int | 可选 | 1000 | 更新动态信息的时间间隔，单位：毫秒 |
| node_name | string | 必选 | "" | 节点名称，默认作为 RPC 服务名使用 |
| service_name | string | 可选 | "" | 自定义 RPC 服务名 |
| soc | string | 必选 | "" | 当前节点所在的 SoC 标识，用于 Web 页面展示 |


### 示例

```yaml
aimrt:
  plugin:
    plugins:
      - name: viz_plugin
        path: ./libaimrt_viz_plugin.so
        options:
          executor: default_viz_executor
          update_interval: 1000
          node_name: rpc_server
          soc: x86_64
      - name: net_plugin
        path: ./libaimrt_net_plugin.so
        options:
          thread_num: 4
          http_options:
            listen_ip: 127.0.0.1
            listen_port: 50083

  rpc:
    backends:
      - type: http
    servers_options:
      - func_name: "(.*)"
        enable_backends: [http]
        enable_filters: [viz]

  channel:
    backends:
      - type: http
    sub_topics_options:
      - topic_name: "(.*)"
        enable_backends: [http]
        enable_filters: [viz]
```


## 模块：VizModule

### 概述
中心化聚合模块。通过 RPC 调用各节点的 `viz_plugin` 拉取数据，并对 Web 暴露统一 RPC 接口用于展示。

注意：`VizModule` 需挂载 `net_plugin`（HTTP）以对外提供服务。

### 配置项

| 配置项 | 类型 | 是否必选 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| system_name | string | 是 | "" | 系统名称标识 |
| work_executor_name | string | 是 | "" | 工作执行器名称 |
| node_service_list | array | 是 | "" | 待拉取的 `viz_plugin` 服务名列表 |
| attributes | array | 否 | "" | 自定义属性（key/value） |

### 示例

```yaml
aimrt:
  plugin:
    plugins:
      - name: net_plugin
        path: ./libaimrt_net_plugin.so
        options:
          thread_num: 4
          http_options:
            listen_ip: 0.0.0.0
            listen_port: 50090

VizModule:
  system_name: "VizModule"
  work_executor_name: work_executor
  node_service_list:
    - channel_pub
    - channel_sub
    - rpc_client
    - rpc_server
    - viz_module
  attributes:
    - key: "开发时间"
      value: "2025年5月"
```


## Web 前端

### 本地开发

```bash
cd src/tools/viz_web
npm install
npm run
```




