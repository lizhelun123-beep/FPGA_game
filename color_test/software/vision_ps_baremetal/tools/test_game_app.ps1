param([switch]$StaticOnly, [switch]$LinuxStaticOnly, [switch]$DisplayOnly, [switch]$SpriteOnly, [switch]$OfflinePackage,
      [string]$DisplayAssets = "", [string]$DisplayControl720 = "", [string]$DisplayOutput = "",
      [string]$LinuxCompiler = "D:/Xilinx/Vitis/2023.1/gnu/aarch32/nt/gcc-arm-linux-gnueabi/bin/arm-linux-gnueabihf-gcc.exe")
$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = (Resolve-Path (Join-Path $appRoot "../../..")).Path
$sourceRoot = Join-Path $appRoot "src"
$testRoot = Join-Path $appRoot "tests"
$buildRoot = Join-Path $repoRoot "output/build/game_app"
if ($DisplayOutput) { $buildRoot = [IO.Path]::GetFullPath($DisplayOutput) }
$compiler = (Get-Command gcc.exe -ErrorAction Stop).Source
New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
python (Join-Path $PSScriptRoot "generate_game_config.py") --output (Join-Path $buildRoot "game_config.h")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$core = @((Join-Path $sourceRoot "game_session.c"),
          (Join-Path $sourceRoot "ray_game.c"),
          (Join-Path $buildRoot "game_config.c"))
$adapter = @((Join-Path $sourceRoot "game_scene_adapter.c"),
             (Join-Path $sourceRoot "game_app.c"))
$inputLoop = @((Join-Path $sourceRoot "game_input.c"),
               (Join-Path $sourceRoot "game_evdev.c"),
               (Join-Path $sourceRoot "game_loop.c"),
               (Join-Path $sourceRoot "game_pump.c"))
$render = @((Join-Path $sourceRoot "game_render.c"), (Join-Path $sourceRoot "vision_overlay.c"))
$linuxIO = @((Join-Path $sourceRoot "game_linux_io.c"))
$flags = @("-std=c99", "-Wall", "-Wextra", "-Werror", "-pedantic", "-I$sourceRoot", "-I$buildRoot")
$display = @((Join-Path $sourceRoot "game_linux_display.c"))
$photo = @((Join-Path $sourceRoot "game_photo_input.c"),
           (Join-Path $sourceRoot "vision_ps.c"), (Join-Path $sourceRoot "green_target_detector.c"))
if ($SpriteOnly) {
    $spriteSources = $core + $adapter + $inputLoop + $render + $display + $linuxIO + $photo
    $spriteTest = Join-Path $testRoot "test_game_sprites.c"
    $spriteEntry = Join-Path $PSScriptRoot "game_linux_static_menu.c"
    & $compiler @flags -fsyntax-only @spriteSources $spriteTest $spriteEntry
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ($StaticOnly) { exit 0 }
    $spriteExe = Join-Path $buildRoot "test_game_sprites.exe"
    & $compiler @flags -O2 @spriteSources $spriteTest -lm -o $spriteExe
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $spriteExe | Tee-Object -FilePath (Join-Path $buildRoot "game_sprites_host.txt")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $menuExe = Join-Path $buildRoot "game_linux_static_menu.exe"
    & $compiler @flags -O2 @spriteSources $spriteEntry -lm -o $menuExe
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    python (Join-Path $testRoot "test_game_sprites.py") --executable $menuExe --output (Join-Path $buildRoot "sprites")
    exit $LASTEXITCODE
}
if ($DisplayOnly) {
    $displaySources = $core + $adapter + $inputLoop + $render + $display + $linuxIO + $photo
    $displayTest = Join-Path $testRoot "test_game_linux_display.c"
    $displayEntry = Join-Path $PSScriptRoot "game_linux_static_menu.c"
    & $compiler @flags -fsyntax-only @displaySources $displayTest $displayEntry
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Output "PASS display focused strict C99 static check"
    if ($StaticOnly) { exit 0 }
    $displayExe = Join-Path $buildRoot "test_game_linux_display.exe"
    & $compiler @flags -O2 @displaySources $displayTest -lm -o $displayExe
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $displayExe | Tee-Object -FilePath (Join-Path $buildRoot "game_linux_display_host.txt")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ($DisplayControl720) {
        & $displayExe --control-bmp $DisplayControl720 | Tee-Object -FilePath (Join-Path $buildRoot "control720_host.txt")
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    if ($DisplayAssets) {
        python (Join-Path $testRoot "test_game_sprites.py") --display-executable $displayExe `
            --assets $DisplayAssets --output (Join-Path $buildRoot "display_asset_submission")
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    $menuExe = Join-Path $buildRoot "game_linux_static_menu.exe"
    & $compiler @flags -O2 @displaySources $displayEntry -lm -o $menuExe
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ($DisplayControl720) {
        & $LinuxCompiler @flags -O2 -static -mcpu=cortex-a9 -mfpu=vfpv3 -mfloat-abi=hard @displaySources $displayEntry -lm -o (Join-Path $buildRoot "display.elf")
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Write-Output "PASS ARM32 hard-float static Linux display executable link"
    }
    $objdump = Join-Path (Split-Path -Parent $compiler) "objdump.exe"
    $imports = & $objdump -p $menuExe
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ($imports -match '(?i)DLL Name:.*(?:libcma|cma\.dll)') {
        throw "CPU/refusal entry must not load libcma before main"
    }
    Write-Output "PASS menu import table: no CMA DLL dependency"
    & $menuExe --check | Tee-Object -FilePath (Join-Path $buildRoot "game_linux_static_menu_host.txt")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if (!((Get-Content -Raw (Join-Path $buildRoot "game_linux_static_menu_host.txt")) -match 'hash=1f497c09 .*snapshot_unchanged=1')) {
        throw "Initial menu hash or immutable snapshot changed"
    }
    & $menuExe --display 2>&1 | ForEach-Object { "$($_)" } |
        Set-Content (Join-Path $buildRoot "game_linux_static_menu_blocked.txt")
    if ($LASTEXITCODE -ne 3) { throw "Unqualified display entry did not fail closed" }
    if (!((Get-Content -Raw (Join-Path $buildRoot "game_linux_static_menu_blocked.txt")) -match 'No display/CMA/device operation performed')) {
        throw "Missing unqualified entry refusal evidence"
    }
    exit 0
}
if ($LinuxStaticOnly) {
    & $LinuxCompiler @flags -fsyntax-only @linuxIO (Join-Path $sourceRoot "game_pump.c")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $LinuxCompiler @flags -O2 -c @linuxIO -o (Join-Path $buildRoot "game_linux_io.arm.o")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Output "PASS ARM Linux source/headers + relocatable object only; no target execution or glibc 2.27 compatibility claim"
    exit 0
}
$tests = @("test_game_session", "test_game_app", "test_game_loop", "test_game_pump", "test_game_render", "test_game_linux_io")
$allSources = $core + $adapter + $inputLoop + $render + $linuxIO + @((Join-Path $testRoot "test_game_session.c"),
                                  (Join-Path $testRoot "test_game_app.c"),
                                  (Join-Path $testRoot "test_game_loop.c"),
                                  (Join-Path $testRoot "test_game_pump.c"),
                                  (Join-Path $testRoot "test_game_render.c"),
                                  (Join-Path $testRoot "test_game_linux_io.c"),
                                  (Join-Path $PSScriptRoot "game_offline.c"))
& $compiler @flags -fsyntax-only @allSources
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output "Game render/pump/input/loop/adapter/app/core C99 static check passed"
if ($StaticOnly) { exit 0 }
foreach ($test in $tests) {
    $inputs = $core + @((Join-Path $testRoot "$test.c"))
    if ($test -eq "test_game_app") { $inputs += $adapter }
    if ($test -in @("test_game_loop", "test_game_pump", "test_game_render", "test_game_linux_io")) { $inputs += $adapter + $inputLoop }
    if ($test -eq "test_game_render") { $inputs += $render }
    if ($test -eq "test_game_linux_io") { $inputs += $linuxIO }
    $executable = Join-Path $buildRoot "$test.exe"
    & $compiler @flags -O2 @inputs -lm -o $executable
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ($test -eq "test_game_render") {
        & $executable (Join-Path $buildRoot "render_budget_test.ppm") |
            Tee-Object -FilePath (Join-Path $buildRoot "game_render_host.txt")
    }
    elseif ($test -eq "test_game_linux_io") {
        & $executable | Tee-Object -FilePath (Join-Path $buildRoot "game_linux_io_host.txt")
    }
    else { & $executable }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
$offline = Join-Path $buildRoot "game_offline.exe"
& $compiler @flags -O2 @core @adapter @inputLoop @render (Join-Path $PSScriptRoot "game_offline.c") -lm -o $offline
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output "Offline text entry built: $offline"
# Replay original 077 through the real stdin parser, including >32-bit stamps.
# Pose values come from the same JSON, not a second maintained template.
$config = Get-Content -Raw (Join-Path $repoRoot "pc_vision/game_config.json") | ConvertFrom-Json
$level = @($config.board_game.levels | Where-Object { $_.id -eq 3 })[0]
$types = @("MIRROR", "PORTAL_A", "PORTAL_B", "TARGET", "SOURCE", "WALL")
$commands = @("select 4294967296 3", "frame 4294967297 1 4294967297 4294967297 1 0 $($level.objects.Count)")
foreach ($object in $level.objects) {
    $directionValid = [int]($object.type -eq "SOURCE")
    $values = @([Array]::IndexOf($types, $object.type), $object.center[0], $object.center[1],
                $object.axis[0], $object.axis[1], $directionValid, $object.axis[0], $object.axis[1])
    $commands += ($values | ForEach-Object { $_.ToString([Globalization.CultureInfo]::InvariantCulture) }) -join " "
}
$commands += @("start 4294967298", "tick 4294967299", "tick 4295147298", "quit")
$transcript = @($commands | & $offline)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (@($transcript -match '^status=0$').Count -ne 5 -or
    !($transcript -match 'state=1 level=3 generation=1 sequence=4294967297 captured_ms=4294967297 .*valid=1 ready=1') -or
    !($transcript -match 'state=2 level=3 .*elapsed_ms=1 remaining_ms=179999') -or
    !($transcript -match 'state=4 level=3 .*elapsed_ms=180000 remaining_ms=0 stars=0')) {
    throw "Offline text replay did not preserve original 077, 64-bit stamps or no-input timeout"
}
$transcript | Set-Content -Encoding utf8 (Join-Path $buildRoot "offline_smoke.txt")
Write-Output "PASS offline text replay: original 077 / 64-bit stamps / explicit start / no-input timeout"
python (Join-Path $testRoot "test_game_offline.py") --executable $offline --output $buildRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($OfflinePackage) {
    $packageRoot = Join-Path $buildRoot "offline_native_20261021"
    $assetRoot = Join-Path $packageRoot "assets"
    python (Join-Path $PSScriptRoot "prepare_game_assets.py") --game --output $assetRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & (Join-Path $buildRoot "test_game_render.exe") (Join-Path $packageRoot "guards.ppm") (Join-Path $assetRoot "game_assets.bin") |
        Tee-Object -FilePath (Join-Path $packageRoot "cached_render_host.txt")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if (Test-Path -LiteralPath $LinuxCompiler) {
        $armExe = Join-Path $packageRoot "game_offline.arm.elf"
        $dynamicExe = Join-Path $packageRoot "game_offline.arm.dynamic.elf"
        $armFlags = @('-mcpu=cortex-a9', '-mfpu=vfpv3-d16', '-mfloat-abi=hard')
        & $LinuxCompiler @flags @armFlags -O2 @core @adapter @inputLoop @render (Join-Path $PSScriptRoot "game_offline.c") -lm -o $dynamicExe
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        $readelf = Join-Path (Split-Path -Parent $LinuxCompiler) "arm-linux-gnueabihf-readelf.exe"
        & $readelf -h -A -l -V $dynamicExe | Set-Content (Join-Path $packageRoot "arm_dynamic_elf_check.txt")
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $LinuxCompiler @flags @armFlags -O2 -static @core @adapter @inputLoop @render (Join-Path $PSScriptRoot "game_offline.c") -lm -o $armExe
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $readelf -h -A -l -V $armExe | Set-Content (Join-Path $packageRoot "arm_elf_check.txt")
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Write-Output "PASS Cortex-A9 armhf static ELF link only; dynamic ELF needs newer glibc and is excluded from package; target execution NOT_RUN"
    }
    python (Join-Path $testRoot "test_native_game.py") --executable $offline --assets (Join-Path $assetRoot "game_assets.bin") --output $packageRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
exit 0
