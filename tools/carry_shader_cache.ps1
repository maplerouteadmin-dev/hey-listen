# Copies OoT's built shader cache from the old emulator data folder (eden) into the new one (fritchii),
# so an emulator update that keeps the same cache version (the "fork-vNN" tag) does not rebuild everything.
# Only files with a matching cache version are copied. Anything replaced is kept as .bak.
$ErrorActionPreference = "Stop"
$title = "0400486024dec000"
$old = Join-Path $env:APPDATA "eden\cache\shader\$title"
$new = Join-Path $env:APPDATA "fritchii\cache\shader\$title"
if (Get-Process lichii -ErrorAction SilentlyContinue) { Write-Host "Fritchii is open. Close it first, then run this again."; exit 1 }
if (-not (Test-Path $old)) { Write-Host "No old shader cache found at $old"; exit 1 }
New-Item -ItemType Directory -Force $new | Out-Null

# The cache version the new build uses, read from the files it has already made (e.g. "fork-v54").
$versions = Get-ChildItem $new -File | ForEach-Object { if ($_.Name -match 'fork-v(\d+)') { $Matches[1] } } | Sort-Object -Unique
if (-not $versions) { Write-Host "Start OoT once in the new Fritchii so it creates its cache folder, close it, then run this again."; exit 1 }
$version = ($versions | Measure-Object -Maximum).Maximum
Write-Host "New build uses shader cache version v$version."

$copied = 0
foreach ($file in Get-ChildItem $old -File) {
    if ($file.Name -like "*.lock") { continue }
    if ($file.Name -match 'fork-v(\d+)' -and $Matches[1] -ne "$version") { continue }   # a different cache version would be thrown away anyway
    $target = Join-Path $new $file.Name
    $existing = Get-Item $target -ErrorAction SilentlyContinue
    if ($existing -and $existing.Length -ge $file.Length) { continue }   # the new folder already has as much or more
    if ($existing) { Copy-Item $target "$target.bak" -Force }
    Copy-Item $file.FullName $target -Force
    Write-Host ("  copied {0}  ({1:N0} MB)" -f $file.Name, ($file.Length / 1MB))
    $copied++
}
if ($copied) { Write-Host "Done: $copied cache files carried over. Start OoT; shaders it already built should load instead of compiling." }
else { Write-Host "Nothing to copy: the new folder already has the full cache." }
