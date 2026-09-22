# AimDK hal 协议

## 简介

本目录放置了系统的 HAL 模块的协议，以支持系统的运动控制功能。

## 人形

### RPC

#### Neck

控制脖子运动、获取脖子状态

- [脖子运动控制接口](./neck/hal_neck_service.proto)

curl使用示例(以hal本机ip:127.0.0.1, hal默认监听端口56421为例)：

```
# 获取脖子状态
curl -i \
    -H 'content-type:application/json' \
    -X POST 'http://127.0.0.1:56421/rpc/aimdk.protocol.HalNeckService/GetNeckState' \
    -d '{}'

# 设置脖子目标位置，注意：当前只有位置控制，其余字段可忽略
curl -i \
    -H 'content-type:application/json' \
    -X POST 'http://127.0.0.1:56421/rpc/aimdk.protocol.HalNeckService/SetNeckCommand' \
    -d '{"data":{"shake":{"name":"neck_shake", "sequence":"1", "position":0.1, "velocity":0.0, "effort":0.0, "stiffness":0.0, "damping":0.0}}}'
```

控制字段解释,具体参考[脖子控制指令和状态接口](./neck/neck.proto)：

```
// 关节信息
message JointState {
  /**
   * 关节名称
   */
  string name = 1;

  /**
   * 关节消息的序号
   */
  uint32 sequence = 2;

  /**
   * 关节角度，单位：弧度 or m
   */
  double position = 3;

  /**
   * 关节角速度，单位：弧度/秒 or m/s
   */
  double velocity = 4;

  /**
   * 关节扭矩，单位：N or N*m
   */
  double effort = 5;
}

message JointCommand {
  /**
   * 关节名称
   */
  string name = 1;

  /**
   * 关节消息的序号
   */
  uint32 sequence = 2;

  /**
   * 关节角度，单位：弧度 or m
   */
  double position = 3;

  /**
   * 关节角速度，单位：弧度/秒 or m/s
   */
  double velocity = 4;

  /**
   * 关节扭矩，单位：N
   */
  double effort = 5;

  /**
   * 阻尼，单位： N·m/rad or N/m
   */
  double stiffness = 6;

  /**
   * 阻尼单位： N·s/m or N·m·s/rad
   */
  double damping = 7;
}
```

- 特别注意的是，目前只开放了位置的控制。

#### Hand

控制灵巧手运动、获取灵巧手状态

- [灵巧手运动控制接口](./hand/hal_hand_service.proto)

curl使用示例(以hal本机ip:127.0.0.1, hal默认监听端口56421为例)：

```
# 获取灵巧手状态
curl -i     -H 'content-type:application/json' \
            -H 'timeout: 60000'   -X POST 'http://127.0.0.1:56421/rpc/aimdk.protocol.HalHandService/GetHandState' \
            -d '{}'

# 设置灵巧手位置
curl -i     -H 'content-type:application/json' \
            -H 'timeout: 60000'   -X POST 'http://127.0.0.1:56421/rpc/aimdk.protocol.HalHandService/SetHandCommand' \
            -d '{"data":{"left":{"agi_hand":{"finger":{"pos":{"thumb_pos_0":0, "thumb_pos_1":0,"index_pos":0,"middle_pos":0,"ring_pos":0,"pinky_pos":0},"toq":{"thumb_toq_0":0, "thumb_toq_1":0,"index_toq":0,"middle_toq":0,"ring_toq":0,"pinky_toq":0}}}}, "right":{"agi_hand":{"finger":{"pos":{"thumb_pos_0":0, "thumb_pos_1":0,"index_pos":0,"middle_pos":0,"ring_pos":0,"pinky_pos":0},"toq":{"thumb_toq_0":0, "thumb_toq_1":0,"index_toq":0,"middle_toq":0,"ring_toq":0,"pinky_toq":0}}}}}}'
```

控制字段解释,具体参考[灵巧手控制指令和状态接口](./hand/agi_hand.proto)：

```
message FingerPos {
  // 拇指第一关节，取值范围：0-2000
  int32 thumb_pos_0 = 1;
  // 拇指第二关节，取值范围：0-2000
  int32 thumb_pos_1 = 2;
  // 食指，取值范围：0-2000
  int32 index_pos = 3;
  // 中指，取值范围：0-2000
  int32 middle_pos = 4;
  // 无名指，取值范围：0-2000
  int32 ring_pos = 5;
  // 小指，取值范围：0-2000
  int32 pinky_pos = 6;
}

message FingerToq {
  // 拇指第一关节，取值范围：0-5700（5700代表57N）
  int32 thumb_toq_0 = 1;
  // 拇指第二关节，取值范围：0-5700（5700代表57N）
  int32 thumb_toq_1 = 2;
  // 食指，取值范围：0-5700（5700代表57N）
  int32 index_toq = 3;
  // 中指，取值范围：0-5700（5700代表57N）
  int32 middle_toq = 4;
  // 无名指，取值范围：0-5700（5700代表57N）
  int32 ring_toq = 5;
  // 小指，取值范围：0-5700（5700代表57N）
  int32 pinky_toq = 6;
}
```

#### BMS

获取BMS状态

- [BMS查询和控制接口](./bms/hal_bms_service.proto)

curl使用示例(以hal本机ip:127.0.0.1, hal默认监听端口56421为例)：

```
# 获取BMS状态
curl -i     -H 'content-type:application/json' \
            -H 'timeout: 60000'   -X POST 'http://127.0.0.1:56421/rpc/aimdk.protocol.HalBmsService/GetBmsState' \
            -d '{}'

// BMS电池包MOSFE控制，具体控制指令参考bms.proto文件中PowerMosfeCmd枚举
curl -i     -H 'content-type:application/json' \
            -H 'timeout: 60000'   -X POST 'http://127.0.0.1:56421/rpc/aimdk.protocol.HalBmsService/SetBmsMosfe' \
            -d '{ "cmd": 0 }'
```

BMS字段解释，具体参考[BMS控制指令和状态接口](./bms/bms.proto)：

```
/**
 * @brief BMS版本号
 */
message Version {
  // 硬件主版本号
  uint32 hardware_major = 1;

  // 硬件次版本号
  uint32 hardware_minor = 2;

  // 硬件修订版本号
  uint32 hardware_revision = 3;

  // 软件主版本号
  uint32 software_major = 4;

  // 软件次版本号
  uint32 software_minor = 5;

  // 软件修订版本号
  uint32 software_revision = 6;
}

/**
 * @brief 电池健康状态
 */
enum PowerSupplyHealth {
  PowerSupplyHealth_UNDEFINED = 0;
  PowerSupplyHealth_GOOD = 1;
  PowerSupplyHealth_OVERHEAT = 2;
  PowerSupplyHealth_DEAD = 3;
  PowerSupplyHealth_OVERVOLTAGE = 4;
  PowerSupplyHealth_UNSPEC_FAILURE = 5;
  PowerSupplyHealth_COLD = 6;
  PowerSupplyHealth_WATCHDOG_TIMER_EXPIRE = 7;
  PowerSupplyHealth_SAFETY_TIMER_EXPIRE = 8;
}

/**
 * @brief 电池充电状态
 */
enum PowerSupplyStatus {
  PowerSupplyStatus_IDEL = 0;
  PowerSupplyStatus_CHARGING = 1;
  PowerSupplyStatus_FULL = 2;
}

/**
 * @brief 电池异常状态
 */
enum PowerAbnormalStatus {
  PowerAbnormalStatus_UNDEFINED = 0;
  PowerAbnormalStatus_SHORT_CIRCUIT = 1;
  PowerAbnormalStatus_DISCHARGE_OVERCURRENT = 2;
  PowerAbnormalStatus_CHARGING_OVERCURRENT = 3;
  PowerAbnormalStatus_UNDERVOLTAGE = 4;
  PowerAbnormalStatus_OVERVOLTAGE = 5;
  PowerAbnormalStatus_EXCEED_DISCHARGE_TEMP_LIMIT = 6;
  PowerAbnormalStatus_EXCEED_CHARGING_TEMP_LIMIT = 7;
}

/**
 * @brief 电池包MOSFE控制指令
 */
enum PowerMosfeCmd {
  PowerMosfeCmd_UNDEFINED = 0;
  PowerMosfeCmd_DISABLE_CHARGE = 1;
  PowerMosfeCmd_ENABLE_CHARGE = 2;
  PowerMosfeCmd_DISABLE_DISCHARGE = 3;
  PowerMosfeCmd_ENABLE_DISCHARGE = 4;
  PowerMosfeCmd_ENABLE_BMS = 5;
  PowerMosfeCmd_DISABLE_BMS = 6;
}

/**
 * @brief BMS状态
 */
message BmsState {
  // 版本号，硬件和软件主版本号，次版本号以及修订版本号
  Version ver = 1;

  // 当前电压，单位：mv
  float voltage = 2;

  // 当前电流, 单位：mA，充电位正，放电位负
  float current = 3;

  // 当前功率, 单位：mW
  float power = 4;

  // 当前温度，单位：0.1℃
  float temperature = 5;

  // 当前容量，单位：mAh
  float capacity = 6;

  // 当前电量，单位：百分比
  float charge = 7;

  // 电池健康状态（暂时不开放）
  PowerSupplyHealth power_supply_health = 8;

  // 充电状态
  PowerSupplyStatus power_supply_status = 9;

  // 循环次数
  uint32 cycles_num = 10;

  // 循环容量(当前电池包总共充放电的容量总计), 单位： Ah
  float cycles_capacity = 11;

  // 异常状态
  PowerAbnormalStatus abnormal_state = 12;
}
```

#### 急停

获取BMS状态

- [急停状态查询和控制接口](./state/hal_emergency_service.proto)

curl使用示例(以hal本机ip:127.0.0.1, hal默认监听端口56421为例)：

```
// 获取急停状态
curl -i     -H 'content-type:application/json'  -H 'timeout: 60000'   -X POST 'http://127.0.0.1:56421/rpc/aimdk.protocol.HalEmergencyService/GetEmergencyState' -d '{}'

// 发送软急停命令
curl -i     -H 'content-type:application/json'  -H 'timeout: 60000'   -X POST 'http://127.0.0.1:56421/rpc/aimdk.protocol.HalEmergencyService/SetEmergencyCommand' -d '{"cmd":{"software_emergency_stop": true}}'

// 发送软急停恢复命令
curl -i     -H 'content-type:application/json'  -H 'timeout: 60000'   -X POST 'http://127.0.0.1:56421/rpc/aimdk.protocol.HalEmergencyService/SetEmergencyCommand' -d '{"cmd":{"software_emergency_stop": false}}'

```

急停字段解释，具体参考[急停控制指令和查询接口](./state/emergency_state.proto)：

```
/**
 * @brief 当前机器人的急停状态描述
 */
message EmergencyCommand {
  // 无线急停按钮被按下
  bool wireless_emergency_stop = 1;
  // 软件急停按钮被按下
  bool software_emergency_stop = 2;
}


/**
 * @brief 当前机器人的急停状态描述
 */
message EmergencyState {
  enum Reason {
    // 未定义原因，一般是程序遗漏设置，才会是该值
    Reason_UNDEFINED = 0;

    // 有线急停按钮被按下
    Reason_ESTOP = 1;

    // 无线急停按钮被按下
    Reason_WIRELESS_ESTOP = 2;

    // 底盘左前触边传感器触碰
    Reason_LEFT_FRONT_SENSOR_ALARM = 3;

    // 底盘右前触边传感器触碰
    Reason_RIGHT_FRONT_SENSOR_ALARM = 4;

    // 底盘左触边传感器触碰
    Reason_LEFT_SENSOR_ALARM = 5;

    // 底盘右触边传感器触碰
    Reason_RIGHT_SENSOR_ALARM = 6;

    // 底盘左后触边传感器触碰
    Reason_LEFT_BACK_SENSOR_ALARM = 7;

    // 底盘右后触边传感器触碰
    Reason_RIGHT_BACK_SENSOR_ALARM = 8;

    // 升降电机上限位触碰
    Reason_LIFT_UPPER_LIMIT_ALARM = 9;

    // 升降电机下限位触碰
    Reason_LIFT_LOWER_LIMIT_ALARM = 10;

    // 托盘限位触碰
    Reason_TRAY_LIMIT_ALARM = 11;

    // 1号TOF报警（前左）
    Reason_FRONT_LEFT_TOF_ALARM = 12;

    // 2号TOF报警（前右）
    Reason_FRONT_RIGHT_TOF_ALARM = 13;

    // 3号TOF报警（右前）
    Reason_RIGHT_FRONT_TOF_ALARM = 14;

    // 4号TOF报警（右后）
    Reason_RIGHT_BACK_TOF_ALARM = 15;

    // 5号TOF报警（后方）
    Reason_BACK_TOF_ALARM = 16;

    // 6号TOF报警（左后）
    Reason_LEFT_BACK_TOF_ALARM = 17;

    // 7号TOF报警（左前）
    Reason_LEFT_FRONT_TOF_ALARM = 18;

    // 软件急停
    Reason_SOFTWARE_ESTOP = 19;

    // 未知原因
    Reason_UNKNOWN = 255;
  }

  // 急停是否处于激活状态
  bool active = 1;

  // 导致急停的原因
  Reason reason = 2;

  // 底盘左前触边传感器触碰
  bool left_front_sensor_alarm = 3;

  // 底盘右前触边传感器触碰
  bool right_front_sensor_alarm = 4;

  // 底盘左触边传感器触碰
  bool left_sensor_alarm = 5;

  // 底盘右触边传感器触碰
  bool right_sensor_alarm = 6;

  // 底盘左后触边传感器触碰
  bool left_back_sensor_alarm = 7;

  // 底盘右后触边传感器触碰
  bool right_back_sensor_alarm = 8;

  // 升降电机上限位触碰
  bool lift_upper_limit_alarm = 9;

  // 升降电机下限位触碰
  bool lift_lower_limit_alarm = 10;

  // 托盘限位触碰
  bool tray_limit_alarm = 11;

  // 1号TOF报警（前左）
  bool front_left_tof_alarm = 12;

  // 2号TOF报警（前右）
  bool front_right_tof_alarm = 13;

  // 3号TOF报警（右前）
  bool right_front_tof_alarm = 14;

  // 4号TOF报警（右后）
  bool right_back_tof_alarm = 15;

  // 5号TOF报警（后方）
  bool back_tof_alarm = 16;

  // 6号TOF报警（左后）
  bool left_back_tof_alarm = 17;

  // 7号TOF报警（左前）
  bool left_front_tof_alarm = 18;

  // 有线急停
  bool wired_emergency_stop = 19;

  // 无线急停
  bool wireless_emergency_stop = 20;

  // 软件急停
  bool software_emergency_stop = 21;
}
```

## 轮式

### RPC

#### Light灯光

获取灯光状态和控制灯光

- [Light查询和控制接口](./light/hal_light_service.proto)

curl使用示例(以hal本机ip:127.0.0.1, hal默认监听端口56422为例)：

```

# 获取补光灯状态
curl -i     -H 'content-type:application/json' \
            -H 'timeout: 60000'   -X POST 'http://127.0.0.1:56422/rpc/aimdk.protocol.HalFillLightService/GetFillLightState' \
            -d '{}'
# 控制补光灯亮度
curl -i     -H 'content-type:application/json' \
            -H 'timeout: 60000'   -X POST 'http://127.0.0.1:56422/rpc/aimdk.protocol.HalFillLightService/SetFillLightCommand' \
            -d '{"cmd":{"level":1}}'
            
# 获取RGB灯状态
curl -i     -H 'content-type:application/json' \
            -H 'timeout: 60000'   -X POST 'http://127.0.0.1:56422/rpc/aimdk.protocol.HalRgbLightService/GetRgbLightState' \
            -d '{}'
# 控制RGB灯亮度
curl -i     -H 'content-type:application/json' \
            -H 'timeout: 60000'   -X POST 'http://127.0.0.1:56422/rpc/aimdk.protocol.HalRgbLightService/SetRgbLightCommand' \
            -d '{"cmd":{"red":255, "green":255, "blue":255, "effect":2}}'

# 获取灯带状态
curl -i     -H 'content-type:application/json' \
            -H 'timeout: 60000'   -X POST 'http://127.0.0.1:56422/rpc/aimdk.protocol.HalLightStripService/GetLightStripState' \
            -d '{}'
# 控制灯带亮度
curl -i     -H 'content-type:application/json' \
            -H 'timeout: 60000'   -X POST 'http://127.0.0.1:56422/rpc/aimdk.protocol.HalLightStripService/SetLightStripCommand' \
            -d '{"cmd":{"red":255, "green":255, "blue":255, "effect":3}}'
```

灯光控制字段解释，具体参考[灯光控制指令和状态接口](./light/light.proto)：

```
/**
 * @brief 补光灯状态
 */
message FillLightState {
  // 档位：0-10
  uint32 level = 1;
}

/**
 * @brief 补光灯控制指令
 */
message FillLightCommand {
  // 档位：0-10
  uint32 level = 1;
}

/**
 * @brief RGB灯效，0:熄灭，1：单色光，2：呼吸灯，3：闪烁灯，4：流水灯
 */
enum RgbEffectStatus {
  RgbEffectStatus_IDLE = 0;
  RgbEffectStatus_MONOCHROME = 1;
  RgbEffectStatus_BREATHING = 2;
  RgbEffectStatus_FLASHING = 3;
  RgbEffectStatus_FLOWING = 4;
}

/**
 * @brief RGB灯光状态
 */
message RgbLightState {
  // 范围：0~255
  uint32 red = 1;
  // 范围：0~255
  uint32 green = 2;
  // 范围：0~255
  uint32 blue = 3;
  // RGB灯效
  RgbEffectStatus effect = 4;
}

/**
 * @brief RGB灯光控制指令
 */
message RgbLightCommand {
  // 范围：0~255
  uint32 red = 1;
  // 范围：0~255
  uint32 green = 2;
  // 范围：0~255
  uint32 blue = 3;
  // RGB灯效
  RgbEffectStatus effect = 4;
}

/**
 * @brief 灯带状态
 */
message LightStripState {
  // 范围：0~255
  uint32 red = 1;
  // 范围：0~255
  uint32 green = 2;
  // 范围：0~255
  uint32 blue = 3;
  // RGB灯效
  RgbEffectStatus effect = 4;
}

/**
 * @brief 灯带控制指令
 */
message LightStripCommand {
  // 范围：0~255
  uint32 red = 1;
  // 范围：0~255
  uint32 green = 2;
  // 范围：0~255
  uint32 blue = 3;
  // RGB灯效
  RgbEffectStatus effect = 4;
}
```

#### Claw夹爪

控制夹爪运动、获取夹爪状态

- [夹爪运动控制接口](./hand/hal_hand_service.proto)

curl使用示例(以hal本机ip:127.0.0.1, hal默认监听端口56421为例)：

```
# 获取夹爪状态
curl -i \
    -H 'content-type:application/json' \
    -X POST 'http://127.0.0.1:56422/rpc/aimdk.protocol.HalHandService/GetHandState' \
    -d '{}'

# 控制夹爪运动
curl -i \
    -H 'content-type:application/json' \
    -X POST 'http://127.0.0.1:56422/rpc/aimdk.protocol.HalHandService/SetHandCommand' \
    -d '{"data":{"left":{"agi_claw_cmd":{"cmd":0,"pos":50,"vel": 50, "force":80,"clamp_method":2,"finger_pos":0}},"right":{"agi_claw_cmd":{"cmd":0,"pos":50, "vel": 50, "force":80,"clamp_method":2,"finger_pos":0}}}}'
```

控制字段解释，具体参考[夹爪控制指令和状态接口](./hand/agi_claw.proto)：

```
// 夹爪手部命令
message AgiClawHandCommand {
  // 夹爪配置指令
  uint32 cmd = 1;
  // 夹爪最大释放范围 0 ~ 作业宽度（由设计而定）,单位：%
  uint32 pos = 2;
  // 0%-100%夹爪最大夹持力
  uint32 force = 3;
  // 0：idle  1：夹持   2：释放
  uint32 clamp_method = 4;
  // reserve
  uint32 finger_pos = 5;
  // 0%-100%夹爪速度
  uint32 vel = 6;
}

// 夹爪手部状态
message AgiClawHandState {
  // 0x11：正在锁定；0x12：锁定成功：0x13：锁定失败；0x14：工件脱落；0x21：正在释放；0x22：释放成功；0x23：释放失败（夹爪堵塞）；
  uint32 state = 1;
  // 夹爪作业宽度（由设计而定）,单位：%
  uint32 pos = 2;
  // 温度，单位：℃
  uint32 temperature = 3;
  // reserve
  uint32 finger_pos = 4;
}
```
