# Puts the voice mod into a Hookshot build of OoT, or takes it back out.
# Hookshot reads the game's files loose from <game>\romfs, so the mod's files are copied over them.
# Every game file that gets replaced is saved first in <game>\voice_mod_backup, and "remove" puts them back.
param([ValidateSet("install", "remove")][string]$Action = "install",
      [string]$Game = "A:\Games",
      [string]$Stage = "A:\OotVoiceMod\mod_stage\OoT Voices\romfs")
$ErrorActionPreference = "Stop"
$romfs = Join-Path $Game "romfs"
$backup = Join-Path $Game "voice_mod_backup"
$added = Join-Path $backup "added_files.txt"
# Hookshot keeps its own copy of the game's resource size table and ignores the one in romfs.
$hookTable = Join-Path $Game "prompts\rsizetable.zs"
$hookTableBackup = Join-Path $Game "voice_mod_rsizetable_backup.zs"
$modTable = Join-Path $Stage "System\Resource\ResourceSizeTable.Product.111.Nin_Ounce_NVN2.rsizetable.zs"

if (Get-Process hookshot, HookshotBuilder -ErrorAction SilentlyContinue) {
    Write-Host "Hookshot or the Hookshot Builder is open. Close both, then run this again."; exit 1
}
if (-not (Test-Path (Join-Path $romfs "Voice"))) { Write-Host "No Hookshot game files found in $romfs"; exit 1 }

function Remove-Mod {
    if (-not (Test-Path $backup)) { Write-Host "The voice mod is not installed."; return }
    $restored = 0; $deleted = 0
    foreach ($file in Get-ChildItem $backup -Recurse -File | Where-Object { $_.FullName -ne $added }) {
        $rel = $file.FullName.Substring($backup.Length + 1)
        Copy-Item $file.FullName (Join-Path $romfs $rel) -Force; $restored++
    }
    if (Test-Path $added) {
        foreach ($rel in Get-Content $added) {
            $path = Join-Path $romfs $rel
            if (Test-Path $path) { Remove-Item $path -Force; $deleted++ }
        }
    }
    Remove-Item $backup -Recurse -Force
    if (Test-Path $hookTableBackup) { Copy-Item $hookTableBackup $hookTable -Force; Remove-Item $hookTableBackup -Force }
    Write-Host "Voice mod removed: $restored game files restored, $deleted voice files deleted."
}

if ($Action -eq "remove") { Remove-Mod; exit 0 }

if (-not (Test-Path $Stage)) { Write-Host "No built mod at $Stage. Run Build Voice Mod.bat first."; exit 1 }
# A reinstall starts from the untouched game, so files the new build no longer has do not linger.
if (Test-Path $backup) { Remove-Mod }
New-Item -ItemType Directory -Force $backup | Out-Null
$newFiles = New-Object System.Collections.Generic.List[string]
$saved = 0; $copied = 0
foreach ($file in Get-ChildItem $Stage -Recurse -File) {
    $rel = $file.FullName.Substring($Stage.Length + 1)
    $target = Join-Path $romfs $rel
    if (Test-Path $target) {
        $keep = Join-Path $backup $rel
        New-Item -ItemType Directory -Force (Split-Path $keep) | Out-Null
        Copy-Item $target $keep -Force; $saved++
    } else {
        $newFiles.Add($rel)
        New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
    }
    Copy-Item $file.FullName $target -Force; $copied++
}
Set-Content $added $newFiles -Encoding utf8
if (Test-Path $hookTable) {
    Copy-Item $hookTable $hookTableBackup -Force
    py -3.14 -I (Join-Path $PSScriptRoot "hookshot_rstb.py") $hookTableBackup $modTable $hookTable
    if ($LASTEXITCODE -ne 0) { Copy-Item $hookTableBackup $hookTable -Force; Write-Host "Could not update Hookshot's size table; removing the mod."; Remove-Mod; exit 1 }
}
Write-Host "Voice mod installed into Hookshot: $copied files ($saved game files backed up in $backup)."
