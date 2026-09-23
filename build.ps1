param([string]$Dotnet = '')

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'test.ps1')

$env:DOTNET_CLI_HOME = Join-Path $PSScriptRoot 'work\dotnethome'
$env:APPDATA = Join-Path $PSScriptRoot 'work\build-appdata'
$env:NUGET_PACKAGES = Join-Path $PSScriptRoot 'work\packages'
$env:TEMP = Join-Path $PSScriptRoot 'work\build-temp'
$env:TMP = $env:TEMP
foreach ($directory in @($env:DOTNET_CLI_HOME, $env:APPDATA, $env:NUGET_PACKAGES, $env:TEMP)) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
}

if (-not $Dotnet) {
    $bundled = Join-Path $PSScriptRoot 'work\dotnet\dotnet.exe'
    $Dotnet = if (Test-Path -LiteralPath $bundled) { $bundled } else { 'dotnet' }
}

$arguments = @{ Dotnet = $Dotnet }
$localNuGet = Join-Path $PSScriptRoot 'work\NuGet.Local.Config'
if (Test-Path -LiteralPath $localNuGet) {
    $arguments.NuGetConfig = $localNuGet
}
& (Join-Path $PSScriptRoot 'outputs\SpirePilot\build.ps1') @arguments
