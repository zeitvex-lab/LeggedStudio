[English](README.md) | 中文

# aimrt_sensor

## 简介

传感器驱动模块，负责对传感器的初始化，配置参数，获取数据，并转换成ros通用消息格式发布出来。

包含4个模块：

1. **hal_lidar** - 激光雷达
2. **hal_d415** - 头部深度相机
3. **hal_dcw2** - 腰部深度相机
4. **tz_camera** - 胸部3个相机


## 消息话题及格式

### hal_lidar

* `/aima/hal/lidar/neck/pointcloud` ([PointCloud2.msg](https://github.com/ros2/common_interfaces/blob/4.2.4/sensor_msgs/msg/PointCloud2.msg) )
* `/aima/hal/lidar/neck/imu` ([Imu.msg](https://github.com/ros2/common_interfaces/blob/4.2.4/sensor_msgs/msg/Imu.msg))

注意：
1. `PointCloud2.msg`中每个点的时间戳为相对于每帧首个点的时间差 
2. `Imu.msg`中加速度单位为**g**

### hal_d415

* `/aima/hal/rgbd_camera/head_front/color` (以下图像格式均为[Image.msg](https://github.com/ros2/common_interfaces/blob/4.2.4/sensor_msgs/msg/Image.msg))
* `/aima/hal/rgbd_camera/head_front/depth`

### hal_dcw2

* `/aima/hal/rgbd_camera/waist_front/color`
* `/aima/hal/rgbd_camera/waist_front/depth`

### tz_camera

* `/aima/hal/fish_eye_camera/chest_left/color`
* `/aima/hal/fish_eye_camera/chest_right/color`
* `/aima/hal/camera/interactive/color`

