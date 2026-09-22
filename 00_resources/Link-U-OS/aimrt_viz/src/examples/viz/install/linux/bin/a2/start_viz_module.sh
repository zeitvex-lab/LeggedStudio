#!/bin/bash

SHELL_FOLDER=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
echo $SHELL_FOLDER
pushd "$SHELL_FOLDER"/../../bin || exit

export LOG_PATH=${LOG_PATH:-"../log"}

CONFIG_FILE_PATH="../config/viz/viz_module.yaml"

RMW_LIBRARY_PATH=$(pwd)/librmw_fastrtps.so LD_LIBRARY_PATH=./:$LD_LIBRARY_PATH ./aimrt_main --cfg_file_path=${CONFIG_FILE_PATH}
