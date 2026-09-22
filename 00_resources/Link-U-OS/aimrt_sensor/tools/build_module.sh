#!/bin/bash
set -e

# Display help information for script usage
Usage() {
    cat <<EOF
    build_moudle.sh [options]
    -t: build target module name
    -c: clean the local bazel cache
    -a: build with the arch type(x86_64, orin_aarch64), default is x86_64
    -j: specify the number of concurrent jobs to run during the build process
    -g: build with '--copt=-g'
    -o: override_repository repo_name=repo_path(Support multiple code repos override)
    -e: extra options
    -h: help
    e.g. build_module.sh -t joint_tf -a x86_64 -j 8 -g -o integration="\$integration_path" -o aimrt_comm="\$aimrt_comm_path" -o aimrt_protocol="\$aimrt_protocol_path" -e "--config=xxx --define=xxx=xxx"
EOF
    exit 1
}

# Parse command line arguments using getopt
ARGS=$(getopt -o a:chgt:j:e:o: --long arch:,clean_cache,help,debug,target:,jobs:,extra_options:,override_repository: -n "$0" -- "$@")
if [ $? != 0 ]; then
    Usage
fi

# Helper function to get formatted timestamp for logging
function get_time() {
    local time=$(date "+%H:%M:%S")
    echo "($time)"
}

# Process parsed arguments
eval set -- "${ARGS}"
echo $(get_time) INFO: formatted parameters=[$@]

# Initialize default values
ARCH_TYPE="x86_64"
OVERRIDE_OPTION=""
BUILD_TARGET=""

# Process command line options
while true; do
    case "$1" in
    -a | --arch)
        echo "$(get_time) INFO: Building for arch type: $2"
        ARCH_TYPE=${2}
        shift 2
        ;;
    -j | --jobs)
        echo "$(get_time) INFO: Building using jobs: $2"
        JOBS_OPTIONS="--jobs=$2"
        shift 2
        ;;
    -e | --extra_options)
        echo "$(get_time) INFO: Building with extra options: $2"
        EXTRA_OPTIONS=${2}
        if [[ $EXTRA_OPTIONS == *"--config=source"* ]]; then
            CONFIG_SOURCE="--config=source"
        fi
        shift 2
        ;;
    -g | --debug)
        echo "$(get_time) INFO: Building in debug mode"
        GDB_FLAG="--copt=-g --copt=-O0"
        shift
        ;;
    -c | --clean_cache)
        echo "$(get_time) INFO: Building with cleaning cache first"
        CLEAN_CACHE_FLAG=true
        shift
        ;;
    -t | --target)
        echo "$(get_time) INFO: Build target"
        BUILD_TARGET=${2}_tar
        shift 2
        ;;
    -o | --override_repository)
        echo "$(get_time) INFO: Building using local repo: $2"
        override+="--override_repository $2 "
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

# Validate required target parameter
if [ -z "$BUILD_TARGET" ]; then
    echo "$(get_time) ERROR: Target must be specified, please use -t parameter"
    Usage
fi

# Main build function that executes bazel build command
build_module() {
    target=$1
SHELL_FOLDER=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
pushd "$SHELL_FOLDER"/../ || exit
    set -x
    bazel build \
        ${COMPILER} \
        ${GDB_FLAG} \
        ${OVERRIDE_OPTION} \
        ${JOBS_OPTIONS} \
        ${EXTRA_OPTIONS} \
        "${target}"
    set +x
popd || exit
}

# Configure compiler settings based on target architecture
if [[ "x$ARCH_TYPE" == "xx86_64" ]]; then
    COMPILER="--config=x86_64"
elif [[ "x$ARCH_TYPE" == "xorin_aarch64" ]]; then
    COMPILER="--config=orin_aarch64"
else
    echo "$(get_time) ERROR: Unsupported ARCH_TYPE for ${ARCH_TYPE}"
    exit 1
fi

# Clean bazel cache if requested
if [ "${CLEAN_CACHE_FLAG}" == true ]; then
    set -x
    bazel clean --expunge || true
    set +x
fi

# Format override options and execute build
OVERRIDE_OPTION=$(printf "%s" "${override[@]}")
build_module ${BUILD_TARGET}
