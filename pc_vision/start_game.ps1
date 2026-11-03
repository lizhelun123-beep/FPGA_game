param(
    [ValidatePattern('^COM[1-9][0-9]*$')]
    [string]$SerialPort = 'COM9',
    [ValidateRange(1, 4000000)]
    [int]$BaudRate = 115200,
    [string]$GodotPath = ''
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($GodotPath)) {
    $GodotPath = Join-Path $projectRoot 'output/tools/godot/Godot_v4.7.2-stable_win64_console.exe'
}
if (-not (Test-Path -LiteralPath $GodotPath -PathType Leaf)) {
    throw 'Godot executable not found. Supply -GodotPath with the installed Godot executable.'
}
$enginePath = (Resolve-Path -LiteralPath $GodotPath).Path
$traceDirectory = Join-Path $PSScriptRoot 'output/serial'
New-Item -ItemType Directory -Force -Path $traceDirectory | Out-Null
$traceName = 'uart_' + [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() + '_' + [guid]::NewGuid().ToString('N').Substring(0, 8) + '.jsonl'
$tracePath = Join-Path $traceDirectory $traceName
Write-Host "Board port: $SerialPort; baud: $BaudRate"
Write-Host "UART trace: $tracePath"
Push-Location $projectRoot
try {
    # Import changed/new source assets before opening the runtime project.
    $importLog = Join-Path $traceDirectory ($traceName + '.godot.log')
    & $enginePath --headless --editor --import --quit --log-file $importLog --path (Join-Path $PSScriptRoot 'godot')
    if ($LASTEXITCODE -ne 0) {
        throw "Godot asset import failed. See $importLog"
    }
    & python -m pc_vision.godot_bridge --serial $SerialPort --baud $BaudRate --godot $enginePath --serial-log $tracePath
    $gameExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $gameExitCode
