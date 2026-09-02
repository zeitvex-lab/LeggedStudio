param(
    [Parameter(Mandatory = $true)]
    [string]$TargetRoot,
    [string]$BootstrapRoot = ''
)

$ErrorActionPreference = 'Stop'
$pythonVersion = '3.12.13'
$uvVersion = '0.11.8'
$torchVersion = '2.11.0'
$mjlabVersion = '1.6.0'
$mjlabCommit = 'b517e0c489139e7fcee95702cfb2b01931264985'
$unitreeCommit = '1425b15f73bd4095f0df53709d7c389c3eb9e790'
$pypiIndex = if ($env:LEGGED_STUDIO_PYPI_INDEX) { $env:LEGGED_STUDIO_PYPI_INDEX } else { 'https://pypi.tuna.tsinghua.edu.cn/simple' }
$torchIndex = if ($env:LEGGED_STUDIO_TORCH_INDEX) { $env:LEGGED_STUDIO_TORCH_INDEX } else { 'https://mirror.sjtu.edu.cn/pytorch-wheels/cu128/' }

if (-not $IsWindows -and $env:OS -ne 'Windows_NT') { throw 'Windows runtime provisioning requires Windows.' }

function Publish-Stage([string]$stageName, [int]$percent, [string]$message) {
    Write-Output "::progress::$stageName|$percent|$message"
}

$target = [System.IO.Path]::GetFullPath($TargetRoot)
$parent = Split-Path $target -Parent
$stage = "$target.installing"
$cache = Join-Path $parent 'downloads'
$uvRoot = Join-Path $parent "uv-$uvVersion"
$uvExe = Join-Path $uvRoot 'uv.exe'
$pythonRoot = Join-Path $stage 'python'
$manifestPath = Join-Path $target 'runtime-manifest.json'

function Get-ManifestPython([string]$root, [string]$manifestFile) {
    if (-not (Test-Path $manifestFile)) { return $null }
    try {
        $manifest = Get-Content $manifestFile -Raw | ConvertFrom-Json
        $candidate = Join-Path $root $manifest.python
        if (Test-Path $candidate) { return $candidate }
    } catch {}
    return $null
}

$installedPython = Get-ManifestPython $target $manifestPath
if ($installedPython) {
    & $installedPython -c "import torch,mjlab,warp,mujoco_warp,fastapi; assert torch.__version__.startswith('$torchVersion')"
    if ($LASTEXITCODE -eq 0) {
        Publish-Stage 'complete' 100 'Runtime is already configured'
        Write-Host "Legged Studio runtime is already ready: $target"
        exit 0
    }
}

New-Item -ItemType Directory -Path $parent,$cache -Force | Out-Null
Publish-Stage 'bootstrap' 5 'Checking bootstrap components'
$bundledUv = if ($BootstrapRoot) { Join-Path $BootstrapRoot 'uv\uv.exe' } else { '' }
if ($bundledUv -and (Test-Path $bundledUv)) {
    $uvExe = $bundledUv
} elseif (-not (Test-Path $uvExe)) {
    $uvArchive = Join-Path $cache "uv-$uvVersion-windows.zip"
    $uvUrl = "https://github.com/astral-sh/uv/releases/download/$uvVersion/uv-x86_64-pc-windows-msvc.zip"
    Write-Host "Downloading uv $uvVersion..."
    Invoke-WebRequest -Uri $uvUrl -OutFile $uvArchive -UseBasicParsing
    if (Test-Path $uvRoot) { Remove-Item -LiteralPath $uvRoot -Recurse -Force }
    Expand-Archive -LiteralPath $uvArchive -DestinationPath $uvRoot -Force
}
if (-not (Test-Path $uvExe)) { throw "uv.exe was not found after download: $uvExe" }

if (Test-Path $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage | Out-Null

Write-Host "Preparing portable CPython $pythonVersion..."
Publish-Stage 'python' 15 "Preparing Python $pythonVersion"
$bundledPython = if ($BootstrapRoot) { Join-Path $BootstrapRoot 'python' } else { '' }
if ($bundledPython -and (Test-Path $bundledPython)) {
    Copy-Item -LiteralPath $bundledPython -Destination $pythonRoot -Recurse -Force
} else {
    & $uvExe python install $pythonVersion --install-dir $pythonRoot --no-bin --no-registry
    if ($LASTEXITCODE -ne 0) { throw 'Python download failed' }
}
$pythonExe = (Get-ChildItem $pythonRoot -Recurse -Filter python.exe | Select-Object -First 1).FullName
if (-not $pythonExe) { throw 'Downloaded Python executable was not found' }
$pythonDirectory = Split-Path $pythonExe -Parent
Get-ChildItem $pythonRoot -Attributes ReparsePoint -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.FullName -ne $pythonDirectory) { [System.IO.Directory]::Delete($_.FullName) }
}
$tempPython = Join-Path $pythonRoot '.temp'
if (Test-Path $tempPython) { Remove-Item -LiteralPath $tempPython -Recurse -Force }

Write-Host "Installing the Windows GPU profile from domestic mirrors..."
Publish-Stage 'dependencies' 25 'Resolving dependencies from domestic mirrors'
Write-Host "PyPI: $pypiIndex"
Write-Host "Torch: $torchIndex"
& $uvExe pip install --break-system-packages --python $pythonExe --index-strategy unsafe-best-match --index $torchIndex --default-index $pypiIndex "torch==$torchVersion+cu128" "mjlab==$mjlabVersion" 'onnxruntime>=1.20,<2' 'fastapi>=0.115.0' 'uvicorn[standard]>=0.31.0' 'pydantic>=2.0.0'
if ($LASTEXITCODE -ne 0) { throw 'MJLab dependency installation failed' }
Publish-Stage 'dependencies' 80 'Python and GPU dependencies installed'

function Install-GitHubSnapshot([string]$repository, [string]$commit, [string]$destination) {
    $safeName = $repository.Replace('/', '-')
    $archive = Join-Path $cache "$safeName-$commit.zip"
    $bundledArchive = if ($BootstrapRoot) { Join-Path $BootstrapRoot "sources\$safeName-$commit.zip" } else { '' }
    $extract = Join-Path $stage ".$safeName-extract"
    if ($bundledArchive -and (Test-Path $bundledArchive)) {
        $archive = $bundledArchive
    } elseif (-not (Test-Path $archive)) {
        Write-Host "Downloading $repository source $commit..."
        Invoke-WebRequest -Uri "https://github.com/$repository/archive/$commit.zip" -OutFile $archive -UseBasicParsing
    }
    if (Test-Path $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
    Expand-Archive -LiteralPath $archive -DestinationPath $extract -Force
    $sourceDirectory = if (Test-Path (Join-Path $extract 'src')) { Get-Item $extract } else { Get-ChildItem $extract -Directory | Select-Object -First 1 }
    if (-not $sourceDirectory) { throw "Unable to extract $repository" }
    Move-Item -LiteralPath $sourceDirectory.FullName -Destination $destination
    Remove-Item -LiteralPath $extract -Recurse -Force
}

Install-GitHubSnapshot 'mujocolab/mjlab' $mjlabCommit (Join-Path $stage 'mjlab_source')
Install-GitHubSnapshot 'unitreerobotics/unitree_rl_mjlab' $unitreeCommit (Join-Path $stage 'mjlab_extension')
Publish-Stage 'sources' 90 'Source snapshots prepared'

& $pythonExe -c "import torch,mjlab,warp,mujoco_warp,fastapi; print(torch.__version__, torch.cuda.is_available())"
if ($LASTEXITCODE -ne 0) { throw 'Downloaded runtime verification failed' }
Publish-Stage 'verify' 95 'Runtime verification passed'

$manifest = [ordered]@{
    schema_version = 'downloaded-runtime-1'
    platform = 'win32-x64'
    python = (Get-Item $pythonExe).FullName.Substring($stage.Length + 1)
    python_version = $pythonVersion
    uv_version = $uvVersion
    torch_version = "$torchVersion+cu128"
    mjlab_version = $mjlabVersion
    mjlab_commit = $mjlabCommit
    unitree_commit = $unitreeCommit
    mjlab_source = 'mjlab_source'
    mjlab_extension = 'mjlab_extension'
    generated_at = (Get-Date).ToUniversalTime().ToString('o')
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stage 'runtime-manifest.json') -Encoding UTF8

if (Test-Path $target) { Remove-Item -LiteralPath $target -Recurse -Force }
Move-Item -LiteralPath $stage -Destination $target
Publish-Stage 'complete' 100 'Runtime configuration complete'
Write-Host "Legged Studio Windows runtime is ready: $target"
