$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = Join-Path $appRoot "src"
$testRoot = Join-Path $appRoot "tests"
$compiler = Get-Command gcc.exe -ErrorAction Stop
$output = Join-Path $env:TEMP "vision_ps_host_test.exe"

& $compiler.Source -std=c99 -O2 -Wall -Wextra -Werror `
  "-I$sourceRoot" `
  (Join-Path $sourceRoot "vision_ps.c") `
  (Join-Path $sourceRoot "vision_overlay.c") `
  (Join-Path $testRoot "test_vision_ps.c") `
  -lm -o $output
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $output
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python (Join-Path $testRoot test_pc_parity.py)
exit $LASTEXITCODE
