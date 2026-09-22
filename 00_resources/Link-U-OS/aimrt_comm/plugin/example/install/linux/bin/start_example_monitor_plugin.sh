#!/bin/bash

export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:./:../lib
export AGIBOT_ENABLE_TRACE=true
export AGIBOT_ENABLE_MONITOR=true

./aimrte-plugin-example-monitor --cfg_file_path=./cfg/example_monitor_plugin.yaml