# Unitree AlienGo Description

This repository contains the urdf model of Aliengo. The origin models could be found at [Unitree ROS](https://github.com/unitreerobotics/unitree_ros).
 
![Aliengo](../../.images/unitree_aliengo.png)

## Build

```bash
cd ~/ros2_ws
colcon build --packages-up-to aliengo_description  --symlink-install
```

## Visualize the robot

```bash
source ~/ros2_ws/install/setup.bash
ros2 launch robot_visualize_config visualize.launch.py robot:=aliengo
```

## Launch ROS2 Control

Tested environment:

* Ubuntu 24.04
  * ROS2 Jazzy

### Mujoco Simulator

* Basic Quadruped Controller
  ```bash
  source ~/ros2_ws/install/setup.bash
  ros2 launch basic_quadruped_controller mujoco.launch.py robot:=aliengo
  ```
* OCS2 Quadruped Controller
  ```bash
  source ~/ros2_ws/install/setup.bash
  ros2 launch ocs2_quadruped_controller mujoco.launch.py pkg_description:=aliengo_description
  ```
  
### Gazebo Harmonic

* Basic Quadruped Controller
  ```bash
  source ~/ros2_ws/install/setup.bash
  ros2 launch basic_quadruped_controller gazebo.launch.py robot:=aliengo
  ```