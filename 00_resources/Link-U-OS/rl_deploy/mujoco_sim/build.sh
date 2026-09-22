#!/bin/bash

# exit on error and print each command
set -e

INSTALL_DIR=../mujoco_sim_install

if [ -d $INSTALL_DIR ]; then
    rm -rf $INSTALL_DIR
fi

# cmake
cmake -B build -S . \
    -DCMAKE_BUILD_TYPE=Release \
    -DAIMRT_INSTALL=ON \
    -DCMAKE_INSTALL_PREFIX=$INSTALL_DIR \
    -DAIMRT_MUJOCO_SIM_INSTALL=ON \
    -DSIMULATE_BUILD_EXECUTABLE=ON \
    -DAIMRT_MUJOCO_SIM_BUILD_WITH_ROS2=ON \
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5
    $@

cmake --build build --config Release --target install --parallel $(nproc)
