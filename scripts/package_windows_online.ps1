$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$version = (Get-Content -LiteralPath (Join-Path $root 'VERSION') -Raw).Trim()
$dist = Join-Path $root 'dist'
$builderOutput = Join-Path $dist 'online-build'
$productDirectory = Join-Path $dist "Legged-Studio-$version-Windows-Online"
$archive = "$productDirectory.7z"
$sevenZip = Join-Path $root 'node_modules\7zip-bin\win\x64\7za.exe'
$bootstrap = Join-Path $root 'build\online-bootstrap'
$pythonVersion = '3.12.13'
$mjlabCommit = 'b517e0c489139e7fcee95702cfb2b01931264985'
$unitreeCommit = '1425b15f73bd4095f0df53709d7c389c3eb9e790'

if (-not (Test-Path $dist)) { New-Item -ItemType Directory -Path $dist | Out-Null }
foreach ($path in @($builderOutput, $productDirectory)) {
    if (Test-Path $path) { Remove-Item -LiteralPath $path -Recurse -Force }
}
if (Test-Path $archive) { Remove-Item -LiteralPath $archive -Force }
if (-not (Test-Path $sevenZip)) { throw '7za is unavailable. Run npm ci first.' }

if (Test-Path $bootstrap) { Remove-Item -LiteralPath $bootstrap -Recurse -Force }
New-Item -ItemType Directory -Path (Join-Path $bootstrap 'uv'),(Join-Path $bootstrap 'sources') | Out-Null
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvCommand) { throw 'uv is required on the build machine.' }
Copy-Item -LiteralPath $uvCommand.Source -Destination (Join-Path $bootstrap 'uv\uv.exe') -Force

Write-Host "Staging CPython $pythonVersion bootstrap..."
& $uvCommand.Source python install $pythonVersion --install-dir (Join-Path $bootstrap 'python') --no-bin --no-registry
if ($LASTEXITCODE -ne 0) { throw 'Unable to stage CPython bootstrap' }
$pythonRoot = Join-Path $bootstrap 'python'
$pythonExe = (Get-ChildItem $pythonRoot -Recurse -Filter python.exe | Select-Object -First 1).FullName
$pythonDirectory = Split-Path $pythonExe -Parent
Get-ChildItem $pythonRoot -Attributes ReparsePoint -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.FullName -ne $pythonDirectory) { [System.IO.Directory]::Delete($_.FullName) }
}
$tempPython = Join-Path $pythonRoot '.temp'
if (Test-Path $tempPython) { Remove-Item -LiteralPath $tempPython -Recurse -Force }

$workspace = Split-Path $root -Parent
$mjlabSource = if ($env:LEGGED_STUDIO_MJLAB_SOURCE) { $env:LEGGED_STUDIO_MJLAB_SOURCE } else { Join-Path $workspace 'mjlab_new\mjlab' }
$unitreeSource = if ($env:LEGGED_STUDIO_MJLAB_EXTENSION) { $env:LEGGED_STUDIO_MJLAB_EXTENSION } else { Join-Path $workspace 'uni_rl\unitree_rl_mjlab' }
if (-not (Test-Path (Join-Path $mjlabSource 'src'))) { throw "MJLab source not found: $mjlabSource" }
if (-not (Test-Path (Join-Path $unitreeSource 'src'))) { throw "Unitree extension not found: $unitreeSource" }

$mjlabArchive = Join-Path $bootstrap "sources\mujocolab-mjlab-$mjlabCommit.zip"
Push-Location $mjlabSource
try { & $sevenZip a -tzip $mjlabArchive 'src' 'LICENSE' 'pyproject.toml' '-xr!__pycache__' } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw 'Unable to archive MJLab source snapshot' }
$unitreeArchive = Join-Path $bootstrap "sources\unitreerobotics-unitree_rl_mjlab-$unitreeCommit.zip"
Push-Location $unitreeSource
try { & $sevenZip a -tzip $unitreeArchive 'src' 'LICENCE' 'setup.py' '-xr!__pycache__' } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw 'Unable to archive Unitree source snapshot' }

& npx electron-builder --dir --win --config packaging/electron-builder.online.js --config.directories.output=dist/online-build
if ($LASTEXITCODE -ne 0) { throw 'Electron directory packaging failed' }
$unpacked = Join-Path $builderOutput 'win-unpacked'
New-Item -ItemType Directory -Path $productDirectory | Out-Null
& robocopy $unpacked $productDirectory /E /NFL /NDL /NJH /NJS /NP | Out-Host
if ($LASTEXITCODE -gt 7) { throw "Unable to stage the named product directory (robocopy $LASTEXITCODE)" }

& $sevenZip a -t7z -mx=5 -mmt=on $archive $productDirectory
if ($LASTEXITCODE -ne 0) { throw '7z archive creation failed' }
Write-Host "Legged Studio online installer package: $archive"
