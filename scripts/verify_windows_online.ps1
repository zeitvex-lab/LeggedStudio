$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$version = (Get-Content -LiteralPath (Join-Path $root 'VERSION') -Raw).Trim()
$appRoot = Join-Path $root "dist\Legged-Studio-$version-Windows-Online\resources\app"
$bootstrap = Join-Path $appRoot 'bootstrap'
$uv = Join-Path $bootstrap 'uv\uv.exe'
$python = (Get-ChildItem (Join-Path $bootstrap 'python') -Recurse -Filter python.exe | Select-Object -First 1).FullName
$sevenZip = Join-Path $root 'node_modules\7zip-bin\win\x64\7za.exe'
$provisioner = Join-Path $appRoot 'scripts\provision_windows_runtime.ps1'

if (-not (Test-Path $uv)) { throw "Bundled uv is missing: $uv" }
if (-not $python) { throw 'Bundled CPython is missing' }
if (-not (Test-Path $provisioner)) { throw "Packaged runtime provisioner is missing: $provisioner" }
if (Test-Path (Join-Path $appRoot 'runtime')) { throw 'Online package unexpectedly contains an installed runtime' }

& $python --version
if ($LASTEXITCODE -ne 0) { throw 'Bundled CPython probe failed' }
& $uv --version
if ($LASTEXITCODE -ne 0) { throw 'Bundled uv probe failed' }

$sourceArchives = Get-ChildItem (Join-Path $bootstrap 'sources') -Filter *.zip
if ($sourceArchives.Count -ne 2) { throw 'Expected two bundled source snapshots' }
foreach ($archive in $sourceArchives) {
    & $sevenZip t $archive.FullName | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Invalid source snapshot: $($archive.Name)" }
}

& $uv pip install --dry-run --break-system-packages --python $python --index-strategy unsafe-best-match --index 'https://mirror.sjtu.edu.cn/pytorch-wheels/cu128/' --default-index 'https://pypi.tuna.tsinghua.edu.cn/simple' 'torch==2.11.0+cu128' 'mjlab==1.6.0' 'onnxruntime>=1.20,<2' 'fastapi>=0.115.0' 'uvicorn[standard]>=0.31.0' 'pydantic>=2.0.0'
if ($LASTEXITCODE -ne 0) { throw 'Domestic mirror dependency resolution failed' }

Write-Host 'Legged Studio Windows Online package verification passed.'
