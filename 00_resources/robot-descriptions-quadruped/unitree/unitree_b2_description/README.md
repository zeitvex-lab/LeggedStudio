# Unitree B2 Description

This repository contains the urdf model of b2. The origin models could be found at [Unitree ROS](https://github.com/unitreerobotics/unitree_ros).

![B2](../../.images/unitree_b2.png)

## Build

```bash
cd ~/ros2_ws
colcon build --packages-up-to unitree_b2_description --symlink-install
```

## Visualize the robot

```bash
source ~/ros2_ws/install/setup.bash
ros2 launch robot_visualize_config visualize.launch.py robot:=unitree_b2
```

## Launch ROS2 Control

### Mujoco Simulator

* Unitree Guide Controller
  ```bash
  source ~/ros2_ws/install/setup.bash
  ros2 launch unitree_guide_controller mujoco.launch.py pkg_description:=unitree_b2_description
  ```
* OCS2 Quadruped Controller
  ```bash
  source ~/ros2_ws/install/setup.bash
  ros2 launch ocs2_quadruped_controller mujoco.launch.py pkg_description:=unitree_b2_description
  ```

### Gazebo Harmonic

* Basic Quadruped Controller
  ```bash
  source ~/ros2_ws/install/setup.bash
  ros2 launch basic_quadruped_controller gazebo.launch.py robot:=unitree_b2 height:=0.68
  ```
* OCS2 Quadruped Controller
  ```bash
  source ~/ros2_ws/install/setup.bash
  ros2 launch ocs2_quadruped_controller gazebo.launch.py pkg_description:=unitree_b2_description height:=0.68
  ```