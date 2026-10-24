param([switch]$StaticOnly)
$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = (Resolve-Path (Join-Path $appRoot "../../..")).Path
$sourceRoot = Join-Path $appRoot "src"
$testRoot = Join-Path $appRoot "tests"
$buildRoot = Join-Path $repoRoot "output/build/game_session"
$compiler = (Get-Command gcc.exe -ErrorAction Stop).Source
New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
python (Join-Path $PSScriptRoot "generate_game_config.py") --output (Join-Path $buildRoot "game_config.h")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$inputs = @((Join-Path $sourceRoot "game_session.c"),
            (Join-Path $sourceRoot "ray_game.c"),
            (Join-Path $buildRoot "game_config.c"),
            (Join-Path $testRoot "test_game_session.c"))
$flags = @("-std=c99", "-Wall", "-Wextra", "-Werror", "-pedantic", "-I$sourceRoot", "-I$buildRoot")
# Cheapest gate first; no linker, BSP, detector, clocks or devices.
& $compiler @flags -fsyntax-only @inputs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output "Game session C99 static check passed"
if ($StaticOnly) { exit 0 }
$executable = Join-Path $buildRoot "test_game_session.exe"
& $compiler @flags -O2 @inputs -lm -o $executable
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $executable
exit $LASTEXITCODE
