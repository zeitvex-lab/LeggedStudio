@echo off
REM Legged Studio - 便携打包脚本（Windows）
REM 生成类似 ComfyUI-aki 的完整便携包

echo ========================================
echo Legged Studio - Portable Package Builder
echo ========================================
echo.

REM 配置
set PYTHON_VERSION=3.12.2
set PYTHON_EMBED_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-embed-amd64.zip
set OUTPUT_DIR=Legged-Studio-Portable-v0.1.0

REM 1. 创建目录结构
echo [1/7] Creating directory structure...
mkdir %OUTPUT_DIR%\runtime\python 2>nul
mkdir %OUTPUT_DIR%\app 2>nul
mkdir %OUTPUT_DIR%\models 2>nul
mkdir %OUTPUT_DIR%\workspace\contracts 2>nul
mkdir %OUTPUT_DIR%\workspace\training 2>nul
mkdir %OUTPUT_DIR%\logs 2>nul

REM 2. 下载 Python embeddable
echo [2/7] Downloading Python embeddable...
if not exist python-embed.zip (
    echo Downloading from %PYTHON_EMBED_URL%
    curl -L %PYTHON_EMBED_URL% -o python-embed.zip
)

REM 3. 解压 Python
echo [3/7] Extracting Python...
powershell -Command "Expand-Archive -Path python-embed.zip -DestinationPath %OUTPUT_DIR%\runtime\python -Force"

REM 4. 安装 pip
echo [4/7] Installing pip...
cd %OUTPUT_DIR%\runtime\python
curl -L https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python.exe get-pip.py

REM 5. 安装依赖
echo [5/7] Installing dependencies...
python.exe -m pip install fastapi uvicorn pydantic --target Lib\site-packages

REM 6. 复制应用文件
echo [6/7] Copying application files...
cd ..\..\..
xcopy /E /I /Y backend %OUTPUT_DIR%\app\backend
xcopy /E /I /Y adapters %OUTPUT_DIR%\app\adapters
xcopy /E /I /Y web %OUTPUT_DIR%\app\web
xcopy /E /I /Y tools %OUTPUT_DIR%\app\tools
xcopy /E /I /Y contracts %OUTPUT_DIR%\app\contracts
xcopy /E /I /Y pipeline %OUTPUT_DIR%\app\pipeline
xcopy /E /I /Y examples %OUTPUT_DIR%\workspace\contracts\examples

REM 7. 打包 Electron
echo [7/7] Building Electron app...
call npm run build
if exist dist\*.exe (
    copy dist\*.exe %OUTPUT_DIR%\"Legged Studio.exe"
)

echo.
echo ========================================
echo Package created: %OUTPUT_DIR%\
echo ========================================
echo.
echo Next steps:
echo 1. Test: cd %OUTPUT_DIR% ^& "Legged Studio.exe"
echo 2. Compress: 7z a -mx9 %OUTPUT_DIR%.zip %OUTPUT_DIR%\
echo.

pause
