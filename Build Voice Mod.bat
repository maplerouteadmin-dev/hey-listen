@echo off
title OoT Voices - building the mod
tasklist /FI "IMAGENAME eq lichii.exe" | find /I "lichii.exe" >nul
if not errorlevel 1 (
    echo The game is open. Close Fritchii's game window first, then run this again.
    pause
    exit /b
)
set STAGE=A:\OotVoiceMod\mod_stage\OoT Voices
rem Fritchii 5.8.4 and later keep their data in %APPDATA%\fritchii; older builds used %APPDATA%\eden.
set MOD=%APPDATA%\fritchii\load\0400486024DEC000\OoT Voice Pack
if not exist "%APPDATA%\fritchii\load" set MOD=%APPDATA%\eden\load\0400486024DEC000\OoT Voice Pack
echo Building the voice mod from every line generated so far. This takes a few minutes.
if exist "A:\OotVoiceMod\mod_stage" rmdir /s /q "A:\OotVoiceMod\mod_stage"
mkdir "%STAGE%\romfs"
py -3.14 -I "%~dp0tools\build_voice_mod.py" "A:\Games\Ocarana\The Legend of Zelda Ocarina of Time [0400486024DEC000][v131072].nup" "A:\OotVoiceMod\pack\manifest.json" "%STAGE%"
if errorlevel 1 (
    echo.
    echo The build failed, so the installed mod was left as it was.
    pause
    exit /b
)
if exist "%MOD%" rmdir /s /q "%MOD%"
robocopy "%STAGE%" "%MOD%" /E /R:1 /W:1 /MT:8 /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo.
    echo Copying into Fritchii failed. Restart the PC, then run "Install Voice Mod.bat".
    pause
    exit /b
)
echo.
echo Installed as "OoT Voice Pack". Start the game.
pause
