$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$outDir = Join-Path $root 'build\exp10a'
$resultsRaw = Join-Path $root 'results\raw'
New-Item -ItemType Directory -Force -Path $resultsRaw | Out-Null

$upstreamExe = Join-Path $outDir 'exp10a_upstream.exe'
$instrumentedExe = Join-Path $outDir 'exp10a_instrumented.exe'
if (-not (Test-Path $upstreamExe)) { throw "missing $upstreamExe; run build.ps1 first" }
if (-not (Test-Path $instrumentedExe)) { throw "missing $instrumentedExe; run build.ps1 first" }

& $upstreamExe upstream $resultsRaw
if ($LASTEXITCODE -ne 0) { throw 'upstream probe FAILED' }
& $instrumentedExe instrumented $resultsRaw
if ($LASTEXITCODE -ne 0) { throw 'instrumented probe FAILED' }

Get-ChildItem $resultsRaw | Where-Object { $_.Name -like 'exp10a_*' } | Select-Object Name, Length
