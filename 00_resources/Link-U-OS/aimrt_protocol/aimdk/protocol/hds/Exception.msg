# Copyright (c) 2025, AgiBot Inc.
# All rights reserved.

#ms时间辍
uint64 timestamp
#异常类型
uint8 type
#模块ID
uint8 module_id
#模块异常码
uint32 code
#异常信息
string info

##############异常类型定义#####################

#正常类型 该类型异常需要周期性上报
uint8 TYPE_NORMAL = 0

#触发式异常 设置异常为产生状态
uint8 TYPE_TRIGGER_APPEAR = 1

#触发式异常 设置异常为消失状态
uint8 TYPE_TRIGGER_DISAPPEAR = 2
