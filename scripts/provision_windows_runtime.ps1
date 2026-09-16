param(
    [Parameter(Mandatory = $false)]
    [string]$TargetRoot,
    [Parameter(Mandatory = $false)]
    [string]$BootstrapRoot = '',
    [ValidateSet('gpu', 'cpu', '')]
    [string]$Device = 'gpu',
    [switch]$DetectGpus,
    # 第 3 段：镜像档位（cn = 国内镜像 / official = 官方 / custom = 用环境变量自定义 / offline = 纯离线）
    [ValidateSet('cn', 'official', 'custom', 'offline')]
    [string]$MirrorProfile = 'cn',
    # 第 4 段：离线 wheelhouse 目录（给了且存在 ⇒ 走 --no-index --find-links，完全不联网）
    [string]$Wheelhouse = '',
    # 只读查询：打印将要使用的档位与源，不写任何文件（供启动器 UI 显示）
    [switch]$ListProfiles
)

$ErrorActionPreference = 'Stop'
$pythonVersion = '3.12.13'
$uvVersion = '0.11.8'
$torchVersion = '2.11.0'
$mjlabVersion = '1.6.0'
$mjlabCommit = 'b517e0c489139e7fcee95702cfb2b01931264985'
$unitreeCommit = '1425b15f73bd4095f0df53709d7c389c3eb9e790'
# 第 3 段：镜像档位 → 源。**档位是显式选择**（不靠"环境变量碰巧设了"），
# 且 cn 档失败时会**回退官方源再试一次**并把回退如实报出来（见 Invoke-PipInstall）。
$cnPyPiIndex = 'https://pypi.tuna.tsinghua.edu.cn/simple'
$cnTorchIndex = 'https://mirror.sjtu.edu.cn/pytorch-wheels/cu128/'
$officialPyPiIndex = 'https://pypi.org/simple'
$officialTorchIndex = 'https://download.pytorch.org/whl/cu128/'
if ($MirrorProfile -eq 'custom') {
    if (-not $env:LEGGED_STUDIO_PYPI_INDEX) { throw 'MirrorProfile=custom 需要 LEGGED_STUDIO_PYPI_INDEX（自定义源不能靠猜）' }
    $pypiIndex = $env:LEGGED_STUDIO_PYPI_INDEX
    $torchIndex = if ($env:LEGGED_STUDIO_TORCH_INDEX) { $env:LEGGED_STUDIO_TORCH_INDEX } else { $cnTorchIndex }
} elseif ($MirrorProfile -eq 'official') {
    $pypiIndex = $officialPyPiIndex
    $torchIndex = $officialTorchIndex
} else {
    $pypiIndex = $cnPyPiIndex
    $torchIndex = $cnTorchIndex
}
$fallbackPyPiIndex = $officialPyPiIndex
$fallbackTorchIndex = $officialTorchIndex
# 离线档位必须**真的拿到** wheelhouse（否则会静默联网，那是"以为离线但其实没有"）
$offlineMode = ($MirrorProfile -eq 'offline') -or ($Wheelhouse -ne '')
if ($offlineMode) {
    if (-not $Wheelhouse) { throw 'MirrorProfile=offline 需要 -Wheelhouse <目录>' }
    if (-not (Test-Path $Wheelhouse)) { throw "wheelhouse 目录不存在：$Wheelhouse" }
    $Wheelhouse = (Resolve-Path $Wheelhouse).Path
}

if ($ListProfiles) {
    # 只读：把将要用的档位/源打出来（启动器 UI 用它显示"配置会从哪下"），**不写盘、不下载**
    @{
        mirror_profile = $MirrorProfile
        offline        = $offlineMode
        wheelhouse     = if ($offlineMode) { $Wheelhouse } else { $null }
        pypi_index     = if ($offlineMode) { $null } else { $pypiIndex }
        torch_index    = if ($offlineMode) { $null } else { $torchIndex }
    } | ConvertTo-Json -Compress
    exit 0
}

if (-not $IsWindows -and $env:OS -ne 'Windows_NT') { throw 'Windows runtime provisioning requires Windows.' }

# GPU detection mode: print one JSON line with NVIDIA device names (available
# to Torch via CUDA) then exit. Used by the desktop launcher to list accelerators.
if ($DetectGpus) {
    $gpus = @()
    try {
        $controllers = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue
        foreach ($controller in $controllers) {
            $gpu = @{
                name = $controller.Name
                pnp_device_id = $controller.PNPDeviceID
                is_nvidia = $false
            }
            if ($controller.PNPDeviceID -match '(?i)VEN_10DE') { $gpu.is_nvidia = $true }
            $gpus += $gpu
        }
    } catch {}
    Write-Output (($gpus | ConvertTo-Json -Compress) -replace '\\u0000', '')
    exit 0
}

if ([string]::IsNullOrWhiteSpace($Device)) { $Device = 'gpu' }
$device = $Device.ToLowerInvariant()

# Select the Torch wheel index by requested device. cu128 includes bundled CUDA
# wheels; the CPU index installs a CPU-only build that runs without an NVIDIA GPU.
if ($device -eq 'cpu') {
    $torchIndex = 'https://download.pytorch.org/whl/cpu'
    $torchSuffix = 'cpu'
} else {
    $torchIndex = if ($env:LEGGED_STUDIO_TORCH_INDEX) { $env:LEGGED_STUDIO_TORCH_INDEX } else { 'https://mirror.sjtu.edu.cn/pytorch-wheels/cu128/' }
    $torchSuffix = 'cu128'
}

function Publish-Stage([string]$stageName, [int]$percent, [string]$message) {
    Write-Output "::progress::$stageName|$percent|$message"
}

function Move-WithRetry([string]$sourcePath, [string]$destinationPath, [int]$maxAttempts = 10) {
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        try {
            Move-Item -LiteralPath $sourcePath -Destination $destinationPath -ErrorAction Stop
            return
        } catch {
            if ($attempt -eq $maxAttempts) {
                throw "Move failed after $maxAttempts attempts: $($_.Exception.Message)"
            }
            Start-Sleep -Milliseconds ($attempt * 400)
        }
    }
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
    $installedDevice = 'unknown'
    try {
        $installedManifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
        $installedDevice = $installedManifest.device
    } catch {}
    $torchCheck = "import torch,mjlab,warp,mujoco_warp,fastapi; assert torch.__version__.startswith('$torchVersion')"
    & $installedPython -c $torchCheck
    if ($LASTEXITCODE -eq 0 -and $installedDevice -eq $device) {
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

$torchRequirement = "torch==$torchVersion+$torchSuffix"
$packages = @($torchRequirement, "mjlab==$mjlabVersion", 'onnxruntime>=1.20,<2', 'fastapi>=0.115.0',
              'uvicorn[standard]>=0.31.0', 'pydantic>=2.0.0')

function Invoke-PipInstall([string]$pypi, [string]$torchIndexValue, [string]$label) {
    $arguments = @('pip', 'install', '-v', '--break-system-packages', '--python', $pythonExe)
    if ($offlineMode) {
        # 离线：只认本地 wheelhouse（--no-index 是"不许联网"的硬保证，不是礼貌请求）
        $arguments += @('--no-index', '--find-links', $Wheelhouse)
    } else {
        $arguments += @('--index-strategy', 'unsafe-best-match', '--index', $torchIndexValue, '--default-index', $pypi)
    }
    $arguments += $packages
    Write-Host "[$label] PyPI: $(if ($offlineMode) { 'offline wheelhouse' } else { $pypi })"
    Write-Host "[$label] Torch: $(if ($offlineMode) { $Wheelhouse } else { $torchIndexValue })"
    & $uvExe @arguments
    return $LASTEXITCODE
}

if ($offlineMode) {
    Write-Host "Installing the Windows $device profile from the offline wheelhouse..."
    Publish-Stage 'dependencies' 25 "Installing from offline wheelhouse: $Wheelhouse"
    $exitCode = Invoke-PipInstall '' '' 'offline'
} else {
    Write-Host "Installing the Windows $device profile (mirror profile: $MirrorProfile)..."
    Publish-Stage 'dependencies' 25 "Resolving dependencies (mirror profile: $MirrorProfile)"
    $exitCode = Invoke-PipInstall $pypiIndex $torchIndex $MirrorProfile
    if ($exitCode -ne 0 -and $MirrorProfile -eq 'cn') {
        # 第 3 段的一部分：国内镜像失败**回退官方源再试一次**，并把"回退过"如实报出来
        Write-Host 'Domestic mirror failed; retrying with the official index...'
        Publish-Stage 'dependencies' 40 '国内镜像失败，回退官方源重试'
        $exitCode = Invoke-PipInstall $fallbackPyPiIndex $fallbackTorchIndex 'official-fallback'
    }
}
if ($exitCode -ne 0) { throw 'MJLab dependency installation failed' }
Publish-Stage 'dependencies' 80 'Python and dependencies installed'

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
    Move-WithRetry $sourceDirectory.FullName $destination
    if (Test-Path $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
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
    device = $device
    python = (Get-Item $pythonExe).FullName.Substring($stage.Length + 1)
    python_version = $pythonVersion
    uv_version = $uvVersion
    torch_version = "$torchVersion+$torchSuffix"
    mjlab_version = $mjlabVersion
    mjlab_commit = $mjlabCommit
    unitree_commit = $unitreeCommit
    mjlab_source = 'mjlab_source'
    mjlab_extension = 'mjlab_extension'
    generated_at = (Get-Date).ToUniversalTime().ToString('o')
}
$manifest.mirror_profile = $MirrorProfile
$manifest.offline_mode = $offlineMode
$manifest.wheelhouse = if ($offlineMode) { $Wheelhouse } else { $null }
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stage 'runtime-manifest.json') -Encoding UTF8

if (Test-Path $target) { Remove-Item -LiteralPath $target -Recurse -Force }
Move-WithRetry $stage $target
Publish-Stage 'complete' 100 'Runtime configuration complete'
Write-Host "Legged Studio Windows runtime is ready: $target"
