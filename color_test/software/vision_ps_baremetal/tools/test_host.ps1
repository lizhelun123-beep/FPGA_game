param([switch]$FixedSceneOnly)
$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = Join-Path $appRoot "src"
$testRoot = Join-Path $appRoot "tests"
if ($FixedSceneOnly) {
  python (Join-Path $testRoot "test_fixed_scene.py")
  exit $LASTEXITCODE
}
$compiler = Get-Command gcc.exe -ErrorAction Stop
$output = Join-Path $env:TEMP "vision_ps_host_test.exe"
$greenOutput = Join-Path $env:TEMP "green_target_host_test.exe"
$rayOutput = Join-Path $env:TEMP "ray_game_host_test.exe"
$stabilizerOutput = Join-Path $env:TEMP "vision_stabilizer_host_test.exe"

& $compiler.Source -std=c99 -O2 -Wall -Wextra -Werror `
  "-I$sourceRoot" `
  (Join-Path $sourceRoot "vision_ps.c") `
  (Join-Path $sourceRoot "green_target_detector.c") `
  (Join-Path $sourceRoot "ray_game.c") `
  (Join-Path $sourceRoot "vision_overlay.c") `
  (Join-Path $testRoot "test_vision_ps.c") `
  -lm -o $output
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $output
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $compiler.Source -std=c99 -O2 -Wall -Wextra -Werror `
  "-I$sourceRoot" `
  (Join-Path $sourceRoot "vision_ps.c") `
  (Join-Path $sourceRoot "green_target_detector.c") `
  (Join-Path $testRoot "test_green_target.c") `
  -lm -o $greenOutput
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $greenOutput
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $compiler.Source -std=c99 -O2 -Wall -Wextra -Werror `
  "-I$sourceRoot" `
  (Join-Path $sourceRoot "ray_game.c") `
  (Join-Path $sourceRoot "vision_overlay.c") `
  (Join-Path $testRoot "test_ray_game.c") `
  -lm -o $rayOutput
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $rayOutput
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $compiler.Source -std=c99 -O2 -Wall -Wextra -Werror `
  "-I$sourceRoot" `
  (Join-Path $sourceRoot "vision_stabilizer.c") `
  (Join-Path $testRoot "test_vision_stabilizer.c") `
  -lm -o $stabilizerOutput
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $stabilizerOutput
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python (Join-Path $testRoot test_sample_photo_regression.py)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python (Join-Path $testRoot test_pc_parity.py)
exit $LASTEXITCODE
