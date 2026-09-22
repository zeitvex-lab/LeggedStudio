English | [中文](README.zh_CN.md)

# aimrt_sensor

## Overview

Sensor driver module responsible for sensor initialization, parameter configuration, data acquisition, and publishing data in ROS standard message formats.

It contains four submodules:

1. **hal_lidar** – LiDAR  
2. **hal_d415** – Head depth camera  
3. **hal_dcw2** – Waist depth camera  
4. **tz_camera** – Three chest-mounted cameras  

## Topics and Message Formats

### hal_lidar

* `/aima/hal/lidar/neck/pointcloud` ([PointCloud2.msg](https://github.com/ros2/common_interfaces/blob/4.2.4/sensor_msgs/msg/PointCloud2.msg))
* `/aima/hal/lidar/neck/imu` ([Imu.msg](https://github.com/ros2/common_interfaces/blob/4.2.4/sensor_msgs/msg/Imu.msg))

**Notes:**

1. In `PointCloud2.msg`, the timestamp of each point represents the time offset relative to the first point of the frame.
2. In `Imu.msg`, the acceleration unit is **g**.

### hal_d415

* `/aima/hal/rgbd_camera/head_front/color` (All image topics use [Image.msg](https://github.com/ros2/common_interfaces/blob/4.2.4/sensor_msgs/msg/Image.msg))
* `/aima/hal/rgbd_camera/head_front/depth`

### hal_dcw2

* `/aima/hal/rgbd_camera/waist_front/color`
* `/aima/hal/rgbd_camera/waist_front/depth`

### tz_camera

* `/aima/hal/fish_eye_camera/chest_left/color`
* `/aima/hal/fish_eye_camera/chest_right/color`
* `/aima/hal/camera/interactive/color`
