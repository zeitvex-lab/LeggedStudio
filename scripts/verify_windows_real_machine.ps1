<#
.SYNOPSIS
  A1 real-machine runbook + structured evidence collector (the "double-click -> configure -> launch" pass).

.DESCRIPTION
  Why this file exists: verify_windows_online.ps1 / verify_windows_embedded.ps1 check the PACKAGE
  layout (bundled uv/python, mirror resolution, archive integrity), and tools/audit_provision_phases.py
  checks the provisioning four phases structurally. Both explicitly state they do NOT replace a real
  Windows run. What was missing is the run itself: it needs a human (double-click, watch, click
  through the wizard), but the EVIDENCE can be structured instead of a hand-written paragraph.

  ASCII-only on purpose: Windows PowerShell 5.1 decodes BOM-less .ps1 as ANSI, so non-ASCII text here
  would be mangled at parse time (same convention as the other scripts/*.ps1 in this repo).

  Exit code: 0 when everything is PASS/NEEDS-HUMAN, 1 when any step FAILs (usable as a gate).

.PARAMETER AppRoot
  Installed/extracted product directory (the one produced by scripts/package_windows_*.ps1, i.e. it
  contains resources\app). Auto-detected under dist\ when omitted.

.PARAMETER BaseUrl
  Backend base URL (default http://127.0.0.1:8000).

.PARAMETER StructureOnly
  Only collect machine/package facts and run the structural gate; do NOT poll /health.
  Lets you confirm the script itself works on a development machine.

.PARAMETER Json
  Evidence output path (default workspace/validation/windows-real-machine-<timestamp>.json).
#>
param(
  [string]$AppRoot = "",
  [string]$BaseUrl = "http://127.0.0.1:8000",
  [switch]$StructureOnly,
  [string]$Json = ""
)

$ErrorActionPreference = 'Stop'
# Tools print Chinese + check marks; without this a redirected stdout on Windows falls back to the
# ANSI code page and print() would raise UnicodeEncodeError. Belt and braces: the tools also
# reconfigure their own stdout, but this is how the repo runs them everywhere else.
$env:PYTHONIOENCODING = 'utf-8'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
if (-not $Json) {
  $Json = Join-Path $root "workspace\validation\windows-real-machine-$stamp.json"
}

$rows = New-Object System.Collections.Generic.List[object]
function Add-Row([string]$name, [string]$verdict, [string]$evidence) {
  $rows.Add([pscustomobject]@{ step = $name; verdict = $verdict; evidence = $evidence })
  $mark = switch ($verdict) { 'PASS' { '[ok]  ' } 'FAIL' { '[FAIL]' } default { '[?]   ' } }
  Write-Host ("  {0} {1,-40} {2}" -f $mark, $name, $evidence)
}

Write-Host ""
Write-Host "A1 real-machine verification (clean Windows, end to end)"
Write-Host "=============================================================="

# ---- 1. machine facts (read only) -----------------------------------------
$os = Get-CimInstance Win32_OperatingSystem
Add-Row "os" "PASS" ("{0} build {1} ({2})" -f $os.Caption, $os.BuildNumber, $env:PROCESSOR_ARCHITECTURE)

$nvidia = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvidia) {
  $gpu = (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>$null | Select-Object -First 1)
  Add-Row "gpu-driver-readonly" "PASS" "$gpu"
} else {
  Add-Row "gpu-driver-readonly" "NEEDS-HUMAN" "nvidia-smi not found: CPU-only is acceptable, just record it"
}

if (Test-Path (Join-Path $root '.venv')) {
  Add-Row "clean-machine-check" "NEEDS-HUMAN" "repo .venv exists: NOT a clean environment, result is indicative only"
} else {
  Add-Row "clean-machine-check" "PASS" "no repo .venv"
}

# ---- 2. package facts ------------------------------------------------------
# Product layout comes from scripts/package_windows_*.ps1: dist/Legged-Studio-<version>-Windows-<flavour>/
# built by robocopy from the electron win-unpacked dir, so a usable root is one that has resources\app.
$version = (Get-Content -LiteralPath (Join-Path $root 'VERSION') -Raw).Trim()
if (-not $AppRoot) {
  $candidates = Get-ChildItem (Join-Path $root 'dist') -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like 'Legged-Studio-*-Windows-*' } | Sort-Object Name -Descending
  $usable = $candidates | Where-Object { Test-Path (Join-Path $_.FullName 'resources\app') } | Select-Object -First 1
  if ($usable) { $AppRoot = $usable.FullName }
  elseif ($candidates) {
    Add-Row "app-root" "NEEDS-HUMAN" ("only stale dirs found (" + (($candidates | Select-Object -First 3).Name -join ', ') + "): pass -AppRoot <real product dir>")
  }
}
if ($AppRoot -and (Test-Path $AppRoot)) {
  Add-Row "app-root" "PASS" $AppRoot
  $names = (Split-Path $AppRoot -Leaf)
  if ($names -notlike "*$version*") {
    Add-Row "app-version-matches-VERSION" "NEEDS-HUMAN" "dir says '$names' but VERSION says $version (stale build?)"
  } else {
    Add-Row "app-version-matches-VERSION" "PASS" $version
  }
  $exes = @(Get-ChildItem $AppRoot -Filter '*.exe' -ErrorAction SilentlyContinue | Where-Object { $_.Name -notlike 'elevate*' })
  if ($exes.Count -gt 0) {
    Add-Row "launcher-exe" "PASS" (($exes | Select-Object -First 3).Name -join ', ')
  } else {
    Add-Row "launcher-exe" "FAIL" "no launcher .exe in the app root"
  }
  # electron-builder productName is "Legged Studio", so the exe name may contain a space.
  $runtime = Join-Path $AppRoot 'resources\app\runtime'
  if (Test-Path $runtime) {
    Add-Row "runtime-dir" "NEEDS-HUMAN" "runtime present: verify against the embedded flavour"
  } else {
    Add-Row "runtime-dir" "NEEDS-HUMAN" "no runtime: verify against the online flavour (installed on first configure)"
  }
} elseif ($AppRoot) {
  Add-Row "app-root" "FAIL" "path does not exist: $AppRoot"
}

# ---- 3. structural gate (reuse the existing implementation) ----------------
$audit = Join-Path $root 'tools\audit_provision_phases.py'
if (Test-Path $audit) {
  $python = (Join-Path $root '.venv\Scripts\python.exe')
  if (-not (Test-Path $python)) { $python = 'python' }
  # Native commands write warnings to stderr; with ErrorActionPreference=Stop that aborts the script,
  # so relax it for the call and judge by exit code only (the gate's own wording is Chinese and we
  # must not match on localized text).
  $previous = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    & $python -W ignore $audit *> $null
    $auditExit = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $previous
  }
  if ($auditExit -eq 0) {
    Add-Row "provision-phases-gate" "PASS" "audit_provision_phases exit 0"
  } else {
    Add-Row "provision-phases-gate" "FAIL" "audit_provision_phases exit $auditExit"
  }
}

# ---- 4. human steps (printed, not executed) --------------------------------
Write-Host ""
Write-Host "  -- the next three steps need a human; expected observations are listed --"
Write-Host "  1) DOUBLE-CLICK the launcher .exe in the app root"
Write-Host "     expect: launcher window appears, nothing is downloaded automatically, GPU probe is read-only"
Write-Host "  2) CONFIGURE explicitly: pick a mirror tier (domestic / official / custom / offline wheelhouse)"
Write-Host "     expect: per-phase progress events; failures reported, never a silent fallback to the network"
Write-Host "  3) LAUNCH the app"
Write-Host "     expect: backend reachable and /health matches the packaged identity/version"
Add-Row "double-click-configure-launch" "NEEDS-HUMAN" "perform the three steps above and record the outcome here"

# ---- 5. poll /health (machine-judgeable part after launch) -----------------
if ($StructureOnly) {
  Add-Row "health-poll" "NEEDS-HUMAN" "-StructureOnly: skipped (drop the switch on the real machine)"
} else {
  $deadline = (Get-Date).AddMinutes(10)
  $health = $null
  while ((Get-Date) -lt $deadline) {
    try {
      $health = Invoke-RestMethod -Uri "$BaseUrl/health" -TimeoutSec 5
      break
    } catch {
      Start-Sleep -Seconds 5
    }
  }
  if ($health) {
    $text = ($health | ConvertTo-Json -Compress)
    Add-Row "health-poll" "PASS" $text.Substring(0, [Math]::Min(150, $text.Length))
  } else {
    Add-Row "health-poll" "FAIL" "no response from $BaseUrl/health within 10 minutes"
  }
}

# ---- 6. evidence ------------------------------------------------------------
$verdict = 'PASS'
if ($rows | Where-Object { $_.verdict -eq 'FAIL' }) { $verdict = 'FAIL' }
elseif ($rows | Where-Object { $_.verdict -eq 'NEEDS-HUMAN' }) { $verdict = 'NEEDS-HUMAN' }
$payload = [pscustomobject]@{
  schema         = 'windows-real-machine-1.0'
  generated_at   = (Get-Date).ToString('o')
  app_root       = $AppRoot
  base_url       = $BaseUrl
  structure_only = [bool]$StructureOnly
  rows           = $rows
  verdict        = $verdict
}
New-Item -ItemType Directory -Force -Path (Split-Path $Json) | Out-Null
$payload | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $Json -Encoding utf8
Write-Host ""
Write-Host ("evidence: {0}  verdict: {1}" -f $Json, $verdict)
exit $(if ($verdict -eq 'FAIL') { 1 } else { 0 })
