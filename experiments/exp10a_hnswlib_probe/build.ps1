$ErrorActionPreference = 'Stop'

$probeDir = $PSScriptRoot
$root = (Resolve-Path (Join-Path $probeDir '..\..')).Path
$pristine = Join-Path $root 'third_party\hnswlib-v0.9.0\hnswlib'
$instrumented = Join-Path $root 'third_party\hnswlib-v0.9.0-instrumented\hnswlib'
$outDir = Join-Path $root 'build\exp10a'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$gxx = 'g++'
$common = @('-std=c++17', '-O2', '-Wall', '-Wextra')

$upstreamCmd = @(
    '-std=c++17', '-O2', '-Wall', '-Wextra',
    ("-I{0}" -f $probeDir),
    ("-I{0}" -f $pristine),
    (Join-Path $probeDir 'main.cpp'),
    '-o', (Join-Path $outDir 'exp10a_upstream.exe')
)
$instrumentedCmd = @(
    '-std=c++17', '-O2', '-Wall', '-Wextra', '-DHNSWLIB_TRACE_ENABLED=1',
    ("-I{0}" -f $probeDir),
    ("-I{0}" -f $instrumented),
    (Join-Path $probeDir 'main.cpp'),
    '-o', (Join-Path $outDir 'exp10a_instrumented.exe')
)

$info = @()
$info += "EXP-10A build info"
$info += "compiler: " + (& $gxx --version | Select-Object -First 1)
$info += "upstream command: $gxx " + ($upstreamCmd -join ' ')
# Native g++ writes warnings to stderr; PowerShell 5.1 with ErrorActionPreference
# 'Stop' would turn those into terminating errors. Only $LASTEXITCODE is authoritative.
$ErrorActionPreference = 'Continue'
& $gxx @upstreamCmd 2>&1 | Out-String | Write-Output
if ($LASTEXITCODE -ne 0) { throw 'upstream build FAILED' }
$info += "instrumented command: $gxx " + ($instrumentedCmd -join ' ')
& $gxx @instrumentedCmd 2>&1 | Out-String | Write-Output
if ($LASTEXITCODE -ne 0) { throw 'instrumented build FAILED' }
$ErrorActionPreference = 'Stop'

$infoPath = Join-Path $outDir 'BUILD_INFO.txt'
$info | Set-Content -Path $infoPath -Encoding utf8
Get-Content -Path $infoPath
