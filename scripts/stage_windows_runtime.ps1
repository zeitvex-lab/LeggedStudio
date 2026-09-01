$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$stage = Join-Path $root 'build\embedded-runtime'
$pythonRoot = Join-Path $stage 'python'
$sourceRoot = Join-Path $stage 'mjlab_source'
$extensionRoot = Join-Path $stage 'mjlab_extension'
$pythonVersion = '3.12.13'

if (-not $IsWindows -and $env:OS -ne 'Windows_NT') {
    throw 'The embedded runtime target is Windows-only.'
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'uv is required. Install it from https://docs.astral.sh/uv/.'
}

if (Test-Path $stage) {
    Remove-Item -LiteralPath $stage -Recurse -Force
}
New-Item -ItemType Directory -Path $stage | Out-Null

$source = if ($env:LEGGED_STUDIO_MJLAB_SOURCE) { $env:LEGGED_STUDIO_MJLAB_SOURCE } else { Join-Path (Split-Path $root -Parent) 'mjlab_new\mjlab' }
$extension = if ($env:LEGGED_STUDIO_MJLAB_EXTENSION) { $env:LEGGED_STUDIO_MJLAB_EXTENSION } else { Join-Path (Split-Path $root -Parent) 'uni_rl\unitree_rl_mjlab' }
if (-not (Test-Path (Join-Path $source 'src'))) { throw "MJLab source not found: $source" }
if (-not (Test-Path $extension)) { throw "Unitree MJLab extension not found: $extension" }

$pythonExe = $null
Write-Host 'Installing portable CPython 3.12 with uv...'
& uv python install $pythonVersion --install-dir $pythonRoot --no-bin --no-registry
if ($LASTEXITCODE -ne 0) { throw 'uv python install failed' }
$pythonExe = (Get-ChildItem $pythonRoot -Recurse -Filter python.exe | Select-Object -First 1).FullName
if (-not $pythonExe) { throw "uv did not produce python.exe under $pythonRoot" }
$pythonDirectory = Split-Path $pythonExe -Parent
Get-ChildItem $pythonRoot -Attributes ReparsePoint -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.FullName -ne $pythonDirectory) { [System.IO.Directory]::Delete($_.FullName) }
}
$temporaryPythonDirectory = Join-Path $pythonRoot '.temp'
if (Test-Path $temporaryPythonDirectory) { Remove-Item -LiteralPath $temporaryPythonDirectory -Recurse -Force }
Write-Host 'Installing CUDA MJLab dependencies...'
& uv pip install --break-system-packages --python $pythonExe --index https://download.pytorch.org/whl/cu128 --default-index https://pypi.org/simple 'torch==2.11.0'
if ($LASTEXITCODE -ne 0) { throw 'CUDA Torch installation failed' }
& uv pip install --break-system-packages --python $pythonExe --index https://pypi.nvidia.com --default-index https://pypi.org/simple 'mjlab==1.6.0' 'onnxruntime>=1.20,<2' 'fastapi>=0.115.0' 'uvicorn[standard]>=0.31.0' 'pydantic>=2.0.0'
if ($LASTEXITCODE -ne 0) { throw 'uv pip dependency installation failed' }

Write-Host 'Copying MJLab and Unitree extension sources...'
New-Item -ItemType Directory -Path $sourceRoot,$extensionRoot | Out-Null
Copy-Item -LiteralPath (Join-Path $source 'src') -Destination $sourceRoot -Recurse -Force
Copy-Item -LiteralPath (Join-Path $source 'LICENSE') -Destination $sourceRoot -Force
Copy-Item -LiteralPath (Join-Path $source 'pyproject.toml') -Destination $sourceRoot -Force
Copy-Item -LiteralPath (Join-Path $extension 'src') -Destination $extensionRoot -Recurse -Force
foreach ($file in @('LICENCE', 'LICENSE', 'setup.py')) {
    $candidate = Join-Path $extension $file
    if (Test-Path $candidate) { Copy-Item -LiteralPath $candidate -Destination $extensionRoot -Force }
}

$manifest = [ordered]@{
    schema_version = 'embedded-runtime-1'
    platform = 'win32-x64'
    python = (Get-Item $pythonExe).FullName.Substring($stage.Length + 1)
    mjlab_source = 'mjlab_source'
    mjlab_extension = 'mjlab_extension'
    torch_variant = 'cu128'
    generated_at = (Get-Date).ToUniversalTime().ToString('o')
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stage 'runtime-manifest.json') -Encoding UTF8
Write-Host "Embedded runtime staged at $stage"
