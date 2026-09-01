$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$appRoot = Join-Path $root 'dist\embedded-win\win-unpacked\resources\app'
$manifestPath = Join-Path $appRoot 'runtime\runtime-manifest.json'
if (-not (Test-Path $manifestPath)) { throw "Packaged runtime manifest not found: $manifestPath" }

$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$runtimeRoot = Join-Path $appRoot 'runtime'
$python = Join-Path $runtimeRoot $manifest.python
if (-not (Test-Path $python)) { throw "Packaged Python not found: $python" }

& $python -c "import torch,mjlab,warp,mujoco_warp,fastapi; print(torch.__version__, torch.cuda.is_available()); print(mjlab.__file__)"
if ($LASTEXITCODE -ne 0) { throw 'Packaged Python import probe failed' }

$env:LEGGED_STUDIO_MJLAB_SOURCE = Join-Path $runtimeRoot 'mjlab_source'
$env:LEGGED_STUDIO_MJLAB_EXTENSION = Join-Path $runtimeRoot 'mjlab_extension'
$env:LEGGED_STUDIO_RUNTIME_PYTHON = $python
$env:LEGGED_STUDIO_MJLAB_PYTHON = $python
$port = 18766
$process = Start-Process -FilePath $python -ArgumentList @('-m', 'uvicorn', 'backend.api_complete:app', '--host', '127.0.0.1', '--port', "$port") -WorkingDirectory $appRoot -WindowStyle Hidden -PassThru
try {
    $health = $null
    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        try {
            $health = Invoke-RestMethod "http://127.0.0.1:$port/health" -TimeoutSec 2
            break
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $health) { throw 'Packaged backend did not become ready' }
    $environment = Invoke-RestMethod "http://127.0.0.1:$port/api/system/environment" -TimeoutSec 10
    $adapter = Invoke-RestMethod "http://127.0.0.1:$port/api/adapters/status" -TimeoutSec 90
    [PSCustomObject]@{
        health = $health.status
        version = $health.version
        python = $environment.control_plane.python_version
        mjlab = $environment.adapters.mjlab.status
        embedded = $environment.adapters.mjlab.embedded
        native_ready = $adapter.native_mjlab.execution_ready
        cuda = $adapter.native_mjlab.runtime.interpreters[0].cuda_available
    } | Format-List
} finally {
    if (-not $process.HasExited) { $process.Kill() }
}
