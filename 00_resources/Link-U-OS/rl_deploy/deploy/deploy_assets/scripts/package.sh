#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DEPLOY_DIR=$(cd "$SCRIPT_DIR/../.." && pwd)
REPO_ROOT=$(cd "$DEPLOY_DIR/.." && pwd)
OUTPUT_DIR="$DEPLOY_DIR"
INSTALL_DIR="$DEPLOY_DIR/install"

if [ -f /opt/ros/humble/setup.bash ]; then
    # Avoid nounset issues inside ROS setup scripts.
    set +u
    source /opt/ros/humble/setup.bash
    set -u
fi

cd "$DEPLOY_DIR"
colcon build

if [ ! -d "$INSTALL_DIR" ]; then
    echo "Install directory not found: $INSTALL_DIR" >&2
    exit 1
fi

commit_id=$(git -C "$REPO_ROOT" rev-parse --short HEAD)
echo "$commit_id" > "$INSTALL_DIR/COMMIT_ID"

pkg_date=$(date +%Y%m%d)
zip_name="rl_deploy_${pkg_date}_${commit_id}.zip"

stage_dir=$(mktemp -d)
trap 'rm -rf "$stage_dir"' EXIT

mkdir -p "$stage_dir/rl_deploy"
cp -a "$INSTALL_DIR"/. "$stage_dir/rl_deploy/"

rm -f "$OUTPUT_DIR/$zip_name"
pushd "$stage_dir" >/dev/null
    zip -qr "$OUTPUT_DIR/$zip_name" rl_deploy
popd >/dev/null

echo "Package created: $OUTPUT_DIR/$zip_name"
