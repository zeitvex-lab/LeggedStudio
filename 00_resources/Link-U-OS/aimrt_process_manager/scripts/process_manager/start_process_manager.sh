#!/bin/bash
set -e

# Print usage information and exit
Usage() {
    cat <<EOF
    start_manager_process.sh [options]
    -p: debug port
    -g: run with debug mode
    -c: using custom config file(absolute path)
    -h: help
    e.g.: 1) start_process_manager.sh -c /home/agibot/process_manager_config.yaml
EOF
    exit 1
}

# Add signal handler function
cleanup() {
    echo -e "\n$(get_time) INFO: 🛑 Received stop signal, terminating program..."
    if [[ -n $PID ]]; then
        kill -TERM $PID 2>/dev/null || true
        
        # 动态等待进程退出，最多等待10秒
        local timeout=10
        local count=0
        while kill -0 $PID 2>/dev/null && [ $count -lt $timeout ]; do
            sleep 1
            count=$((count + 1))
            echo "$(get_time) INFO: Waiting for graceful shutdown... ($count/$timeout)"
        done
        
        # 如果超时仍未退出，强制终止
        if kill -0 $PID 2>/dev/null; then
            echo "$(get_time) WARNING: Timeout reached, force killing process $PID"
            kill -KILL $PID 2>/dev/null || true
        else
            echo "$(get_time) INFO: Process terminated gracefully"
        fi
    fi
    popd 2>/dev/null || true
    exit 0
}

# Set up signal handling
trap cleanup SIGINT SIGTERM

# Parse command line arguments
ARGS=$(getopt -o c:p:gh --long config:,port:,debug,help -n "$0" -- "$@")
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

# Default configuration values
CONFIG_FILE_PATH="../config/process_manager/process_manager_config.yaml"
PORT=65001

# Process command line options
while true; do
    case "$1" in
    -g | --debug)
        echo "$(get_time) INFO: Run with debug mode"
        DEBUG_FLAG=true
        shift
        ;;
    -p | --port)
        PORT=${2}
        shift 2
        ;;
    -c | --config)
        echo "$(get_time) INFO: Run with config: $2"
        CONFIG_FILE_PATH=${2}
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

# Set up debug command if debug mode is enabled
DEBUG_COMMAND=""
if [[ $DEBUG_FLAG == true ]]; then
    DEBUG_COMMAND="lldb-server g 0.0.0.0:${PORT} -- "
fi

# Get script directory and change to bin folder
SHELL_FOLDER=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
echo $SHELL_FOLDER
pushd "$SHELL_FOLDER"/../../bin || exit

# Execute process_manager binary with background execution to capture PID
echo -e "\n$(get_time) INFO: ✊ Start running process_manager ..."
chmod a+x ./process_manager
export LOG_PATH="/agibot/data/log/process_manager"
export ROS_LOG_DIR="/agibot/data/log/process_manager/ros"
export LOG_PATH=${LOG_PATH:-"../log"}

soc=$(cat /agibot/info/soc_index)
export EM_APP_NAME="process_manager${soc}"
if [ "$soc" == "0" ]; then
    export SOC_NAME="x86_64"
else
    export SOC_NAME="orin"
fi

# ros2 相关
export ROS_LOCALHOST_ONLY="0"
export ROS_DOMAIN_ID="232"
export FASTRTPS_DEFAULT_PROFILES_FILE="/agibot/software/v0/entry/bin/cfg/privileged_ros_dds_configuration.xml"
export AGIBOT_FEATURE_ROS2_CHANNEL_QOS='history: "keep_last"
        depth: 10
        reliability: "best_effort"'

# Start program and get PID
RMW_LIBRARY_PATH=$(pwd)/librmw_fastrtps.so LD_LIBRARY_PATH=./:$LD_LIBRARY_PATH ${DEBUG_COMMAND} ./process_manager --cfg_file_path=$CONFIG_FILE_PATH &
PID=$!

# Wait for process to finish
wait $PID
EXIT_CODE=$?

# Check execution status and exit accordingly
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "\n$(get_time) INFO: ✅ process_manager executed successfully"
else
    echo -e "\n$(get_time) ERROR: ❌ process_manager execution failed, exit code: $EXIT_CODE"
    exit 1
fi
popd || exit
