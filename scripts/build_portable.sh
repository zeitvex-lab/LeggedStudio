#!/bin/bash
# Legged Studio - 便携打包脚本
# 生成类似 ComfyUI-aki 的完整便携包

set -e

echo "========================================"
echo "Legged Studio - Portable Package Builder"
echo "========================================"
echo

# 配置
PYTHON_VERSION="3.12.2"
PYTHON_EMBED_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/python-${PYTHON_VERSION}-embed-amd64.zip"
OUTPUT_DIR="Legged-Studio-Portable-v0.1.0"

# 1. 创建目录结构
echo "[1/6] Creating directory structure..."
mkdir -p ${OUTPUT_DIR}/{runtime/python,app,models,workspace/{contracts,training},logs}

# 2. 下载 Python embeddable
echo "[2/6] Downloading Python embeddable..."
if [ ! -f "python-embed.zip" ]; then
    curl -L ${PYTHON_EMBED_URL} -o python-embed.zip
fi

# 3. 解压 Python
echo "[3/6] Extracting Python..."
unzip -q python-embed.zip -d ${OUTPUT_DIR}/runtime/python

# 4. 安装 pip
echo "[4/6] Installing pip..."
cd ${OUTPUT_DIR}/runtime/python
curl -L https://bootstrap.pypa.io/get-pip.py -o get-pip.py
./python.exe get-pip.py

# 5. 安装依赖
echo "[5/6] Installing dependencies..."
./python.exe -m pip install -r ../../../backend/requirements.txt --target Lib/site-packages

# 6. 复制应用文件
echo "[6/6] Copying application files..."
cd ../../..
cp -r backend ${OUTPUT_DIR}/app/
cp -r adapters ${OUTPUT_DIR}/app/
cp -r web ${OUTPUT_DIR}/app/
cp -r tools ${OUTPUT_DIR}/app/
cp -r contracts ${OUTPUT_DIR}/app/
cp -r pipeline ${OUTPUT_DIR}/app/
cp -r examples ${OUTPUT_DIR}/workspace/contracts/

# 7. 打包 Electron（需要在 Windows 环境）
echo "Building Electron app..."
# npm run build
# 将生成的 exe 复制到根目录

echo
echo "========================================"
echo "Package created: ${OUTPUT_DIR}/"
echo "Size: $(du -sh ${OUTPUT_DIR} | cut -f1)"
echo "========================================"
echo
echo "Next steps:"
echo "1. Build Electron: npm run build"
echo "2. Copy exe to ${OUTPUT_DIR}/"
echo "3. Compress: 7z a -mx9 ${OUTPUT_DIR}.zip ${OUTPUT_DIR}/"
