# Gemini Code Understanding

## Project Overview

This project, `aimrt_protocol`, is the central repository for defining the communication protocols used in Link-U OS. It contains the definitions for data structures, messages, and services using both Protocol Buffers (`.proto`) for RPC and ROS2 (`.msg`, `.srv`).

The project's core responsibility is to provide a single source of truth for all inter-process communication contracts. It also includes the necessary Bazel build configurations (`BUILD` files with `exports_files`) to allow other repositories (like `aimrt_comm`) to consume these definitions and generate the required language-specific code using a provided build toolchain (`protobuf_utils` and `ros_utils` rules).

## Building and Running

The documentation indicates that the protocols are not built directly in this repository. Instead, other repositories, such as `aimrt_comm`, consume the `.proto`, `.msg`, and `.srv` files from this repository and build them using custom Bazel rules.

The general workflow is:

1.  Define `.proto`, `.msg`, or `.srv` files in `aimrt_protocol`.
2.  Export these files in the `BUILD` files using `exports_files`.
3.  In a separate repository (e.g., `aimrt_comm`), define a `protobuf_utils` or `ros_utils` target that points to the protocol files in `aimrt_protocol`.
4.  Other projects can then depend on these generated targets.

## Development Conventions

*   Protocol definitions are organized into subdirectories under `aimdk/protocol` and `ros2`.
*   Each subdirectory with protocol files should have a `BUILD` file that exports the protocol files.
*   The `protobuf_utils` and `ros_utils` rules are used in other repositories to generate code from the protocol files.
