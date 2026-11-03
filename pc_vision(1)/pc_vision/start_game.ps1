param(
    [ValidatePattern('^COM[1-9][0-9]*$')]
    [string]$SerialPort = 'COM9',
    [ValidateRange(1, 4000000)]
    [int]$BaudRate = 115200,
    [ValidateRange(1, 65535)]
    [int]$Port = 8765,
    [switch]$Preview,
    [switch]$Check,
    [string]$PythonPath = ''
)

$ErrorActionPreference = 'Stop'
if ($Preview -and $Check) { throw 'Choose -Preview or -Check, not both.' }
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $localPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    if (Test-Path -LiteralPath $localPython -PathType Leaf) { $PythonPath = $localPython }
    else { $PythonPath = (Get-Command python -ErrorAction Stop).Source }
}
$runtime = (Get-Command $PythonPath -ErrorAction Stop).Source
& $runtime -B -c 'import aiohttp, serial'
if ($LASTEXITCODE -ne 0) {
    throw "Install web dependencies: & '$runtime' -m pip install -r '$PSScriptRoot/requirements-web.txt'"
}
$bridgeArgs = @('-B', '-m', 'pc_vision.web_bridge', '--port', "$Port")
if ($Check) { $bridgeArgs += '--check' }
elseif ($Preview) { $bridgeArgs += '--preview' }
else {
    $traceDirectory = Join-Path $PSScriptRoot 'output/serial'
    New-Item -ItemType Directory -Force -Path $traceDirectory | Out-Null
    $traceName = 'uart_' + [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() + '_' + [guid]::NewGuid().ToString('N').Substring(0, 8) + '.jsonl'
    $tracePath = Join-Path $traceDirectory $traceName
    $bridgeArgs += @('--serial', $SerialPort, '--baud', "$BaudRate", '--serial-log', $tracePath)
    Write-Host 'Board compatibility: version14 BOOT / binary wire v3'
    Write-Host "Board port: $SerialPort; baud: $BaudRate"
    Write-Host "UART trace: $tracePath"
}
if (-not $Check) { Write-Host "Web UI: http://127.0.0.1:$Port/" }
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    & $runtime @bridgeArgs
    $gameExitCode = $LASTEXITCODE
}
finally { Pop-Location }
exit $gameExitCode
