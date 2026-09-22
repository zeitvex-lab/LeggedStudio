#!/bin/bash
set -e

# Get script directory and change to bin folder
SHELL_FOLDER=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
echo $SHELL_FOLDER
pushd "$SHELL_FOLDER"/../../bin || exit

source install/share/example_ros2/local_setup.bash

./normal_ros2_rpc_client_app ../config/ros2_rpc/examples_cpp_ros2_rpc_client_app_cfg.yaml

popd || exit