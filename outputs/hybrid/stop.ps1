$ErrorActionPreference = 'Stop'
Set-Content -LiteralPath (Join-Path $PSScriptRoot 'STOP') -Value 'User requested stop'
Write-Output 'Stop requested. Pending model responses will not execute game actions after this flag is observed.'
