#!/bin/bash

set -e


cmd_args="--cfg_file_path ../config/record_playback/record_playback_config.yaml"

# Store current directory and change to script location
SHELL_FOLDER=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
echo "SHELL_FOLDER: $SHELL_FOLDER"
pushd "$SHELL_FOLDER"/../../bin || exit
echo "run_recorder"
export AGIBOT_ENABLE_LOG_CONTROL=false
RMW_LIBRARY_PATH=$(pwd)/librmw_fastrtps.so LD_LIBRARY_PATH=./:$LD_LIBRARY_PATH ./aimrte-tool-record_playback $cmd_args

popd || exit
