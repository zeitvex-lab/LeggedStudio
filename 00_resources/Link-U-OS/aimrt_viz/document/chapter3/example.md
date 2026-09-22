# 第三章 示例

本章节提供viz 前端的说明：

Web界面采用三栏式布局设计：

- 左侧导航栏：包含四个主要功能模块的导航入口
  - System：系统概览信息
  - Node：节点详细信息
  - RPC：RPC通信监控
  - Channel：Channel通信监控
- 中部上方：填写连接的机器人IP地址，viz_module 占用的端口是 50090
- 右侧控制区：页面刷新时间设置

## System 页面

System 页面分为基本信息和其他信息，分别对应的是 module 所配置的 system_name 和 attributes

![System 页面](./pic/system.png)


## Node 页面

### Node 列表页

- 支持按节点名称、SOC型号和在线状态进行筛选
- 每个节点展示运行信息，包括在线时长、SOC型号、进程ID等实时状态数据

![节点列表页](./pic/node_idx.png)


### Node 详情页面

该详情页面提供了节点的完整配置信息，包括：
- 动态运行信息：内存占用、CPU使用率、在线时长等实时状态数据
- 静态配置信息：插件配置、日志配置、执行器配置等
- 通信配置：Channel发布/订阅配置、RPC客户端/服务端配置
- 通信对端信息：显示每个Channel的发布/订阅对端节点，以及每个RPC客户端/服务端的对端连接信息

![节点详情页](./pic/node_detail.png)

## Channel 页面

### Channel 列表页
该页面提供了Channel通信的全面监控视图，展示每个Channel主题的详细配置信息，包括：
- 后端配置：显示各Channel主题使用的通信后端类型（如HTTP、ROS2等）
- 过滤器配置：展示应用于Channel通信的过滤器设置
- 统计信息：实时显示当前系统中活跃的Channel发布者和订阅者数量以及对应的频率

![Channl 列表页](./pic/channel_idx.png)

### channel 详情页
该页面提供了每个Channel主题的详细监控数据，包括：
- 消息类型的Schema定义
- 每个发布者和订阅者的频率统计
- 使用的通信后端信息
- 发布者与订阅者之间的拓扑关系图

![channl 详情页](./pic/channel_detail.png)


## Rpc 页面

### Rpc 列表页

该页面提供了RPC通信的全面监控视图，展示每个RPC服务的详细配置信息，包括：
- 后端配置：显示各RPC服务使用的通信后端类型（如HTTP、ROS2等）
- 过滤器配置：展示应用于RPC通信的过滤器设置
- 统计信息：实时显示当前系统中活跃的RPC客户端和服务端数量以及对应的qps

![RPC 列表页](./pic/rpc_idx.png)


### Rpc 详情页

该页面提供了RPC服务的详细监控数据，包括：
- 请求和响应的Schema定义
- 每个使用该RPC服务的客户端QPS统计
- 使用的通信后端信息
- 客户端与服务端之间的拓扑关系图

![Rpc 详情页](./pic/rpc_detail.png)
