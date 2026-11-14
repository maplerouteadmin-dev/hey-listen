# Unified installer for the OoT Voices mod: finds a Hookshot build, a Longshot build, and/or an
# emulator (Fritchii/eden) load folder, checks each one is the same game dump this mod was built
# from, and installs or removes the mod. Safe to run again after any rebuild/update.
#
# By default this downloads just the main story-cast voices (smallest), then asks whether to also
# fetch the bigger optional tiers, naming the extra download size before fetching anything.
#
#   install_voice_mod.ps1                       asks which voice tiers to install, into every target found
#   install_voice_mod.ps1 -Tier 3                skip the prompts, install the full "everyone voiced" tier
#   install_voice_mod.ps1 -Action remove         removes from every target it can find
#   install_voice_mod.ps1 -GameDir <path>        only that Hookshot or Longshot folder
#   install_voice_mod.ps1 -Emulator none         skip the emulator target
#   install_voice_mod.ps1 -Stage <folder>        use an already-built mod folder, skip tiers/downloading
#   install_voice_mod.ps1 -Force                 install even if the version check fails
param(
    [ValidateSet("install", "remove")][string]$Action = "install",
    [string]$Stage,
    [ValidateSet(0, 1, 2, 3)][int]$Tier = 0,
    [string]$ReleaseBaseUrl = "https://github.com/OWNER/REPO/releases/latest/download",
    [string]$LocalTierSource,
    [string]$CacheDir = (Join-Path $env:LOCALAPPDATA "OotVoiceMod\cache"),
    [string]$GameDir,
    [ValidateSet("auto", "fritchii", "eden", "none")][string]$Emulator = "auto",
    [string[]]$Targets = @("hookshot", "longshot", "emulator"),
    [switch]$Force
)
$ErrorActionPreference = "Stop"
$Here = $PSScriptRoot
$TierName = @{ 1 = "Main"; 2 = "Named"; 3 = "Full" }
$TierLabel = @{ 1 = "Main story cast"; 2 = "Main + named NPCs"; 3 = "Everyone (incl. background crowd)" }

# ---------- picking and fetching a voice tier ----------

function Select-Tier {
    if ($Tier -ge 1) { return $Tier }
    Write-Host "The main story-cast voices are included by default."
    $addNamed = Read-Host "Also get the extra named NPCs (shopkeepers, townsfolk, etc)? This downloads roughly 230 MB more [y/N]"
    if ($addNamed -notmatch "^(y|yes)$") { return 1 }
    $addCrowd = Read-Host "Also get generic background crowd voices (repeated NPC template lines)? This downloads roughly 135 MB more on top of that [y/N]"
    if ($addCrowd -notmatch "^(y|yes)$") { return 2 }
    return 3
}

function Get-TierPackage([int]$tier) {
    $name = $TierName[$tier]
    $cacheFolder = Join-Path $CacheDir $name
    if (Test-Path (Join-Path $cacheFolder "romfs")) {
        Write-Host "Using the already-downloaded '$name' voice pack."
        return $cacheFolder
    }
    if ($LocalTierSource) {
        $src = Get-ChildItem $LocalTierSource -Directory | Where-Object { $_.Name -like "*$name*" } | Select-Object -First 1
        if (-not $src) { throw "No local tier folder matching '$name' under $LocalTierSource" }
        New-Item -ItemType Directory -Force (Split-Path $cacheFolder) | Out-Null
        Copy-Item $src.FullName $cacheFolder -Recurse -Force
        return $cacheFolder
    }
    $url = "$ReleaseBaseUrl/OoT-Voices-$name.zip"
    try {
        $head = Invoke-WebRequest -Uri $url -Method Head -UseBasicParsing
    } catch {
        throw "Could not reach $url ($($_.Exception.Message)). Pass -Stage or -LocalTierSource to install from a local build instead."
    }
    $len = $head.Headers["Content-Length"]
    $mb = if ($len) { [math]::Round(([double]$len) / 1MB, 0) } else { "an unknown amount of" }
    Write-Host "Downloading the '$name' voice pack: $mb MB."
    $zip = Join-Path $env:TEMP "OoT-Voices-$name.zip"
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    New-Item -ItemType Directory -Force $cacheFolder | Out-Null
    Expand-Archive $zip -DestinationPath $cacheFolder -Force
    Remove-Item $zip -Force
    return $cacheFolder
}

function Get-ModInfo {
    $path = Join-Path $Stage "mod_info.json"
    if (Test-Path $path) { return Get-Content $path -Raw | ConvertFrom-Json }
    return $null
}

function Test-GameMatch($romfsRoot, $info) {
    # $null = could not check (no mod_info.json, or the target file is missing); true/false = checked.
    if (-not $info) { return $null }
    $target = Join-Path $romfsRoot $info.fingerprint_file
    if (-not (Test-Path $target)) { return $null }
    return (Get-FileHash -Algorithm SHA256 $target).Hash -ieq $info.fingerprint_sha256
}

function Confirm-Match($match, $label) {
    if ($match -eq $false -and -not $Force) {
        Write-Host "$label looks like a different game version/dump than this mod was built from. Skipping (pass -Force to install anyway)."
        return $false
    }
    if ($match -eq $false) {
        Write-Host "$label looks like a different game version/dump than this mod was built from. Continuing anyway (-Force)."
    } elseif ($null -eq $match) {
        Write-Host "$label : could not verify the game version matches (no reference file found); continuing."
    }
    return $true
}

# ---------- discovery ----------

function Find-HookshotDir {
    if ($GameDir) { return @($GameDir) }
    $candidates = @($Here, (Split-Path $Here -Parent), (Split-Path (Split-Path $Here -Parent) -Parent), "A:\Games")
    $candidates | Select-Object -Unique | Where-Object {
        $_ -and (Test-Path (Join-Path $_ "romfs\Voice")) -and
        ((Test-Path (Join-Path $_ "bin\hookshot.exe")) -or (Test-Path (Join-Path $_ "hookshot.exe")))
    } | Select-Object -First 1
}

function Find-LongshotDir {
    if ($GameDir) { return @($GameDir) }
    $candidates = @($Here, (Split-Path $Here -Parent), (Split-Path (Split-Path $Here -Parent) -Parent), "A:\Games\longshot")
    $candidates | Select-Object -Unique | Where-Object {
        $_ -and (Test-Path (Join-Path $_ "romfs\Voice")) -and
        ((Test-Path (Join-Path $_ "bin\longshot.exe")) -or (Test-Path (Join-Path $_ "longshot.exe")))
    } | Select-Object -First 1
}

function Find-EmulatorLoadDirs {
    $dirs = @()
    if ($Emulator -eq "auto" -or $Emulator -eq "fritchii") {
        $p = Join-Path $env:APPDATA "fritchii\load"
        if (Test-Path $p) { $dirs += , @{ name = "Fritchii"; load = $p } }
    }
    if ($Emulator -eq "auto" -or $Emulator -eq "eden") {
        $p = Join-Path $env:APPDATA "eden\load"
        if (Test-Path $p) { $dirs += , @{ name = "eden"; load = $p } }
    }
    return $dirs
}

# ---------- Hookshot (direct romfs replacement) ----------

function Remove-Hookshot($dir) {
    $romfs = Join-Path $dir "romfs"
    $backup = Join-Path $dir "voice_mod_backup"
    $added = Join-Path $backup "added_files.txt"
    $hookTable = Join-Path $dir "prompts\rsizetable.zs"
    $hookTableBackup = Join-Path $dir "voice_mod_rsizetable_backup.zs"
    if (-not (Test-Path $backup)) { Write-Host "Hookshot ($dir): voice mod is not installed."; return }
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
    Write-Host "Hookshot ($dir): voice mod removed, $restored game files restored, $deleted voice files deleted."
}

function Install-Hookshot($dir, $info) {
    if (Get-Process hookshot, HookshotBuilder -ErrorAction SilentlyContinue) {
        Write-Host "Hookshot ($dir): Hookshot or its Builder is open. Close both and run this again."; return
    }
    $romfs = Join-Path $dir "romfs"
    if (-not (Confirm-Match (Test-GameMatch $romfs $info) "Hookshot ($dir)")) { return }
    $stageRomfs = Join-Path $Stage "romfs"
    $backup = Join-Path $dir "voice_mod_backup"
    $added = Join-Path $backup "added_files.txt"
    $hookTable = Join-Path $dir "prompts\rsizetable.zs"
    $hookTableBackup = Join-Path $dir "voice_mod_rsizetable_backup.zs"
    $modTable = Join-Path $stageRomfs "System\Resource\ResourceSizeTable.Product.111.Nin_Ounce_NVN2.rsizetable.zs"
    if (Test-Path $backup) { Remove-Hookshot $dir }
    New-Item -ItemType Directory -Force $backup | Out-Null
    $newFiles = New-Object System.Collections.Generic.List[string]
    $saved = 0; $copied = 0
    foreach ($file in Get-ChildItem $stageRomfs -Recurse -File) {
        $rel = $file.FullName.Substring($stageRomfs.Length + 1)
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
        py -3.14 -I (Join-Path $Here "hookshot_rstb.py") $hookTableBackup $modTable $hookTable
        if ($LASTEXITCODE -ne 0) {
            Copy-Item $hookTableBackup $hookTable -Force
            Write-Host "Hookshot ($dir): could not update the size table; removing the mod."
            Remove-Hookshot $dir
            return
        }
    }
    Write-Host "Hookshot ($dir): voice mod installed, $copied files ($saved game files backed up in $backup)."
}

# ---------- Longshot (mods overlay + direct Stream files) ----------

function Remove-Longshot($dir) {
    $modsDest = Join-Path $dir "mods\OoT Voices\romfs"
    $addedList = Join-Path $dir "voice_mod_stream_added.txt"
    if (Test-Path $modsDest) { Remove-Item (Split-Path $modsDest) -Recurse -Force }
    if (Test-Path $addedList) {
        $removed = 0
        foreach ($rel in Get-Content $addedList) {
            $path = Join-Path $dir "romfs\$rel"
            if (Test-Path $path) { Remove-Item $path -Force; $removed++ }
        }
        Remove-Item $addedList -Force
        Write-Host "Longshot ($dir): voice mod removed, mods folder cleared, $removed stream files deleted."
    } else {
        Write-Host "Longshot ($dir): voice mod's mods folder cleared (nothing else to remove)."
    }
}

function Install-Longshot($dir, $info) {
    if (Get-Process longshot, LongshotLauncher -ErrorAction SilentlyContinue) {
        Write-Host "Longshot ($dir): Longshot or its launcher is open. Close it and run this again."; return
    }
    $romfs = Join-Path $dir "romfs"
    if (-not (Confirm-Match (Test-GameMatch $romfs $info) "Longshot ($dir)")) { return }
    $stageRomfs = Join-Path $Stage "romfs"
    $modsDest = Join-Path $dir "mods\OoT Voices\romfs"
    $streamStage = Join-Path $stageRomfs "Voice\Resource\Stream"
    $streamDest = Join-Path $romfs "Voice\Resource\Stream"
    $addedList = Join-Path $dir "voice_mod_stream_added.txt"
    if (Test-Path $modsDest) { Remove-Longshot $dir }
    New-Item -ItemType Directory -Force $modsDest | Out-Null
    robocopy $stageRomfs $modsDest /E /NFL /NDL /NJH /NJS | Out-Null
    New-Item -ItemType Directory -Force $streamDest | Out-Null
    $added = New-Object System.Collections.Generic.List[string]
    foreach ($file in Get-ChildItem $streamStage -File) {
        Copy-Item $file.FullName (Join-Path $streamDest $file.Name) -Force
        $added.Add("Voice/Resource/Stream/$($file.Name)")
    }
    Set-Content $addedList $added -Encoding utf8
    $modFiles = (Get-ChildItem $modsDest -Recurse -File | Measure-Object).Count
    Write-Host "Longshot ($dir): voice mod installed, $modFiles files via mods folder, $($added.Count) stream files added to romfs."
}

# ---------- Emulator (Fritchii / eden load folder) ----------

function Remove-Emulator($target) {
    $modDir = Join-Path $target.load "0400486024DEC000\OoT Voice Pack"
    if (Test-Path $modDir) { Remove-Item $modDir -Recurse -Force; Write-Host "$($target.name): voice mod removed." }
    else { Write-Host "$($target.name): voice mod is not installed." }
}

function Install-Emulator($target, $info) {
    $modDir = Join-Path $target.load "0400486024DEC000\OoT Voice Pack"
    if ($info) {
        Write-Host "$($target.name): built for game $($info.game_id) v$($info.game_version). Make sure your own dump matches, or lines may not line up."
    }
    if (Test-Path $modDir) { Remove-Item $modDir -Recurse -Force }
    New-Item -ItemType Directory -Force $modDir | Out-Null
    robocopy (Join-Path $Stage "romfs") (Join-Path $modDir "romfs") /E /R:1 /W:1 /MT:8 /NFL /NDL /NJH /NJS /NP | Out-Null
    Write-Host "$($target.name): voice mod installed as `"OoT Voice Pack`"."
}

# ---------- main ----------

if ($Action -eq "install") {
    if (-not $Stage) {
        $chosenTier = Select-Tier
        Write-Host "Installing tier: $($TierLabel[$chosenTier])"
        $Stage = Get-TierPackage $chosenTier
    }
    if (-not (Test-Path (Join-Path $Stage "romfs"))) { Write-Host "No built mod at $Stage."; exit 1 }
}
$info = Get-ModInfo
$hookshot = if ($Targets -contains "hookshot") { Find-HookshotDir } else { $null }
$longshot = if ($Targets -contains "longshot") { Find-LongshotDir } else { $null }
$emulators = if ($Targets -contains "emulator") { Find-EmulatorLoadDirs } else { @() }
if (-not $hookshot -and -not $longshot -and -not $emulators) {
    Write-Host "No Hookshot build, Longshot build, or emulator (Fritchii/eden) found. Pass -GameDir to point at one directly."
    exit 1
}
foreach ($dir in $hookshot) { if ($Action -eq "install") { Install-Hookshot $dir $info } else { Remove-Hookshot $dir } }
foreach ($dir in $longshot) { if ($Action -eq "install") { Install-Longshot $dir $info } else { Remove-Longshot $dir } }
foreach ($target in $emulators) { if ($Action -eq "install") { Install-Emulator $target $info } else { Remove-Emulator $target } }
