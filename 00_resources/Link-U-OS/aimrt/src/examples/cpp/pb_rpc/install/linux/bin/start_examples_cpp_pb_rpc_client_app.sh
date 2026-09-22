#!/bin/bash
set -e

# Get script directory and change to bin folder
SHELL_FOLDER=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
echo $SHELL_FOLDER
pushd "$SHELL_FOLDER"/../../bin || exit

./normal_pb_rpc_client_app ./config/pb_rpc/examples_cpp_pb_rpc_client_app_cfg.yaml

popd || exit
