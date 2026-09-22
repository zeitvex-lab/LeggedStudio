# MC

## 简介

本目录放置了系统的 MC 模块的协议，以支持系统的运动控制功能。



## 检索

- [Action管理接口](./action/mc_action_service.proto)
- [轨迹运动控制接口](./motion/mc_motion_service.proto)
- [下肢运动控制接口](./motion/mc_motion_channel.proto)


## channel

### 订阅消息

#### 关节状态
- 消息：[hal_msgs::msg::JointState](../hal/joint/msg/JointState.msg)
- 手臂关节状态TOPIC：/body_drive/arm_joint_state
- 腿部关节状态TOPIC：/body_drive/leg_joint_state

#### imu
- 消息：[sensor_msgs::msg::Imu](https://docs.ros2.org/foxy/api/sensor_msgs/msg/Imu.html)
- TOPIC: /body_drive/imu/data


#### 下肢导航指令
- 消息：[aimdk::protocol::McLocomotionVelocityChannel](./motion/mc_motion_channel.proto)
- TOPIC: /motion/control/locomotion_velocity


#### 腰部控制（下蹲、侧身、弯腰、转身）指令
- 消息：[aimdk::protocol::McMoveWaistLiftChannel](./motion/mc_motion_channel.proto)
- TOPIC: /motion/control/move_waist_lift
- 消息：[aimdk::protocol::McMoveWaistSidewaysChannel](./motion/mc_motion_channel.proto)
- TOPIC: /motion/control/move_waist_sideways
- 消息：[aimdk::protocol::McMoveWaistPitchChannel](./motion/mc_motion_channel.proto)
- TOPIC: /motion/control/move_waist_pitch
- 消息：[aimdk::protocol::McMoveWaistTwistChannel](./motion/mc_motion_channel.proto)
- TOPIC: /motion/control/move_waist_twist


### 发布消息

#### 关节指令
- 消息：[hal_msgs::msg::JointCommand](../hal/joint/msg/JointCommand.msg)
- 手臂关节指令TOPIC：/body_drive/arm_joint_command
- 腿部关节指令TOPIC: /body_drive/leg_joint_command
- 头部关节指令TOPIC:/body_drive/neck_joint_command

#### 手部指令
- 消息：[aimdk::protocol::HandCommandChannel](../hal/hand/hand_channel.proto)
- 手部关节指令TOPIC: /body_drive/hand_joint_command

#### 腿部运动学数据
- 消息：[aimdk::protocol::FootKinematicsChannel](./kinematics/mc_kinematics_channel.proto)
- 腿部运动学数据TOPIC: /mc/kinematics/foot_kine


## RPC

### Action

设置、查询Action，获取可用action列表、获取action切换命令
- [SetAction](./action/mc_action.proto)
- [GetAction](./action/mc_action.proto)
- [GetAvailableActions](./action/mc_action.proto)
- [GetAvailableCommands](./action/mc_action.proto)

### Data

运控数据服务: 获取任务状态、获取关节状态、获取关节角度
- [GetTaskState](./data/mc_data_service.proto)
- [GetJointState](./data/joint.proto)
- [GetJointAngle](./data/joint.proto)

### Motion

运控运动服务：轨迹运动、安全停止、站立、设置手部命令、设置头部命令
- 轨迹运动: [TrajectoryMove](./motion/move.proto)
- 安全停止: [SafeStop](./motion/mc_motion_service.proto)
- 站立: [Stand](./motion/mc_motion_service.proto)
- 设置手部命令: [SetHandCommand](./motion/mc_motion_service.proto)
- 设置头部命令: [SetNeckCommand](./motion/mc_motion_service.proto)
