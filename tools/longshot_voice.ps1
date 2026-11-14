# Puts the voice mod into a Longshot build of OoT, or takes it back out.
# Longshot's own "mods" folder correctly overlays everything EXCEPT the actual audio stream files:
# Voice/Resource/Stream/*.bwav never gets read through the mods overlay (confirmed 2026-11-14: the bank
# container loads fine from mods, but no stream file is ever opened, so nothing plays). Those files are new
# additions only (they don't grow any existing archive), so copying them straight into romfs is safe: it
# can't touch the resource size table and can't cause the size-table crash a full romfs replacement does.
param([ValidateSet("install", "remove")][string]$Action = "install",
      [string]$Game = "A:\Games\longshot",
      [string]$Stage = "A:\OotVoiceMod\mod_stage\OoT Voices\romfs")
$ErrorActionPreference = "Stop"
$modsDest = Join-Path $Game "mods\OoT Voices\romfs"
$streamStage = Join-Path $Stage "Voice\Resource\Stream"
$streamDest = Join-Path $Game "romfs\Voice\Resource\Stream"
$addedList = Join-Path $Game "voice_mod_stream_added.txt"

if (Get-Process longshot, LongshotLauncher -ErrorAction SilentlyContinue) {
    Write-Host "Longshot or its launcher is open. Close it, then run this again."; exit 1
}
if (-not (Test-Path (Join-Path $Game "romfs\Voice"))) { Write-Host "No Longshot game files found under $Game"; exit 1 }

function Remove-Mod {
    if (Test-Path $modsDest) { Remove-Item (Split-Path $modsDest) -Recurse -Force }
    if (Test-Path $addedList) {
        $removed = 0
        foreach ($rel in Get-Content $addedList) {
            $path = Join-Path $Game "romfs\$rel"
            if (Test-Path $path) { Remove-Item $path -Force; $removed++ }
        }
        Remove-Item $addedList -Force
        Write-Host "Voice mod removed: mods folder cleared, $removed stream files deleted from romfs."
    } else {
        Write-Host "Voice mod's mods folder cleared (no stream-file record to clean up)."
    }
}

if ($Action -eq "remove") { Remove-Mod; exit 0 }

if (-not (Test-Path $Stage)) { Write-Host "No built mod at $Stage. Run Build Voice Mod.bat first."; exit 1 }
if (Test-Path $modsDest) { Remove-Mod }

# Step 1: the mods folder, for everything except the audio streams.
New-Item -ItemType Directory -Force $modsDest | Out-Null
robocopy $Stage $modsDest /E /NFL /NDL /NJH /NJS | Out-Null

# Step 2: the audio streams, copied straight into romfs (new files only, nothing replaced).
New-Item -ItemType Directory -Force $streamDest | Out-Null
$added = New-Object System.Collections.Generic.List[string]
foreach ($file in Get-ChildItem $streamStage -File) {
    $target = Join-Path $streamDest $file.Name
    $added.Add("Voice/Resource/Stream/$($file.Name)")
    Copy-Item $file.FullName $target -Force
}
Set-Content $addedList $added -Encoding utf8

$modFiles = (Get-ChildItem $modsDest -Recurse -File | Measure-Object).Count
Write-Host "Voice mod installed into Longshot: $modFiles files via mods folder, $($added.Count) stream files added directly to romfs."
