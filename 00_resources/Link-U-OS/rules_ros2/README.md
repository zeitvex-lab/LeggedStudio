[![CI](https://github.com/mvukov/rules_ros2/actions/workflows/main.yml/badge.svg?branch=main)](https://github.com/mvukov/rules_ros2/actions/workflows/main.yml)

# Bazel rules for ROS 2 (Forked and Adapted)

This repository is a fork of [mvukov/rules_ros2](https://github.com/mvukov/rules_ros2).

## Fork Information

This project originated as a fork of `https://github.com/mvukov/rules_ros2`. It has been adapted and extended to include:
*   **Third-party Dependency Management Optimization:** Third-party dependencies now rely on dependency definitions in `integration`, making dependency management more centralized and flexible.
*   **FastDDS Middleware Support:** Added support for FastDDS middleware and set it as the default middleware, providing greater flexibility and performance options.
*   **Static Compilation of Typesupport:** Supports static compilation of typesupport for `msg/srv`, eliminating the need for dynamic loading of corresponding shared libraries, improving startup speed and deployment convenience.
*   **Static Compilation of URDF Plugins:** Supports static compilation of URDF plugins, avoiding the need for dynamic loading of `.so` files and simplifying system configuration.
*   **Extended ROS 2 Message Support:** Added compilation support for ROS 2 messages including `map_msgs`, `pcl_msgs`, and `foxglove_msgs`, expanding the available message types.

Please refer to the original repository for the base functionality and the history of the project.

This repo provides functionality to build and use ROS 2 with Bazel.

## Prerequisites

You will need to install Bazel, see [here](https://docs.bazel.build/versions/master/install.html).
Besides Bazel, you will need a C++ compiler and a Python 3 interpreter.

Third-party dependencies are managed through definitions in the `integration` module.

And no, you don't have to install any ROS 2 packages via `apt`.

The code is developed and tested on Ubuntu 22.04 with Python 3.10.

## What works?

Available features:

- Building of C++, Python and Rust nodes.
- C/C++/Python/Rust code generation for interfaces (messages, services and actions).
- Defining ROS 2 deployments with `ros2_launch` Bazel macro.
- Defining ROS 2 tests with `ros2_test` Bazel macro.
- Defining ROS 2 plugins with `ros2_plugin` Bazel macro.
- Only CycloneDDS middleware can be used at the moment.
  - Zero copy transport via shared memory backend ([iceoryx](https://github.com/eclipse-iceoryx/iceoryx)) for CycloneDDS.
- Logging backends:
  - `spdlog` (default): `--@com_github_mvukov_rules_ros2//ros2:rcl_logging_impl=spdlog`
  - `syslog`: `--@com_github_mvukov_rules_ros2//ros2:rcl_logging_impl=syslog`
- Utilities:
  - [`foxglove_bridge`](https://github.com/foxglove/ros-foxglove-bridge) for visualization and debugging
  - `ros2_bag` for handling rosbags
  - `ros2_lifecycle` for handling node lifecycle
  - `ros2_node` for handling nodes
  - `ros2_param` for handling parameters
  - `ros2_service` for handling services
  - `ros2_topic` for handling topics
  - `xacro` for Xacro to URDF conversion

Please take a look at the [examples](examples) folder to get started.

ROS 2 packages are by default locked to versions from [release-humble-20241205](https://github.com/ros2/ros2/releases/tag/release-humble-20241205).

## Notes

- Unlike ROS genmsg which refuses to generate code if the deps between
  interface targets are not set correctly, code generation for ROS 2 seems to not
  care about this. If the deps are not correctly set, you'll only see failures
  during compilation of the generated code.

## Alternatives

For alternative approaches, see:

- [`ApexAI/rules_ros`](https://github.com/ApexAI/rules_ros/)
- [`RobotLocomotion/drake-ros/bazel_ros2_rules`](https://github.com/RobotLocomotion/drake-ros/tree/main/bazel_ros2_rules/ros2#alternatives),
  which includes a brief analysis of this and other approaches.
