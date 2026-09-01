#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "Legged Studio Linux release builder"
npm ci
npm run release:check
npm run build:linux
