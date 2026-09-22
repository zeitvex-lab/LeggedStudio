#!/bin/bash
set -e

# Get script directory and change to bin folder
SHELL_FOLDER=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
echo $SHELL_FOLDER
pushd "$SHELL_FOLDER"/../../bin || exit

./aimrt_main --cfg_file_path=../config/pb_chn/examples_cpp_pb_chn_benchmark_cfg.yaml

popd || exit
