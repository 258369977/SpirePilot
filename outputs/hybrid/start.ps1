param([string]$RunDir = '')

$ErrorActionPreference = 'Stop'
$pythonExe = (Get-Command python -ErrorAction Stop).Source
$lockFile = Join-Path $PSScriptRoot 'controller.lock'
$stopFile = Join-Path $PSScriptRoot 'STOP'
$configPath = Join-Path $PSScriptRoot 'config.json'
if (-not (Test-Path -LiteralPath $configPath)) {
    $configPath = Join-Path $PSScriptRoot 'config.example.json'
}
$config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json

if (Test-Path -LiteralPath $lockFile) {
    throw 'controller.lock exists. Check whether the previous controller is still running before removing it.'
}
if (Test-Path -LiteralPath $stopFile) {
    Remove-Item -LiteralPath $stopFile
}

$temporaryVariables = [System.Collections.Generic.List[string]]::new()
foreach ($entry in @(
    @{ Label = '长期规划模型'; Name = $config.planner_key_env },
    @{ Label = '战斗模型'; Name = $config.combat_key_env }
)) {
    $name = [string]$entry.Name
    if ([string]::IsNullOrWhiteSpace($name)) {
        throw "$($entry.Label)没有配置密钥环境变量。"
    }
    if (-not [Environment]::GetEnvironmentVariable($name, 'Process')) {
        $secret = Read-Host "$($entry.Label) API Key（隐藏输入，环境变量 $name）" -AsSecureString
        $value = [System.Net.NetworkCredential]::new('', $secret).Password
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        $temporaryVariables.Add($name)
    }
}

try {
    if (-not $RunDir) {
        $RunDir = Join-Path $PSScriptRoot ('runs\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    }
    New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
    $RunDir = (Resolve-Path -LiteralPath $RunDir).Path
    $scriptPath = Join-Path $PSScriptRoot 'hybrid_player.py'
    $process = Start-Process -FilePath $pythonExe `
        -ArgumentList @('-u', ('"' + $scriptPath + '"'), '--run-dir', ('"' + $RunDir + '"')) `
        -WorkingDirectory $PSScriptRoot -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $RunDir 'stdout.log') `
        -RedirectStandardError (Join-Path $RunDir 'stderr.log') -PassThru
    @{ pid = $process.Id; run_dir = $RunDir } | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $PSScriptRoot 'background.json')
    Start-Sleep -Seconds 2
    if ($process.HasExited) {
        throw "Controller exited. Inspect $RunDir\stderr.log"
    }
    Write-Output "Started PID $($process.Id). Logs: $RunDir"
} finally {
    foreach ($name in $temporaryVariables) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
}
