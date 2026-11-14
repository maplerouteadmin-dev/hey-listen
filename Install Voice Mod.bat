@echo off
title OoT Voices - installing the mod
tasklist /FI "IMAGENAME eq lichii.exe" | find /I "lichii.exe" >nul
if not errorlevel 1 (
    echo The game is open. Close Fritchii first, then run this again.
    pause
    exit /b
)
echo Copying the already-built voice mod into Fritchii/eden. About 3 GB, a minute or two.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install_voice_mod.ps1" -Stage "A:\OotVoiceMod\mod_stage\OoT Voices" -Targets emulator
echo.
echo Make sure it is ticked in the emulator's add-ons list for the game, then play.
echo Do not run "Start Voices.bat" at the same time, or lines will play twice.
pause
