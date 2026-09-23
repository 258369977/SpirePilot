param([string]$Version = 'v0.1.0', [string]$OutputDirectory = '')

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem

$root = Split-Path $PSScriptRoot -Parent
$release = if ($OutputDirectory) { [System.IO.Path]::GetFullPath((Join-Path $root $OutputDirectory)) } else { Join-Path $root ("work\release\" + $Version) }
if (Test-Path -LiteralPath $release) { throw "Release directory already exists: $release" }

$appSource = Join-Path $root 'outputs\SpirePilotApp'
$controllerSource = Join-Path $root 'outputs\hybrid'
$modSource = Join-Path $controllerSource 'mod\STS2_MCP.dll'
foreach ($required in @((Join-Path $appSource 'SpirePilot.exe'), (Join-Path $controllerSource 'config.example.json'), $modSource)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing release input: $required" }
}

$appStage = Join-Path $release 'app-stage\SpirePilot'
$appTarget = Join-Path $appStage 'SpirePilotApp'
$controllerTarget = Join-Path $appStage 'hybrid'
$modStage = Join-Path $release 'mod-stage\STS2MCP-SpirePilot'
foreach ($directory in @($appTarget, $controllerTarget, $modStage)) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
}

# The publish directory also contains local smoke-test output and app settings.
$excludedAppFiles = @('desktop-settings.json', 'ui-smoke.json', 'bridge-smoke.log', 'startup.log', 'startup-error.log', 'crash.log', 'preview-error.log')
Get-ChildItem -LiteralPath $appSource -Force | ForEach-Object {
    if ($_.Name -in $excludedAppFiles -or $_.Name -like 'ui-*.png' -or $_.Name -like '*.pdb') { return }
    Copy-Item -LiteralPath $_.FullName -Destination $appTarget -Recurse -Force
}

$controllerFiles = @('config.example.json', 'desktop_bridge.py', 'experience.py', 'game_actions.py', 'hybrid_player.py', 'role_memory.py', 'run_journal.py', 'start.ps1', 'stop.ps1', 'README.md')
foreach ($name in $controllerFiles) {
    Copy-Item -LiteralPath (Join-Path $controllerSource $name) -Destination $controllerTarget
}
Copy-Item -LiteralPath (Join-Path $root 'LICENSE') -Destination $appStage
Copy-Item -LiteralPath (Join-Path $root 'THIRD_PARTY_NOTICES.md') -Destination $appStage

Copy-Item -LiteralPath $modSource -Destination $modStage
Copy-Item -LiteralPath (Join-Path $root 'vendor\STS2MCP\mod_manifest.json') -Destination (Join-Path $modStage 'STS2_MCP.json')
Copy-Item -LiteralPath (Join-Path $root 'vendor\STS2MCP\LICENSE') -Destination $modStage

@'
Spire Pilot Windows x64 preview

Keep SpirePilotApp and hybrid in the same folder. Install Python 3.10+ and
the matching STS2MCP-SpirePilot Mod, start Slay the Spire 2, then run
SpirePilotApp\SpirePilot.exe. Configure both providers and API keys in the app.
The application contains .NET and Windows App SDK runtime files.
Run data and API keys are not included. This preview has not completed a full
end-to-end paid-model game validation.
'@ | Set-Content -LiteralPath (Join-Path $appStage 'README.txt') -Encoding UTF8

@'
Spire Pilot STS2MCP Mod preview

With the game closed, copy STS2_MCP.dll and STS2_MCP.json into the game's
mods directory, replacing the existing STS2MCP version. Restart the game.
The Mod should expose player.deck through its local state endpoint.
This binary was compiled against a local game installation; compatibility
with other game versions has not been verified. MIT license applies to the Mod.
'@ | Set-Content -LiteralPath (Join-Path $modStage 'README.txt') -Encoding UTF8

$appZip = Join-Path $release "SpirePilot-$Version-win-x64.zip"
$modZip = Join-Path $release "STS2MCP-SpirePilot-$Version.zip"
[System.IO.Compression.ZipFile]::CreateFromDirectory($appStage, $appZip, [System.IO.Compression.CompressionLevel]::Optimal, $false)
[System.IO.Compression.ZipFile]::CreateFromDirectory($modStage, $modZip, [System.IO.Compression.CompressionLevel]::Optimal, $false)

$checksums = foreach ($file in @($appZip, $modZip)) {
    $hash = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $(Split-Path $file -Leaf)"
}
$checksums | Set-Content -LiteralPath (Join-Path $release 'SHA256SUMS.txt') -Encoding ascii
Get-Item -LiteralPath $appZip, $modZip, (Join-Path $release 'SHA256SUMS.txt') | Select-Object FullName, Length
