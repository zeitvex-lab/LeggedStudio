# HDS

本目录放置了系统健康诊断的相关接口定义，包括系统健康诊断的查询、上报等。


## Channel

### 订阅消息

#### 模块异常信息

- topic名: `/aima/hds/exception`
- 消息类型：[`aimdk.protocol.ModuleExceptionChannel`](./exception_channel.proto)


### 发布消息

#### 实时产生或消失的告警信息

- topic名: `/aima/hds/alert`
- 消息类型：[`aimdk.protocol.AlertChannel`](./alert_channel.proto)

#### 机器人健康状态

- topic名: `/aima/hds/health_status`
- 消息类型：[`aimdk.protocol.HealthStatusChannel`](./health_channel.proto)


## Rpc

### 服务端

#### 查询系统中存活的告警事件

[`aimdk.protocol.HDSService.GetAlertList`](./hds_service.proto)

#### 清除指定的告警

[`aimdk.protocol.HDSService.ClearAlert`](./hds_service.proto)

#### 查询系统中的所有告警事件

[`aimdk.protocol.HDSService.GetTotalAlertList`](./hds_service.proto)

#### 查询当前系统中的异常事件

[`aimdk.protocol.HDSService.GetExceptionEvent`](./hds_service.proto)


### 客户端

暂无

