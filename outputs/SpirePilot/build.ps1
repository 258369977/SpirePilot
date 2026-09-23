param(
    [string]$Dotnet = 'dotnet',
    [string]$NuGetConfig = '',
    [switch]$NoRestore
)
$ErrorActionPreference = 'Stop'
$project = Join-Path $PSScriptRoot 'SpirePilot.csproj'
$destination = Join-Path (Split-Path $PSScriptRoot -Parent) 'SpirePilotApp'
if (-not $NoRestore) {
    $restoreArgs = @('restore', $project)
    if ($NuGetConfig) { $restoreArgs += @('--configfile', $NuGetConfig) }
    & $Dotnet @restoreArgs
    if ($LASTEXITCODE -ne 0) { throw 'NuGet restore failed.' }
}
& $Dotnet publish $project --no-restore -c Release -o $destination
if ($LASTEXITCODE -ne 0) { throw 'Publish failed.' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'README.md') -Destination (Join-Path $destination 'README.md') -Force
Write-Output (Join-Path $destination 'SpirePilot.exe')
