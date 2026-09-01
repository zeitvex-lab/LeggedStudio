$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$output = Join-Path $root 'dist\embedded-win'
$version = (Get-Content -LiteralPath (Join-Path $root 'VERSION') -Raw).Trim()
$archive = Join-Path $root "dist\Legged-Studio-$version-Windows-CUDA.7z"
$sevenZip = Join-Path $root 'node_modules\7zip-bin\win\x64\7za.exe'

if (-not (Test-Path (Join-Path $root 'build\embedded-runtime\runtime-manifest.json'))) {
    throw 'Embedded runtime is not staged. Run npm run stage:runtime:win first.'
}
if (-not (Test-Path $sevenZip)) {
    throw '7za is unavailable. Run npm ci first.'
}

$distDirectory = Join-Path $root 'dist'
if (-not (Test-Path $distDirectory)) { New-Item -ItemType Directory -Path $distDirectory | Out-Null }
$distRoot = (Resolve-Path (Join-Path $root 'dist')).Path
if (Test-Path $output) {
    $resolvedOutput = (Resolve-Path $output).Path
    if (-not $resolvedOutput.StartsWith($distRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to replace output outside dist: $resolvedOutput"
    }
    Remove-Item -LiteralPath $resolvedOutput -Recurse -Force
}
if (Test-Path $archive) { Remove-Item -LiteralPath $archive -Force }

& npx electron-builder --dir --win --config packaging/electron-builder.embedded.js --config.directories.output=dist/embedded-win
if ($LASTEXITCODE -ne 0) { throw 'electron-builder directory packaging failed' }

$appDir = Join-Path $output 'win-unpacked'
& $sevenZip a -t7z -mx=3 -mmt=on $archive $appDir
if ($LASTEXITCODE -ne 0) { throw '7z archive creation failed' }

Write-Host "Embedded Windows directory: $appDir"
Write-Host "Embedded Windows archive: $archive"
