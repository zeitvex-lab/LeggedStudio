# Unitree Go1 Description

This repository contains the urdf model of go1. The origin models could be found at [Unitree ROS](https://github.com/unitreerobotics/unitree_ros).

![go1](../../.images/unitree_go1.png)

## 1. Build

```bash
cd ~/ros2_ws
colcon build --packages-up-to unitree_go1_description  --symlink-install
```

## 2. Visualize the robot

To visualize and check the configuration of the robot in rviz, simply launch:

```bash
source ~/ros2_ws/install/setup.bash
ros2 launch robot_visualize_config visualize.launch.py robot:=unitree_go1
```


## 3. Launch ROS2 Control

### 3.1 Mujoco Simulator

* Basic Quadruped Controller
  ```bash
  source ~/ros2_ws/install/setup.bash
  ros2 launch basic_quadruped_controller mujoco.launch.py robot:=unitree_go1
  ```
* OCS2 Quadruped Controller
  ```bash
  source ~/ros2_ws/install/setup.bash
  ros2 launch ocs2_quadruped_controller mujoco.launch.py pkg_description:=unitree_go1_description
  ```

### 3.2 Gazebo Harmonic

* Basic Quadruped Controller
  ```bash
  source ~/ros2_ws/install/setup.bash
  ros2 launch basic_quadruped_controller gazebo.launch.py robot:=unitree_go1
  ```