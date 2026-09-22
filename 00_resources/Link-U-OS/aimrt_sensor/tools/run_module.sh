#!/bin/bash
set -e

# Function to display usage information
Usage() {
    cat <<EOF
    run_module.sh [options]
    -t: run target module name
    -c: config file absolute path, default file is in bazel-bin/"\$module_name"_tar/config/"\$module_name"/running_"\$module_name"_cfg.yaml
    -p: debug port
    -g: run with debug mode
    -h: help
    e.g.: 1) run_module.sh -t joint_tf -c aimrt_tf/config/joint_tf/running_joint_tf_cfg.yaml
EOF
    exit 1
}

# Parse command line arguments
ARGS=$(getopt -o t:c:p:gh --long target:,config:,port:,debug,help -n "$0" -- "$@")
if [ $? != 0 ]; then
    Usage
fi

# Get current timestamp for logging
function get_time() {
    local time=$(date "+%H:%M:%S")
    echo "($time)"
}

eval set -- "${ARGS}"
echo $(get_time) INFO: formatted parameters=[$@]

# Initialize variables
RUN_TARGET=""
PORT=65001

# Process command line options
while true; do
    case "$1" in
    -t | --target)
        echo "$(get_time) INFO: Run target: $2"
        RUN_TARGET=${2}
        shift 2
        ;;
    -c | --config)
        echo "$(get_time) INFO: Run with config: $2"
        CONFIG_PATH=${2}
        shift 2
        ;;
    -g | --debug)
        echo "$(get_time) INFO: Run with debug mode"
        DEBUG_FLAG=true
        shift
        ;;
    -p | --port)
        PORT=${2}
        shift 2
        ;;
    --)
        shift
        break
        ;;
    -h | --help)
        Usage
        ;;
    *)
        Usage
        ;;
    esac
done

# Validate required parameters
if [ -z "$RUN_TARGET" ]; then
    echo "$(get_time) ERROR: Target must be specified, please use -t parameter"
    Usage
fi

# Store current directory and change to script location
SHELL_FOLDER=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
pushd "$SHELL_FOLDER"/../ || exit
    # Setup paths and check target existence
    MODULE_TARGET_TAR_PATH="bazel-bin/${RUN_TARGET}_tar.tar"
    if [ ! -f "$MODULE_TARGET_TAR_PATH" ]; then
        echo "$(get_time) ERROR: Target tar does not exist: $MODULE_TARGET_TAR_PATH, please run build_module.sh to build the target tar first"
        exit 1
    fi

    # Prepare target directory and extract files
    rm -rf bazel-bin/${RUN_TARGET}_tar || true
    mkdir -p bazel-bin/${RUN_TARGET}_tar
    tar -xvf "$MODULE_TARGET_TAR_PATH" -C bazel-bin/${RUN_TARGET}_tar

    # Prepare execution command
    EXEC_SHELL_SCRIPT_PATH="bazel-bin/${RUN_TARGET}_tar/scripts/${RUN_TARGET}/start_${RUN_TARGET}.sh"
    chmod a+x ${EXEC_SHELL_SCRIPT_PATH}
    EXEC_COMMAND="${EXEC_SHELL_SCRIPT_PATH}"

    # Add optional parameters to command
    if [ -n "$CONFIG_PATH" ]; then
        EXEC_COMMAND+=" -c ${CONFIG_PATH}"
    fi
    if [ -n "$DEBUG_FLAG" ] && [ -n "$PORT" ]; then
        EXEC_COMMAND+=" -g -p ${PORT}"
    fi

    # Execute the command
    ${EXEC_COMMAND}
popd || exit
