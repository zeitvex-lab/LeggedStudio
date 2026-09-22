#!/bin/sh

# 指定进程名称
export EM_APP_NAME="pong"

# 是否不注入框架配置
export AGIBOT_ENABLE_IGNORE_PREDEFINED_CFG="false"

# 是否使用程序上一次 dump 的配置，并不再注入框架配置
export AGIBOT_ENABLE_IGNORE_PREDEFINED_CFG_AND_USE_DUMP_FILE="false"

# 是否启用日志控制功能
export AGIBOT_ENABLE_LOG_CONTROL="false"

# 是否启用框架心跳功能
export AGIBOT_ENABLE_MONITOR="true"

# 是否启用通信 trace 功能
export AGIBOT_ENABLE_TRACE="true"

# 选择 HDS 告警链路通信后端（测试特性）
export AGIBOT_FEATURE_HDS_NEW_BACKEND="mqtt"

# 选择心跳链路通信后端（测试特性）
export AGIBOT_FEATURE_HEARTBEAT_NEW_BACKEND="ros2"

# 为 ros2 channel 通信统一指定 qos（测试特性）
export AGIBOT_FEATURE_ROS2_CHANNEL_QOS='
  history                  : "keep_last"
  depth                    : 10
  reliability              : "best_effort"
  liveliness               : "automatic"
  liveliness_lease_duration: 2000
'

# 为日志指定强制落盘时间间隔（ms）（测试特性）
export AGIBOT_FEATURE_LOG_SYNC_INTERVAL="5000"
