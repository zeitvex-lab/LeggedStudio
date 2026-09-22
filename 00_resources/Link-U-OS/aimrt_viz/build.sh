#!/bin/bash

# exit on error and print each command
set -e

build_with_bazel() {
    echo "Building with Bazel..."
    bazel build //:aimrt_viz_flatten_tar --config=source
    echo "Bazel build completed successfully!"
}

build_with_cmake() {
    echo "Building with CMake..."

    if [ -d ./build/install ]; then
        rm -rf ./build/install
    fi

    cmake -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=./build/install \
        -DAIMRT_VIZ_INSTALL=ON \
        -DAIMRT_VIZ_BUILD_TESTS=OFF \
        -DAIMRT_VIZ_BUILD_PLUGIN=ON \
        -DAIMRT_VIZ_BUILD_MODULE=ON \
        -DAIMRT_VIZ_BUILD_WEB=ON \
        -DAIMRT_VIZ_BUILD_EXAMPLES=ON \
        "${cmake_extra_args[@]}"

    cmake --build build --config Release --target install --parallel $(nproc)
    echo "CMake build completed successfully!"
}

# Parse command line arguments
build_system="cmake"  # Default to cmake
cmake_extra_args=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --cmake)
            build_system="cmake"
            shift
            ;;
        --bazel)
            build_system="bazel"
            shift
            ;;
        -D*)
            # Collect CMake -D arguments
            cmake_extra_args+=("$1")
            shift
            ;;
        *)
            # Collect other arguments for CMake
            cmake_extra_args+=("$1")
            shift
            ;;
    esac
done

# Execute build based on selected system
case $build_system in
    bazel)
        if [[ ${#cmake_extra_args[@]} -gt 0 ]]; then
            echo "Warning: Extra arguments are ignored for Bazel build: ${cmake_extra_args[*]}"
        fi
        build_with_bazel
        ;;
    cmake)
        build_with_cmake
        ;;
    *)
        echo "Error: Unknown build system: $build_system"
        exit 1
        ;;
esac
