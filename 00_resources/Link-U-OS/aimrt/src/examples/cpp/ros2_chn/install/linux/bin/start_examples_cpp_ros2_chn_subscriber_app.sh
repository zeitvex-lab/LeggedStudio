#!/bin/bash
set -e

# Get script directory and change to bin folder
SHELL_FOLDER=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
echo $SHELL_FOLDER
pushd "$SHELL_FOLDER"/../../bin || exit

source install/share/example_ros2/local_setup.bash

./normal_ros2_chn_subscriber_app ./config/ros2_chn/examples_cpp_ros2_chn_subscriber_app_cfg.yaml

popd || exit